from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema_contract import (
    CONFIG_SCHEMA,
    FINAL_JSON_SCHEMA,
    HTML_EXPORT_JSON_SCHEMA,
    MANIFEST_SCHEMA,
    METADATA_SCHEMA,
    REVIEW_JSON_SCHEMA,
    STAGE_META_SCHEMA,
    STAGES_SCHEMA,
    subagent_schema_checks,
    validate_json_file,
    validate_schema,
)
from .store import ArtifactStore


REQUIRED_FILES = [
    "input.md",
    "config.json",
    "manifest.json",
    "events.jsonl",
    "runtime/doctor.json",
    "runtime/traecli.models.json",
    "stage1/member.prompt.md",
    "stage2/review.prompt.md",
    "stage2/label_to_model.json",
    "stage2/aggregate.json",
    "stage3/chairman.prompt.md",
    "stage3/final.md",
    "stage3/final.json",
]


# Newly generated meta files should include these fields; validation keeps them
# optional so older run artifacts do not fail before semantic checks run.
STAGE_META_COMPAT_OPTIONAL_FIELDS = {
    "permission_mode",
    "member_tool_mode",
    "allowed_tools",
    "disallowed_tools",
    "forbidden_tool_calls",
    "tool_budget_status",
    "assistant_content_chars_total",
    "last_assistant_content_chars",
    "raw_partial_recoverable",
}


def validate_run(store: ArtifactStore) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stage_meta_records: list[tuple[str, dict[str, Any]]] = []
    manifest, manifest_checks = validate_json_file("manifest", store.root / "manifest.json", MANIFEST_SCHEMA)
    checks.extend(manifest_checks)
    if not isinstance(manifest, dict):
        failures = [check for check in checks if not check["ok"]]
        return {
            "run_id": None,
            "status": "failed",
            "manifest_status": None,
            "checks": checks,
            "failures": failures,
        }

    checks.extend(validate_schema("manifest.config", manifest.get("config"), CONFIG_SCHEMA))
    checks.extend(validate_schema("manifest.stages", manifest.get("stages"), STAGES_SCHEMA))
    checks.extend(validate_schema("manifest.metadata", manifest.get("metadata"), METADATA_SCHEMA))
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    provider_mode = config.get("provider_mode")
    subagent_mode = provider_mode == "subagent"
    manifest_status = manifest.get("status")

    if manifest_status == "running":
        checks.append(
            {
                "name": "run_in_progress",
                "ok": False,
                "message": "manifest status is running; validation deferred until terminal status",
            }
        )
        failures = [check for check in checks if not check["ok"]]
        return {
            "run_id": manifest.get("run_id"),
            "status": "running",
            "manifest_status": manifest_status,
            "checks": checks,
            "failures": failures,
        }

    for relative in REQUIRED_FILES:
        checks.append(file_check(store.root, relative))

    stage1 = stage_items(stages, "stage1", checks)
    for item in stage1:
        label = item.get("file_label")
        if label:
            checks.extend(
                [
                    file_check(store.root, f"stage1/{label}.response.md"),
                    file_check(store.root, f"stage1/{label}.meta.json"),
                    file_check(store.root, f"stage1/{label}.traecli.stream.jsonl"),
                ]
            )
            meta, meta_checks = validate_json_file(
                f"stage1.{label}.meta",
                store.root / f"stage1/{label}.meta.json",
                STAGE_META_SCHEMA,
                optional=STAGE_META_COMPAT_OPTIONAL_FIELDS,
            )
            checks.extend(meta_checks)
            if isinstance(meta, dict):
                stage_meta_records.append((f"stage1.{label}.meta", meta))
        checks.append(model_match_check("stage1", item))
        if subagent_mode:
            checks.extend(subagent_schema_checks(f"manifest.stage1.{label}", item))
            checks.append(subagent_invocation_check("stage1", item))

    stage2 = stage_items(stages, "stage2", checks)
    for item in stage2:
        label = item.get("reviewer_label")
        if label:
            checks.extend(
                [
                    file_check(store.root, f"stage2/{label}.review.md"),
                    file_check(store.root, f"stage2/{label}.review.json"),
                    file_check(store.root, f"stage2/{label}.meta.json"),
                    file_check(store.root, f"stage2/{label}.traecli.stream.jsonl"),
                ]
            )
            meta, meta_checks = validate_json_file(
                f"stage2.{label}.meta",
                store.root / f"stage2/{label}.meta.json",
                STAGE_META_SCHEMA,
                optional=STAGE_META_COMPAT_OPTIONAL_FIELDS,
            )
            checks.extend(meta_checks)
            if isinstance(meta, dict):
                stage_meta_records.append((f"stage2.{label}.meta", meta))
            _, review_checks = validate_json_file(f"stage2.{label}.review", store.root / f"stage2/{label}.review.json", REVIEW_JSON_SCHEMA)
            checks.extend(review_checks)
        checks.append(model_match_check("stage2", item))
        if subagent_mode:
            checks.extend(subagent_schema_checks(f"manifest.stage2.{label}", item))
            checks.append(subagent_invocation_check("stage2", item))
        parse_ok = item.get("parse_status") == "ok" if item.get("status") == "ok" else True
        checks.append(
            {
                "name": f"stage2_parse_{label}",
                "ok": parse_ok,
                "message": item.get("parse_status") or item.get("status") or "missing",
            }
        )

    raw_stage3 = stages.get("stage3")
    stage3 = raw_stage3 if isinstance(raw_stage3, dict) else {}
    checks.extend(validate_schema("manifest.stage3.final", stage3, FINAL_JSON_SCHEMA))
    checks.append(model_match_check("stage3", stage3))
    if subagent_mode:
        checks.extend(subagent_schema_checks("manifest.stage3.final", stage3))
        checks.append(subagent_invocation_check("stage3", stage3))
    checks.extend(
        [
            file_check(store.root, "stage3/final.meta.json"),
            file_check(store.root, "stage3/final.traecli.stream.jsonl"),
        ]
    )
    final_meta, final_meta_checks = validate_json_file(
        "stage3.final.meta",
        store.root / "stage3/final.meta.json",
        STAGE_META_SCHEMA,
        optional=STAGE_META_COMPAT_OPTIONAL_FIELDS,
    )
    checks.extend(final_meta_checks)
    if isinstance(final_meta, dict):
        stage_meta_records.append(("stage3.final.meta", final_meta))
    _, final_json_checks = validate_json_file("stage3.final", store.root / "stage3/final.json", FINAL_JSON_SCHEMA)
    checks.extend(final_json_checks)
    checks.extend(tool_contamination_checks(manifest_status, stage1, stage2, stage3, stage_meta_records))

    html_path = store.root / "html" / "index.html"
    if html_path.exists():
        checks.append(file_check(store.root, "html/index.html"))
        checks.append(file_check(store.root, "html/export.json"))
        _, html_export_checks = validate_json_file("html.export", store.root / "html/export.json", HTML_EXPORT_JSON_SCHEMA)
        checks.extend(html_export_checks)
    else:
        checks.append({"name": "html_export", "ok": False, "message": "html/index.html missing"})

    failures = [check for check in checks if not check["ok"]]
    if not failures and manifest_status in ("ok", "degraded_ok"):
        final_status = manifest_status
    else:
        final_status = "failed"
    return {
        "run_id": manifest.get("run_id"),
        "status": final_status,
        "manifest_status": manifest_status,
        "checks": checks,
        "failures": failures,
    }


