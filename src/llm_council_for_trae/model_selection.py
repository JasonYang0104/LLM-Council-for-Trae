from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TextIO

from .council import DEFAULT_CHAIRMAN, DEFAULT_MEMBERS


PREFERRED_MEMBERS = [
    "DeepSeek-V4-Pro",
    "openrouter-1o",
    "GPT-5.4",
    "Kimi-K2.6",
    "GPT-5.2",
    "openrouter-1",
    "Gemini-3.1-Pro-Preview",
    "DeepSeek-V4-Flash",
    "MiniMax-M2.7",
    "Qwen3.6-Plus",
]
PREFERRED_CHAIRMEN = ["DeepSeek-V4-Pro", "Kimi-K2.6", "DeepSeek-V4-Flash", "GPT-5.2", "openrouter-1"]
HARD_BAN_EXACT = {"gpt-5.5"}
HARD_BAN_MARKERS = ("seed", "doubao", "gpt-5.5", "glm")
QUEUE_HEAT_THRESHOLD = 95
QUEUE_HEAT_RE = re.compile(r"(?:queue\s*heat|排队热度|队列热度)[^\d%]*(\d{1,3})\s*%", re.IGNORECASE)


@dataclass(frozen=True)
class ModelChoice:
    members: list[str]
    chairman: str
    source: str
    provenance: dict[str, Any] = field(default_factory=dict)


