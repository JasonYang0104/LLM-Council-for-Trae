from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .council import parse_ranking_from_text, ranking_is_complete
from .models import get_models
from .provider import ModelCallResult, TraeCliProvider
from .utils import DEFAULT_TRAECLI, append_jsonl, utc_now, write_json, write_text


DEFAULT_CANDIDATES = [
    "DeepSeek-V4-Pro",
    "GPT-5.4",
    "openrouter-3o",
    "Kimi-K2.6",
    "MiniMax-M2.7",
    "Qwen3.6-Plus",
    "GPT-5.2",
    "DeepSeek-V4-Flash",
    "openrouter-1o",
    "Gemini-3.1-Pro-Preview",
    "GPT-5.5",
]


@dataclass(frozen=True)
class BenchmarkTask:
    name: str
    stage: str
    role: str
    prompt: str
    parse_kind: str = "non_empty"
    valid_labels: list[str] | None = None


def default_tasks() -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            name="short_judgment",
            stage="stage1",
            role="member",
            prompt=(
                "用简体中文回答。判断：本地端侧 AI 推理在未来 12 个月会不会成为消费级硬件的主要卖点？"
                "要求：只输出 3 行，分别以“结论：”“理由：”“风险：”开头。"
            ),
        ),
        BenchmarkTask(
            name="structured_json",
            stage="stage1",
            role="member",
            prompt=(
                "只输出 JSON，不要 Markdown。字段必须是 conclusion、signals、risks。"
                "signals 和 risks 都是字符串数组，各 2 项。主题：2026 年本地 AI 消费硬件机会。"
            ),
            parse_kind="json_object",
        ),
        BenchmarkTask(
            name="stage2_ranking",
            stage="stage2",
            role="reviewer",
            prompt=(
                "你正在评估同一个问题的三个匿名回答。\n\n"
                "用户问题：本地 AI 推理会如何影响消费电子？\n\n"
                "Response A:\n只说芯片更快，但没有讨论用户场景。\n\n"
                "Response B:\n讨论隐私、离线可用、成本、开发者生态，并指出短期受功耗和模型体积限制。\n\n"
                "Response C:\n认为所有应用都会立刻迁移到本地，缺少证据。\n\n"
                "先简评每个回答，最后必须严格输出：\n"
                "FINAL RANKING:\n1. Response B\n2. Response A\n3. Response C"
            ),
            parse_kind="ranking",
            valid_labels=["Response A", "Response B", "Response C"],
        ),
        BenchmarkTask(
            name="stage3_synthesis",
            stage="stage3",
            role="chairman",
            prompt=(
                "你是 LLM Council 的主席。请综合下面材料，输出简体中文最终结论，必须包含“结论”“关键证据”“保留分歧”。\n\n"
                "原始问题：2026 年本地 AI 推理是否会成为消费硬件核心卖点？\n\n"
                "阶段 1 回答摘要：\n"
                "- 模型 A：看好隐私和低延迟，但担心功耗。\n"
                "- 模型 B：认为会先在高端手机、PC、智能眼镜出现，不会马上普及到低端设备。\n"
                "- 模型 C：强调开发者生态和系统级入口比峰值算力更关键。\n\n"
                "阶段 2 排序：B 第一，C 第二，A 第三。"
            ),
            parse_kind="chairman_markers",
        ),
    ]


def parse_ok(task: BenchmarkTask, response: str) -> bool:
    text = response.strip()
    if not text:
        return False
    if task.parse_kind == "json_object":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, dict)
    if task.parse_kind == "ranking":
        labels = set(task.valid_labels or [])
        return ranking_is_complete(parse_ranking_from_text(text), labels)
    if task.parse_kind == "chairman_markers":
        return all(marker in text for marker in ["结论", "关键证据", "保留分歧"])
    return True


def benchmark_record_from_call(
    task: BenchmarkTask,
    model: str,
    repeat_index: int,
    call: ModelCallResult,
    *,
    latency_seconds: float,
) -> dict[str, Any]:
    return {
        "captured_at": utc_now(),
        "task": task.name,
        "stage": task.stage,
        "role": task.role,
        "repeat_index": repeat_index,
        "expected_model": model,
        "model": model,
        "actual_model": call.actual_model,
        "status": call.status,
        "latency_seconds": round(latency_seconds, 2),
        "response_chars": len(call.response),
        "parse_ok": parse_ok(task, call.response),
        "error": call.error,
        "session_id": call.session_id,
        "stdout_path": call.stdout_path,
        "stderr_path": call.stderr_path,
    }


