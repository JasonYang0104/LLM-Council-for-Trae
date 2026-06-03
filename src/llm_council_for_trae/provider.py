from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import DEFAULT_TRAECLI, slugify, utc_now, write_json, write_text


ALWAYS_FORBIDDEN_TOOLS = [
    "Skill",
    "Agent",
    "TaskCreate",
    "TaskList",
    "TaskGet",
    "TaskUpdate",
    "TodoWrite",
]

WORKSPACE_WRITE_TOOLS = ["Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"]
WORKSPACE_READ_TOOLS = ["Read", "Glob", "Grep", "LS"]
WEB_TOOLS = ["WebSearch", "WebFetch"]

TOOL_MODE_ALLOWED: dict[str, list[str]] = {
    "answer_only": [],
    "search_enabled": WEB_TOOLS,
    "workspace_enabled": WORKSPACE_READ_TOOLS + WEB_TOOLS,
    "subagent_invocation": ["Agent"],
}


def tool_policy_for_mode(member_tool_mode: str) -> tuple[list[str], list[str]]:
    if member_tool_mode not in TOOL_MODE_ALLOWED:
        raise ValueError(f"unknown member_tool_mode: {member_tool_mode}")
    allowed = list(TOOL_MODE_ALLOWED[member_tool_mode])
    if member_tool_mode == "subagent_invocation":
        denied = [tool for tool in ALWAYS_FORBIDDEN_TOOLS if tool != "Agent"]
        denied += WORKSPACE_WRITE_TOOLS + WORKSPACE_READ_TOOLS + WEB_TOOLS
    else:
        denied = ALWAYS_FORBIDDEN_TOOLS + WORKSPACE_WRITE_TOOLS
    if member_tool_mode == "answer_only":
        denied += WORKSPACE_READ_TOOLS + WEB_TOOLS
    elif member_tool_mode == "search_enabled":
        denied += WORKSPACE_READ_TOOLS
    return allowed, list(dict.fromkeys(denied))


def forbidden_tool_calls_for_mode(tool_calls: list[dict[str, Any]], member_tool_mode: str) -> list[dict[str, Any]]:
    allowed, disallowed = tool_policy_for_mode(member_tool_mode)
    allowed_set = set(allowed)
    disallowed_set = set(disallowed)
    forbidden: list[dict[str, Any]] = []
    for call in tool_calls:
        name = call.get("name")
        if not isinstance(name, str) or not name:
            forbidden.append(call)
            continue
        if name in disallowed_set or name not in allowed_set:
            forbidden.append(call)
    return forbidden


@dataclass
class ModelCallResult:
    expected_model: str
    actual_model: str | None
    response: str
    status: str
    session_id: str
    command: list[str]
    exit_code: int
    stdout_path: str
    stderr_path: str
    runtime_cwd: str | None = None
    agent: str | None = None
    subagent_invocation: dict[str, Any] | None = None
    copied_session_files: dict[str, str] = field(default_factory=dict)
    raw_model_markers: list[str] = field(default_factory=list)
    error: str | None = None
    permission_mode: str | None = None
    member_tool_mode: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    forbidden_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_budget_status: str = "ok"
    assistant_content_chars_total: int = 0
    last_assistant_content_chars: int = 0
    raw_partial_recoverable: bool = False
    tool_calls_count: int = 0
    turns_count: int = 0
    retried: bool = False
    retry_error: str | None = None
    termination: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "expected_model": self.expected_model,
            "actual_model": self.actual_model,
            "response_chars": len(self.response),
            "status": self.status,
            "session_id": self.session_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "runtime_cwd": self.runtime_cwd,
            "agent": self.agent,
            "subagent_invocation": self.subagent_invocation,
            "copied_session_files": self.copied_session_files,
            "raw_model_markers": self.raw_model_markers,
            "error": self.error,
            "permission_mode": self.permission_mode,
            "member_tool_mode": self.member_tool_mode,
            "allowed_tools": self.allowed_tools,
            "disallowed_tools": self.disallowed_tools,
            "forbidden_tool_calls": self.forbidden_tool_calls,
            "tool_calls": self.tool_calls,
            "tool_budget_status": self.tool_budget_status,
            "assistant_content_chars_total": self.assistant_content_chars_total,
            "last_assistant_content_chars": self.last_assistant_content_chars,
            "raw_partial_recoverable": self.raw_partial_recoverable,
            "tool_calls_count": self.tool_calls_count,
            "turns_count": self.turns_count,
            "retried": self.retried,
            "retry_error": self.retry_error,
            "termination": self.termination,
        }