def available_model_names(models: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for model in models:
        name = model.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def recommend_model_choice(models: list[dict[str, Any]]) -> ModelChoice:
    unique_models = _dedupe_named_models(models)
    if not unique_models:
        return ModelChoice(DEFAULT_MEMBERS, DEFAULT_CHAIRMAN, "static-default")

    safe_models = [model for model in unique_models if not model_exclusion_reasons(model)]
    if not safe_models:
        return ModelChoice([], "", "no-safe-candidates")

    safe_names = [model["name"] for model in safe_models]

    members: list[str] = []
    for preferred in PREFERRED_MEMBERS:
        if preferred in safe_names and preferred not in members:
            members.append(preferred)
        if len(members) >= 4:
            break

    if not members:
        return ModelChoice([], "", "no-approved-candidates")

    chairman = next(
        (name for name in PREFERRED_CHAIRMEN if name in safe_names),
        members[0],
    )
    return ModelChoice(members, chairman, "recommended")


def normalize_user_model_selection(
    *,
    requested_members: list[str],
    requested_chairman: str | None,
    models: list[dict[str, Any]],
    selection_surface: str,
    target_members: int = 4,
) -> ModelChoice:
    names = available_model_names(models)
    if not names:
        raise ValueError("当前模型列表为空，无法归一化用户自选模型。")

    resolved_requested_members = resolve_model_names(requested_members, names)
    if not resolved_requested_members:
        raise ValueError("自选模型路径至少需要一个成员模型。")

    resolved_chairman = resolve_model_token(requested_chairman, names) if requested_chairman else resolved_requested_members[0]
    filled_members: list[str] = []
    trimmed_members: list[str] = []
    if len(resolved_requested_members) < target_members:
        final_members = list(resolved_requested_members)
        for preferred in PREFERRED_MEMBERS:
            if len(final_members) >= target_members:
                break
            if preferred in names and preferred not in final_members:
                final_members.append(preferred)
                filled_members.append(preferred)
        if len(final_members) < target_members:
            raise ValueError(
                f"无法归一化到 {target_members} 个成员：当前可用且批准的成员模型不足。"
                f" resolved={final_members}"
            )
    elif len(resolved_requested_members) > target_members:
        requested_order = {name: index for index, name in enumerate(resolved_requested_members)}
        preferred_order = {name: index for index, name in enumerate(PREFERRED_MEMBERS)}
        ranked = sorted(
            resolved_requested_members,
            key=lambda name: (preferred_order.get(name, len(PREFERRED_MEMBERS)), requested_order[name]),
        )
        final_members = ranked[:target_members]
        trimmed_members = [name for name in resolved_requested_members if name not in final_members]
    else:
        final_members = list(resolved_requested_members)

    provenance = {
        "selection_surface": selection_surface,
        "requested_members": list(requested_members),
        "requested_chairman": requested_chairman,
        "resolved_requested_members": resolved_requested_members,
        "resolved_members": list(final_members),
        "resolved_chairman": resolved_chairman,
        "filled_members": filled_members,
        "trimmed_members": trimmed_members,
        "final_members": list(final_members),
        "final_chairman": resolved_chairman,
        "normalization_target_members": target_members,
    }
    return ModelChoice(final_members, resolved_chairman, selection_surface, provenance)


def build_backfill_candidates(
    models: list[dict[str, Any]],
    *,
    primary_members: list[str],
    attempted_models: list[str] | None = None,
    failed_models: list[str] | None = None,
    chairman: str | None = None,
    explicit_members: list[str] | None = None,
) -> list[str]:
    safe_names = [
        model["name"]
        for model in _dedupe_named_models(models)
        if not model_exclusion_reasons(model)
    ]
    safe_name_set = set(safe_names)
    excluded = set(primary_members)
    excluded.update(attempted_models or [])
    if chairman:
        excluded.add(chairman)

    def add_candidate(target: list[str], name: str | None) -> None:
        if not name or name not in safe_name_set or name in excluded or name in target:
            return
        target.append(name)

    candidates: list[str] = []
    if explicit_members:
        for name in explicit_members:
            add_candidate(candidates, name)
        return candidates

    for name in PREFERRED_MEMBERS:
        add_candidate(candidates, name)
    return candidates


def is_auto_excluded_model(name: str) -> bool:
    return bool(model_exclusion_reasons({"name": name}))


def model_exclusion_reasons(model: dict[str, Any], *, queue_heat_threshold: int = QUEUE_HEAT_THRESHOLD) -> list[str]:
    name = str(model.get("name") or "")
    lowered = name.lower()
    reasons: list[str] = []
    if lowered in HARD_BAN_EXACT or any(marker in lowered for marker in HARD_BAN_MARKERS):
        reasons.append("hard-banned model")
    if any(marker in lowered for marker in ("seed", "doubao")):
        reasons.append("Seed/Doubao model")
    if _is_beta_model(model):
        reasons.append("Beta model")
    queue_heat = parse_queue_heat_percent(model)
    if queue_heat is not None and queue_heat >= queue_heat_threshold:
        reasons.append(f"Queue heat {queue_heat}%")
    return reasons


def parse_queue_heat_percent(model: dict[str, Any]) -> int | None:
    for key in ("queue_heat", "queue_heat_percent", "queueHeat", "queueHeatPercent"):
        value = model.get(key)
        parsed = _parse_percent(value)
        if parsed is not None:
            return parsed

    usage = model.get("usage")
    if isinstance(usage, dict):
        for key in ("queue_heat", "queue_heat_percent", "queueHeat", "queueHeatPercent"):
            parsed = _parse_percent(usage.get(key))
            if parsed is not None:
                return parsed

    for key in ("description", "label", "status", "tags", "labels"):
        value = model.get(key)
        if isinstance(value, list):
            haystack = " ".join(str(item) for item in value)
        else:
            haystack = str(value or "")
        match = QUEUE_HEAT_RE.search(haystack)
        if match:
            return int(match.group(1))
    return None


def _parse_percent(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.endswith("%"):
            stripped = stripped[:-1].strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _is_beta_model(model: dict[str, Any]) -> bool:
    for key in ("beta", "is_beta", "isBeta"):
        if model.get(key) is True:
            return True
    text = " ".join(
        str(model.get(key) or "")
        for key in ("name", "description", "label", "status")
    ).lower()
    for key in ("tags", "labels"):
        value = model.get(key)
        if isinstance(value, list):
            text += " " + " ".join(str(item).lower() for item in value)
    return "beta" in text or "测试" in text


def _dedupe_named_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for model in models:
        name = model.get("name")
        if not isinstance(name, str) or not name.strip() or name in seen:
            continue
        seen.add(name)
        deduped.append(model | {"name": name})
    return deduped


def select_model_choice_interactively(
    models: list[dict[str, Any]],
    *,
    stdin: TextIO,
    stderr: TextIO,
) -> ModelChoice:
    names = available_model_names(models)
    if not names:
        raise ValueError("当前 traecli 模型列表为空，无法进行模型选择。")

    recommendation = recommend_model_choice(models)
    write_model_menu(stderr, models, recommendation)
    mode = read_answer(stdin, stderr, "选择 [回车=使用推荐 / d=默认模型套 / c=自定义 / q=取消]: ").strip().lower()
    if mode in {"", "r", "recommend", "recommended"}:
        if not recommendation.members:
            raise ValueError("当前模型列表没有安全推荐候选；请显式传 --members/--chairman。")
        return recommendation
    if mode in {"d", "default"}:
        return ModelChoice(list(DEFAULT_MEMBERS), DEFAULT_CHAIRMAN, "static-default")
    if mode in {"q", "quit", "cancel"}:
        raise KeyboardInterrupt
    if mode not in {"c", "custom"}:
        raise ValueError(f"无法识别的模型选择：{mode}")

    members_text = read_answer(stdin, stderr, "成员模型编号或名称，逗号分隔: ").strip()
    members = resolve_model_tokens(members_text, names)
    if not members:
        raise ValueError("至少需要选择一个成员模型。")
    chairman_text = read_answer(stdin, stderr, f"主席模型编号或名称 [回车={members[0]}]: ").strip()
    chairman = resolve_model_token(chairman_text, names) if chairman_text else members[0]
    return normalize_user_model_selection(
        requested_members=members,
        requested_chairman=chairman,
        models=models,
        selection_surface="cli_tty_custom",
    )


def write_model_menu(stderr: TextIO, models: list[dict[str, Any]], recommendation: ModelChoice) -> None:
    names = available_model_names(models)
    stderr.write("\nLCT 检测到当前 traecli 可用模型：\n")
    for index, model in enumerate(models, start=1):
        name = model.get("name") or "unknown"
        context_window = model.get("context_window")
        description = model.get("description") or ""
        detail_parts = []
        if context_window:
            detail_parts.append(f"context {context_window}")
        if description and str(description) not in detail_parts:
            detail_parts.append(str(description))
        detail = f" ({'; '.join(detail_parts)})" if detail_parts else ""
        stderr.write(f"  {index}. {name}{detail}\n")
    stderr.write("\n推荐 council 模型套：\n")
    stderr.write(f"  members: {', '.join(recommendation.members)}\n")
    stderr.write(f"  chairman: {recommendation.chairman}\n")
    stderr.write("推荐逻辑：只从成员整体优先级中推荐可用模型；硬排除 Seed/Doubao/GLM/GPT-5.5、Beta 和 Queue heat 过高模型。主席优先级：DeepSeek、Kimi、DeepSeek Flash、GPT、OpenRouter。\n")
    if names:
        stderr.write("\n")
    stderr.flush()


def resolve_model_tokens(text: str, names: list[str]) -> list[str]:
    if not text:
        return []
    return resolve_model_names([token.strip() for token in text.split(",") if token.strip()], names)


def resolve_model_names(tokens: list[str], names: list[str]) -> list[str]:
    resolved: list[str] = []
    for token in tokens:
        name = resolve_model_token(token, names)
        if name not in resolved:
            resolved.append(name)
    return resolved


def resolve_model_token(token: str, names: list[str]) -> str:
    if token.isdigit():
        index = int(token)
        if 1 <= index <= len(names):
            return names[index - 1]
        raise ValueError(f"模型编号超出范围：{token}")
    matches = [name for name in names if name == token]
    if matches:
        return matches[0]
    lower_matches = [name for name in names if name.lower() == token.lower()]
    if lower_matches:
        return lower_matches[0]
    raise ValueError(f"模型不在当前 traecli 模型列表中：{token}")


def read_answer(stdin: TextIO, stderr: TextIO, prompt: str) -> str:
    stderr.write(prompt)
    stderr.flush()
    answer = stdin.readline()
    if answer == "":
        raise EOFError("模型选择需要终端输入；若要跳过询问，请传 --default-models 或显式传 --members/--chairman。")
    return answer
