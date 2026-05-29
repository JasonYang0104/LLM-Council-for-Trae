import unittest

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
        self.assertIsInstance(CHAIRMAN_FALLBACK_CHAIN, list)
        self.assertGreater(len(CHAIRMAN_FALLBACK_CHAIN), 0)

    def test_primary_chairman_is_kimi(self):
        self.assertEqual(PRIMARY_CHAIRMAN, "Kimi-K2.6")


if __name__ == "__main__":
    unittest.main()