async def monitor_stream_for_budget(
    stream: AsyncIterator[bytes],
    tool_limit: int,
) -> tuple[list[bytes], int, bool]:
    collected: list[bytes] = []
    tool_calls_seen = 0
    budget_exceeded = False

    try:
        async for raw_line in stream:
            collected.append(raw_line)
            if budget_exceeded:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                message = event.get("message")
                if isinstance(message, dict):
                    for _tc in message.get("tool_calls") or []:
                        tool_calls_seen += 1
                if tool_calls_seen > tool_limit:
                    budget_exceeded = True
    except Exception:
        pass

    return collected, tool_calls_seen, budget_exceeded


class TraeCliProvider:
    def __init__(
        self,
        runtime_command: str = DEFAULT_TRAECLI,
        query_timeout: int = 180,
        runtime_cwd: Path | None = None,
        use_yolo: bool = False,
        member_tool_mode: str = "search_enabled",
    ):
        self.runtime_command = os.environ.get("LLM_COUNCIL_FOR_TRAE_TRAECLI", runtime_command)
        self.query_timeout = query_timeout
        self.runtime_cwd = runtime_cwd
        self.use_yolo = use_yolo
        self.member_tool_mode = member_tool_mode
        self.allowed_tools, self.disallowed_tools = tool_policy_for_mode(member_tool_mode)
        self.explore_tool_limit: int = 16
        self.explore_turn_limit: int = 12
        self.deliver_tool_limit: int = 45
        self.deliver_turn_limit: int = 24

    def _build_command(
        self,
        model: str,
        prompt: str,
        run_id: str,
        stage: str,
        label: str,
        session_id: str,
        query_timeout: int | float | None = None,
    ) -> list[str]:
        timeout_seconds = query_timeout if query_timeout is not None else self.query_timeout
        cmd = [
            self.runtime_command,
            "-p",
            prompt,
            "-c",
            f"model.name={model}",
            "--output-format",
            "stream-json",
            "--query-timeout",
            f"{timeout_seconds}s",
            "--session-id",
            session_id,
        ]
        for tool in self.allowed_tools:
            cmd.extend(["--allowed-tool", tool])
        for tool in self.disallowed_tools:
            cmd.extend(["--disallowed-tool", tool])
        if self.use_yolo:
            cmd.append("--yolo")
        return cmd

    async def query_model(
        self,
        *,
        model: str,
        prompt: str,
        run_id: str,
        stage: str,
        label: str,
        output_dir: Path,
        agent: str | None = None,
        query_timeout: int | float | None = None,
    ) -> ModelCallResult:
        result = await self._query_model_once(
            model=model, prompt=prompt, run_id=run_id,
            stage=stage, label=label, output_dir=output_dir, agent=agent,
            query_timeout=query_timeout,
        )
        is_runtime_error = (
            result.status == "failed"
            and result.exit_code != 0
            and result.error is not None
            and "dropped_tool_budget" not in result.error
            and result.error != "timeout"
        )
        if is_runtime_error:
            first_error = result.error
            await asyncio.sleep(10)
            result = await self._query_model_once(
                model=model, prompt=prompt, run_id=run_id,
                stage=stage, label=label, output_dir=output_dir, agent=agent,
                query_timeout=query_timeout,
            )
            result.retried = True
            result.retry_error = first_error
            write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
        return result

    async def _query_model_once(
        self,
        *,
        model: str,
        prompt: str,
        run_id: str,
        stage: str,
        label: str,
        output_dir: Path,
        agent: str | None = None,
        query_timeout: int | float | None = None,
    ) -> ModelCallResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        session_id = slugify(f"{run_id}-{stage}-{label}")
        stream_path = output_dir / f"{label}.traecli.stream.jsonl"
        stderr_path = output_dir / f"{label}.traecli.stderr.log"
        runtime_prompt = f"@{agent} {prompt}" if agent else prompt
        effective_timeout = query_timeout if query_timeout is not None else self.query_timeout
        cmd = self._build_command(model, runtime_prompt, run_id, stage, label, session_id, query_timeout=effective_timeout)
        permission_mode = "bypass_permissions" if self.use_yolo else "default"

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
            limit=10 * 1024 * 1024,
            start_new_session=os.name != "nt",
        )
        budget_killed = False
        termination: dict[str, Any] = {}
        try:
            collected, _stream_tool_calls, budget_exceeded = await asyncio.wait_for(
                monitor_stream_for_budget(proc.stdout, self.deliver_tool_limit),
                timeout=effective_timeout + 30,
            )
            if budget_exceeded:
                budget_killed = True
                termination = termination_with_reason(await terminate_process_tree(proc), "tool_budget")
            try:
                await proc.wait()
            except ProcessLookupError:
                pass
            stdout_b = b"".join(collected)
            stderr_b = await proc.stderr.read()
        except asyncio.TimeoutError:
            termination = termination_with_reason(await terminate_process_tree(proc), "timeout")
            stdout_b = b""
            stderr_b = b""
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace") + "\nTimed out while waiting for traecli."
            write_text(stream_path, stdout)
            write_text(stderr_path, stderr)
            result = ModelCallResult(
                expected_model=model,
                actual_model=None,
                response="",
                status="failed",
                session_id=session_id,
                command=safe_command(cmd),
                exit_code=-1,
                stdout_path=stream_path.name,
                stderr_path=stderr_path.name,
                runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
                agent=agent,
                subagent_invocation=missing_subagent_invocation(agent),
                error="timeout",
                permission_mode=permission_mode,
                member_tool_mode=self.member_tool_mode,
                allowed_tools=self.allowed_tools,
                disallowed_tools=self.disallowed_tools,
                termination=termination,
            )
            write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
            return result
        except asyncio.CancelledError:
            termination = termination_with_reason(await terminate_process_tree(proc), "cancelled")
            write_text(stream_path, "")
            write_text(stderr_path, "Cancelled while waiting for traecli.\n")
            result = ModelCallResult(
                expected_model=model,
                actual_model=None,
                response="",
                status="failed",
                session_id=session_id,
                command=safe_command(cmd),
                exit_code=-1,
                stdout_path=stream_path.name,
                stderr_path=stderr_path.name,
                runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
                agent=agent,
                subagent_invocation=missing_subagent_invocation(agent),
                error="cancelled",
                permission_mode=permission_mode,
                member_tool_mode=self.member_tool_mode,
                allowed_tools=self.allowed_tools,
                disallowed_tools=self.disallowed_tools,
                termination=termination,
            )
            write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
            raise

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        write_text(stream_path, stdout)
        write_text(stderr_path, stderr)

        parsed = parse_stream_json(stdout, expected_agent=agent)
        actual_model = parsed["actual_model"]
        response = parsed["response"]
        raw_model_markers = parsed["raw_model_markers"]
        subagent_invocation = parsed["subagent_invocation"]
        tool_calls_count = parsed.get("tool_calls_count", 0)
        tool_calls = parsed.get("tool_calls", [])
        turns_count = parsed.get("turns_count", 0)
        forbidden_tool_calls = forbidden_tool_calls_for_mode(tool_calls, self.member_tool_mode)
        status = "ok"
        error = None
        if proc.returncode != 0:
            status = "failed"
            error = stderr.strip() or parsed.get("error") or f"traecli exited {proc.returncode}"
        elif not response.strip():
            status = "failed"
            error = "empty model response"
        elif actual_model != model:
            status = "failed"
            error = f"expected model {model}, actual model {actual_model or 'unknown'}"
        elif agent and not subagent_invocation.get("ok"):
            status = "failed"
            error = f"expected subagent {agent} invocation evidence, got {subagent_invocation}"
        if forbidden_tool_calls:
            status = "failed"
            names = ", ".join(call.get("name", "unknown") for call in forbidden_tool_calls)
            error = f"tool_contaminated: forbidden tool call(s): {names}"

        copied = copy_traecli_session_files(session_id, output_dir, label)
        tool_budget_status = "ok"
        if budget_killed or tool_calls_count > self.deliver_tool_limit or turns_count > self.deliver_turn_limit:
            tool_budget_status = "dropped_tool_budget"
        elif tool_calls_count > self.explore_tool_limit or turns_count > self.explore_turn_limit:
            tool_budget_status = "near_limit"
        if budget_killed and status == "ok":
            status = "failed"
            error = f"dropped_tool_budget: killed after {tool_calls_count} tool calls (limit {self.deliver_tool_limit})"
        result = ModelCallResult(
            expected_model=model,
            actual_model=actual_model,
            response=response,
            status=status,
            session_id=session_id,
            command=safe_command(cmd),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout_path=stream_path.name,
            stderr_path=stderr_path.name,
            runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
            agent=agent,
            subagent_invocation=subagent_invocation,
            copied_session_files=copied,
            raw_model_markers=raw_model_markers,
            error=error,
            permission_mode=permission_mode,
            member_tool_mode=self.member_tool_mode,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            forbidden_tool_calls=forbidden_tool_calls,
            tool_calls=tool_calls,
            tool_budget_status=tool_budget_status,
            assistant_content_chars_total=parsed.get("assistant_content_chars_total", 0),
            last_assistant_content_chars=parsed.get("last_assistant_content_chars", 0),
            raw_partial_recoverable=parsed.get("raw_partial_recoverable", False),
            tool_calls_count=tool_calls_count,
            turns_count=turns_count,
            termination=termination,
        )
        write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
        return result


