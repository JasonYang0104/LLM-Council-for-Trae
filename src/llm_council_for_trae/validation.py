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
from .html_export import summarize_search_usage
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
            "terminal": False,
            "usable_final": False,
            "stage3_final_exists": nonempty_file(store.root / "stage3" / "final.md"),
            "html_exists": nonempty_file(store.root / "html" / "index.html"),
            "failed_stage_records": [],
            "verdict": "invalid_artifacts",
            "checks": checks,
            "failures": failures,
            "warnings": [],
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
            "terminal": False,
            "usable_final": False,
            "stage3_final_exists": nonempty_file(store.root / "stage3" / "final.md"),
            "html_exists": nonempty_file(store.root / "html" / "index.html"),
            "failed_stage_records": collect_failed_stage_records(manifest),
            "verdict": "in_progress",
            "checks": checks,
            "failures": failures,
            "warnings": [],
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
    checks.extend(quorum_semantic_checks(manifest_status, manifest, stage1, stage2))

    html_path = store.root / "html" / "index.html"
    if html_path.exists():
        checks.append(file_check(store.root, "html/index.html"))
        checks.append(file_check(store.root, "html/export.json"))
        _, html_export_checks = validate_json_file("html.export", store.root / "html/export.json", HTML_EXPORT_JSON_SCHEMA)
        checks.extend(html_export_checks)
    else:
        checks.append({"name": "html_export", "ok": False, "message": "html/index.html missing"})

    warnings = search_delivery_warnings(manifest)
    failures = [check for check in checks if not check["ok"]]
    if not failures and manifest_status in ("ok", "degraded_ok"):
        final_status = manifest_status
    else:
        final_status = "failed"
    stage3_final_exists = nonempty_file(store.root / "stage3" / "final.md")
    html_exists = nonempty_file(store.root / "html" / "index.html")
    terminal = manifest_status in ("ok", "degraded_ok", "failed")
    usable_final = bool(terminal and manifest_status in ("ok", "degraded_ok") and stage3_final_exists and html_exists and not failures)
    return {
        "run_id": manifest.get("run_id"),
        "status": final_status,
        "manifest_status": manifest_status,
        "terminal": terminal,
        "usable_final": usable_final,
        "stage3_final_exists": stage3_final_exists,
        "html_exists": html_exists,
        "failed_stage_records": collect_failed_stage_records(manifest),
        "verdict": validation_verdict(manifest_status, usable_final, failures, stage3_final_exists),
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
    }


def nonempty_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def validation_verdict(manifest_status: Any, usable_final: bool, failures: list[dict[str, Any]], stage3_final_exists: bool) -> str:
    if manifest_status == "running":
        return "in_progress"
    if usable_final and manifest_status == "ok":
        return "complete_ok_final"
    if usable_final and manifest_status == "degraded_ok":
        return "usable_degraded_final"
    if manifest_status in ("ok", "degraded_ok") and failures:
        return "invalid_artifacts"
    if manifest_status == "failed" or not stage3_final_exists:
        return "failed_no_final"
    return "invalid_artifacts"