def tool_contamination_checks(
    manifest_status: Any,
    stage1: list[dict[str, Any]],
    stage2: list[dict[str, Any]],
    stage3: dict[str, Any],
    stage_meta_records: list[tuple[str, dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    records: list[tuple[str, dict[str, Any]]] = []
    records.extend(("stage1", item) for item in stage1)
    records.extend(("stage2", item) for item in stage2)
    if stage3:
        records.append(("stage3", stage3))
    if stage_meta_records:
        records.extend(stage_meta_records)

    contaminated = [
        (stage, item)
        for stage, item in records
        if isinstance(item.get("forbidden_tool_calls"), list) and item.get("forbidden_tool_calls")
    ]
    checks: list[dict[str, Any]] = []
    if contaminated:
        checks.append(
            {
                "name": "tool_contamination_manifest_ok",
                "ok": manifest_status != "ok",
                "message": f"manifest_status={manifest_status}, contaminated_records={len(contaminated)}",
            }
        )
    for stage, item in contaminated:
        checks.append(
            {
                "name": f"{stage}_tool_contamination_status",
                "ok": item.get("status") != "ok",
                "message": f"status={item.get('status')}, forbidden_tool_calls={item.get('forbidden_tool_calls')}",
            }
        )
    return checks


def stage_items(stages: dict[str, Any], stage_name: str, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_items = stages.get(stage_name)
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, dict):
            items.append(item)
        else:
            checks.append(
                {
                    "name": f"schema:manifest.stages.{stage_name}[{index}]",
                    "ok": False,
                    "message": f"expected object, got {type(item).__name__}",
                }
            )
    return items


def file_check(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    ok = path.exists() and path.stat().st_size > 0
    return {"name": f"file:{relative}", "ok": ok, "message": "present" if ok else "missing or empty"}


def model_match_check(stage: str, item: dict[str, Any]) -> dict[str, Any]:
    status = item.get("status")
    if status not in (None, "ok", "degraded_ok"):
        return {
            "name": f"{stage}_expected_actual_model",
            "ok": True,
            "message": f"skipped non-ok record: {status}",
        }
    expected = item.get("expected_model")
    actual = item.get("actual_model")
    ok = bool(expected) and expected == actual
    return {
        "name": f"{stage}_expected_actual_model",
        "ok": ok,
        "message": f"{expected} -> {actual}",
    }


def subagent_invocation_check(stage: str, item: dict[str, Any]) -> dict[str, Any]:
    agent = item.get("agent")
    invocation = item.get("subagent_invocation")
    ok = (
        bool(agent)
        and isinstance(invocation, dict)
        and invocation.get("required") is True
        and invocation.get("expected_agent") == agent
        and invocation.get("ok") is True
        and invocation.get("tool_call_seen") is True
        and invocation.get("tool_result_seen") is True
        and invocation.get("subagent_message_seen") is True
        and bool(invocation.get("subagent_source_models"))
    )
    return {
        "name": f"{stage}_subagent_invocation",
        "ok": ok,
        "message": f"agent={agent}, evidence={invocation}",
    }
