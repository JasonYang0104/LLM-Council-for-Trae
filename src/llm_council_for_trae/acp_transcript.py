from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_ACP_METHODS = ("initialize", "session/new", "session/prompt", "session/update")


@dataclass
class AcpTranscriptParseResult:
    response: str = ""
    actual_model: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_permission_requests: list[dict[str, Any]] = field(default_factory=list)
    turns_count: int = 0
    tool_calls_count: int = 0
    protocol_errors: list[str] = field(default_factory=list)


def parse_acp_transcript_text(transcript_text: str) -> AcpTranscriptParseResult:
    result = AcpTranscriptParseResult()
    seen_methods: set[str] = set()
    response_parts: list[str] = []
    pending_permission_indexes: dict[str, int] = {}
    saw_line = False

    for line_number, raw_line in enumerate(transcript_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        saw_line = True
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            result.protocol_errors.append(f"invalid_json_line:{line_number}")
            continue
        if not isinstance(event, dict):
            result.protocol_errors.append(f"invalid_json_line:{line_number}:not_object")
            continue

        method = event.get("method")
        if isinstance(method, str):
            seen_methods.add(method)
        params = event.get("params") if isinstance(event.get("params"), dict) else {}

        if method == "session/request_permission":
            request_id = _id_to_str(event.get("id"))
            permission = {
                "id": request_id,
                "tool_name": _tool_name_from_params(params),
                "arguments": _normalise_arguments(params.get("arguments") or params.get("input") or {}),
                "decision": "unknown",
            }
            pending_permission_indexes[request_id] = len(result.tool_permission_requests)
            result.tool_permission_requests.append(permission)
            continue

        if _id_to_str(event.get("id")) in pending_permission_indexes and "result" in event:
            request_id = _id_to_str(event.get("id"))
            decision = _normalise_decision(event.get("result"))
            result.tool_permission_requests[pending_permission_indexes[request_id]]["decision"] = decision
            continue

        if method != "session/update":
            continue

        result.turns_count += 1
        model = _extract_model(params)
        if model:
            result.actual_model = model
        content = _extract_content(params)
        if content:
            response_parts.append(content)
        result.tool_calls.extend(_extract_tool_calls(params, result.turns_count))

    if not saw_line:
        result.protocol_errors.append("empty_transcript")
    for required in REQUIRED_ACP_METHODS:
        if required not in seen_methods:
            result.protocol_errors.append(f"missing_required_method:{required}")

    result.response = "\n".join(part.strip() for part in response_parts if part.strip()).strip()
    result.tool_calls_count = len(result.tool_calls)
    return result


def resolve_acp_transcript_path(run_root: Path, relative_path: str) -> Path:
    candidate_relative = Path(relative_path)
    if candidate_relative.is_absolute():
        raise ValueError("relative ACP transcript path required")
    root = run_root.resolve()
    candidate = (root / candidate_relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("ACP transcript path escapes run root") from exc
    return candidate


def _id_to_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _tool_name_from_params(params: dict[str, Any]) -> str:
    for key in ("tool_name", "name", "tool"):
        value = params.get(key)
        if isinstance(value, str):
            return value
    tool = params.get("tool")
    if isinstance(tool, dict):
        name = tool.get("name")
        if isinstance(name, str):
            return name
    return ""


def _normalise_arguments(value: Any) -> str:
    if isinstance(value, str):
        return value[:500]
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:500]
    except TypeError:
        return ""


def _normalise_decision(value: Any) -> str:
    if isinstance(value, bool):
        return "allow" if value else "deny"
    if isinstance(value, str):
        return _decision_from_string(value)
    if isinstance(value, dict):
        for key in ("decision", "status", "action", "value"):
            decision = value.get(key)
            if isinstance(decision, str):
                return _decision_from_string(decision)
        allowed = value.get("allowed")
        if isinstance(allowed, bool):
            return "allow" if allowed else "deny"
    return "unknown"


def _decision_from_string(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"allow", "allowed", "approve", "approved", "accept", "accepted"}:
        return "allow"
    if lowered in {"deny", "denied", "reject", "rejected", "block", "blocked"}:
        return "deny"
    return "unknown"


def _extract_model(params: dict[str, Any]) -> str | None:
    for source in _nested_sources(params):
        for key in ("model", "model_name", "actual_model"):
            value = source.get(key)
            if isinstance(value, str):
                return value
    return None


def _extract_content(params: dict[str, Any]) -> str:
    for source in _nested_sources(params):
        for key in ("content", "text", "response", "result"):
            value = source.get(key)
            if isinstance(value, str):
                return value
        message = source.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _extract_tool_calls(params: dict[str, Any], turn_index: int) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for source in _nested_sources(params):
        for key in ("tool_calls", "toolCalls"):
            raw_calls = source.get(key)
            if isinstance(raw_calls, list):
                calls.extend(_normalise_tool_call(call, turn_index) for call in raw_calls if isinstance(call, dict))
        for key in ("tool_call", "toolCall"):
            raw_call = source.get(key)
            if isinstance(raw_call, dict):
                calls.append(_normalise_tool_call(raw_call, turn_index))
    return [call for call in calls if call["name"]]


def _nested_sources(params: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [params]
    for key in ("update", "delta", "data"):
        value = params.get(key)
        if isinstance(value, dict):
            sources.append(value)
    return sources


def _normalise_tool_call(call: dict[str, Any], turn_index: int) -> dict[str, Any]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = (
        function.get("name")
        or call.get("name")
        or call.get("tool_name")
        or call.get("tool")
        or ""
    )
    arguments = (
        function.get("arguments")
        if "arguments" in function
        else call.get("arguments", call.get("input", {}))
    )
    return {
        "id": _id_to_str(call.get("id") or call.get("tool_call_id")),
        "name": name if isinstance(name, str) else "",
        "arguments": _normalise_arguments(arguments),
        "turn_index": turn_index,
    }
