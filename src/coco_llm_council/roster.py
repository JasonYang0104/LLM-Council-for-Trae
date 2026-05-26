from typing import Optional

VENDOR_TIERS = [
    {"vendor": "openai", "primary": "GPT-5.4", "fallback": "GPT-5.2"},
    {"vendor": "zhipu", "primary": "GLM-5.1", "fallback": "GLM-5"},
    {"vendor": "deepseek", "primary": "DeepSeek-V4-Pro", "fallback": "DeepSeek-V4-Flash"},
    {"vendor": "qwen", "primary": "Qwen3.6-Plus", "fallback": "Qwen3.5-Plus"},
    {"vendor": "kimi", "primary": "Kimi-K2.6", "fallback": "Kimi-K2.5"},
    {"vendor": "minimax", "primary": "MiniMax-M2.7", "fallback": "MiniMax-M2.5"},
    {"vendor": "gemini", "primary": "Gemini-3.1-Pro-Preview", "fallback": "Gemini-3-Flash-Preview"},
    {"vendor": "openrouter", "primary": "openrouter-2o", "fallback": "openrouter-1o"},
]

PRIMARY_CHAIRMAN = "GLM-5.1"

CHAIRMAN_FALLBACK_CHAIN = ["Qwen3.6-Plus", "DeepSeek-V4-Pro"]


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
