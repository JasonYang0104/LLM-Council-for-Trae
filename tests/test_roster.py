import unittest

from llm_council_for_trae import model_selection
from llm_council_for_trae.roster import (
    CHAIRMAN_FALLBACK_CHAIN,
    PRIMARY_CHAIRMAN,
    VENDOR_TIERS,
    get_vendor,
    resolve_fallback,
)


class TestRoster(unittest.TestCase):
    def test_resolve_fallback_returns_same_vendor_fallback(self):
        self.assertEqual(resolve_fallback("GPT-5.4"), "GPT-5.2")

    def test_resolve_fallback_returns_none_for_fallback_model(self):
        self.assertIsNone(resolve_fallback("GPT-5.2"))

    def test_resolve_fallback_returns_none_for_unknown(self):
        self.assertIsNone(resolve_fallback("UnknownModel"))

    def test_get_vendor_returns_vendor_name(self):
        self.assertEqual(get_vendor("GPT-5.4"), "openai")

    def test_get_vendor_returns_none_for_unknown(self):
        self.assertIsNone(get_vendor("UnknownModel"))

    def test_chairman_fallback_chain_defined(self):
        self.assertEqual(CHAIRMAN_FALLBACK_CHAIN, ["Kimi-K2.6", "DeepSeek-V4-Flash", "GPT-5.2", "openrouter-1"])

    def test_primary_chairman_is_deepseek(self):
        self.assertEqual(PRIMARY_CHAIRMAN, "DeepSeek-V4-Pro")

    def test_roster_chairman_exports_derive_from_model_selection_priority(self):
        priority = getattr(model_selection, "CHAIRMAN_PRIORITY", None)

        self.assertEqual(priority, ["DeepSeek-V4-Pro", "Kimi-K2.6", "DeepSeek-V4-Flash", "GPT-5.2", "openrouter-1"])
        self.assertEqual(model_selection.PREFERRED_CHAIRMEN, priority)
        self.assertEqual(PRIMARY_CHAIRMAN, priority[0])
        self.assertEqual(CHAIRMAN_FALLBACK_CHAIN, priority[1:])

    def test_glm_is_not_an_active_vendor_tier(self):
        serialized = repr(VENDOR_TIERS)
        self.assertNotIn("GLM-5.1", serialized)
        self.assertNotIn("GLM-5", serialized)


if __name__ == "__main__":
    unittest.main()
