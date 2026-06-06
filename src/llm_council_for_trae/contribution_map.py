from __future__ import annotations

import json
import re
from typing import Any


ALLOWED_BLOCK_TYPES = {"heading", "paragraph", "editor_note", "disagreement"}
ALLOWED_ATTRIBUTION_KINDS = {
    "single_member",
    "multi_member_consensus",
    "editor_note",
    "synthesis",
    "not_attributable",
}


def extract_contribution_map(text: str) -> dict[str, Any] | None:
    candidates = []
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    candidates.extend(re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text))
    for candidate in candidates:
        data = parse_contribution_map_candidate(candidate)
        if isinstance(data, dict) and isinstance(data.get("blocks"), list):
            data.setdefault("schema_version", 1)
            data.setdefault("enabled", True)
            data.setdefault("source", "chairman_structured_output")
            return data
    return None


def parse_contribution_map_candidate(candidate: str) -> Any | None:
    try:
        return json.loads(candidate)
    except Exception:
        pass
    if not looks_like_contribution_map_candidate(candidate):
        return None
    repaired = repair_unescaped_quotes_in_json_strings(candidate)
    if repaired == candidate:
        return None
    try:
        return json.loads(repaired)
    except Exception:
        return None


def looks_like_contribution_map_candidate(candidate: str) -> bool:
    return '"blocks"' in candidate and '"attribution"' in candidate and '"schema_version"' in candidate


def repair_unescaped_quotes_in_json_strings(candidate: str) -> str:
    repaired: list[str] = []
    in_string = False
    escape = False
    length = len(candidate)
    for index, char in enumerate(candidate):
        if not in_string:
            repaired.append(char)
            if char == '"':
                in_string = True
                escape = False
            continue
        if escape:
            repaired.append(char)
            escape = False
            continue
        if char == "\\":
            repaired.append(char)
            escape = True
            continue
        if char != '"':
            repaired.append(char)
            continue
        next_nonspace = ""
        for lookahead in range(index + 1, length):
            if not candidate[lookahead].isspace():
                next_nonspace = candidate[lookahead]
                break
        if next_nonspace in {":", ",", "}", "]"}:
            repaired.append(char)
            in_string = False
        else:
            repaired.append('\\"')
    return "".join(repaired)


def strip_contribution_map_fence(text: str) -> str:
    match = re.search(r"\n?```(?:json)?\s*([\s\S]*?)\s*```\s*$", text.rstrip())
    if not match:
        return text
    candidate = match.group(1)
    data = parse_contribution_map_candidate(candidate)
    if isinstance(data, dict) and isinstance(data.get("blocks"), list):
        return text[: match.start()].rstrip()
    if looks_like_contribution_map_candidate(candidate):
        return text[: match.start()].rstrip()
    return text


def contribution_map_semantic_checks(data: dict[str, Any], stage1: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        return [
            {
                "name": "contribution_map_block_fields",
                "ok": False,
                "message": "blocks must be a list",
            }
        ]

    valid_stage1_models = {
        item.get("model")
        for item in stage1
        if item.get("status") == "ok" and isinstance(item.get("model"), str) and not item.get("forbidden_tool_calls")
    }
    bad_field_blocks: list[str] = []
    bad_member_refs: list[str] = []
    bad_consensus_blocks: list[str] = []
    bad_kind_blocks: list[str] = []
    bad_type_blocks: list[str] = []

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            label = str(index)
            bad_field_blocks.append(f"{label}:block_object")
            bad_type_blocks.append(label)
            continue

        raw_id = block.get("id")
        block_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else str(index)
        missing_fields: list[str] = []
        if not isinstance(raw_id, str) or not raw_id.strip():
            missing_fields.append("id")
        if not isinstance(block.get("type"), str) or not str(block.get("type")).strip():
            missing_fields.append("type")
        if not isinstance(block.get("text"), str) or not str(block.get("text")).strip():
            missing_fields.append("text")
        attribution = block.get("attribution") if isinstance(block.get("attribution"), dict) else {}
        if not isinstance(block.get("attribution"), dict):
            missing_fields.append("attribution")
        if missing_fields:
            bad_field_blocks.append(f"{block_id}:{'/'.join(missing_fields)}")

        if block.get("type") not in ALLOWED_BLOCK_TYPES:
            bad_type_blocks.append(block_id)
        kind = attribution.get("kind")
        if kind not in ALLOWED_ATTRIBUTION_KINDS:
            bad_kind_blocks.append(block_id)
        members = attribution.get("members") if isinstance(attribution.get("members"), list) else []
        member_names = [member for member in members if isinstance(member, str)]
        unknown = [member for member in member_names if member not in valid_stage1_models]
        if unknown:
            bad_member_refs.extend(f"{block_id}:{member}" for member in unknown)
        if kind == "multi_member_consensus" and len(member_names) < 2:
            bad_consensus_blocks.append(block_id)
        if kind == "single_member" and len(member_names) != 1:
            bad_member_refs.append(f"{block_id}:single_member_requires_one_member")

    return [
        {
            "name": "contribution_map_block_fields",
            "ok": not bad_field_blocks,
            "message": "ok" if not bad_field_blocks else ", ".join(bad_field_blocks),
        },
        {
            "name": "contribution_map_block_types",
            "ok": not bad_type_blocks,
            "message": "ok" if not bad_type_blocks else ", ".join(bad_type_blocks),
        },
        {
            "name": "contribution_map_attribution_kind",
            "ok": not bad_kind_blocks,
            "message": "ok" if not bad_kind_blocks else ", ".join(bad_kind_blocks),
        },
        {
            "name": "contribution_map_member_refs",
            "ok": not bad_member_refs,
            "message": "ok" if not bad_member_refs else ", ".join(bad_member_refs),
        },
        {
            "name": "contribution_map_consensus_members",
            "ok": not bad_consensus_blocks,
            "message": "ok" if not bad_consensus_blocks else ", ".join(bad_consensus_blocks),
        },
    ]
