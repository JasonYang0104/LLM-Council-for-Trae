from typing import Optional

from .model_selection import CHAIRMAN_PRIORITY

VENDOR_TIERS = [
    {"vendor": "openai", "primary": "GPT-5.4", "fallback": "GPT-5.2"},
    {"vendor": "deepseek", "primary": "DeepSeek-V4-Pro", "fallback": "DeepSeek-V4-Flash"},
    {"vendor": "qwen", "primary": "Qwen3.6-Plus", "fallback": "Qwen3.5-Plus"},
    {"vendor": "kimi", "primary": "Kimi-K2.6", "fallback": "Kimi-K2.5"},
    {"vendor": "minimax", "primary": "MiniMax-M2.7", "fallback": "MiniMax-M2.5"},
    {"vendor": "gemini", "primary": "Gemini-3.1-Pro-Preview", "fallback": "Gemini-3-Flash-Preview"},
    {"vendor": "openrouter", "primary": "openrouter-1o", "fallback": "openrouter-1"},
]

PRIMARY_CHAIRMAN = CHAIRMAN_PRIORITY[0]

CHAIRMAN_FALLBACK_CHAIN = CHAIRMAN_PRIORITY[1:]


def resolve_fallback(model_name: str) -> Optional[str]:
    for tier in VENDOR_TIERS:
        if tier["primary"] == model_name:
            return tier["fallback"]
        if tier["fallback"] == model_name:
            return None
    return None


def get_vendor(model_name: str) -> Optional[str]:
    for tier in VENDOR_TIERS:
        if tier["primary"] == model_name or tier["fallback"] == model_name:
            return tier["vendor"]
    return None