def scorecard_rows(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        model = str(record.get("model") or record.get("expected_model") or "")
        if model:
            by_model.setdefault(model, []).append(record)

    rows: list[dict[str, str]] = []
    for model, model_records in sorted(by_model.items()):
        latencies = [float(r["latency_seconds"]) for r in model_records if isinstance(r.get("latency_seconds"), (int, float))]
        ok_records = [r for r in model_records if r.get("status") == "ok"]
        parse_ok_records = [r for r in model_records if r.get("parse_ok") is True]
        mismatch_count = sum(1 for r in model_records if r.get("actual_model") and r.get("actual_model") != r.get("expected_model"))
        role_rates = {
            role: _rate([r for r in model_records if r.get("role") == role], lambda item: item.get("status") == "ok" and item.get("parse_ok") is True)
            for role in ["member", "reviewer", "chairman"]
        }
        rows.append(
            {
                "model": model,
                "samples": str(len(model_records)),
                "success_rate": f"{len(ok_records) / len(model_records):.2f}" if model_records else "0.00",
                "parse_ok_rate": f"{len(parse_ok_records) / len(model_records):.2f}" if model_records else "0.00",
                "member_ok_parse_rate": f"{role_rates['member']:.2f}",
                "reviewer_ok_parse_rate": f"{role_rates['reviewer']:.2f}",
                "chairman_ok_parse_rate": f"{role_rates['chairman']:.2f}",
                "p50_latency_seconds": f"{statistics.median(latencies):.2f}" if latencies else "",
                "p95_latency_seconds": f"{percentile(latencies, 0.95):.2f}" if latencies else "",
                "max_latency_seconds": f"{max(latencies):.2f}" if latencies else "",
                "timeout_count": str(sum(1 for r in model_records if str(r.get("error") or "").lower() == "timeout")),
                "empty_count": str(sum(1 for r in model_records if r.get("status") != "ok" and int(r.get("response_chars") or 0) == 0)),
                "model_mismatch_count": str(mismatch_count),
                "failed_count": str(sum(1 for r in model_records if r.get("status") != "ok")),
            }
        )
    return rows


def recommend_rosters_from_scorecard(rows: list[dict[str, str]]) -> dict[str, Any]:
    def f(row: dict[str, str], key: str) -> float:
        try:
            return float(row.get(key) or 0)
        except ValueError:
            return 0.0

    viable_members = [
        row for row in rows
        if f(row, "member_ok_parse_rate") >= 1.0
        and f(row, "success_rate") >= 0.75
        and row.get("model_mismatch_count") == "0"
    ]
    viable_members.sort(key=lambda row: (f(row, "p95_latency_seconds"), row["model"]))

    fast_default = [row["model"] for row in viable_members if f(row, "p95_latency_seconds") <= 60][:3]
    analysis_default = [row["model"] for row in viable_members if f(row, "p95_latency_seconds") <= 120][:4]
    research_stress = [row["model"] for row in viable_members][:6]

    viable_chairmen = [
        row for row in rows
        if f(row, "chairman_ok_parse_rate") >= 1.0
        and f(row, "success_rate") >= 0.75
        and row.get("model_mismatch_count") == "0"
    ]
    viable_chairmen.sort(key=lambda row: (-f(row, "chairman_ok_parse_rate"), f(row, "p95_latency_seconds"), row["model"]))
    chairman = viable_chairmen[0]["model"] if viable_chairmen else None

    return {
        "fast_default_members": fast_default,
        "analysis_default_members": analysis_default,
        "research_stress_members": research_stress,
        "chairman": chairman,
        "chairman_candidates": [row["model"] for row in viable_chairmen[:3]],
    }


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output).expanduser().resolve()
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_models = get_models(args.runtime_command)
    available = {m.get("name") for m in runtime_models if isinstance(m.get("name"), str)}
    candidates = [model for model in split_csv(args.models) if model in available]
    unavailable = [model for model in split_csv(args.models) if model not in available]
    tasks = default_tasks()
    if args.tasks:
        selected = set(split_csv(args.tasks))
        tasks = [task for task in tasks if task.name in selected]

    write_json(output_dir / "runtime-models.json", runtime_models)
    write_json(output_dir / "benchmark-config.json", {
        "created_at": utc_now(),
        "runtime_command": args.runtime_command,
        "timeout": args.timeout,
        "repeats": args.repeats,
        "concurrency": args.concurrency,
        "models": candidates,
        "unavailable_models": unavailable,
        "tasks": [task.__dict__ for task in tasks],
    })

    provider = TraeCliProvider(args.runtime_command, args.timeout)
    semaphore = asyncio.Semaphore(args.concurrency)
    results_path = output_dir / "results.jsonl"
    if results_path.exists() and not args.append:
        results_path.unlink()

    async def one_call(model: str, task: BenchmarkTask, repeat_index: int) -> dict[str, Any]:
        async with semaphore:
            start = time.perf_counter()
            call = await provider.query_model(
                model=model,
                prompt=task.prompt,
                run_id=f"model-benchmark-{output_dir.name}",
                stage=task.stage,
                label=f"{model}-{task.name}-{repeat_index}",
                output_dir=raw_dir / model / task.name / str(repeat_index),
            )
            record = benchmark_record_from_call(
                task,
                model,
                repeat_index,
                call,
                latency_seconds=time.perf_counter() - start,
            )
            append_jsonl(results_path, record)
            return record

    records = await asyncio.gather(*[
        one_call(model, task, repeat_index)
        for model in candidates
        for task in tasks
        for repeat_index in range(1, args.repeats + 1)
    ])
    rows = scorecard_rows(records)
    write_scorecard(output_dir / "scorecard.csv", rows)
    rosters = recommend_rosters_from_scorecard(rows)
    write_json(output_dir / "recommended-rosters.json", rosters)
    write_readme(output_dir, rows, rosters, unavailable)
    return {
        "output_dir": str(output_dir),
        "records": len(records),
        "scorecard": str(output_dir / "scorecard.csv"),
        "recommended_rosters": rosters,
        "unavailable_models": unavailable,
    }


