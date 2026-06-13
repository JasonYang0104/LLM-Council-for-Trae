from __future__ import annotations

import asyncio
import json
import re
import tempfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .acp_runtime import AcpTraeCliRuntime
from .models import doctor as runtime_doctor
from .models import get_models, require_models_available
from .contribution_map import extract_contribution_map, strip_contribution_map_fence
from .model_selection import DEFAULT_CHAIRMAN, DEFAULT_MEMBERS
from .provider import ModelCallResult, ModelRuntime, TraeCliProvider, tool_policy_for_mode
from .store import ArtifactStore
from .utils import utc_now, write_json


DEFAULT_READER_LANGUAGE_INSTRUCTION = "默认面向中文读者，使用简体中文回答。若用户原始问题明确指定另一种输出语言，则遵循用户指定语言。"


@dataclass
class CouncilConfig:
    members: list[str]
    chairman: str
    provider_mode: str = "direct"
    runtime_command: str = "traecli"
    runtime_cwd: str | None = None
    query_timeout: int = 180
    export_html: bool = True
    member_agents: list[str | None] | None = None
    chairman_agent: str | None = None
    use_yolo: bool = False
    min_valid_members: int = 3
    target_valid_members: int = 3
    chairman_fallback: list[str] | None = None
    member_soft_checkpoint: int = 300
    member_quorum_checkpoint: int = 480
    member_hard_timeout: int = 660
    stage2_timeout: float | None = None
    chairman_timeout: int = 720
    member_mode: str = "normal"
    member_tool_mode: str = "search_enabled"
    member_runtime_cwd_mode: str = "isolated_temp"
    runtime_backend: str = "direct"
    acp_startup_timeout: int = 30
    stage1_max_retries: int = 1
    backfill_members: list[str] = field(default_factory=list)
    stage1_auto_backfill: bool = True
    stage2_auto_backfill: bool = True
    allow_low_quorum: bool = True
    low_quorum_floor: int = 2
    model_selection_provenance: dict[str, Any] | None = None
    chairman_contribution_enabled: bool = True
    chairman_contribution_required: bool = False
    chairman_contribution_repair_attempts: int = 2
    debate_enabled: bool = False

    def agent_for_member(self, index: int) -> str | None:
        if not self.member_agents or index >= len(self.member_agents):
            return None
        return self.member_agents[index]


def ensure_stage1_stream_sidecar(store: ArtifactStore, label: str, call: ModelCallResult) -> None:
    if call.runtime_backend != "direct":
        return
    stream_path = store.root / "stage1" / f"{label}.traecli.stream.jsonl"
    if stream_path.exists() and stream_path.stat().st_size > 0:
        return
    stream_event = {
        "event": "synthetic_stage1_result",
        "stage": "stage1",
        "label": label,
        "expected_model": call.expected_model,
        "actual_model": call.actual_model,
        "status": call.status,
        "error": call.error,
        "captured_at": utc_now(),
    }
    store.write_text(f"stage1/{label}.traecli.stream.jsonl", json.dumps(stream_event, ensure_ascii=False) + "\n")


def runtime_stdout_path(runtime_backend: str, label: str) -> str:
    if runtime_backend == "acp":
        return f"{label}.acp.transcript.jsonl"
    return f"{label}.traecli.stream.jsonl"


def runtime_stderr_path(runtime_backend: str, label: str) -> str:
    if runtime_backend == "acp":
        return f"{label}.acp.stderr.log"
    return f"{label}.traecli.stderr.log"


def runtime_acp_transcript_path(runtime_backend: str, stage: str, label: str) -> str | None:
    if runtime_backend != "acp":
        return None
    return f"{stage}/{label}.acp.transcript.jsonl"