def safe_command(cmd: list[str]) -> list[str]:
    safe = list(cmd)
    if len(safe) > 2:
        safe[2] = f"<prompt {len(cmd[2])} chars>"
    return safe


async def terminate_process_tree(proc: Any, grace_seconds: float = 2.0) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "pid": getattr(proc, "pid", None),
        "pgid": None,
        "terminated": False,
        "termination_reason": None,
        "signals_sent": [],
        "final_returncode": getattr(proc, "returncode", None),
    }
    if getattr(proc, "returncode", None) is not None:
        return metadata
    if os.name != "nt" and getattr(proc, "pid", None):
        try:
            pgid = os.getpgid(proc.pid)
            metadata["pgid"] = pgid
            os.killpg(pgid, signal.SIGTERM)
            metadata["signals_sent"].append("SIGTERM")
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
            metadata["terminated"] = True
            metadata["final_returncode"] = getattr(proc, "returncode", None)
            return metadata
        except ProcessLookupError:
            metadata["terminated"] = True
            metadata["final_returncode"] = getattr(proc, "returncode", None)
            return metadata
        except asyncio.TimeoutError:
            try:
                os.killpg(pgid, signal.SIGKILL)
                metadata["signals_sent"].append("SIGKILL")
            except ProcessLookupError:
                metadata["terminated"] = True
                metadata["final_returncode"] = getattr(proc, "returncode", None)
                return metadata
            try:
                await proc.wait()
            except ProcessLookupError:
                pass
            metadata["terminated"] = True
            metadata["final_returncode"] = getattr(proc, "returncode", None)
            return metadata
        except Exception:
            pass
    try:
        proc.kill()
        metadata["signals_sent"].append("kill")
    except ProcessLookupError:
        metadata["terminated"] = True
        metadata["final_returncode"] = getattr(proc, "returncode", None)
        return metadata
    try:
        await proc.wait()
    except ProcessLookupError:
        pass
    metadata["terminated"] = True
    metadata["final_returncode"] = getattr(proc, "returncode", None)
    return metadata


