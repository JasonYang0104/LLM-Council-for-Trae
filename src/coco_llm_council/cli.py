from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .council import DEFAULT_CHAIRMAN, DEFAULT_MEMBERS, CouncilConfig, load_profile, run_full_council
from .html_export import export_html
from .model_selection import ModelChoice, recommend_model_choice, select_model_choice_interactively
from .models import doctor as runtime_doctor
from .models import get_models
from .store import ArtifactStore, resolve_store_base
from .subagents import inspect_subagents
from .utils import DEFAULT_TRAECLI, PROJECT_ROOT, read_text, run_command, utc_now
from .validation import validate_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coco-llm-council",
        description="Run an llm-council style 3-stage council over COCO/traecli.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit stable JSON output.")
    parser.add_argument("--runtime-command", default=DEFAULT_TRAECLI, help="Runtime command, default: traecli.")
    parser.add_argument("--runtime-cwd", help="Working directory for traecli subprocesses. Subagent mode defaults to this CLI project root.")
    parser.add_argument("--store", help="Run store base directory. Default: .coco-llm-council/runs in cwd.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_p = sub.add_parser("doctor", help="Check runtime health and local CLI setup.")
    doctor_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    doctor_p.set_defaults(func=cmd_doctor)

    models_p = sub.add_parser("models", help="List models reported by traecli.")
    models_p.add_argument("--recommend", action="store_true", help="Also include CLC's recommended council roster.")
    models_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    models_p.set_defaults(func=cmd_models)

    subagents_p = sub.add_parser("subagents", help="Inspect project-level fixed council subagent templates.")
    subagents_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    subagents_p.set_defaults(func=cmd_subagents)

    run_p = sub.add_parser("run", help="Run Stage 1, Stage 2, Stage 3, and HTML export.")
    run_p.add_argument("--input", required=True, help="Input markdown/text file.")
    run_p.add_argument("--members", help="Comma-separated model roster. If omitted, CLC asks you to choose from current COCO models.")
    run_p.add_argument("--chairman", help="Chairman model. If omitted with --members, default chairman is used.")
    run_p.add_argument("--profile", help="Optional JSON profile overriding members/chairman/provider.")
    run_p.add_argument("--default-models", action="store_true", help="Skip model selection and use CLC's default model suite.")
    run_p.add_argument("--run-id", help="Explicit run id. Default generated from UTC timestamp.")
    run_p.add_argument("--timeout", type=int, default=180, help="Per-model query timeout seconds.")
    run_p.add_argument("--no-yolo", action="store_true", help="Do not pass --yolo to traecli.")
    run_p.add_argument("--min-valid-members", type=int, default=4, help="Minimum valid members for quorum.")
    run_p.add_argument("--target-valid-members", type=int, default=5, help="Target valid members for quorum.")
    run_p.add_argument("--chairman-fallback", help="Comma-separated fallback chairman models.")
    run_p.add_argument("--member-mode", choices=["normal", "deep_research"], default="normal", help="Member execution mode.")
    run_p.add_argument("--skip-html", action="store_true", help="Skip automatic HTML export after Stage 3.")
    run_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    run_p.set_defaults(func=cmd_run)

    show_p = sub.add_parser("show", help="Show a run manifest.")
    show_p.add_argument("run_id")
    show_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    show_p.set_defaults(func=cmd_show)

    validate_p = sub.add_parser("validate", help="Validate artifact completeness and model consistency.")
    validate_p.add_argument("run_id")
    validate_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    validate_p.set_defaults(func=cmd_validate)

    export_p = sub.add_parser("export", help="Export an existing run.")
    export_p.add_argument("run_id")
    export_p.add_argument("--format", choices=["html"], default="html")
    export_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    export_p.set_defaults(func=cmd_export)

    replay_p = sub.add_parser("replay", help="Print a saved prompt without calling a model.")
    replay_p.add_argument("run_id")
    replay_p.add_argument("--stage", choices=["stage1", "stage2", "stage3", "html"], required=True)
    replay_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    replay_p.set_defaults(func=cmd_replay)

    raw_p = sub.add_parser("raw", help="Restricted raw escape hatch to COCO/traecli read-only commands.")
    raw_p.add_argument("--unsafe", action="store_true", help="Allow arbitrary traecli args.")
    raw_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    raw_p.add_argument("args", nargs=argparse.REMAINDER)
    raw_p.set_defaults(func=cmd_raw)

    return parser


def cmd_doctor(args: argparse.Namespace) -> int:
    health = runtime_doctor(args.runtime_command)
    payload = {
        "ok": health.ok,
        "cli": {"name": "coco-llm-council", "version": __version__},
        "runtime": {
            "command": health.command,
            "version": health.version,
            "doctor_exit_code": health.doctor_exit_code,
            "doctor": health.doctor,
        },
        "auth": {"required_by_cli": False, "source": "coco-local-config"},
        "models": {"count": len(health.models), "names": [m.get("name") for m in health.models]},
        "warnings": health.warnings,
        "errors": health.errors,
        "ignored_errors": health.ignored_errors,
    }
    return emit(payload, args.json_output, ok=health.ok, text=f"doctor {'ok' if health.ok else 'failed'}; models={len(health.models)}")


def cmd_models(args: argparse.Namespace) -> int:
    models = get_models(args.runtime_command)
    payload = {"count": len(models), "models": models}
    if args.recommend:
        choice = recommend_model_choice(models)
        payload["recommendation"] = {
            "members": choice.members,
            "chairman": choice.chairman,
            "source": choice.source,
        }
    if args.json_output:
        return emit(payload, True)
    text = f"{len(models)} models"
    if args.recommend:
        choice = payload["recommendation"]
        text += f"\nrecommended members={', '.join(choice['members'])}; chairman={choice['chairman']}"
    return emit(payload, False, text=text)


def cmd_subagents(args: argparse.Namespace) -> int:
    payload = inspect_subagents(PROJECT_ROOT, args.runtime_command)
    return emit(payload, args.json_output, ok=payload["ok"], text=json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    user_query = read_text(input_path)
    store_base = resolve_store_base(args.store)
    run_id = args.run_id or f"run-{utc_now().replace(':', '').replace('-', '').replace('Z', '')}"
    args.selected_model_choice = resolve_run_model_choice(args)
    config = build_config(args)
    store = ArtifactStore.create(store_base, run_id)
    manifest = asyncio.run(run_full_council(user_query, config, store))
    export_record = None
    if manifest.get("status") == "ok" and config.export_html:
        export_record = export_html(store)
        manifest = store.read_manifest()
    payload = {
        "run_id": run_id,
        "status": manifest.get("status"),
        "store": str(store.root),
        "manifest": str(store.root / "manifest.json"),
        "html": str(store.root / "html" / "index.html") if export_record else None,
        "warnings": manifest.get("warnings", []),
        "failures": manifest.get("failures", []),
        "recommendations": failure_recommendations(manifest),
    }
    return emit(payload, args.json_output, ok=manifest.get("status") == "ok", text=f"run {run_id} {manifest.get('status')} -> {store.root}")


def cmd_show(args: argparse.Namespace) -> int:
    store = ArtifactStore.open(resolve_store_base(args.store), args.run_id)
    manifest = store.read_manifest()
    return emit(manifest, args.json_output, ok=manifest.get("status") == "ok", text=json.dumps(summary_manifest(manifest), ensure_ascii=False, indent=2))


def cmd_validate(args: argparse.Namespace) -> int:
    store = ArtifactStore.open(resolve_store_base(args.store), args.run_id)
    result = validate_run(store)
    return emit(result, args.json_output, ok=result["status"] == "ok", text=json.dumps(result, ensure_ascii=False, indent=2))


def cmd_export(args: argparse.Namespace) -> int:
    store = ArtifactStore.open(resolve_store_base(args.store), args.run_id)
    if args.format != "html":
        raise ValueError("only html export is supported")
    record = export_html(store)
    payload = record | {"absolute_path": str(store.root / record["path"])}
    return emit(payload, args.json_output, text=f"html -> {payload['absolute_path']}")


def cmd_replay(args: argparse.Namespace) -> int:
    store = ArtifactStore.open(resolve_store_base(args.store), args.run_id)
    prompt_paths = {
        "stage1": "stage1/member.prompt.md",
        "stage2": "stage2/review.prompt.md",
        "stage3": "stage3/chairman.prompt.md",
        "html": "html/artifact.prompt.md",
    }
    relative = prompt_paths[args.stage]
    path = store.root / relative
    content = read_text(path)
    payload = {"run_id": args.run_id, "stage": args.stage, "path": relative, "content": content}
    return emit(payload, args.json_output, text=content)


def cmd_raw(args: argparse.Namespace) -> int:
    raw_args = list(args.args)
    if raw_args and raw_args[0] == "--":
        raw_args = raw_args[1:]
    if not raw_args:
        raise ValueError("raw requires arguments, e.g. raw -- models --json")
    safe_first = raw_args[0] in {"models", "doctor", "doc", "--version", "-v", "help"}
    if not safe_first and not args.unsafe:
        raise ValueError("raw is restricted to read-only commands unless --unsafe is passed")
    proc = run_command([args.runtime_command] + raw_args, timeout=120)
    payload = {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
    return proc.returncode


def build_config(args: argparse.Namespace) -> CouncilConfig:
    profile: dict[str, Any] = {}
    if getattr(args, "profile", None):
        profile = load_profile(Path(args.profile).expanduser().resolve())
    provider_mode = profile.get("provider_mode") or profile.get("provider", {}).get("mode") or "direct"
    member_agents = None
    chairman_agent = None
    if provider_mode == "subagent":
        members, member_agents = parse_subagent_members(profile.get("members") or [])
        chairman, chairman_agent = parse_subagent_chairman(profile.get("chairman") or {})
        runtime_cwd = str(Path(args.runtime_cwd).expanduser().resolve()) if args.runtime_cwd else str(PROJECT_ROOT)
    else:
        selected: ModelChoice | None = getattr(args, "selected_model_choice", None)
        members = profile.get("members") or (selected.members if selected else None) or split_csv(args.members or ",".join(DEFAULT_MEMBERS))
        chairman = profile.get("chairman") or (selected.chairman if selected else None) or args.chairman or DEFAULT_CHAIRMAN
        if any(isinstance(item, dict) for item in members):
            raise ValueError("direct provider members must be model-name strings")
        runtime_cwd = str(Path(args.runtime_cwd).expanduser().resolve()) if args.runtime_cwd else None
    chairman_fallback = None
    if getattr(args, "chairman_fallback", None):
        chairman_fallback = [m.strip() for m in args.chairman_fallback.split(",")]
    return CouncilConfig(
        members=members,
        chairman=chairman,
        provider_mode=provider_mode,
        runtime_command=args.runtime_command,
        runtime_cwd=runtime_cwd,
        query_timeout=args.timeout,
        export_html=not args.skip_html,
        member_agents=member_agents,
        chairman_agent=chairman_agent,
        use_yolo=not getattr(args, "no_yolo", False),
        min_valid_members=getattr(args, "min_valid_members", 4),
        target_valid_members=getattr(args, "target_valid_members", 5),
        chairman_fallback=chairman_fallback,
        member_mode=getattr(args, "member_mode", "normal"),
    )


def resolve_run_model_choice(args: argparse.Namespace) -> ModelChoice | None:
    if getattr(args, "profile", None):
        return None
    if getattr(args, "default_models", False):
        return ModelChoice(list(DEFAULT_MEMBERS), DEFAULT_CHAIRMAN, "static-default")
    if getattr(args, "members", None) or getattr(args, "chairman", None):
        return None
    if not sys.stdin.isatty():
        raise ValueError(
            "未指定模型，且当前不是可交互终端。请传 --default-models 使用默认模型套，"
            "或显式传 --members/--chairman，或使用 --profile。"
        )
    models = get_models(args.runtime_command)
    return select_model_choice_interactively(models, stdin=sys.stdin, stderr=sys.stderr)


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_subagent_members(raw_members: list[Any]) -> tuple[list[str], list[str | None]]:
    if not raw_members:
        raise ValueError("subagent profile requires members")
    models: list[str] = []
    agents: list[str | None] = []
    for item in raw_members:
        if not isinstance(item, dict):
            raise ValueError("subagent profile members must be objects with agent/model")
        agent = item.get("agent")
        model = item.get("model")
        if not agent or not model:
            raise ValueError("subagent profile member missing agent or model")
        agents.append(str(agent))
        models.append(str(model))
    return models, agents


def parse_subagent_chairman(raw_chairman: Any) -> tuple[str, str | None]:
    if not isinstance(raw_chairman, dict):
        raise ValueError("subagent profile chairman must be an object with agent/model")
    agent = raw_chairman.get("agent")
    model = raw_chairman.get("model")
    if not agent or not model:
        raise ValueError("subagent profile chairman missing agent or model")
    return str(model), str(agent)


def summary_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": manifest.get("run_id"),
        "status": manifest.get("status"),
        "members": manifest.get("config", {}).get("members"),
        "chairman": manifest.get("config", {}).get("chairman"),
        "aggregate_rankings": manifest.get("metadata", {}).get("aggregate_rankings"),
        "warnings": manifest.get("warnings"),
        "failures": manifest.get("failures"),
    }


def failure_recommendations(manifest: dict[str, Any]) -> list[str]:
    failures = manifest.get("failures") or []
    if not isinstance(failures, list):
        return []

    successful_models = successful_stage1_models(manifest)
    recommendations: list[str] = []
    for failure in failures:
        if isinstance(failure, dict):
            error = str(failure.get("error") or "")
            expected_model = failure.get("expected_model")
            stage_record = failure.get("stage_record")
        else:
            error = str(failure)
            expected_model = None
            stage_record = None
        lower_error = error.lower()
        if "context deadline exceeded" in lower_error or "timeout" in lower_error:
            recommendations.append(model_failure_hint(stage_record, expected_model, "超时", successful_models))
        elif "traecli result error" in lower_error:
            recommendations.append(model_failure_hint(stage_record, expected_model, "返回 traecli result error", successful_models))
        elif "model(s) not available" in lower_error:
            recommendations.append("模型不在当前 traecli models --json 列表中；请先运行 coco-llm-council models --recommend --json，再显式传 --members/--chairman。")
    return unique_strings(recommendations)


def successful_stage1_models(manifest: dict[str, Any]) -> list[str]:
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    stage1 = stages.get("stage1") if isinstance(stages, dict) else []
    if not isinstance(stage1, list):
        return []
    models: list[str] = []
    for item in stage1:
        if not isinstance(item, dict) or item.get("status") != "ok":
            continue
        model = item.get("model")
        if isinstance(model, str) and model not in models:
            models.append(model)
    return models


def model_failure_hint(stage_record: Any, expected_model: Any, reason: str, successful_models: list[str]) -> str:
    model_text = str(expected_model) if expected_model else "该模型"
    stage_text = f"{stage_record} " if stage_record else ""
    hint = f"{stage_text}{model_text} {reason}；可提高 --timeout，或替换/移除该模型后重跑。"
    if successful_models:
        hint += " 本次 Stage 1 已成功响应的模型: " + ", ".join(successful_models) + "。"
    return hint


def unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique


def emit(payload: Any, as_json: bool, ok: bool = True, text: str | None = None) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text if text is not None else payload)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except subprocess.TimeoutExpired as exc:
        payload = {"ok": False, "error": f"command timed out: {exc}"}
        return emit(payload, getattr(args, "json_output", False), ok=False, text=payload["error"])
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}
        return emit(payload, getattr(args, "json_output", False), ok=False, text=f"error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
