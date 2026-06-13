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
from .model_selection import DEFAULT_MEMBER_COUNT, ModelChoice, normalize_user_model_selection, recommend_model_choice, select_model_choice_interactively
from .models import doctor as runtime_doctor
from .models import get_models
from .runtime import RunLease
from .store import ArtifactStore, resolve_store_base
from .subagents import inspect_subagents
from .utils import DEFAULT_TRAECLI, PROJECT_ROOT, read_text, run_command, utc_now
from .validation import validate_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-council-for-trae",
        description="Run an llm-council style 3-stage council over traecli.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit stable JSON output.")
    parser.add_argument("--runtime-command", default=DEFAULT_TRAECLI, help="Runtime command, default: traecli.")
    parser.add_argument("--runtime-cwd", help="Working directory for traecli subprocesses. Subagent mode defaults to this CLI project root.")
    parser.add_argument("--store", help="Run store base directory. Default: .llm-council-for-trae/runs in cwd.")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_p = sub.add_parser("doctor", help="Check runtime health and local CLI setup.")
    doctor_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    doctor_p.set_defaults(func=cmd_doctor)

    models_p = sub.add_parser("models", help="List models reported by traecli.")
    models_p.add_argument("--recommend", action="store_true", help="Also include LCT's recommended council roster.")
    models_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    models_p.set_defaults(func=cmd_models)

    subagents_p = sub.add_parser("subagents", help="Inspect project-level fixed council subagent templates.")
    subagents_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    subagents_p.set_defaults(func=cmd_subagents)

    run_p = sub.add_parser("run", help="Run Stage 1, Stage 2, Stage 3, and HTML export.")
    run_p.add_argument("--input", required=True, help="Input markdown/text file.")
    run_p.add_argument("--members", help="Comma-separated model roster. If omitted, LCT asks you to choose from current traecli models.")
    run_p.add_argument("--chairman", help="Chairman model. If omitted with --members, default chairman is used.")
    run_p.add_argument("--selected-members", help="Agent-assisted selected member seed models. This opt-in path normalizes to 3 and records provenance.")
    run_p.add_argument("--selected-chairman", help="Agent-assisted selected chairman model for --selected-members.")
    run_p.add_argument("--profile", help="Optional JSON profile overriding members/chairman/provider.")
    run_p.add_argument("--default-models", action="store_true", help="Skip model selection and use LCT's default model suite.")
    run_p.add_argument("--run-id", help="Explicit run id. Default generated from UTC timestamp.")
    run_p.add_argument("--timeout", type=int, default=180, help="Per-model query timeout seconds.")
    run_p.add_argument("--stage2-timeout", type=float, help="Stage 2 total timeout seconds. Default: max(timeout+30, 240).")
    run_p.add_argument("--chairman-timeout", type=int, default=720, help="Per-chairman Stage 3 timeout seconds, including fallback attempts.")
    run_p.add_argument("--yolo", action="store_true", help="Pass --yolo to traecli. Default member runs do not bypass permissions.")
    run_p.add_argument("--no-yolo", action="store_true", help="Compatibility no-op: default member runs already omit --yolo.")
    run_p.add_argument("--min-valid-members", type=int, default=3, help="Minimum valid members for quorum.")
    run_p.add_argument("--target-valid-members", type=int, default=DEFAULT_MEMBER_COUNT, help="Target valid members for quorum.")
    run_p.add_argument("--backfill-members", help="Comma-separated explicit backfill candidate models. If omitted, LCT uses the approved member priority roster only.")
    run_p.add_argument("--no-auto-backfill", action="store_true", help="Disable automatic Stage 1 and Stage 2 backfill.")
    run_p.add_argument("--low-quorum-floor", type=int, default=2, help="Minimum valid members required for low-quorum degraded delivery.")
    run_p.add_argument("--chairman-fallback", help="Comma-separated fallback chairman models.")
    run_p.add_argument("--member-mode", choices=["normal", "deep_research"], default="normal", help="Member execution mode.")
    run_p.add_argument("--member-tool-mode", choices=["answer_only", "search_enabled", "workspace_enabled"], default="search_enabled", help="Tool capability policy for direct member runtime.")
    run_p.add_argument("--member-runtime-cwd-mode", choices=["isolated_temp", "inherit"], default="isolated_temp", help="Working-directory isolation mode for direct member runtime when --runtime-cwd is omitted.")
    run_p.add_argument("--runtime-backend", choices=["direct", "acp"], default=None, help="Runtime backend implementation. ACP is the default; pass --runtime-backend direct to fall back to the direct runtime. (subagent profiles always run on the direct backend.)")
    run_p.add_argument("--acp-startup-timeout", type=int, default=30, help="ACP startup timeout seconds when --runtime-backend acp is used.")
    run_p.add_argument("--skip-html", action="store_true", help="Skip automatic HTML export after Stage 3.")
    run_p.add_argument("--chairman-contribution-map", dest="chairman_contribution_map", action="store_true", default=None, help="Compatibility alias: Stage 3 requests a contribution-map sidecar by default.")
    run_p.add_argument("--no-chairman-contribution-map", dest="chairman_contribution_map", action="store_false", help="Do not ask Stage 3 to emit a contribution-map sidecar.")
    run_p.add_argument("--require-chairman-contribution-map", action="store_true", help="Fail validation when the contribution-map sidecar is missing or invalid.")
    run_p.add_argument("--debate", action="store_true", help="Enable one fixed Stage 2.5 rebuttal round before chairman synthesis.")
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

    raw_p = sub.add_parser("raw", help="Restricted raw escape hatch to traecli read-only commands.")
    raw_p.add_argument("--unsafe", action="store_true", help="Allow arbitrary traecli args.")
    raw_p.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS)
    raw_p.add_argument("args", nargs=argparse.REMAINDER)
    raw_p.set_defaults(func=cmd_raw)

    return parser