def termination_with_reason(termination: dict[str, Any], reason: str) -> dict[str, Any]:
    if not termination:
        termination = {}
    return termination | {"termination_reason": termination.get("termination_reason") or reason}


def parse_stream_json(stdout: str, expected_agent: str | None = None) -> dict[str, Any]:
    assistant_messages: list[str] = []
    result_text: str | None = None
    actual_model: str | None = None
    top_level_model: str | None = None
    subagent_source_models: list[str] = []
    assistant_source_models: list[str] = []
    agent_tool_call_ids: list[str] = []
    agent_tool_call_subagent_types: list[str] = []
    agent_tool_result_ids: list[str] = []
    subagent_message_tool_ids: list[str] = []
    markers: list[str] = []
    error: str | None = None
    tool_calls_count: int = 0
    turns_count: int = 0
    tool_calls: list[dict[str, Any]] = []

    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        model = event.get("model")
        if isinstance(model, str):
            markers.append(model)
            if top_level_model is None:
                top_level_model = model
        updates = event.get("updates")
        if isinstance(updates, dict):
            model_name = updates.get("model_name")
            if isinstance(model_name, str):
                markers.append(model_name)
                actual_model = actual_model or model_name
        if event.get("type") == "assistant":
            turns_count += 1
            message = event.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                assistant_messages.append(message["content"])
            if isinstance(message, dict):
                for tool_call in message.get("tool_calls") or []:
                    tool_calls_count += 1
                    function = tool_call.get("function") if isinstance(tool_call, dict) else None
                    if isinstance(function, dict):
                        tool_id = tool_call.get("id") if isinstance(tool_call, dict) else None
                        tool_name = function.get("name")
                        arguments = function.get("arguments")
                        tool_calls.append(
                            {
                                "id": tool_id if isinstance(tool_id, str) else "",
                                "name": tool_name if isinstance(tool_name, str) else "",
                                "arguments": arguments[:500] if isinstance(arguments, str) else "",
                                "turn_index": turns_count,
                            }
                        )
                    if not isinstance(function, dict) or function.get("name") != "Agent":
                        continue
                    tool_id = tool_call.get("id")
                    if isinstance(tool_id, str):
                        agent_tool_call_ids.append(tool_id)
                    arguments = function.get("arguments")
                    if isinstance(arguments, str):
                        try:
                            parsed_arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            parsed_arguments = {}
                        subagent_type = parsed_arguments.get("subagent_type")
                        if isinstance(subagent_type, str):
                            agent_tool_call_subagent_types.append(subagent_type)
            extra = message.get("extra") if isinstance(message, dict) else None
            if isinstance(extra, dict):
                source_model = extra.get("_source_model")
                if isinstance(source_model, str):
                    markers.append(source_model)
                    assistant_source_models.append(source_model)
                    if event.get("parent_tool_use_id"):
                        subagent_source_models.append(source_model)
                        parent_tool_use_id = event.get("parent_tool_use_id")
                        if isinstance(parent_tool_use_id, str):
                            subagent_message_tool_ids.append(parent_tool_use_id)
        if event.get("subtype") == "tool_result" and event.get("tool_name") == "Agent":
            tool_use_id = event.get("tool_use_id")
            if isinstance(tool_use_id, str):
                agent_tool_result_ids.append(tool_use_id)
        if event.get("type") == "result":
            if isinstance(event.get("result"), str):
                result_text = event["result"]
            if event.get("is_error"):
                error = event.get("result") if isinstance(event.get("result"), str) else "traecli result error"

    actual_model = (
        subagent_source_models[-1]
        if subagent_source_models
        else (top_level_model or (assistant_source_models[-1] if assistant_source_models else None))
    )
    response = result_text or (assistant_messages[-1] if assistant_messages else "")
    assistant_content_chars_total = sum(len(msg) for msg in assistant_messages)
    last_assistant_content_chars = len(assistant_messages[-1]) if assistant_messages else 0
    raw_partial_recoverable = assistant_content_chars_total > 0 and (not response.strip() or error is not None)
    subagent_invocation = {
        "required": bool(expected_agent),
        "expected_agent": expected_agent,
        "tool_call_seen": bool(agent_tool_call_ids),
        "tool_call_ids": agent_tool_call_ids,
        "tool_call_subagent_types": sorted(set(agent_tool_call_subagent_types)),
        "tool_result_seen": bool(agent_tool_result_ids),
        "tool_result_ids": agent_tool_result_ids,
        "subagent_message_seen": bool(subagent_message_tool_ids),
        "subagent_message_tool_ids": subagent_message_tool_ids,
        "subagent_source_models": subagent_source_models,
    }
    if expected_agent:
        subagent_invocation["ok"] = (
            expected_agent in agent_tool_call_subagent_types
            and bool(set(agent_tool_call_ids) & set(agent_tool_result_ids))
            and bool(set(agent_tool_call_ids) & set(subagent_message_tool_ids))
            and bool(subagent_source_models)
        )
    else:
        subagent_invocation["ok"] = True
    return {
        "actual_model": actual_model,
        "response": response.strip(),
        "raw_model_markers": sorted(set(markers)),
        "subagent_invocation": subagent_invocation,
        "error": error,
        "tool_calls_count": tool_calls_count,
        "turns_count": turns_count,
        "tool_calls": tool_calls,
        "assistant_content_chars_total": assistant_content_chars_total,
        "last_assistant_content_chars": last_assistant_content_chars,
        "raw_partial_recoverable": raw_partial_recoverable,
    }


def missing_subagent_invocation(expected_agent: str | None) -> dict[str, Any]:
    return {
        "required": bool(expected_agent),
        "expected_agent": expected_agent,
        "tool_call_seen": False,
        "tool_call_ids": [],
        "tool_call_subagent_types": [],
        "tool_result_seen": False,
        "tool_result_ids": [],
        "subagent_message_seen": False,
        "subagent_message_tool_ids": [],
        "subagent_source_models": [],
        "ok": not bool(expected_agent),
    }


def copy_traecli_session_files(session_id: str, output_dir: Path, label: str) -> dict[str, str]:
    session_root = Path.home() / "Library" / "Caches" / "coco" / "sessions" / session_id
    copied: dict[str, str] = {}
    for name in ("session.json", "session.log", "events.jsonl", "traces.jsonl"):
        src = session_root / name
        if src.exists():
            dest = output_dir / f"{label}.traecli.{name}"
            dest.write_bytes(src.read_bytes())
            copied[name] = dest.name
    return copied
