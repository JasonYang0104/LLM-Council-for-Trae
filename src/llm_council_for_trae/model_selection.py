from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TextIO

from .council import DEFAULT_CHAIRMAN, DEFAULT_MEMBERS


PREFERRED_MEMBERS = [
    "GPT-5.4",
    "GLM-5.1",
    "DeepSeek-V4-Pro",
    "Kimi-K2.6",
    "Qwen3.6-Plus",
    "Gemini-3.1-Pro-Preview",
    "MiniMax-M2.7",
    "GPT-5.2",
]
PREFERRED_CHAIRMEN = ["Kimi-K2.6", "DeepSeek-V4-Pro", "GPT-5.4", "GLM-5.1"]
AUTO_EXCLUDED_MODEL_MARKERS = ("seed", "doubao")


@dataclass(frozen=True)
class ModelChoice:
    members: list[str]
    chairman: str
    source: str


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
    names = available_model_names(models)
    if not names:
        return ModelChoice(DEFAULT_MEMBERS, DEFAULT_CHAIRMAN, "static-default")

    non_openrouter = [name for name in names if not name.lower().startswith("openrouter")]
    safe_names = [name for name in names if not is_auto_excluded_model(name)]
    safe_non_openrouter = [name for name in non_openrouter if not is_auto_excluded_model(name)]
    if safe_non_openrouter:
        usable = safe_non_openrouter
    elif safe_names:
        usable = safe_names
    elif non_openrouter:
        usable = non_openrouter
    else:
        usable = names

    members: list[str] = []
    for preferred in PREFERRED_MEMBERS:
        if preferred in usable and preferred not in members:
            members.append(preferred)
        if len(members) >= 3:
            break
    for name in usable:
        if name not in members:
            members.append(name)
        if len(members) >= 3:
            break

    chairman = next((name for name in PREFERRED_CHAIRMEN if name in usable), members[0])
    return ModelChoice(members, chairman, "recommended")


def is_auto_excluded_model(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in AUTO_EXCLUDED_MODEL_MARKERS)


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
    return ModelChoice(members, chairman, "custom")


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
    stderr.write("推荐逻辑：优先选择当前列表里可用、互补、非 OpenRouter 且非 Seed/Doubao 的强模型；没有更安全候选时才回落。主席优先级：Kimi、DeepSeek、GPT、GLM。\n")
    if names:
        stderr.write("\n")
    stderr.flush()


def resolve_model_tokens(text: str, names: list[str]) -> list[str]:
    if not text:
        return []
    resolved: list[str] = []
    for raw_token in text.split(","):
        token = raw_token.strip()
        if not token:
            continue
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