def search_delivery_warnings(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    summary = summarize_search_usage(manifest)
    calls = summary["lct_web_tool_calls"]
    effective = summary["lct_web_tool_effective_calls"]
    if calls <= 0 or effective >= calls:
        return []
    return [
        {
            "name": "search_tool_output_conversion",
            "ok": True,
            "severity": "warning",
            "message": "WebSearch/WebFetch tool calls observed, but effective delivery is lower than calls",
            "lct_web_tool_calls": calls,
            "lct_web_tool_effective_calls": effective,
            "lct_search_conversion_errors": summary["lct_search_conversion_errors"],
        }
    ]


def collect_failed_stage_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    stages = manifest.get("stages") if isinstance(manifest.get("stages"), dict) else {}
    for stage_name in ("stage1", "stage2"):
        stage_items_raw = stages.get(stage_name)
        if isinstance(stage_items_raw, list):
            for item in stage_items_raw:
                if isinstance(item, dict) and is_failed_stage_record(item):
                    records.append(compact_failed_stage_record(item, stage_name))
    stage3 = stages.get("stage3")
    if isinstance(stage3, dict) and is_failed_stage_record(stage3):
        records.append(compact_failed_stage_record(stage3, "stage3"))

    manifest_failures = manifest.get("failures")
    if isinstance(manifest_failures, list):
        for item in manifest_failures:
            if isinstance(item, dict):
                records.append(compact_failed_stage_record(item, item.get("stage")))
            else:
                records.append({"stage": "manifest", "status": "failed", "error": str(item)})

    deduped: list[dict[str, Any]] = []
    for record in records:
        existing = next((item for item in deduped if same_failure_record(item, record)), None)
        if existing is None:
            deduped.append(record)
        else:
            for key, value in record.items():
                existing.setdefault(key, value)
    return deduped


def same_failure_record(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_model = left.get("model") or left.get("expected_model") or left.get("actual_model")
    right_model = right.get("model") or right.get("expected_model") or right.get("actual_model")
    return (
        failure_stage_record_key(left) == failure_stage_record_key(right)
        and left_model == right_model
        and left.get("status") == right.get("status")
        and left.get("error") == right.get("error")
    )


def failure_stage_record_key(record: dict[str, Any]) -> Any:
    return record.get("stage_record") or record.get("label") or record.get("reviewer_label") or record.get("model")


def is_failed_stage_record(item: dict[str, Any]) -> bool:
    status = item.get("status")
    return isinstance(status, str) and status not in ("ok", "degraded_ok", "running")


def compact_failed_stage_record(item: dict[str, Any], stage_name: Any = None) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    stage = stage_name or item.get("stage")
    if stage:
        compact["stage"] = stage
    stage_record = item.get("stage_record") or item.get("label") or item.get("reviewer_label") or item.get("model")
    if stage_record:
        compact["stage_record"] = stage_record
    for field in (
        "label",
        "reviewer_label",
        "model",
        "expected_model",
        "actual_model",
        "status",
        "error",
        "parse_status",
        "agent",
    ):
        value = item.get(field)
        if value is not None:
            compact[field] = value
    if "status" not in compact:
        compact["status"] = "failed"
    return compact


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


def quorum_semantic_checks(
    manifest_status: Any,
    manifest: dict[str, Any],
    stage1: list[dict[str, Any]],
    stage2: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    quorum = metadata.get("quorum") if isinstance(metadata.get("quorum"), dict) else None
    if not quorum:
        return []

    checks: list[dict[str, Any]] = []
    low_quorum_used = quorum.get("low_quorum_used") is True
    if low_quorum_used:
        checks.append(
            {
                "name": "quorum_low_status",
                "ok": manifest_status == "degraded_ok",
                "message": f"low_quorum_used=true requires manifest.status=degraded_ok, got {manifest_status}",
            }
        )

    backfill_attempted = {
        item for item in quorum.get("backfill_attempted") or []
        if isinstance(item, str)
    }
    backfill_used = quorum.get("backfill_used") is True or bool(backfill_attempted)
    if backfill_used:
        for item in stage1:
            model = item.get("model")
            attempt_role = item.get("attempt_role")
            if attempt_role == "backfill":
                continue
            if isinstance(model, str) and model in backfill_attempted:
                label = item.get("file_label") or item.get("label") or model
                checks.append(
                    {
                        "name": f"stage1_backfill_attempt_role_{label}",
                        "ok": False,
                        "message": f"backfilled model {model} is missing attempt_role=backfill",
                    }
                )

    valid_stage1_models = {
        item.get("model")
        for item in stage1
        if item.get("status") == "ok" and not item.get("forbidden_tool_calls")
    }
    label_to_model = metadata.get("label_to_model") if isinstance(metadata.get("label_to_model"), dict) else {}
    subject_labels = set(label_to_model)
    subject_models = {
        model for model in label_to_model.values()
        if isinstance(model, str)
    }
    for item in stage2:
        model = item.get("model")
        if item.get("reviewer_eligible") is True:
            source = item.get("reviewer_source")
            if source == "stage2_reviewer_backfill":
                reviewer_label = item.get("reviewer_label") or model
                parsed_ranking = item.get("parsed_ranking") if isinstance(item.get("parsed_ranking"), list) else []
                checks.append(
                    {
                        "name": f"stage2_reviewer_backfill_not_subject_{reviewer_label}",
                        "ok": model not in subject_models,
                        "message": f"reviewer-only model {model} must not appear in label_to_model subjects",
                    }
                )
                checks.append(
                    {
                        "name": f"stage2_reviewer_backfill_ranking_subjects_{reviewer_label}",
                        "ok": set(parsed_ranking) == subject_labels and len(parsed_ranking) == len(subject_labels),
                        "message": f"reviewer-only ranking must match review subjects: {sorted(subject_labels)}",
                    }
                )
                continue
            checks.append(
                {
                    "name": f"stage2_reviewer_effective_stage1_{item.get('reviewer_label') or model}",
                    "ok": model in valid_stage1_models,
                    "message": f"reviewer model {model} must have an effective Stage 1 answer",
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