async def stage1_collect_responses(
    user_query: str,
    config: CouncilConfig,
    provider: ModelRuntime,
    store: ArtifactStore,
) -> list[dict[str, Any]]:
    prompt = build_stage1_prompt(user_query)
    store.write_text("stage1/member.prompt.md", prompt + "\n")
    output_dir = store.path("stage1")
    task_map: dict[asyncio.Task, tuple[int, str, str]] = {}
    for index, model in enumerate(config.members):
        label = chr(65 + index)
        task = asyncio.create_task(
            provider.query_model(
                model=model,
                prompt=prompt,
                run_id=store.root.name,
                stage="stage1",
                label=label,
                output_dir=output_dir,
                agent=config.agent_for_member(index),
            )
        )
        task_map[task] = (index, model, label)

    call_results: list[ModelCallResult | None] = [None] * len(config.members)
    loop = asyncio.get_running_loop()
    stage_start = loop.time()
    soft_warned = False
    pending: set[asyncio.Task] = set(task_map.keys())

    try:
        while pending:
            elapsed = loop.time() - stage_start

            if elapsed > config.member_hard_timeout:
                store.event("stage1_hard_timeout", {"elapsed_seconds": int(elapsed)})
                await cancel_and_drain(pending)
                pending = set()
                break

            if not soft_warned and elapsed > config.member_soft_checkpoint:
                store.event("stage1_soft_checkpoint", {"elapsed_seconds": int(elapsed)})
                soft_warned = True

            if elapsed > config.member_quorum_checkpoint:
                ok_count = sum(1 for r in call_results if r is not None and r.status == "ok")
                if ok_count >= config.min_valid_members:
                    store.event("stage1_quorum_checkpoint", {"ok_count": ok_count, "elapsed_seconds": int(elapsed)})
                    await cancel_and_drain(pending)
                    pending = set()
                    break

            done, pending = await asyncio.wait(pending, timeout=10, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                idx, model, label = task_map[task]
                try:
                    call_results[idx] = task.result()
                except (asyncio.CancelledError, Exception) as exc:
                    call_results[idx] = synthetic_failed_call(
                        model,
                        f"cancelled_by_stage_timeout: {exc}",
                        config,
                        stdout_path=runtime_stdout_path(config.runtime_backend, label),
                        stderr_path=runtime_stderr_path(config.runtime_backend, label),
                        acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage1", label),
                    )
    finally:
        await cancel_and_drain(pending)

    for task in task_map:
        idx, model, label = task_map[task]
        if call_results[idx] is None:
            call_results[idx] = synthetic_failed_call(
                model,
                "cancelled_by_stage_timeout",
                config,
                stdout_path=runtime_stdout_path(config.runtime_backend, label),
                stderr_path=runtime_stderr_path(config.runtime_backend, label),
                acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage1", label),
            )

    stage1_results: list[dict[str, Any]] = []
    for index, (model, call) in enumerate(zip(config.members, call_results)):
        label = chr(65 + index)
        if call is None:
            call = synthetic_failed_call(
                model,
                "cancelled_by_stage_timeout",
                config,
                stdout_path=runtime_stdout_path(config.runtime_backend, label),
                stderr_path=runtime_stderr_path(config.runtime_backend, label),
                acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage1", label),
            )
        if not (store.root / "stage1" / f"{label}.meta.json").exists():
            store.write_json(f"stage1/{label}.meta.json", call.to_json() | {"captured_at": utc_now()})
        ensure_stage1_stream_sidecar(store, label, call)
        store.write_text(f"stage1/{label}.response.md", call.response + "\n")
        stage1_results.append(
            {
                "label": f"Response {label}",
                "file_label": label,
                "model": model,
                "expected_model": call.expected_model,
                "actual_model": call.actual_model,
                "agent": call.agent,
                "subagent_invocation": call.subagent_invocation,
                "response": call.response,
                "status": call.status,
                "meta_path": f"stage1/{label}.meta.json",
                "response_path": f"stage1/{label}.response.md",
                "error": call.error,
                "attempt_role": "primary",
                "attempt_index": 1,
                "tool_calls_count": call.tool_calls_count,
                "turns_count": call.turns_count,
                "tool_budget_status": call.tool_budget_status,
                "raw_partial_recoverable": call.raw_partial_recoverable,
                "retried": call.retried,
                "retry_error": call.retry_error,
            } | tool_policy_record(call)
        )
    return stage1_results


async def backfill_stage1_responses(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    config: CouncilConfig,
    provider: ModelRuntime,
    store: ArtifactStore,
    runtime_models: list[dict[str, Any]],
    target_valid_members: int | None = None,
) -> tuple[list[str], list[str]]:
    from .model_selection import build_backfill_candidates

    if not config.stage1_auto_backfill:
        return [], []

    prompt = build_stage1_prompt(user_query)
    output_dir = store.path("stage1")
    attempted_models = [str(result.get("model")) for result in stage1_results if result.get("model")]
    failed_models = [
        str(result.get("model"))
        for result in stage1_results
        if result.get("model") and not stage1_record_is_valid(result)
    ]
    candidates = build_backfill_candidates(
        runtime_models,
        primary_members=config.members,
        attempted_models=attempted_models,
        failed_models=failed_models,
        chairman=config.chairman,
        explicit_members=config.backfill_members or None,
    )
    attempted_backfill: list[str] = []
    target = target_valid_members or config.min_valid_members
    for model in candidates:
        if effective_stage1_count(stage1_results) >= target:
            break
        label = chr(65 + len(stage1_results))
        attempted_backfill.append(model)
        store.event("stage1_backfill_attempt", {"model": model, "label": label})
        call = await provider.query_model(
            model=model,
            prompt=prompt,
            run_id=store.root.name,
            stage="stage1",
            label=label,
            output_dir=output_dir,
        )
        if not (store.root / "stage1" / f"{label}.meta.json").exists():
            store.write_json(f"stage1/{label}.meta.json", call.to_json() | {"captured_at": utc_now()})
        ensure_stage1_stream_sidecar(store, label, call)
        store.write_text(f"stage1/{label}.response.md", call.response + "\n")
        stage1_results.append(
            {
                "label": f"Response {label}",
                "file_label": label,
                "model": model,
                "expected_model": call.expected_model,
                "actual_model": call.actual_model,
                "agent": call.agent,
                "subagent_invocation": call.subagent_invocation,
                "response": call.response,
                "status": call.status,
                "meta_path": f"stage1/{label}.meta.json",
                "response_path": f"stage1/{label}.response.md",
                "error": call.error,
                "attempt_role": "backfill",
                "attempt_index": 1,
                "tool_calls_count": call.tool_calls_count,
                "turns_count": call.turns_count,
                "tool_budget_status": call.tool_budget_status,
                "raw_partial_recoverable": call.raw_partial_recoverable,
                "retried": call.retried,
                "retry_error": call.retry_error,
            } | tool_policy_record(call)
        )
    return candidates, attempted_backfill


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    config: CouncilConfig,
    provider: ModelRuntime,
    store: ArtifactStore,
    reviewers: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    review_subjects = [result for result in stage1_results if stage1_record_is_valid(result)]
    reviewer_records = [result for result in (reviewers or review_subjects) if stage2_reviewer_record_is_valid(result)]
    label_to_model = {result["label"]: result["model"] for result in review_subjects}
    store.write_json("stage2/label_to_model.json", label_to_model)

    ranking_prompt = build_stage2_prompt(user_query, review_subjects)
    store.write_text("stage2/review.prompt.md", ranking_prompt + "\n")

    output_dir = store.path("stage2")
    task_map: dict[asyncio.Task, tuple[int, dict[str, Any], str, str]] = {}
    for index, reviewer in enumerate(reviewer_records):
        model = str(reviewer["model"])
        label = stage_file_label(reviewer, index)
        member_index = config.members.index(model) if model in config.members else -1
        agent = config.agent_for_member(member_index) if member_index >= 0 else None
        task = asyncio.create_task(
            provider.query_model(
                model=model,
                prompt=ranking_prompt,
                run_id=store.root.name,
                stage="stage2",
                label=label,
                output_dir=output_dir,
                agent=agent,
            )
        )
        task_map[task] = (index, reviewer, model, label)

    call_results: list[ModelCallResult | None] = [None] * len(reviewer_records)
    stage2_timeout = config.stage2_timeout if config.stage2_timeout is not None else max(config.query_timeout + 30, 240)
    loop = asyncio.get_running_loop()
    stage_start = loop.time()
    pending: set[asyncio.Task] = set(task_map.keys())

    try:
        while pending:
            elapsed = loop.time() - stage_start
            remaining = stage2_timeout - elapsed
            if remaining <= 0:
                store.event("stage2_timeout", {"elapsed_seconds": round(elapsed, 2)})
                break

            done, pending = await asyncio.wait(
                pending,
                timeout=min(10, max(0.01, remaining)),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                idx, _reviewer, model, label = task_map[task]
                try:
                    call_results[idx] = task.result()
                except (asyncio.CancelledError, Exception) as exc:
                    call_results[idx] = synthetic_failed_call(
                        model,
                        f"cancelled_by_stage_timeout: {exc}",
                        config,
                        stdout_path=runtime_stdout_path(config.runtime_backend, label),
                        stderr_path=runtime_stderr_path(config.runtime_backend, label),
                        acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage2", label),
                    )
    finally:
        await cancel_and_drain(pending)

    for task, (idx, _reviewer, model, label) in task_map.items():
        if call_results[idx] is None:
            call_results[idx] = synthetic_failed_call(
                model,
                "cancelled_by_stage_timeout",
                config,
                stdout_path=runtime_stdout_path(config.runtime_backend, label),
                stderr_path=runtime_stderr_path(config.runtime_backend, label),
                acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage2", label),
            )

    stage2_results: list[dict[str, Any]] = []
    valid_labels = set(label_to_model)
    for reviewer, call in zip(reviewer_records, call_results):
        model = str(reviewer["model"])
        label = stage_file_label(reviewer, 0)
        if call is None:
            call = synthetic_failed_call(
                model,
                "cancelled_by_stage_timeout",
                config,
                stdout_path=runtime_stdout_path(config.runtime_backend, label),
                stderr_path=runtime_stderr_path(config.runtime_backend, label),
                acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage2", label),
            )
        parsed = parse_ranking_from_text(call.response)
        parse_status = "ok" if ranking_is_complete(parsed, valid_labels) else "incomplete"
        review = {
            "reviewer_label": label,
            "model": model,
            "expected_model": call.expected_model,
            "actual_model": call.actual_model,
            "agent": call.agent,
            "subagent_invocation": call.subagent_invocation,
            "ranking": call.response,
            "parsed_ranking": parsed,
            "parse_status": parse_status,
            "status": call.status if call.status != "ok" else parse_status,
            "error": call.error,
            "review_path": f"stage2/{label}.review.md",
            "json_path": f"stage2/{label}.review.json",
            "reviewer_eligible": True,
            "reviewer_source": reviewer_source(reviewer),
            "review_subject_count": len(review_subjects),
            "attempt_role": reviewer_attempt_role(reviewer),
            "tool_calls_count": call.tool_calls_count,
            "turns_count": call.turns_count,
            "tool_budget_status": call.tool_budget_status,
            "raw_partial_recoverable": call.raw_partial_recoverable,
            "retried": call.retried,
            "retry_error": call.retry_error,
        } | tool_policy_record(call)
        store.write_text(f"stage2/{label}.review.md", call.response + "\n")
        store.write_json(f"stage2/{label}.review.json", review)
        store.write_json(f"stage2/{label}.meta.json", call.to_json() | {"captured_at": utc_now()})
        if call.runtime_backend == "direct":
            stream_path = output_dir / f"{label}.traecli.stream.jsonl"
            if not stream_path.exists() or stream_path.stat().st_size == 0:
                stream_text = call.response or call.error or call.status
                store.write_text(f"stage2/{label}.traecli.stream.jsonl", stream_text + "\n")
        stage2_results.append(review)

    aggregate_rankings = calculate_aggregate_rankings(valid_stage2_rankings(stage2_results), label_to_model)
    store.write_json("stage2/aggregate.json", aggregate_rankings)
    return stage2_results, label_to_model


def strip_final_ranking_section(text: str) -> str:
    if "FINAL RANKING:" not in text:
        return text.strip()
    return text.split("FINAL RANKING:", 1)[0].strip()


def redact_model_names(text: str, models: list[str]) -> str:
    redacted = text
    for model in sorted({model for model in models if model}, key=len, reverse=True):
        redacted = redacted.replace(model, "[模型名已隐藏]")
    return redacted


def build_stage2_5_prompt(
    user_query: str,
    target: dict[str, Any],
    stage2_results: list[dict[str, Any]],
    stage1_results: list[dict[str, Any]],
) -> str:
    models = [str(result.get("model")) for result in stage1_results if result.get("model")]
    target_label = str(target.get("label") or f"Response {target.get('file_label', '?')}")
    target_response = redact_model_names(str(target.get("response") or ""), models)
    review_blocks: list[str] = []
    for index, review in enumerate([item for item in stage2_results if item.get("status") == "ok"], start=1):
        prose = strip_final_ranking_section(str(review.get("ranking") or ""))
        prose = redact_model_names(prose, models)
        if prose:
            review_blocks.append(f"评审 {index}：\n{prose}")
    reviews_text = "\n\n".join(review_blocks) if review_blocks else "没有可用的匿名评审 prose。"
    safe_query = redact_model_names(user_query, models)
    return f"""你正在参加 LLM Council 的 Stage 2.5 质询轮。

{DEFAULT_READER_LANGUAGE_INSTRUCTION}

用户原始问题：
{safe_query}

你的匿名回答标签：{target_label}

你的 Stage 1 原回答：
{target_response}

以下是匿名评审对所有候选回答的批评材料。评审者身份和最终排序已被移除；你只需要回应其中涉及 {target_label} 的批评。

{reviews_text}

请输出一份有界答辩，必须包含三部分：
1. 承认成立的批评：哪些批评成立，你会如何修正。
2. 反驳不成立的批评：哪些批评不成立，理由是什么。
3. 修正后立场：给出你当前的最新结论；如维持原立场，也要说明理由。

不要猜测评审者或其他回答背后的模型身份。不要输出 FINAL RANKING。"""


async def stage2_5_collect_rebuttals(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    config: CouncilConfig,
    provider: ModelRuntime,
    store: ArtifactStore,
) -> list[dict[str, Any]]:
    if not config.debate_enabled:
        return []

    participants = [result for result in stage1_results if stage1_record_is_valid(result)]
    output_dir = store.path("stage2_5")
    task_map: dict[asyncio.Task, tuple[int, dict[str, Any], str, str, str]] = {}
    for index, target in enumerate(participants):
        model = str(target["model"])
        label = stage_file_label(target, index)
        prompt = build_stage2_5_prompt(user_query, target, stage2_results, participants)
        prompt_path = f"stage2_5/{label}.rebuttal.prompt.md"
        store.write_text(prompt_path, prompt + "\n")
        task = asyncio.create_task(
            provider.query_model(
                model=model,
                prompt=prompt,
                run_id=store.root.name,
                stage="stage2_5",
                label=label,
                output_dir=output_dir,
                agent=config.agent_for_member(config.members.index(model)) if model in config.members else None,
            )
        )
        task_map[task] = (index, target, model, label, prompt_path)

    call_results: list[ModelCallResult | None] = [None] * len(participants)
    stage_timeout = max(config.query_timeout + 30, 240)
    loop = asyncio.get_running_loop()
    stage_start = loop.time()
    pending: set[asyncio.Task] = set(task_map.keys())

    try:
        while pending:
            elapsed = loop.time() - stage_start
            remaining = stage_timeout - elapsed
            if remaining <= 0:
                store.event("stage2_5_timeout", {"elapsed_seconds": round(elapsed, 2)})
                break
            done, pending = await asyncio.wait(
                pending,
                timeout=min(10, max(0.01, remaining)),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                idx, _target, model, label, _prompt_path = task_map[task]
                try:
                    call_results[idx] = task.result()
                except (asyncio.CancelledError, Exception) as exc:
                    call_results[idx] = synthetic_failed_call(
                        model,
                        f"cancelled_by_stage2_5_timeout: {exc}",
                        config,
                        stdout_path=runtime_stdout_path(config.runtime_backend, label),
                        stderr_path=runtime_stderr_path(config.runtime_backend, label),
                        acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage2_5", label),
                    )
    finally:
        await cancel_and_drain(pending)

    for task, (idx, _target, model, label, _prompt_path) in task_map.items():
        if call_results[idx] is None:
            call_results[idx] = synthetic_failed_call(
                model,
                "cancelled_by_stage2_5_timeout",
                config,
                stdout_path=runtime_stdout_path(config.runtime_backend, label),
                stderr_path=runtime_stderr_path(config.runtime_backend, label),
                acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage2_5", label),
            )

    rebuttals: list[dict[str, Any]] = []
    for target, call in zip(participants, call_results):
        label = stage_file_label(target, 0)
        if call is None:
            call = synthetic_failed_call(
                str(target["model"]),
                "cancelled_by_stage2_5_timeout",
                config,
                stdout_path=runtime_stdout_path(config.runtime_backend, label),
                stderr_path=runtime_stderr_path(config.runtime_backend, label),
                acp_transcript_path=runtime_acp_transcript_path(config.runtime_backend, "stage2_5", label),
            )
        status = call.status
        error = call.error
        if status == "ok" and not call.response.strip():
            status = "failed"
            error = "empty_rebuttal"
        store.write_text(f"stage2_5/{label}.rebuttal.md", call.response + "\n")
        store.write_json(f"stage2_5/{label}.meta.json", call.to_json() | {"captured_at": utc_now()})
        if call.runtime_backend == "direct":
            stream_path = output_dir / f"{label}.traecli.stream.jsonl"
            if not stream_path.exists() or stream_path.stat().st_size == 0:
                stream_text = call.response or error or status
                store.write_text(f"stage2_5/{label}.traecli.stream.jsonl", stream_text + "\n")
        rebuttals.append(
            {
                "label": target.get("label"),
                "file_label": label,
                "model": target.get("model"),
                "expected_model": call.expected_model,
                "actual_model": call.actual_model,
                "agent": call.agent,
                "subagent_invocation": call.subagent_invocation,
                "status": status,
                "error": error,
                "prompt_path": f"stage2_5/{label}.rebuttal.prompt.md",
                "response_path": f"stage2_5/{label}.rebuttal.md",
                "meta_path": f"stage2_5/{label}.meta.json",
                "response": call.response,
                "tool_calls_count": call.tool_calls_count,
                "turns_count": call.turns_count,
                "tool_budget_status": call.tool_budget_status,
                "raw_partial_recoverable": call.raw_partial_recoverable,
                "retried": call.retried,
                "retry_error": call.retry_error,
            } | tool_policy_record(call)
        )
    return rebuttals


async def backfill_stage2_reviewers(
    user_query: str,
    review_subjects: list[dict[str, Any]],
    existing_stage1_results: list[dict[str, Any]],
    failed_stage2_results: list[dict[str, Any]],
    config: CouncilConfig,
    provider: ModelRuntime,
    store: ArtifactStore,
    runtime_models: list[dict[str, Any]],
    needed_reviewers: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    from .model_selection import build_backfill_candidates

    if needed_reviewers <= 0:
        return [], [], []

    attempted_models = [
        str(result.get("model"))
        for result in existing_stage1_results + failed_stage2_results
        if result.get("model")
    ]
    failed_models = [
        str(result.get("model"))
        for result in failed_stage2_results
        if result.get("model") and result.get("status") != "ok"
    ]
    candidates = build_backfill_candidates(
        runtime_models,
        primary_members=config.members,
        attempted_models=attempted_models,
        failed_models=failed_models,
        chairman=config.chairman,
        explicit_members=config.backfill_members or None,
    )

    attempted_backfill: list[str] = []
    reviewer_records: list[dict[str, Any]] = []
    existing_reviewer_count = len(failed_stage2_results)
    for model in candidates:
        if len(reviewer_records) >= needed_reviewers:
            break
        label = f"R{existing_reviewer_count + len(reviewer_records) + 1}"
        attempted_backfill.append(model)
        reviewer_records.append(
            {
                "model": model,
                "file_label": label,
                "reviewer_label": label,
                "reviewer_source": "stage2_reviewer_backfill",
                "attempt_role": "reviewer_backfill",
            }
        )
        store.event("stage2_reviewer_backfill_attempt", {"model": model, "label": label})

    if not reviewer_records:
        return [], candidates, attempted_backfill

    stage2_results, _label_to_model = await stage2_collect_rankings(
        user_query,
        review_subjects,
        config,
        provider,
        store,
        reviewers=reviewer_records,
    )
    return stage2_results, candidates, attempted_backfill


async def cancel_and_drain(tasks: set[asyncio.Task] | list[asyncio.Task]) -> None:
    pending = [task for task in tasks if not task.done()]
    if not pending:
        return
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def contribution_map_is_renderable(data: dict[str, Any] | None) -> bool:
    if not isinstance(data, dict):
        return False
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("text"), str) and block["text"].strip():
            return True
    return False


def build_contribution_map_repair_prompt(
    final_response: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    aggregate_rankings: list[dict[str, Any]] | None = None,
    *,
    previous_error: str | None = None,
) -> str:
    stage1_text = "\n\n".join(
        f"{result.get('label', 'Response ?')}:\nModel: {result.get('model')}\nResponse: {result.get('response', '')}"
        for result in stage1_results
        if result.get("status") == "ok"
    ) or "无可用 Stage 1 成员素材。"
    stage2_text = "\n\n".join(
        f"Model: {result.get('model')}\nRanking: {result.get('ranking')}\nParsed: {result.get('parsed_ranking')}"
        for result in stage2_results
        if result.get("status") == "ok"
    ) or "无可用 Stage 2 排序。"
    aggregate_text = "未生成可用的 Stage 2 综合排序。"
    if aggregate_rankings:
        aggregate_text = "\n".join(
            f"{index}. {item.get('label') or item.get('response_label') or item.get('stage1_label') or item.get('source_stage1_label') or 'Response ?'} | "
            f"model={item.get('model')} | average_rank={item.get('average_rank')} | "
            f"rankings_count={item.get('rankings_count')} | positions={item.get('positions', [])}"
            for index, item in enumerate(aggregate_rankings, start=1)
        )
    retry_note = ""
    if previous_error:
        retry_note = f"\n上一次生成失败原因：{previous_error}\n这一次必须更严格：只输出 JSON，不要输出解释、正文或注释。\n"
    return f"""你是 LLM Council 的主席。你已经完成最终综述正文。现在不要改写正文，只为这份 final.md 生成 contribution_map JSON。{retry_note}

要求：
- 只输出唯一一个 fenced `json` 代码块，代码块内是 JSON object；也允许只输出纯 JSON object。
- 不要输出正文、解释、注释或额外 Markdown。
- JSON 必须包含 schema_version=1、enabled=true、source="chairman_structured_output"、blocks。
- blocks 必须是非空列表；每个 block 必须有 id、type、text、attribution。
- block.text 必须摘自 final.md 的对应内容，不得新增观点，不得改写最终正文。
- block.type 只能使用 heading、paragraph、editor_note、disagreement。
- attribution.kind 只能使用 single_member、multi_member_consensus、editor_note、synthesis、not_attributable。
- single_member.members 只写一个真实 Stage 1 模型名；multi_member_consensus.members 至少两个真实 Stage 1 模型名。
- synthesis.members 表示主席主要参考素材，不表示成员共识。
- 无法可靠归因时用 not_attributable，members 用空列表；不要用 synthesis 当兜底大筐。
- 有顺序关系要点用有序 Markdown 列表；并列要点用无序 Markdown 列表。
- editor_note 类型的 block.text 必须是纯评注意见，不得包含“编者注：”“主席评注：”“评注：”前缀。

final.md:
{final_response}

Stage 1 成员素材:
{stage1_text}

Stage 2 排序与评价:
{stage2_text}

Stage 2 综合排序:
{aggregate_text}
"""


async def repair_contribution_map(
    *,
    provider: ModelRuntime,
    store: ArtifactStore,
    model: str,
    final_response: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    aggregate_rankings: list[dict[str, Any]],
    config: CouncilConfig,
    agent: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    max_attempts = max(0, int(config.chairman_contribution_repair_attempts))
    records: list[dict[str, Any]] = []
    previous_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        prompt_path = f"stage3/contribution_map.repair.{attempt}.prompt.md"
        response_path = f"stage3/contribution_map.repair.{attempt}.response.md"
        prompt = build_contribution_map_repair_prompt(
            final_response,
            stage1_results,
            stage2_results,
            aggregate_rankings,
            previous_error=previous_error,
        )
        store.write_text(prompt_path, prompt + "\n")
        repair_call = await provider.query_model(
            model=model,
            prompt=prompt,
            run_id=store.root.name,
            stage="stage3",
            label=f"contribution-map-repair-{attempt}",
            output_dir=store.path("stage3"),
            agent=agent,
            query_timeout=config.chairman_timeout,
        )
        record: dict[str, Any] = {
            "attempt": attempt,
            "prompt_path": prompt_path,
            "response_path": response_path,
            "status": repair_call.status,
            "error": repair_call.error,
        }
        if repair_call.status != "ok":
            previous_error = repair_call.error or "provider_failed"
            record["status"] = "provider_failed"
            record["error"] = previous_error
            records.append(record)
            continue
        store.write_text(response_path, repair_call.response + "\n")
        contribution_map = extract_contribution_map(repair_call.response)
        if contribution_map_is_renderable(contribution_map):
            record["status"] = "ok"
            record["error"] = None
            records.append(record)
            return contribution_map, {
                "attempted": True,
                "attempts": attempt,
                "status": "ok",
                "prompt_path": prompt_path,
                "response_path": response_path,
                "error": None,
                "attempt_records": records,
            }
        previous_error = "missing_or_invalid_contribution_map_json"
        record["status"] = "invalid_json"
        record["error"] = previous_error
        records.append(record)
    return None, {
        "attempted": True,
        "attempts": max_attempts,
        "status": "failed",
        "error": previous_error or "missing_or_invalid_contribution_map_json",
        "attempt_records": records,
    }


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    config: CouncilConfig,
    provider: ModelRuntime,
    store: ArtifactStore,
    fallback_chain: list[str] | None = None,
    rebuttal_results: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    label_to_model = {
        result["label"]: result["model"]
        for result in stage1_results
        if result.get("label") and result.get("model")
    }
    aggregate_rankings = aggregate_rankings_with_labels(
        calculate_aggregate_rankings(valid_stage2_rankings(stage2_results), label_to_model),
        label_to_model,
    )
    chairman_prompt = build_stage3_prompt(
        user_query,
        stage1_results,
        stage2_results,
        aggregate_rankings=aggregate_rankings,
        contribution_map_enabled=config.chairman_contribution_enabled,
        rebuttal_results=rebuttal_results,
    )
    store.write_text("stage3/chairman.prompt.md", chairman_prompt + "\n")

    attempted = [config.chairman]
    used = config.chairman
    fallback_from = None
    failed_attempts: list[dict[str, Any]] = []

    call = await provider.query_model(
        model=config.chairman,
        prompt=chairman_prompt,
        run_id=store.root.name,
        stage="stage3",
        label="final",
        output_dir=store.path("stage3"),
        agent=config.chairman_agent,
        query_timeout=config.chairman_timeout,
    )
    if call.status != "ok":
        failed_attempts.append(stage3_failure_record(config.chairman, call))

    if call.status != "ok" and fallback_chain:
        for fb_model in fallback_chain:
            attempted.append(fb_model)
            fb_call = await provider.query_model(
                model=fb_model,
                prompt=chairman_prompt,
                run_id=store.root.name,
                stage="stage3",
                label=f"final-fb-{fb_model}",
                output_dir=store.path("stage3"),
                query_timeout=config.chairman_timeout,
            )
            if fb_call.status == "ok":
                call = fb_call
                used = fb_model
                fallback_from = config.chairman
                break
            failed_attempts.append(stage3_failure_record(fb_model, fb_call))

    chairman_meta = {
        "attempted": attempted,
        "used": used,
        "fallback_from": fallback_from,
        "failed_attempts": failed_attempts,
    }

    if call.status != "ok":
        degraded = degraded_final_from_stage2(stage1_results, stage2_results)
        if degraded is not None:
            chairman_meta["used"] = degraded["model"]
            chairman_meta["degraded_from"] = attempted
            store.write_text("stage3/final.md", degraded["response"] + "\n")
            store.write_json("stage3/final.json", degraded)
            return degraded, chairman_meta

    copy_check = stage3_copy_check(call.response, stage1_results) if call.status == "ok" else None
    prompt_path = "stage3/chairman.prompt.md"
    original_prompt_path: str | None = None
    if copy_check and copy_check["triggered"]:
        retry_prompt = build_stage3_copy_retry_prompt(chairman_prompt, copy_check["matched_stage1"])
        store.write_text("stage3/chairman.copy_retry.prompt.md", retry_prompt + "\n")
        retry_call = await provider.query_model(
            model=used,
            prompt=retry_prompt,
            run_id=store.root.name,
            stage="stage3",
            label="final-copy-retry",
            output_dir=store.path("stage3"),
            agent=config.chairman_agent if used == config.chairman else None,
            query_timeout=config.chairman_timeout,
        )
        copy_check["retry_attempted"] = True
        copy_check["retry_status"] = retry_call.status
        copy_check["retry_prompt_path"] = "stage3/chairman.copy_retry.prompt.md"
        if retry_call.status == "ok":
            retry_matches = stage3_copy_matches(retry_call.response, stage1_results)
            copy_check["retry_matched_stage1"] = retry_matches
            call = retry_call
            prompt_path = "stage3/chairman.copy_retry.prompt.md"
            original_prompt_path = "stage3/chairman.prompt.md"
            if retry_matches:
                copy_check["resolved"] = False
                copy_check["unresolved_reason"] = "retry_still_copies_stage1"
            else:
                copy_check["resolved"] = True
                copy_check["unresolved_reason"] = None
        else:
            copy_check["resolved"] = False
            copy_check["unresolved_reason"] = "retry_failed"
            copy_check["retry_error"] = retry_call.error

    final_response = strip_contribution_map_fence(call.response) if config.chairman_contribution_enabled else call.response
    final = {
        "model": used,
        "expected_model": call.expected_model,
        "actual_model": call.actual_model,
        "agent": call.agent,
        "subagent_invocation": call.subagent_invocation,
        "response": final_response,
        "status": call.status,
        "error": call.error,
        "prompt_path": prompt_path,
        "response_path": "stage3/final.md",
        "json_path": "stage3/final.json",
        "tool_calls_count": call.tool_calls_count,
        "turns_count": call.turns_count,
        "tool_budget_status": call.tool_budget_status,
        "raw_partial_recoverable": call.raw_partial_recoverable,
        "retried": call.retried,
        "retry_error": call.retry_error,
    } | tool_policy_record(call)
    if final_response != call.response:
        final["raw_response"] = call.response
    if original_prompt_path:
        final["original_prompt_path"] = original_prompt_path
    if copy_check:
        final["chairman_copy_check"] = copy_check
        chairman_meta["copy_check"] = copy_check
    final["contribution_map_enabled"] = bool(config.chairman_contribution_enabled)
    final["contribution_map_requested"] = bool(config.chairman_contribution_enabled)
    final["contribution_map_required"] = bool(config.chairman_contribution_required)
    if config.chairman_contribution_enabled:
        final["contribution_map_path"] = "stage3/contribution_map.json"
        contribution_map = extract_contribution_map(call.response)
        repair_meta = None
        if not contribution_map_is_renderable(contribution_map):
            contribution_map, repair_meta = await repair_contribution_map(
                provider=provider,
                store=store,
                model=used,
                final_response=final_response,
                stage1_results=stage1_results,
                stage2_results=stage2_results,
                aggregate_rankings=aggregate_rankings,
                config=config,
                agent=config.chairman_agent if used == config.chairman else None,
            )
        if contribution_map is None:
            final["contribution_map_error"] = "missing_or_invalid_contribution_map_json"
        else:
            store.write_json("stage3/contribution_map.json", contribution_map)
            final.pop("contribution_map_error", None)
        if repair_meta:
            final["contribution_map_repair"] = repair_meta
        final["contribution_map_stripped_from_response"] = final_response != call.response
    store.write_text("stage3/final.md", final_response + "\n")
    store.write_json("stage3/final.meta.json", call.to_json() | {"captured_at": utc_now()})
    store.write_json("stage3/final.json", final)
    return final, chairman_meta


def normalize_for_stage3_copy_check(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return normalized


def stage3_copy_matches(
    final_text: str,
    stage1_results: list[dict[str, Any]],
    *,
    exact_min_chars: int = 80,
    similarity_min_chars: int = 200,
    similarity_threshold: float = 0.92,
) -> list[dict[str, Any]]:
    final_normalized = normalize_for_stage3_copy_check(final_text)
    if not final_normalized:
        return []

    matches: list[dict[str, Any]] = []
    for result in stage1_results:
        if result.get("status") != "ok":
            continue
        source_normalized = normalize_for_stage3_copy_check(result.get("response", ""))
        if not source_normalized:
            continue
        exact_match = (
            final_normalized == source_normalized
            and len(final_normalized) >= exact_min_chars
        )
        similarity = 1.0 if exact_match else 0.0
        near_match = False
        if not exact_match and min(len(final_normalized), len(source_normalized)) >= similarity_min_chars:
            similarity = SequenceMatcher(None, final_normalized, source_normalized).ratio()
            near_match = similarity >= similarity_threshold
        if not exact_match and not near_match:
            continue
        matches.append(
            {
                "label": result.get("label"),
                "model": result.get("model"),
                "similarity": round(similarity, 4),
                "match_type": "exact_normalized" if exact_match else "near_copy",
            }
        )
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return matches


def stage3_copy_check(final_text: str, stage1_results: list[dict[str, Any]]) -> dict[str, Any]:
    matches = stage3_copy_matches(final_text, stage1_results)
    return {
        "triggered": bool(matches),
        "matched_stage1": matches,
        "retry_attempted": False,
        "resolved": not matches,
        "unresolved_reason": None,
    }


def build_stage3_copy_retry_prompt(chairman_prompt: str, matches: list[dict[str, Any]]) -> str:
    match_lines = "\n".join(
        f"- {match.get('label')} | model={match.get('model')} | "
        f"similarity={match.get('similarity')} | match_type={match.get('match_type')}"
        for match in matches
    )
    return f"""{chairman_prompt}

ANTI-COPY RETRY:
你刚才的主席最终答案与以下 Stage 1 回答过于接近：
{match_lines}

请重新生成最终答案。硬性要求：
- 不得逐字或近似复用上述 Stage 1 回答。
- 必须重新组织论证结构，并融合综合排序靠前回答的不同洞察。
- 仍然直接回答用户原始问题，不要输出模型排名或解释重试过程。"""


def degraded_final_from_stage2(
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    label_to_model = {
        result["label"]: result["model"]
        for result in stage1_results
        if result.get("label") and result.get("model")
    }
    aggregate = calculate_aggregate_rankings(valid_stage2_rankings(stage2_results), label_to_model)
    by_model = {
        result.get("model"): result
        for result in stage1_results
        if result.get("status") == "ok" and result.get("model") and result.get("response")
    }
    for item in aggregate:
        model = item.get("model")
        source = by_model.get(model)
        if not source:
            continue
        return {
            "model": model,
            "expected_model": model,
            "actual_model": source.get("actual_model") or model,
            "agent": source.get("agent"),
            "subagent_invocation": source.get("subagent_invocation"),
            "response": source["response"],
            "status": "degraded_ok",
            "error": None,
            "degraded_source": "stage2_best_stage1_response",
            "source_stage1_label": source.get("label"),
            "prompt_path": "stage3/chairman.prompt.md",
            "response_path": "stage3/final.md",
            "json_path": "stage3/final.json",
            "tool_calls_count": source.get("tool_calls_count", 0),
            "turns_count": source.get("turns_count", 0),
            "tool_budget_status": source.get("tool_budget_status", "ok"),
            "raw_partial_recoverable": source.get("raw_partial_recoverable", False),
            "retried": source.get("retried", False),
            "retry_error": source.get("retry_error"),
            "member_tool_mode": source.get("member_tool_mode"),
            "allowed_tools": source.get("allowed_tools", []),
            "disallowed_tools": source.get("disallowed_tools", []),
            "forbidden_tool_calls": source.get("forbidden_tool_calls", []),
        }
    return None


def valid_stage2_rankings(stage2_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        result for result in stage2_results
        if result.get("status") == "ok" and result.get("parse_status") == "ok"
    ]


def stage3_failure_record(model: str, call: ModelCallResult) -> dict[str, Any]:
    return {
        "stage_record": model,
        "status": call.status,
        "error": call.error or f"non-ok status: {call.status}",
        "expected_model": call.expected_model,
        "actual_model": call.actual_model,
    }


def build_stage1_prompt(user_query: str) -> str:
    return f"""{DEFAULT_READER_LANGUAGE_INSTRUCTION}

用户原始问题：
{user_query.strip()}"""


def build_stage2_prompt(user_query: str, stage1_results: list[dict[str, Any]]) -> str:
    responses_text = "\n\n".join(
        f"{result['label']}:\n{result['response']}" for result in stage1_results
    )
    return f"""你正在评估多个模型对同一个用户问题的回答。

{DEFAULT_READER_LANGUAGE_INSTRUCTION}

用户原始问题：
{user_query}

以下是不同模型的匿名回答：

{responses_text}

你的任务：
1. 先逐一评价每个回答，说明它做得好的地方和不足。
2. 在回复的最后给出最终排序。

重要：最终排序区块必须严格保持以下格式，便于机器解析：
- 必须以英文大写行 "FINAL RANKING:" 开始。
- 然后按从好到差列出编号列表。
- 每一行只能包含编号、英文句点、空格和回答标签，例如 "1. Response A"。
- 排序区块里不要添加其他解释。

正确格式示例：

Response A 对 X 有清晰说明，但遗漏了 Y...
Response B 准确但深度不足...
Response C 覆盖最完整...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

现在请给出你的评价和排序："""


def build_stage3_prompt(
    user_query: str,
    stage1_results: list[dict[str, Any]],
    stage2_results: list[dict[str, Any]],
    aggregate_rankings: list[dict[str, Any]] | None = None,
    contribution_map_enabled: bool = True,
    rebuttal_results: list[dict[str, Any]] | None = None,
) -> str:
    stage1_text = "\n\n".join(
        f"{result.get('label', 'Response ?')}:\nModel: {result['model']}\nResponse: {result['response']}" for result in stage1_results
    )
    stage2_text = "\n\n".join(
        f"Model: {result['model']}\nRanking: {result['ranking']}" for result in stage2_results
    )
    model_to_label: dict[str, str] = {}
    for result in stage1_results:
        if result.get("model") and result.get("label"):
            model_to_label.setdefault(str(result["model"]), str(result["label"]))
    aggregate_text = "未生成可用的 Stage 2 综合排序。"
    if aggregate_rankings:
        aggregate_lines: list[str] = []
        for index, item in enumerate(aggregate_rankings, start=1):
            label = (
                item.get("label")
                or item.get("response_label")
                or item.get("stage1_label")
                or item.get("source_stage1_label")
                or model_to_label.get(str(item.get("model")))
                or "Response ?"
            )
            positions = item.get("positions", [])
            aggregate_lines.append(
                f"{index}. {label} | model={item.get('model')} | "
                f"average_rank={item.get('average_rank')} | "
                f"rankings_count={item.get('rankings_count')} | positions={positions}"
            )
        aggregate_text = "\n".join(aggregate_lines)
    rebuttal_section = ""
    rebuttal_instruction = ""
    if rebuttal_results:
        rebuttal_text = "\n\n".join(
            f"{result.get('label', 'Response ?')} | model={result.get('model')}:\n{result.get('response', '')}"
            for result in rebuttal_results
            if result.get("status") == "ok" and str(result.get("response") or "").strip()
        )
        if rebuttal_text:
            rebuttal_section = f"""

阶段 2.5 - 成员答辩：
{rebuttal_text}
"""
            rebuttal_instruction = "\n- Stage 2.5 答辩中的让步或修正代表该成员最新立场；与原答案冲突时，以答辩后的修正为准。"
    contribution_instruction = ""
    if contribution_map_enabled:
        contribution_instruction = """

贡献说明灰度要求：
- 除最终综述正文外，最后必须输出唯一一个 fenced `json` 代码块，代码块内只放 contribution_map JSON 对象，供系统保存为 stage3/contribution_map.json。
- contribution_map JSON 必须能被 `json.loads` 直接解析；JSON 字符串内如需引用引号，必须转义英文双引号，或改用中文引号 / 单引号，禁止写未转义的 `"`。
- JSON 代码块之后不要再输出任何解释、注释或 Markdown。
- JSON 必须包含 schema_version=1、enabled=true、source 和 blocks。
- blocks 中每个 block 必须有 id、type、text、attribution。
- block.type 只能使用 heading、paragraph、editor_note、disagreement。
- attribution.kind 只能使用 single_member、multi_member_consensus、editor_note、synthesis、not_attributable。
- single_member 的 members 必须只引用真实在场 Stage 1 成员。
- multi_member_consensus 的 members 至少 2 个；multi_member_consensus.members 表示这些成员都表达过同一核心观点。
- synthesis 是主席对成员素材进行编辑、合并、桥接或结构化整理；synthesis 不等于成员共识。
- synthesis.members 表示主席主要参考了这些成员素材，不表示这些成员对最终表述达成共识。
- 无法可靠归因时优先使用 not_attributable，不要用 synthesis 当兜底大筐。
- members 只写模型名，不要自行写同侪排名；系统会根据 Stage 2 综合排序渲染"同侪#n"。
- editor_note 必须明确表示主席基于成员素材延伸的编者注。
- 不要输出贡献百分比，不要把同侪排序写成模型能力排行。

Contribution map 输出约束：
1. block.text 中如有 2 个以上连续要点，必须使用 Markdown 列表格式，不得写成一整段内联编号或内联顿号串。
2. 有顺序关系的要点使用有序列表：
   1. ...
   2. ...
   3. ...
3. 无顺序关系的并列要点使用无序列表：
   - ...
   - ...
   - ...
4. editor_note 类型的 block.text 必须是纯评注意见，不得包含“编者注：”“主席评注：”“评注：”等重复标签。
5. block.type 与 attribution.kind 是两个不同字段，必须分别按 schema 取值，不得混用。
6. 输出前自检：正文应能直接进入 HTML 渲染，不应依赖渲染器二次拆段。
"""
    return f"""你是 LLM Council 的主席。多个 AI 模型已经回答了用户问题，并对彼此的回答进行了排序。

{DEFAULT_READER_LANGUAGE_INSTRUCTION}

原始问题：
{user_query}

阶段 1 - 各模型独立回答：
{stage1_text}

阶段 2 - 同侪排序与评价：
{stage2_text}

Stage 2 综合排序（按 average_rank 从低到高，越靠前代表同侪排序越好）：
{aggregate_text}{rebuttal_section}

你的任务是综合以上所有信息，给出一个直接、清晰、有判断力的综述答案。请考虑：
- 各个回答提供的有效洞察。
- 同侪排序反映出的回答质量差异。
- 模型之间的一致意见和分歧。{rebuttal_instruction}
- 必须显式融合 top-ranked responses 的不同洞察，尤其是综合排序靠前回答的关键证据、判断和边界条件。

重要：
- 你的输出应该是针对原始问题的综述性最终答案，而不是对各模型表现的评价或排名。不要评价哪个模型更好，不要输出模型排名对比。直接回答用户的问题。
- 不得逐字或近似复用任何 Stage 1 回答；不能把某个候选回答原封不动当成最终答案。
- 如果某个 Stage 1 回答整体最好，也必须重新组织、压缩、补足边界，并融合其他高排名回答的有效洞察。{contribution_instruction}"""


def parse_ranking_from_text(ranking_text: str) -> list[str]:
    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r"\d+\.\s*Response [A-Z]", ranking_section)
            if numbered_matches:
                return [re.search(r"Response [A-Z]", m).group() for m in numbered_matches if re.search(r"Response [A-Z]", m)]
            return re.findall(r"Response [A-Z]", ranking_section)
    return re.findall(r"Response [A-Z]", ranking_text)


def ranking_is_complete(parsed: list[str], valid_labels: set[str]) -> bool:
    return set(parsed) == valid_labels and len(parsed) == len(valid_labels)


def calculate_aggregate_rankings(
    stage2_results: list[dict[str, Any]],
    label_to_model: dict[str, str],
) -> list[dict[str, Any]]:
    model_positions: dict[str, list[int]] = {}
    for ranking in stage2_results:
        parsed_ranking = ranking.get("parsed_ranking") or parse_ranking_from_text(ranking.get("ranking", ""))
        seen: set[str] = set()
        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model and label not in seen:
                seen.add(label)
                model_name = label_to_model[label]
                model_positions.setdefault(model_name, []).append(position)

    aggregate: list[dict[str, Any]] = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append(
                {
                    "model": model,
                    "average_rank": round(avg_rank, 2),
                    "rankings_count": len(positions),
                    "positions": positions,
                }
            )
    aggregate.sort(key=lambda x: (x["average_rank"], x["model"]))
    return aggregate


def aggregate_rankings_with_labels(
    aggregate_rankings: list[dict[str, Any]],
    label_to_model: dict[str, str],
) -> list[dict[str, Any]]:
    model_to_label: dict[str, str] = {}
    for label, model in label_to_model.items():
        model_to_label.setdefault(model, label)
    return [
        {"label": model_to_label.get(item.get("model"), "Response ?")} | item
        for item in aggregate_rankings
    ]


async def run_full_council(
    user_query: str,
    config: CouncilConfig,
    store: ArtifactStore,
) -> dict[str, Any]:
    manifest = initial_manifest(store.root.name, user_query, config)
    store.write_manifest(manifest)
    store.write_text("input.md", user_query.rstrip() + "\n")
    store.write_json("config.json", config_to_json(config))

    store.event("runtime_check_start")
    health = runtime_doctor(config.runtime_command)
    store.write_json("runtime/doctor.json", {
        "ok": health.ok,
        "command": health.command,
        "version": health.version,
        "doctor_exit_code": health.doctor_exit_code,
        "doctor": health.doctor,
        "errors": health.errors,
        "warnings": health.warnings,
        "ignored_errors": health.ignored_errors,
    })
    store.write_json("runtime/traecli.models.json", health.models)
    manifest["warnings"].extend(health.warnings)
    manifest["warnings"].extend(f"ignored runtime doctor error: {error}" for error in health.ignored_errors)
    if not health.ok:
        manifest["status"] = "failed"
        manifest["failures"].extend(health.errors)
        store.write_manifest(manifest)
        return manifest

    expected_models = list(dict.fromkeys(config.members + [config.chairman]))
    try:
        require_models_available(expected_models, health.models)
    except ValueError as exc:
        manifest["status"] = "failed"
        manifest["failures"].append(str(exc))
        store.write_manifest(manifest)
        return manifest

    provider_runtime_cwd = Path(config.runtime_cwd) if config.runtime_cwd else None
    if config.provider_mode == "direct" and provider_runtime_cwd is None and config.member_runtime_cwd_mode == "isolated_temp":
        provider_runtime_cwd = Path(tempfile.mkdtemp(prefix=f"lct-{store.root.name}-member-cwd-"))
        provider_runtime_cwd.mkdir(parents=True, exist_ok=True)
        store.write_text("runtime/member-cwd.path", str(provider_runtime_cwd) + "\n")
        store.event("member_runtime_cwd_ready", {"mode": config.member_runtime_cwd_mode, "path": str(provider_runtime_cwd)})

    provider_member_tool_mode = "subagent_invocation" if config.provider_mode == "subagent" else config.member_tool_mode
    provider = build_model_runtime(config, provider_runtime_cwd, provider_member_tool_mode)

    store.event("stage1_start", {"members": config.members})
    stage1_results = await stage1_collect_responses(user_query, config, provider, store)

    for retry_round in range(config.stage1_max_retries):
        stage1_status = classify_stage1_status(stage1_results, config.min_valid_members, chairman_model=config.chairman)
        if stage1_status != "failed":
            break
        failed_indices = [
            i for i, r in enumerate(stage1_results)
            if r.get("status") != "ok" and not (config.chairman and r.get("model") == config.chairman and r.get("status") == "failed")
        ]
        if not failed_indices:
            break
        store.event("stage1_retry", {"round": retry_round + 1, "failed_count": len(failed_indices)})
        for idx in failed_indices:
            model = config.members[idx]
            label = chr(65 + idx)
            output_dir = store.path("stage1")
            retry_call = await provider.query_model(
                model=model,
                prompt=build_stage1_prompt(user_query),
                run_id=store.root.name,
                stage="stage1",
                label=label,
                output_dir=output_dir,
                agent=config.agent_for_member(idx),
            )
            stage1_results[idx] = {
                "label": f"Response {label}",
                "file_label": label,
                "model": model,
                "expected_model": retry_call.expected_model,
                "actual_model": retry_call.actual_model,
                "agent": retry_call.agent,
                "subagent_invocation": retry_call.subagent_invocation,
                "response": retry_call.response,
                "status": retry_call.status,
                "meta_path": f"stage1/{label}.meta.json",
                "response_path": f"stage1/{label}.response.md",
                "error": retry_call.error,
                "attempt_role": "retry",
                "attempt_index": retry_round + 1,
                "tool_calls_count": retry_call.tool_calls_count,
                "turns_count": retry_call.turns_count,
                "tool_budget_status": retry_call.tool_budget_status,
                "raw_partial_recoverable": retry_call.raw_partial_recoverable,
                "retried": True,
                "retry_error": retry_call.retry_error or retry_call.error,
            } | tool_policy_record(retry_call)
            store.write_text(f"stage1/{label}.response.md", retry_call.response + "\n")
            store.write_json(f"stage1/{label}.meta.json", retry_call.to_json() | {"captured_at": utc_now()})
            ensure_stage1_stream_sidecar(store, label, retry_call)

    backfill_candidates, backfill_attempted = await backfill_stage1_responses(
        user_query,
        stage1_results,
        config,
        provider,
        store,
        health.models,
    )
    manifest["stages"]["stage1"] = stage1_results
    stage1_status = classify_stage1_status(stage1_results, config.min_valid_members, chairman_model=config.chairman)
    quorum_metadata = stage1_quorum_metadata(
        stage1_results,
        config,
        primary_members=config.members,
        backfill_candidates=backfill_candidates,
        backfill_attempted=backfill_attempted,
    )
    manifest["metadata"]["quorum"] = quorum_metadata
    if stage1_status == "failed" and quorum_metadata["low_quorum_used"]:
        stage1_status = "degraded_ok"
        manifest["warnings"].append(
            f"low quorum degraded result: {quorum_metadata['effective_valid_members']} / {config.min_valid_members} valid Stage 1 members"
        )
    update_manifest_with_stage1_status(manifest, stage1_status)
    record_stage_failures(manifest, stage1_results)
    store.write_manifest(manifest)
    if stage1_status == "failed":
        return manifest

    valid_stage1 = [r for r in stage1_results if stage1_record_is_valid(r)]

    store.event("stage2_start")
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, valid_stage1, config, provider, store)
    valid_stage2 = [r for r in stage2_results if r.get("status") == "ok"]
    stage2_reviewer_target = min(len(valid_stage1), config.min_valid_members)
    stage2_backfill_candidates: list[str] = []
    stage2_backfill_attempted: list[str] = []
    if (
        config.stage2_auto_backfill
        and 0 < len(valid_stage2) < stage2_reviewer_target
    ):
        needed_reviewers = stage2_reviewer_target - len(valid_stage2)
        more_stage2, stage2_backfill_candidates, stage2_backfill_attempted = await backfill_stage2_reviewers(
            user_query,
            valid_stage1,
            stage1_results,
            stage2_results,
            config,
            provider,
            store,
            health.models,
            needed_reviewers,
        )
        if more_stage2:
            store.event("stage2_backfill_reviewers", {"models": [r["model"] for r in more_stage2]})
            stage2_results.extend(more_stage2)
            valid_stage2 = [r for r in stage2_results if r.get("status") == "ok"]
    aggregate_rankings = calculate_aggregate_rankings(valid_stage2_rankings(stage2_results), label_to_model)
    store.write_json("stage2/aggregate.json", aggregate_rankings)
    manifest["metadata"]["label_to_model"] = label_to_model
    manifest["metadata"]["aggregate_rankings"] = aggregate_rankings
    valid_reviewer_models = [r["model"] for r in stage2_results if r.get("status") == "ok"]
    failed_reviewer_models = [r["model"] for r in stage2_results if r.get("status") != "ok"]
    stage1_backfill_members = [
        r["model"]
        for r in valid_stage1
        if r.get("attempt_role") == "backfill"
    ]
    stage2_reviewer_backfill = [
        r["model"]
        for r in stage2_results
        if r.get("reviewer_source") == "stage2_reviewer_backfill"
    ]
    manifest["metadata"]["stage2_reviewers"] = {
        "reviewer_target": stage2_reviewer_target,
        "review_subject_count": len(valid_stage1),
        "review_subject_labels": [r["label"] for r in valid_stage1],
        "review_subject_models": [r["model"] for r in valid_stage1],
        "reviewer_count": len(valid_reviewer_models),
        "valid_reviewers": valid_reviewer_models,
        "failed_reviewers": failed_reviewer_models,
        "backfill_reviewers": [
            r["model"]
            for r in stage2_results
            if r.get("reviewer_source") in ("stage1_backfill", "stage2_reviewer_backfill")
        ],
        "backfill_attempted": stage2_backfill_attempted,
        "reviewer_backfill_candidates": stage2_backfill_candidates,
        "reviewer_backfill_attempted": stage2_backfill_attempted,
        "member_backfill_attempted": backfill_attempted,
        "stage1_backfill_members": stage1_backfill_members,
        "stage2_reviewer_backfill": stage2_reviewer_backfill,
        "reviewer_only_backfill": bool(stage2_reviewer_backfill),
    }
    manifest["stages"]["stage2"] = stage2_results
    record_stage_failures(manifest, stage2_results)
    if not valid_stage2:
        manifest["status"] = "failed"
        store.write_manifest(manifest)
        return manifest
    stage2_degraded = any(r.get("status") != "ok" for r in stage2_results)
    stage2_5_results: list[dict[str, Any]] = []
    if config.debate_enabled:
        store.event("stage2_5_start")
        stage2_5_results = await stage2_5_collect_rebuttals(user_query, valid_stage1, stage2_results, config, provider, store)
        manifest["stages"]["stage2_5"] = stage2_5_results
        manifest["metadata"]["debate"] = debate_metadata(config, stage2_5_results)
        for item in stage2_5_results:
            if item.get("status") != "ok":
                manifest["warnings"].append(
                    f"stage2_5 rebuttal unavailable for {item.get('label') or item.get('model')}: {item.get('error') or item.get('status')}"
                )
        store.write_manifest(manifest)

    fallback_chain = config.chairman_fallback
    if not fallback_chain:
        from .roster import CHAIRMAN_FALLBACK_CHAIN
        fallback_chain = CHAIRMAN_FALLBACK_CHAIN

    store.event("stage3_start", {"chairman": config.chairman})
    if config.debate_enabled:
        stage3_result, chairman_meta = await stage3_synthesize_final(
            user_query, valid_stage1, stage2_results, config, provider, store,
            fallback_chain=fallback_chain,
            rebuttal_results=stage2_5_results,
        )
    else:
        stage3_result, chairman_meta = await stage3_synthesize_final(
            user_query, valid_stage1, stage2_results, config, provider, store,
            fallback_chain=fallback_chain,
        )
    manifest["stages"]["stage3"] = stage3_result
    manifest["metadata"]["chairman"] = chairman_meta
    contribution_path = "stage3/contribution_map.json"
    manifest["metadata"]["chairman_contribution"] = chairman_contribution_metadata(
        config,
        present=(store.root / contribution_path).exists(),
        error=stage3_result.get("contribution_map_error"),
    )
    copy_check = stage3_result.get("chairman_copy_check") or chairman_meta.get("copy_check")
    if copy_check and copy_check.get("triggered") and not copy_check.get("resolved"):
        matched_labels = [
            str(match.get("label"))
            for match in copy_check.get("matched_stage1", [])
            if match.get("label")
        ]
        manifest["warnings"].append(
            "stage3_copy_risk: chairman final still closely matches Stage 1 after anti-copy retry; "
            f"matched_stage1={', '.join(matched_labels) or 'unknown'}"
        )
    record_stage_failures(manifest, [stage3_result])
    if stage3_result.get("status") == "degraded_ok":
        manifest["status"] = "degraded_ok"
        manifest["warnings"].append("stage3 degraded to the best ranked Stage 1 response")
        manifest["failures"].extend(chairman_meta.get("failed_attempts") or [])
    elif stage3_result.get("status") != "ok":
        manifest["status"] = "failed"
    elif stage1_status == "degraded_ok" or stage2_degraded or manifest.get("failures"):
        manifest["status"] = "degraded_ok"
    else:
        manifest["status"] = "ok"
    store.write_manifest(manifest)
    return manifest


def initial_manifest(run_id: str, user_query: str, config: CouncilConfig) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "status": "running",
        "input_chars": len(user_query),
        "config": config_to_json(config),
        "artifacts": {
            "input": "input.md",
            "config": "config.json",
            "events": "events.jsonl",
            "runtime_doctor": "runtime/doctor.json",
            "runtime_models": "runtime/traecli.models.json",
            "html": "html/index.html",
        },
        "stages": {"stage1": [], "stage2": [], "stage3": None},
        "metadata": initial_metadata(config),
        "warnings": [],
        "failures": [],
    }


def initial_metadata(config: CouncilConfig) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "label_to_model": {},
        "aggregate_rankings": [],
        "chairman_contribution": chairman_contribution_metadata(config),
    }
    if config.debate_enabled:
        metadata["debate"] = debate_metadata(config)
    if config.model_selection_provenance:
        metadata["model_selection"] = config.model_selection_provenance
    return metadata


def chairman_contribution_metadata(
    config: CouncilConfig,
    *,
    present: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    requested = bool(config.chairman_contribution_enabled)
    path = "stage3/contribution_map.json" if requested else None
    return {
        "enabled": requested,
        "requested": requested,
        "required": bool(config.chairman_contribution_required),
        "present": bool(present),
        "path": path,
        "source": "chairman_structured_output" if requested and present else None,
        "error": error,
    }


def debate_metadata(config: CouncilConfig, rebuttals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rebuttals = rebuttals or []
    participants = [str(item.get("model")) for item in rebuttals if item.get("model")]
    completed = [str(item.get("model")) for item in rebuttals if item.get("model") and item.get("status") == "ok"]
    failed = [str(item.get("model")) for item in rebuttals if item.get("model") and item.get("status") != "ok"]
    return {
        "enabled": bool(config.debate_enabled),
        "rounds": 1 if config.debate_enabled else 0,
        "participants": participants,
        "participant_labels": [str(item.get("label")) for item in rebuttals if item.get("label")],
        "completed": completed,
        "completed_labels": [str(item.get("label")) for item in rebuttals if item.get("label") and item.get("status") == "ok"],
        "failed": failed,
        "failed_labels": [str(item.get("label")) for item in rebuttals if item.get("label") and item.get("status") != "ok"],
        "failed_all": bool(config.debate_enabled and participants and not completed),
        "review_material": "stage2_reviews_ranking_stripped_reviewer_anonymized" if config.debate_enabled else None,
    }


def config_to_json(config: CouncilConfig) -> dict[str, Any]:
    payload = {
        "members": config.members,
        "chairman": config.chairman,
        "provider_mode": config.provider_mode,
        "runtime_command": config.runtime_command,
        "runtime_cwd": config.runtime_cwd,
        "query_timeout": config.query_timeout,
        "export_html": config.export_html,
        "member_agents": config.member_agents,
        "chairman_agent": config.chairman_agent,
        "use_yolo": config.use_yolo,
        "min_valid_members": config.min_valid_members,
        "target_valid_members": config.target_valid_members,
        "chairman_fallback": config.chairman_fallback,
        "member_soft_checkpoint": config.member_soft_checkpoint,
        "member_quorum_checkpoint": config.member_quorum_checkpoint,
        "member_hard_timeout": config.member_hard_timeout,
        "stage2_timeout": config.stage2_timeout,
        "chairman_timeout": config.chairman_timeout,
        "member_mode": config.member_mode,
        "member_tool_mode": config.member_tool_mode,
        "member_runtime_cwd_mode": config.member_runtime_cwd_mode,
        "runtime_backend": config.runtime_backend,
        "acp_startup_timeout": config.acp_startup_timeout,
        "stage1_max_retries": config.stage1_max_retries,
        "backfill_members": config.backfill_members,
        "stage1_auto_backfill": config.stage1_auto_backfill,
        "stage2_auto_backfill": config.stage2_auto_backfill,
        "allow_low_quorum": config.allow_low_quorum,
        "low_quorum_floor": config.low_quorum_floor,
        "model_selection_provenance": config.model_selection_provenance,
        "chairman_contribution_enabled": config.chairman_contribution_enabled,
        "chairman_contribution_required": config.chairman_contribution_required,
        "chairman_contribution_repair_attempts": config.chairman_contribution_repair_attempts,
    }
    if config.debate_enabled:
        payload["debate_enabled"] = True
    return payload


def build_model_runtime(
    config: CouncilConfig,
    provider_runtime_cwd: Path | None,
    provider_member_tool_mode: str,
) -> ModelRuntime:
    if config.runtime_backend == "direct":
        return TraeCliProvider(
            config.runtime_command,
            config.query_timeout,
            runtime_cwd=provider_runtime_cwd,
            use_yolo=config.use_yolo,
            member_tool_mode=provider_member_tool_mode,
        )
    if config.runtime_backend == "acp":
        return AcpTraeCliRuntime(
            config.runtime_command,
            config.query_timeout,
            runtime_cwd=provider_runtime_cwd,
            use_yolo=config.use_yolo,
            member_tool_mode=provider_member_tool_mode,
            acp_startup_timeout=config.acp_startup_timeout,
        )
    raise ValueError(f"unknown runtime_backend: {config.runtime_backend}")


def tool_policy_record(call: ModelCallResult) -> dict[str, Any]:
    return {
        "member_tool_mode": call.member_tool_mode,
        "allowed_tools": call.allowed_tools,
        "disallowed_tools": call.disallowed_tools,
        "forbidden_tool_calls": call.forbidden_tool_calls,
        "tool_calls": call.tool_calls,
        "tool_result_calls": call.tool_result_calls,
        "web_tool_result_calls_count": call.web_tool_result_calls_count,
        "web_tool_result_call_ids": call.web_tool_result_call_ids,
        "tool_output_conversion_errors": call.tool_output_conversion_errors,
        "lct_search_conversion_errors": call.lct_search_conversion_errors,
        "web_tool_effective_calls_count": call.web_tool_effective_calls_count,
        "lct_web_tool_effective_calls": call.web_tool_effective_calls_count,
        "lct_web_tool_result_calls": call.web_tool_result_calls_count,
        "termination": call.termination,
        "runtime_backend": call.runtime_backend,
        "enforcement_method": call.enforcement_method,
        "enforcement_proof": call.enforcement_proof,
        "disabled_tools": call.disabled_tools,
        "tool_permission_requests": call.tool_permission_requests,
        "acp_transcript_path": call.acp_transcript_path,
        "acp_startup_status": call.acp_startup_status,
    }


def synthetic_failed_call(
    model: str,
    error: str,
    config: CouncilConfig,
    stdout_path: str = "",
    stderr_path: str = "",
    termination: dict[str, Any] | None = None,
    acp_transcript_path: str | None = None,
) -> ModelCallResult:
    allowed_tools, disallowed_tools = tool_policy_for_mode(config.member_tool_mode)
    kwargs: dict[str, Any] = {}
    if config.runtime_backend == "acp":
        kwargs = {
            "permission_mode": "acp_permission_broker",
            "runtime_backend": "acp",
            "enforcement_method": "acp_disabled_tool_permission_broker",
            "enforcement_proof": "transcript_permission_evidence",
            "disabled_tools": disallowed_tools,
            "acp_transcript_path": acp_transcript_path,
            "acp_startup_status": "failed" if error.startswith("acp_startup_failed:") else "ok",
        }
    return ModelCallResult(
        expected_model=model,
        actual_model=None,
        response="",
        status="failed",
        session_id="",
        command=[],
        exit_code=-1,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        error=error,
        member_tool_mode=config.member_tool_mode,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        termination=termination or {},
        **kwargs,
    )


def stage1_record_is_valid(record: dict[str, Any]) -> bool:
    return record.get("status") == "ok" and not record.get("forbidden_tool_calls")


def stage2_reviewer_record_is_valid(record: dict[str, Any]) -> bool:
    if reviewer_source(record) == "stage2_reviewer_backfill":
        return bool(record.get("model"))
    return stage1_record_is_valid(record)


def reviewer_source(record: dict[str, Any]) -> str:
    source = record.get("reviewer_source")
    if isinstance(source, str) and source:
        return source
    return "stage1_backfill" if record.get("attempt_role") == "backfill" else "stage1_ok"


def reviewer_attempt_role(record: dict[str, Any]) -> str:
    attempt_role = record.get("attempt_role")
    if isinstance(attempt_role, str) and attempt_role:
        return attempt_role
    return "backfill" if reviewer_source(record) == "stage1_backfill" else "primary"


def stage_file_label(record: dict[str, Any], index: int) -> str:
    file_label = record.get("file_label")
    if isinstance(file_label, str) and file_label:
        return file_label
    label = record.get("label")
    if isinstance(label, str) and label.startswith("Response "):
        suffix = label.removeprefix("Response ").strip()
        if suffix:
            return suffix
    return chr(65 + index)


def effective_stage1_count(stage1_results: list[dict[str, Any]]) -> int:
    return sum(1 for result in stage1_results if stage1_record_is_valid(result))


def stage1_quorum_metadata(
    stage1_results: list[dict[str, Any]],
    config: CouncilConfig,
    *,
    primary_members: list[str],
    backfill_candidates: list[str],
    backfill_attempted: list[str],
) -> dict[str, Any]:
    effective_members = [
        str(result.get("model"))
        for result in stage1_results
        if result.get("model") and stage1_record_is_valid(result)
    ]
    effective_valid_members = len(effective_members)
    normal_quorum_met = effective_valid_members >= config.min_valid_members
    low_quorum_used = (
        not normal_quorum_met
        and config.allow_low_quorum
        and effective_valid_members >= config.low_quorum_floor
    )
    return {
        "min_valid_members": config.min_valid_members,
        "target_valid_members": config.target_valid_members,
        "low_quorum_floor": config.low_quorum_floor,
        "effective_valid_members": effective_valid_members,
        "normal_quorum_met": normal_quorum_met,
        "low_quorum_used": low_quorum_used,
        "backfill_used": bool(backfill_attempted),
        "primary_members": list(primary_members),
        "candidate_source": "explicit" if config.backfill_members else "member_priority.filtered",
        "backfill_candidates": backfill_candidates,
        "backfill_attempted": backfill_attempted,
        "effective_stage1_members": effective_members,
    }


def classify_stage1_status(results: list[dict[str, Any]], min_valid_members: int = 6, chairman_model: str | None = None) -> str:
    chairman_in_members = chairman_model and any(r.get("model") == chairman_model for r in results)
    if chairman_in_members:
        chairman_results = [r for r in results if r.get("model") == chairman_model]
        non_chairman = [r for r in results if r.get("model") != chairman_model]
        chairman_ok = all(r.get("status") == "ok" for r in chairman_results)
        if chairman_ok:
            ok_count = sum(1 for r in non_chairman if r.get("status") == "ok") + len(chairman_results)
            total = len(non_chairman) + len(chairman_results)
        else:
            ok_count = sum(1 for r in non_chairman if r.get("status") == "ok")
            total = len(non_chairman)
    else:
        non_chairman = [r for r in results if r.get("model") != chairman_model] if chairman_model else results
        ok_count = sum(1 for r in non_chairman if r.get("status") == "ok")
        total = len(non_chairman)
    effective_min = min(min_valid_members, total)
    if ok_count == total and total > 0:
        return "ok"
    if ok_count >= effective_min:
        return "degraded_ok"
    return "failed"


def update_manifest_with_stage1_status(manifest: dict[str, Any], stage1_status: str) -> None:
    if stage1_status == "failed":
        manifest["status"] = "failed"


def record_stage_failures(manifest: dict[str, Any], records: list[dict[str, Any]]) -> None:
    for record in records:
        if record.get("status") not in ("ok", "degraded_ok"):
            failure = {
                "stage_record": record.get("label") or record.get("reviewer_label") or record.get("model"),
                "status": record.get("status"),
                "error": record.get("error") or f"non-ok status: {record.get('status')}",
                "expected_model": record.get("expected_model"),
                "actual_model": record.get("actual_model"),
            }
            manifest["failures"].append(failure)


def load_profile(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