def cmd_doctor(args: argparse.Namespace) -> int:
    health = runtime_doctor(args.runtime_command)
    payload = {
        "ok": health.ok,
        "cli": {"name": "llm-council-for-trae", "version": __version__},
        "runtime": {
            "command": health.command,
            "version": health.version,
            "doctor_exit_code": health.doctor_exit_code,
            "doctor": health.doctor,
        },
        "auth": {"required_by_cli": False, "source": "traecli-local-config"},
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
    with RunLease.acquire(store_base, run_id) as lease:
        args.selected_model_choice = resolve_run_model_choice(args)
        config = build_config(args)
        store = ArtifactStore.create(store_base, run_id)
        manifest = asyncio.run(run_full_council(user_query, config, store))
        if lease.stale_replaced:
            manifest["warnings"].append("stale runtime run lease was replaced")
            store.write_manifest(manifest)
    export_record = None
    if manifest.get("status") in ("ok", "degraded_ok") and config.export_html:
        export_record = export_html(store)
        manifest = store.read_manifest()
    summary_failures = list(manifest.get("failures", []))
    startup_hint = acp_startup_failure_hint(manifest)
    if startup_hint:
        summary_failures.append(startup_hint)
    payload = {
        "run_id": run_id,
        "status": manifest.get("status"),
        "degraded": manifest.get("status") == "degraded_ok",
        "store": str(store.root),
        "manifest": str(store.root / "manifest.json"),
        "html": str(store.root / "html" / "index.html") if export_record else None,
        "warnings": manifest.get("warnings", []),
        "failures": summary_failures,
        "recommendations": failure_recommendations(manifest),
    }
    return emit(payload, args.json_output, ok=manifest.get("status") in ("ok", "degraded_ok"), text=f"run {run_id} {manifest.get('status')} -> {store.root}")


def cmd_show(args: argparse.Namespace) -> int:
    store = ArtifactStore.open(resolve_store_base(args.store), args.run_id)
    manifest = store.read_manifest()
    return emit(manifest, args.json_output, ok=manifest.get("status") == "ok", text=json.dumps(summary_manifest(manifest), ensure_ascii=False, indent=2))


def cmd_validate(args: argparse.Namespace) -> int:
    store = ArtifactStore.open(resolve_store_base(args.store), args.run_id)
    result = validate_run(store)
    return emit(result, args.json_output, ok=result["status"] in ("ok", "degraded_ok"), text=json.dumps(result, ensure_ascii=False, indent=2))


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
    runtime_backend = resolve_runtime_backend(getattr(args, "runtime_backend", None), provider_mode)
    member_agents = None
    chairman_agent = None
    model_selection_provenance = None
    if provider_mode == "subagent":
        members, member_agents = parse_subagent_members(profile.get("members") or [])
        chairman, chairman_agent = parse_subagent_chairman(profile.get("chairman") or {})
        runtime_cwd = str(Path(args.runtime_cwd).expanduser().resolve()) if args.runtime_cwd else str(PROJECT_ROOT)
    else:
        selected: ModelChoice | None = getattr(args, "selected_model_choice", None)
        members = profile.get("members") or (selected.members if selected else None) or split_csv(args.members or ",".join(DEFAULT_MEMBERS))
        chairman = profile.get("chairman") or (selected.chairman if selected else None) or args.chairman or DEFAULT_CHAIRMAN
        model_selection_provenance = selected.provenance if selected and selected.provenance else None
        if any(isinstance(item, dict) for item in members):
            raise ValueError("direct provider members must be model-name strings")
        runtime_cwd = str(Path(args.runtime_cwd).expanduser().resolve()) if args.runtime_cwd else None
    chairman_fallback = None
    if getattr(args, "chairman_fallback", None):
        chairman_fallback = [m.strip() for m in args.chairman_fallback.split(",")]
    chairman_contribution_requested = getattr(args, "chairman_contribution_map", None)
    if chairman_contribution_requested is None:
        chairman_contribution_requested = True
    chairman_contribution_required = bool(getattr(args, "require_chairman_contribution_map", False))
    if chairman_contribution_required and chairman_contribution_requested is False:
        raise ValueError("--require-chairman-contribution-map cannot be combined with --no-chairman-contribution-map")
    if chairman_contribution_required:
        chairman_contribution_requested = True

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
        use_yolo=bool(getattr(args, "yolo", False)) and not bool(getattr(args, "no_yolo", False)),
        min_valid_members=getattr(args, "min_valid_members", 3),
        target_valid_members=getattr(args, "target_valid_members", DEFAULT_MEMBER_COUNT),
        chairman_fallback=chairman_fallback,
        stage2_timeout=getattr(args, "stage2_timeout", None),
        chairman_timeout=getattr(args, "chairman_timeout", 720),
        member_mode=getattr(args, "member_mode", "normal"),
        member_tool_mode=getattr(args, "member_tool_mode", "search_enabled"),
        member_runtime_cwd_mode=getattr(args, "member_runtime_cwd_mode", "isolated_temp"),
        runtime_backend=runtime_backend,
        acp_startup_timeout=getattr(args, "acp_startup_timeout", 30),
        backfill_members=split_csv(getattr(args, "backfill_members", "") or ""),
        stage1_auto_backfill=not getattr(args, "no_auto_backfill", False),
        stage2_auto_backfill=not getattr(args, "no_auto_backfill", False),
        allow_low_quorum=True,
        low_quorum_floor=getattr(args, "low_quorum_floor", 2),
        model_selection_provenance=model_selection_provenance,
        chairman_contribution_enabled=bool(chairman_contribution_requested),
        chairman_contribution_required=chairman_contribution_required,
        debate_enabled=bool(getattr(args, "debate", False)),
    )


