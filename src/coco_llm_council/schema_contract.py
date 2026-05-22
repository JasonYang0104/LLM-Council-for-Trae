from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


JsonTypeCheck = Callable[[Any], bool]


def is_str(value: Any) -> bool:
    return isinstance(value, str)


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def is_list(value: Any) -> bool:
    return isinstance(value, list)


def is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def is_str_or_none(value: Any) -> bool:
    return value is None or isinstance(value, str)


def is_dict_or_none(value: Any) -> bool:
    return value is None or isinstance(value, dict)


def is_list_of_str(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


MANIFEST_SCHEMA: dict[str, JsonTypeCheck] = {
    "schema_version": is_int,
    "run_id": is_str,
    "created_at": is_str,
    "updated_at": is_str,
    "status": is_str,
    "input_chars": is_int,
    "config": is_dict,
    "artifacts": is_dict,
    "stages": is_dict,
    "metadata": is_dict,
    "warnings": is_list,
    "failures": is_list,
}


CONFIG_SCHEMA: dict[str, JsonTypeCheck] = {
    "members": is_list_of_str,
    "chairman": is_str,
    "provider_mode": is_str,
    "runtime_command": is_str,
    "query_timeout": is_int,
    "export_html": is_bool,
}


STAGES_SCHEMA: dict[str, JsonTypeCheck] = {
    "stage1": is_list,
    "stage2": is_list,
    "stage3": lambda value: isinstance(value, dict) or value is None,
}


METADATA_SCHEMA: dict[str, JsonTypeCheck] = {
    "label_to_model": is_dict,
    "aggregate_rankings": is_list,
}


STAGE_META_SCHEMA: dict[str, JsonTypeCheck] = {
    "expected_model": is_str,
    "actual_model": is_str_or_none,
    "response_chars": is_int,
    "status": is_str,
    "session_id": is_str,
    "command": is_list_of_str,
    "exit_code": is_int,
    "stdout_path": is_str,
    "stderr_path": is_str,
    "copied_session_files": is_dict,
    "raw_model_markers": is_list_of_str,
    "error": is_str_or_none,
    "captured_at": is_str,
}


REVIEW_JSON_SCHEMA: dict[str, JsonTypeCheck] = {
    "reviewer_label": is_str,
    "model": is_str,
    "expected_model": is_str,
    "actual_model": is_str_or_none,
    "ranking": is_str,
    "parsed_ranking": is_list_of_str,
    "parse_status": is_str,
    "status": is_str,
    "error": is_str_or_none,
    "review_path": is_str,
    "json_path": is_str,
}


FINAL_JSON_SCHEMA: dict[str, JsonTypeCheck] = {
    "model": is_str,
    "expected_model": is_str,
    "actual_model": is_str_or_none,
    "response": is_str,
    "status": is_str,
    "error": is_str_or_none,
    "prompt_path": is_str,
    "response_path": is_str,
    "json_path": is_str,
}


HTML_EXPORT_JSON_SCHEMA: dict[str, JsonTypeCheck] = {
    "run_id": is_str,
    "generated_at": is_str,
    "format": is_str,
    "path": is_str,
    "source_manifest": is_str,
}


SUBAGENT_INVOCATION_SCHEMA: dict[str, JsonTypeCheck] = {
    "required": is_bool,
    "expected_agent": is_str_or_none,
    "tool_call_seen": is_bool,
    "tool_call_ids": is_list_of_str,
    "tool_call_subagent_types": is_list_of_str,
    "tool_result_seen": is_bool,
    "tool_result_ids": is_list_of_str,
    "subagent_message_seen": is_bool,
    "subagent_message_tool_ids": is_list_of_str,
    "subagent_source_models": is_list_of_str,
    "ok": is_bool,
}


def validate_schema(name: str, data: Any, schema: dict[str, JsonTypeCheck]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [{"name": f"schema:{name}", "ok": False, "message": f"expected object, got {type(data).__name__}"}]
    for field, type_check in schema.items():
        if field not in data:
            checks.append({"name": f"schema:{name}.{field}", "ok": False, "message": "missing required field"})
            continue
        value = data[field]
        checks.append(
            {
                "name": f"schema:{name}.{field}",
                "ok": type_check(value),
                "message": "ok" if type_check(value) else f"wrong type: {type(value).__name__}",
            }
        )
    return checks


def validate_json_file(name: str, path: Path, schema: dict[str, JsonTypeCheck]) -> tuple[Any | None, list[dict[str, Any]]]:
    if not path.exists():
        return None, [{"name": f"schema:{name}", "ok": False, "message": f"missing file: {path.name}"}]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [{"name": f"schema:{name}", "ok": False, "message": f"invalid JSON: {exc}"}]
    return data, validate_schema(name, data, schema)


def subagent_schema_checks(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.extend(validate_schema(f"{name}.subagent_invocation", data.get("subagent_invocation"), SUBAGENT_INVOCATION_SCHEMA))
    if "agent" not in data:
        checks.append({"name": f"schema:{name}.agent", "ok": False, "message": "missing required field"})
    else:
        checks.append(
            {
                "name": f"schema:{name}.agent",
                "ok": is_str(data["agent"]),
                "message": "ok" if is_str(data["agent"]) else f"wrong type: {type(data['agent']).__name__}",
            }
        )
    return checks