def write_scorecard(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "model",
        "samples",
        "success_rate",
        "parse_ok_rate",
        "member_ok_parse_rate",
        "reviewer_ok_parse_rate",
        "chairman_ok_parse_rate",
        "p50_latency_seconds",
        "p95_latency_seconds",
        "max_latency_seconds",
        "timeout_count",
        "empty_count",
        "model_mismatch_count",
        "failed_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(output_dir: Path, rows: list[dict[str, str]], rosters: dict[str, Any], unavailable: list[str]) -> None:
    lines = [
        "# LCT 模型基准测试",
        "",
        f"生成时间：`{utc_now()}`",
        "",
        "## 产物",
        "",
        "- `benchmark-config.json`：测试配置和任务定义。",
        "- `runtime-models.json`：本次 `traecli models --json` 快照。",
        "- `results.jsonl`：逐次调用结果。",
        "- `scorecard.csv`：按模型聚合的稳定性、格式和时延指标。",
        "- `recommended-rosters.json`：机器生成的候选 roster。",
        "- `raw/`：每次 `traecli` 调用的 stream 和 stderr 证据。",
        "",
        "## 机器推荐",
        "",
        f"- fast_default_members: `{', '.join(rosters.get('fast_default_members') or []) or '无'}`",
        f"- analysis_default_members: `{', '.join(rosters.get('analysis_default_members') or []) or '无'}`",
        f"- research_stress_members: `{', '.join(rosters.get('research_stress_members') or []) or '无'}`",
        f"- chairman: `{rosters.get('chairman') or '无'}`",
        "",
    ]
    if unavailable:
        lines.extend(["## 本次不可用候选", "", *[f"- `{model}`" for model in unavailable], ""])
    lines.extend(["## Scorecard", "", "| model | samples | success | parse | p95 latency | failed |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in rows:
        lines.append(
            f"| `{row['model']}` | {row['samples']} | {row['success_rate']} | {row['parse_ok_rate']} | "
            f"{row['p95_latency_seconds']} | {row['failed_count']} |"
        )
    write_text(output_dir / "README.md", "\n".join(lines) + "\n")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def _rate(records: list[dict[str, Any]], predicate: Any) -> float:
    if not records:
        return 0.0
    return sum(1 for record in records if predicate(record)) / len(records)


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run traecli model benchmark tasks for LCT roster selection.")
    parser.add_argument("--output", default="docs/model-benchmark-20260525")
    parser.add_argument("--models", default=",".join(DEFAULT_CANDIDATES))
    parser.add_argument("--tasks", help="Comma-separated task names. Default: all built-in tasks.")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--runtime-command", default=DEFAULT_TRAECLI)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--score-only", help="Regenerate scorecard/recommendations from an existing results.jsonl.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.score_only:
        output_dir = Path(args.output).expanduser().resolve()
        records = load_jsonl(Path(args.score_only).expanduser().resolve())
        rows = scorecard_rows(records)
        rosters = recommend_rosters_from_scorecard(rows)
        write_scorecard(output_dir / "scorecard.csv", rows)
        write_json(output_dir / "recommended-rosters.json", rosters)
        write_readme(output_dir, rows, rosters, [])
        payload = {"output_dir": str(output_dir), "records": len(records), "recommended_rosters": rosters}
    else:
        payload = asyncio.run(run_benchmark(args))
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"benchmark records={payload['records']} -> {payload['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