def resolve_runtime_backend(requested: str | None, provider_mode: str) -> str:
    """Resolve the effective runtime backend.

    Explicit user input wins. When the user does not pass --runtime-backend
    (requested is None), subagent profiles resolve to direct (acp is not
    supported there) and every other run uses the new acp default. An explicit
    --runtime-backend acp combined with a subagent profile stays a hard error.
    """
    if requested is None:
        return "direct" if provider_mode == "subagent" else "acp"
    if requested == "acp" and provider_mode == "subagent":
        raise ValueError("runtime_backend=acp is not supported with provider_mode=subagent")
    return requested


def resolve_run_model_choice(args: argparse.Namespace) -> ModelChoice | None:
    if getattr(args, "selected_members", None) or getattr(args, "selected_chairman", None):
        if (
            getattr(args, "members", None)
            or getattr(args, "chairman", None)
            or getattr(args, "default_models", False)
            or getattr(args, "profile", None)
        ):
            raise ValueError("--selected-members/--selected-chairman cannot be combined with --members/--chairman, --default-models, or --profile")
        if not getattr(args, "selected_members", None):
            raise ValueError("--selected-chairman requires --selected-members")
        models = get_models(args.runtime_command)
        return normalize_user_model_selection(
            requested_members=split_csv(args.selected_members),
            requested_chairman=args.selected_chairman,
            models=models,
            selection_surface="agent_assisted",
        )
    if getattr(args, "profile", None):
        return None
    if getattr(args, "default_models", False):
        return ModelChoice(list(DEFAULT_MEMBERS), DEFAULT_CHAIRMAN, "static-default")
    if getattr(args, "members", None) or getattr(args, "chairman", None):
        return None
    if not sys.stdin.isatty():
        raise ValueError(
            "未指定模型，且当前不是可交互终端。请传 --default-models 使用默认模型套，"
            "或传 --selected-members/--selected-chairman 使用 agent-assisted 自选归一化路径，"
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
            recommendations.append("模型不在当前 traecli models --json 列表中；请先运行 llm-council-for-trae models --recommend --json，再显式传 --members/--chairman。")
    return unique_strings(recommendations)


def acp_startup_failure_hint(manifest: dict[str, Any]) -> str | None:
    """Return a readable fallback hint when an ACP startup failure sank the run.

    This only adds user-facing guidance; it does not change failure semantics
    and never auto-falls back to the direct runtime.
    """
    failures = manifest.get("failures") or []
    if not isinstance(failures, list):
        return None
    for failure in failures:
        error = failure.get("error") if isinstance(failure, dict) else failure
        if isinstance(error, str) and "acp_startup_failed" in error:
            return "ACP startup failed; retry with --runtime-backend direct to fall back to the direct runtime."
    return None


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
