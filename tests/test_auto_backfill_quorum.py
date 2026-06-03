from __future__ import annotations

import unittest


class AutoBackfillQuorumTests(unittest.TestCase):
    def test_backfill_candidates_filter_runtime_models_and_prefer_same_vendor_fallback(self):
        from llm_council_for_trae.model_selection import build_backfill_candidates

        candidates = build_backfill_candidates(
            [
                {"name": "Kimi-K2.6"},
                {"name": "MiniMax-M2.7"},
                {"name": "MiniMax-M2.5"},
                {"name": "Qwen3.6-Plus"},
                {"name": "Gemini-3.1-Pro-Preview"},
                {"name": "Seed-Dogfooding-2.0"},
                {"name": "GPT-5.5"},
                {"name": "Beta-Reasoner"},
                {"name": "GPT-5.4", "description": "Queue heat 104%"},
                {"name": "Already-Tried"},
            ],
            primary_members=["Kimi-K2.6", "MiniMax-M2.7"],
            attempted_models=["Already-Tried"],
            failed_models=["MiniMax-M2.7"],
            chairman="Kimi-K2.6",
        )

        self.assertEqual(candidates, ["MiniMax-M2.5", "Qwen3.6-Plus", "Gemini-3.1-Pro-Preview"])

    def test_explicit_backfill_candidates_keep_priority_but_still_filter_unsafe_and_attempted(self):
        from llm_council_for_trae.model_selection import build_backfill_candidates

        candidates = build_backfill_candidates(
            [
                {"name": "Kimi-K2.6"},
                {"name": "Qwen3.6-Plus"},
                {"name": "Gemini-3.1-Pro-Preview"},
                {"name": "Seed-Dogfooding-2.0"},
                {"name": "Already-Tried"},
            ],
            primary_members=["Kimi-K2.6"],
            attempted_models=["Already-Tried"],
            explicit_members=["Gemini-3.1-Pro-Preview", "Seed-Dogfooding-2.0", "Qwen3.6-Plus", "Already-Tried"],
            chairman="Kimi-K2.6",
        )

        self.assertEqual(candidates, ["Gemini-3.1-Pro-Preview", "Qwen3.6-Plus"])

    def test_build_config_accepts_backfill_and_low_quorum_flags(self):
        from llm_council_for_trae.cli import build_config, build_parser, resolve_run_model_choice

        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--input",
            "question.md",
            "--default-models",
            "--backfill-members",
            "Qwen3.6-Plus,Gemini-3.1-Pro-Preview",
            "--no-auto-backfill",
            "--low-quorum-floor",
            "2",
        ])
        args.selected_model_choice = resolve_run_model_choice(args)
        config = build_config(args)

        self.assertEqual(config.backfill_members, ["Qwen3.6-Plus", "Gemini-3.1-Pro-Preview"])
        self.assertFalse(config.stage1_auto_backfill)
        self.assertFalse(config.stage2_auto_backfill)
        self.assertTrue(config.allow_low_quorum)
        self.assertEqual(config.low_quorum_floor, 2)


if __name__ == "__main__":
    unittest.main()
