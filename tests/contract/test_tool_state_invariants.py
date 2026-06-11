from __future__ import annotations

import unittest

from llm_council_for_trae.html_export import summarize_search_usage


class ToolStateInvariantTests(unittest.TestCase):
    def test_allowed_search_does_not_imply_used_search(self):
        manifest = {
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": ["WebSearch", "WebFetch"],
                        "tool_calls": [],
                        "tool_calls_count": 0,
                        "forbidden_tool_calls": [],
                    }
                ],
                "stage2": [],
                "stage3": None,
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertTrue(summary["lct_search_allowed"])
        self.assertFalse(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 0)

    def test_web_tool_use_is_reported_even_when_search_was_not_allowed(self):
        manifest = {
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": [],
                        "tool_calls": [{"id": "tc1", "name": "WebSearch", "arguments": "{}", "turn_index": 1}],
                        "forbidden_tool_calls": [],
                    }
                ],
                "stage2": [],
                "stage3": None,
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertFalse(summary["lct_search_allowed"])
        self.assertTrue(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 1)

    def test_forbidden_web_tool_calls_still_count_as_used(self):
        manifest = {
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": [],
                        "tool_calls": [],
                        "tool_calls_count": 0,
                        "forbidden_tool_calls": [
                            {"id": "tc1", "name": "WebFetch", "arguments": "{}", "turn_index": 1}
                        ],
                    }
                ],
                "stage2": [],
                "stage3": None,
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertFalse(summary["lct_search_allowed"])
        self.assertTrue(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 1)
        self.assertEqual(summary["forbidden_tool_calls_count"], 1)


if __name__ == "__main__":
    unittest.main()
