from __future__ import annotations

import json
import unittest
from pathlib import Path

from llm_council_for_trae.council import DEFAULT_CHAIRMAN, DEFAULT_MEMBERS
from llm_council_for_trae.html_export import summarize_search_usage
from llm_council_for_trae.model_selection import (
    PREFERRED_MEMBERS,
    model_exclusion_reasons,
    parse_queue_heat_percent,
    recommend_model_choice,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class LctModelProductizationTests(unittest.TestCase):
    def read_text(self, relative: str) -> str:
        return (REPO_ROOT / relative).read_text(encoding="utf-8")

    def test_default_roster_uses_current_priority_suite(self):
        self.assertEqual(
            DEFAULT_MEMBERS,
            ["DeepSeek-V4-Pro", "GPT-5.5", "openrouter-3o"],
        )
        self.assertEqual(DEFAULT_CHAIRMAN, "DeepSeek-V4-Pro")
        self.assertEqual(
            PREFERRED_MEMBERS,
            [
                "DeepSeek-V4-Pro",
                "GPT-5.5",
                "openrouter-3o",
                "GPT-5.4",
                "openrouter-2o",
                "Kimi-K2.6",
                "MiniMax-M2.7",
                "GPT-5.2",
                "openrouter-1o",
                "DeepSeek-V4-Flash",
                "Gemini-3.1-Pro-Preview",
                "Qwen3.6-Plus",
            ],
        )

    def test_recommendation_uses_safe_openrouter_to_fill_three_members(self):
        choice = recommend_model_choice(
            [
                {"name": "Kimi-K2.6"},
                {"name": "GPT-5.2"},
                {"name": "openrouter-1o", "description": "Quota available; L4"},
                {"name": "openrouter-1", "description": "Quota available; L4"},
            ]
        )

        self.assertEqual(choice.members, ["Kimi-K2.6", "GPT-5.2", "openrouter-1o"])
        self.assertEqual(choice.chairman, "Kimi-K2.6")

    def test_recommendation_caps_primary_members_at_three(self):
        choice = recommend_model_choice(
            [
                {"name": "DeepSeek-V4-Pro"},
                {"name": "openrouter-1o"},
                {"name": "GPT-5.4"},
                {"name": "openrouter-3o"},
                {"name": "Kimi-K2.6"},
                {"name": "Gemini-3.1-Pro-Preview"},
                {"name": "openrouter-2o"},
            ]
        )

        self.assertEqual(choice.members, ["DeepSeek-V4-Pro", "openrouter-3o", "GPT-5.4"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")

    def test_recommendation_excludes_seed_doubao_glm_but_allows_gpt55_beta_and_hot_queue(self):
        choice = recommend_model_choice(
            [
                {"name": "Kimi-K2.6"},
                {"name": "Seed-Dogfooding-2.0"},
                {"name": "Doubao-Seed-1.8"},
                {"name": "GLM-5.1"},
                {"name": "openrouter-3o"},
                {"name": "GPT-5.5"},
                {"name": "GPT-5.4", "description": "Queue heat 104%"},
                {"name": "Beta-Reasoner"},
                {"name": "DeepSeek-V4-Pro"},
            ]
        )

        self.assertEqual(choice.members, ["DeepSeek-V4-Pro", "GPT-5.5", "openrouter-3o"])
        joined = ",".join(choice.members + [choice.chairman]).lower()
        for banned in ("seed", "doubao", "glm"):
            self.assertNotIn(banned, joined)
        self.assertEqual(model_exclusion_reasons({"name": "GPT-5.5"}), [])
        self.assertEqual(model_exclusion_reasons({"name": "GPT-5.4", "description": "Queue heat 104%"}), [])
        self.assertEqual(model_exclusion_reasons({"name": "Beta-Reasoner", "beta": True}), [])

    def test_gpt55_can_be_recommended_when_higher_priority_models_are_absent(self):
        choice = recommend_model_choice(
            [
                {"name": "Seed-Dogfooding-2.0"},
                {"name": "GPT-5.5"},
            ]
        )

        self.assertEqual(choice.members, ["GPT-5.5"])
        self.assertEqual(choice.chairman, "GPT-5.5")

    def test_recommendation_excludes_glm_models(self):
        choice = recommend_model_choice(
            [
                {"name": "GLM-5.1"},
                {"name": "GLM-5"},
                {"name": "DeepSeek-V4-Pro"},
                {"name": "Kimi-K2.6"},
            ]
        )

        self.assertEqual(choice.members, ["DeepSeek-V4-Pro", "Kimi-K2.6"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")
        self.assertNotIn("GLM", ",".join(choice.members + [choice.chairman]))

    def test_beta_metadata_is_not_an_auto_exclusion_reason(self):
        beta_models = [
            {"name": "GPT-5.2", "beta": True},
            {"name": "GPT-5.2", "is_beta": True},
            {"name": "GPT-5.2", "isBeta": True},
            {"name": "GPT-5.2", "labels": ["Beta"]},
        ]

        for model in beta_models:
            with self.subTest(model=model):
                self.assertEqual(model_exclusion_reasons(model), [])

    def test_openrouter_quota_and_l4_copy_is_not_an_exclusion_reason(self):
        reasons = model_exclusion_reasons({"name": "openrouter-1o", "description": "Quota available; L4"})

        self.assertEqual(reasons, [])

    def test_queue_heat_parser_supports_numeric_fields_and_text(self):
        self.assertEqual(parse_queue_heat_percent({"name": "A", "queue_heat": "96%"}), 96)
        self.assertEqual(parse_queue_heat_percent({"name": "A2", "queueHeat": 116}), 116)
        self.assertEqual(parse_queue_heat_percent({"name": "A3", "queueHeatPercent": "116%"}), 116)
        self.assertEqual(parse_queue_heat_percent({"name": "A4", "usage": {"queue_heat": 116}}), 116)
        self.assertEqual(parse_queue_heat_percent({"name": "A5", "usage": {"queueHeatPercent": "116%"}}), 116)
        self.assertEqual(parse_queue_heat_percent({"name": "B", "description": "Queue heat: 104%"}), 104)
        self.assertEqual(parse_queue_heat_percent({"name": "C", "description": "队列热度 95%"}), 95)
        self.assertIsNone(parse_queue_heat_percent({"name": "D", "description": "Quota available; L4"}))

    def test_search_summary_exposes_lct_aliases(self):
        summary = summarize_search_usage(
            {
                "stages": {
                    "stage1": [
                        {
                            "allowed_tools": ["WebSearch", "WebFetch"],
                            "tool_calls": [{"id": "tc1", "name": "WebFetch"}],
                        }
                    ],
                    "stage2": [],
                    "stage3": {},
                }
            }
        )

        self.assertTrue(summary["lct_search_allowed"])
        self.assertTrue(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 1)
        self.assertEqual(summary["lct_web_tool_effective_calls"], 0)

    def test_search_summary_distinguishes_calls_from_effective_calls(self):
        summary = summarize_search_usage(
            {
                "stages": {
                    "stage1": [
                        {
                            "allowed_tools": ["WebSearch", "WebFetch"],
                            "tool_calls": [
                                {"id": "tc1", "name": "WebSearch"},
                                {"id": "tc2", "name": "WebSearch"},
                            ],
                            "web_tool_result_call_ids": ["tc1", "tc2"],
                            "lct_search_conversion_errors": 2,
                        }
                    ],
                    "stage2": [],
                    "stage3": {},
                }
            }
        )

        self.assertEqual(summary["lct_web_tool_calls"], 2)
        self.assertEqual(summary["lct_web_tool_result_calls"], 2)
        self.assertEqual(summary["lct_search_conversion_errors"], 2)
        self.assertEqual(summary["lct_web_tool_effective_calls"], 0)

        partial = summarize_search_usage(
            {
                "stages": {
                    "stage1": [
                        {
                            "allowed_tools": ["WebSearch", "WebFetch"],
                            "tool_calls": [
                                {"id": "tc1", "name": "WebSearch"},
                                {"id": "tc2", "name": "WebSearch"},
                            ],
                            "web_tool_result_call_ids": ["tc1", "tc2"],
                            "lct_search_conversion_errors": 1,
                        }
                    ],
                    "stage2": [],
                    "stage3": {},
                }
            }
        )

        self.assertEqual(partial["lct_web_tool_effective_calls"], 1)

    def test_search_summary_deduplicates_web_tool_calls_per_stage_record(self):
        summary = summarize_search_usage(
            {
                "stages": {
                    "stage1": [
                        {
                            "allowed_tools": ["WebSearch"],
                            "tool_calls": [{"id": "tc1", "name": "WebSearch"}],
                            "web_tool_result_call_ids": ["tc1"],
                            "lct_web_tool_effective_calls": 1,
                        },
                        {
                            "allowed_tools": ["WebSearch"],
                            "tool_calls": [{"id": "tc1", "name": "WebSearch"}],
                            "web_tool_result_call_ids": ["tc1"],
                            "lct_web_tool_effective_calls": 1,
                        },
                    ],
                    "stage2": [],
                    "stage3": {},
                }
            }
        )

        self.assertEqual(summary["lct_web_tool_calls"], 2)
        self.assertEqual(summary["lct_web_tool_effective_calls"], 2)

    def test_search_summary_clamps_persisted_effective_calls_to_observed_calls(self):
        summary = summarize_search_usage(
            {
                "stages": {
                    "stage1": [
                        {
                            "allowed_tools": ["WebSearch"],
                            "tool_calls": [{"id": "tc1", "name": "WebSearch"}],
                            "web_tool_result_call_ids": ["tc1"],
                            "lct_web_tool_effective_calls": 5,
                        }
                    ],
                    "stage2": [],
                    "stage3": {},
                }
            }
        )

        self.assertEqual(summary["lct_web_tool_calls"], 1)
        self.assertEqual(summary["lct_web_tool_effective_calls"], 1)

    def test_skill_docs_do_not_describe_stage1_as_six_member_default(self):
        for relative in (
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ):
            text = self.read_text(relative)
            self.assertNotIn("6 个成员模型", text, relative)
            self.assertIn("DeepSeek-V4-Pro, GPT-5.5, openrouter-3o", text, relative)

    def test_canonical_skill_and_readme_split_lct_and_agent_search_evidence(self):
        for relative in ("README.md", "skills/llm-council-for-trae/SKILL.md"):
            text = self.read_text(relative)
            for field in (
                "lct_search_allowed",
                "lct_search_used",
                "lct_web_tool_calls",
                "agent_external_search_allowed",
                "agent_external_search_used",
                "agent_sources",
                "agent_fact_pack_path",
                "agent_added_context",
                "final_answer_source",
            ):
                self.assertIn(field, text, relative)

    def test_readme_current_status_does_not_claim_six_member_direct_default(self):
        text = self.read_text("README.md")

        self.assertNotIn("模型阵容：6 成员", text)
        self.assertNotIn("subagent profile 已对齐 6 成员全阵容", text)
        self.assertIn("direct 默认 3 成员", text)

    def test_readme_documents_defined_roster_only_default_backfill(self):
        text = self.read_text("README.md")

        self.assertIn("models --recommend 只会从成员整体优先级中推荐可用模型", text)
        self.assertIn("默认 auto-backfill 只从成员整体优先级中选择候补", text)
        self.assertNotIn("当前 runtime safe models 生成 backfill candidates", text)
        self.assertNotIn("同 vendor fallback、`models --recommend --json` 和当前 runtime safe models", text)

    def test_subagent_profile_is_not_direct_default_source(self):
        text = self.read_text("docs/traecli-subagents.md")

        self.assertIn("不作为 direct 默认阵容的源头", text)
        self.assertIn("镜像 direct 默认 3 成员", text)
        self.assertIn("src/llm_council_for_trae/council.py", text)

    def test_benchmark_default_candidates_follow_current_priority_without_glm(self):
        from llm_council_for_trae.model_benchmark import DEFAULT_CANDIDATES

        self.assertEqual(
            DEFAULT_CANDIDATES,
            [
                "DeepSeek-V4-Pro",
                "GPT-5.5",
                "openrouter-3o",
                "GPT-5.4",
                "openrouter-2o",
                "Kimi-K2.6",
                "MiniMax-M2.7",
                "GPT-5.2",
                "openrouter-1o",
                "DeepSeek-V4-Flash",
                "Gemini-3.1-Pro-Preview",
                "Qwen3.6-Plus",
            ],
        )
        self.assertNotIn("GLM", ",".join(DEFAULT_CANDIDATES))

    def test_active_subagent_profile_excludes_glm_and_tracks_current_default(self):
        profile = json.loads(self.read_text("profiles/subagents.json"))
        member_models = [item["model"] for item in profile["members"]]
        agent_names = [item["agent"] for item in profile["members"]] + [profile["chairman"]["agent"]]

        self.assertEqual(member_models, DEFAULT_MEMBERS)
        self.assertEqual(profile["chairman"]["model"], DEFAULT_CHAIRMAN)
        self.assertNotIn("GLM", json.dumps(profile))
        self.assertFalse((REPO_ROOT / ".trae/agents/council-glm51.md").exists())
        for agent_name in agent_names:
            self.assertTrue((REPO_ROOT / f".trae/agents/{agent_name}.md").exists(), agent_name)


if __name__ == "__main__":
    unittest.main()
