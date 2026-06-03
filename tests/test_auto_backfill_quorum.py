from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_run_full_council_stage1_backfill_appends_without_overwriting_failures(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage1-backfill")
            config = CouncilConfig(
                members=["M1", "M2", "M3", "M4"],
                chairman="Chair",
                min_valid_members=3,
                stage1_max_retries=0,
                backfill_members=["M5", "M6"],
                stage2_timeout=1,
            )
            seen_stage1 = []

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    model = kwargs["model"]
                    if stage == "stage1":
                        seen_stage1.append((model, kwargs["label"]))
                        status = "ok" if model in {"M1", "M2", "M5"} else "failed"
                        return ModelCallResult(
                            expected_model=model,
                            actual_model=model if status == "ok" else None,
                            response=f"answer {model}" if status == "ok" else "",
                            status=status,
                            session_id=f"s-{model}",
                            command=["traecli"],
                            exit_code=0 if status == "ok" else 1,
                            stdout_path="out.jsonl",
                            stderr_path="err.log",
                            error=None if status == "ok" else "timeout",
                        )
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=model,
                        response="unused",
                        status="ok",
                        session_id="s",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                    )

            async def fake_stage2(user_query, stage1_results, config, provider, store):
                label_to_model = {r["label"]: r["model"] for r in stage1_results}
                return [], label_to_model

            async def fake_stage3(user_query, stage1_results, stage2_results, config, provider, store, fallback_chain=None):
                return {
                    "model": "Chair",
                    "expected_model": "Chair",
                    "actual_model": "Chair",
                    "response": "final",
                    "status": "ok",
                    "error": None,
                    "prompt_path": "stage3/chairman.prompt.md",
                    "response_path": "stage3/final.md",
                    "json_path": "stage3/final.json",
                }, {"attempted": ["Chair"], "used": "Chair", "fallback_from": None, "failed_attempts": []}

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": name} for name in ["M1", "M2", "M3", "M4", "M5", "M6", "Chair"]],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        with patch.object(council_mod, "stage2_collect_rankings", fake_stage2):
                            with patch.object(council_mod, "stage3_synthesize_final", fake_stage3):
                                manifest = await run_full_council("question", config, store)

            stage1 = manifest["stages"]["stage1"]
            self.assertEqual([(r["model"], r["file_label"], r["status"]) for r in stage1], [
                ("M1", "A", "ok"),
                ("M2", "B", "ok"),
                ("M3", "C", "failed"),
                ("M4", "D", "failed"),
                ("M5", "E", "ok"),
            ])
            self.assertEqual(seen_stage1, [("M1", "A"), ("M2", "B"), ("M3", "C"), ("M4", "D"), ("M5", "E")])
            self.assertEqual(stage1[-1]["attempt_role"], "backfill")
            self.assertEqual(manifest["metadata"]["quorum"]["effective_stage1_members"], ["M1", "M2", "M5"])
            self.assertTrue(manifest["metadata"]["quorum"]["normal_quorum_met"])
            self.assertEqual(manifest["metadata"]["quorum"]["backfill_attempted"], ["M5"])

        import asyncio
        asyncio.run(_run())

    def test_run_full_council_stage1_low_quorum_degraded_when_backfill_exhausted(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage1-low-quorum")
            config = CouncilConfig(
                members=["M1", "M2", "M3", "M4"],
                chairman="Chair",
                min_valid_members=3,
                stage1_max_retries=0,
                backfill_members=["M5"],
                low_quorum_floor=2,
                stage2_timeout=1,
            )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    model = kwargs["model"]
                    status = "ok" if model in {"M1", "M2"} else "failed"
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=model if status == "ok" else None,
                        response=f"answer {model}" if status == "ok" else "",
                        status=status,
                        session_id=f"s-{model}",
                        command=["traecli"],
                        exit_code=0 if status == "ok" else 1,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                        error=None if status == "ok" else "timeout",
                    )

            async def fake_stage2(user_query, stage1_results, config, provider, store):
                label_to_model = {r["label"]: r["model"] for r in stage1_results}
                reviews = [
                    {
                        "reviewer_label": r["file_label"],
                        "model": r["model"],
                        "expected_model": r["model"],
                        "actual_model": r["model"],
                        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                        "parsed_ranking": ["Response A", "Response B"],
                        "parse_status": "ok",
                        "status": "ok",
                        "error": None,
                    }
                    for r in stage1_results
                ]
                return reviews, label_to_model

            async def fake_stage3(user_query, stage1_results, stage2_results, config, provider, store, fallback_chain=None):
                return {
                    "model": "Chair",
                    "expected_model": "Chair",
                    "actual_model": "Chair",
                    "response": "final",
                    "status": "ok",
                    "error": None,
                    "prompt_path": "stage3/chairman.prompt.md",
                    "response_path": "stage3/final.md",
                    "json_path": "stage3/final.json",
                }, {"attempted": ["Chair"], "used": "Chair", "fallback_from": None, "failed_attempts": []}

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": name} for name in ["M1", "M2", "M3", "M4", "M5", "Chair"]],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        with patch.object(council_mod, "stage2_collect_rankings", fake_stage2):
                            with patch.object(council_mod, "stage3_synthesize_final", fake_stage3):
                                manifest = await run_full_council("question", config, store)

            self.assertEqual(manifest["status"], "degraded_ok")
            quorum = manifest["metadata"]["quorum"]
            self.assertEqual(quorum["effective_valid_members"], 2)
            self.assertFalse(quorum["normal_quorum_met"])
            self.assertTrue(quorum["low_quorum_used"])
            self.assertEqual(quorum["backfill_attempted"], ["M5"])

        import asyncio
        asyncio.run(_run())

    def test_stage2_reviewers_default_to_valid_stage1_models(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, stage2_collect_rankings
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage2-eligible")
            config = CouncilConfig(members=["M1", "M2", "M3"], chairman="Chair", stage2_timeout=1)
            seen = []

            async def query_model(**kwargs):
                seen.append((kwargs["model"], kwargs["label"]))
                return ModelCallResult(
                    expected_model=kwargs["model"],
                    actual_model=kwargs["model"],
                    response="FINAL RANKING:\n1. Response A\n2. Response B",
                    status="ok",
                    session_id="s",
                    command=["traecli"],
                    exit_code=0,
                    stdout_path="out.jsonl",
                    stderr_path="err.log",
                )

            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = query_model
            stage1_results = [
                {"label": "Response A", "file_label": "A", "model": "M1", "response": "A", "status": "ok"},
                {"label": "Response B", "file_label": "B", "model": "M2", "response": "B", "status": "ok"},
                {"label": "Response C", "file_label": "C", "model": "M3", "response": "", "status": "failed"},
            ]

            stage2_results, label_to_model = await stage2_collect_rankings("question", stage1_results, config, provider, store)

            self.assertEqual(seen, [("M1", "A"), ("M2", "B")])
            self.assertEqual(label_to_model, {"Response A": "M1", "Response B": "M2"})
            self.assertEqual([r["reviewer_label"] for r in stage2_results], ["A", "B"])
            self.assertTrue(all(r["reviewer_eligible"] for r in stage2_results))

        import asyncio
        asyncio.run(_run())

    def test_run_full_council_stage2_reviewer_failure_backfills_reviewer_only_when_stage1_quorum_met(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage2-backfill")
            config = CouncilConfig(
                members=["M1", "M2", "M3"],
                chairman="Chair",
                min_valid_members=3,
                stage1_max_retries=0,
                backfill_members=["M4"],
                stage2_timeout=1,
            )
            calls = []

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    model = kwargs["model"]
                    calls.append((stage, model, kwargs["label"]))
                    if stage == "stage1":
                        return ModelCallResult(
                            expected_model=model,
                            actual_model=model,
                            response=f"answer {model}",
                            status="ok",
                            session_id=f"s-{model}",
                            command=["traecli"],
                            exit_code=0,
                            stdout_path="out.jsonl",
                            stderr_path="err.log",
                        )
                    status = "failed" if stage == "stage2" and model == "M2" else "ok"
                    ranking = "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=model if status == "ok" else None,
                        response=ranking if status == "ok" else "",
                        status=status,
                        session_id=f"s-{model}",
                        command=["traecli"],
                        exit_code=0 if status == "ok" else 1,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                        error=None if status == "ok" else "timeout",
                    )

            async def fake_stage3(user_query, stage1_results, stage2_results, config, provider, store, fallback_chain=None):
                return {
                    "model": "Chair",
                    "expected_model": "Chair",
                    "actual_model": "Chair",
                    "response": "final",
                    "status": "ok",
                    "error": None,
                    "prompt_path": "stage3/chairman.prompt.md",
                    "response_path": "stage3/final.md",
                    "json_path": "stage3/final.json",
                }, {"attempted": ["Chair"], "used": "Chair", "fallback_from": None, "failed_attempts": []}

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": name} for name in ["M1", "M2", "M3", "M4", "Chair"]],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        with patch.object(council_mod, "stage3_synthesize_final", fake_stage3):
                            manifest = await run_full_council("question", config, store)

            self.assertNotIn(("stage1", "M4", "D"), calls)
            self.assertIn(("stage2", "M4", "R4"), calls)
            self.assertEqual(
                [(r["model"], r["file_label"]) for r in manifest["stages"]["stage1"]],
                [("M1", "A"), ("M2", "B"), ("M3", "C")],
            )
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["backfill_reviewers"], ["M4"])
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["reviewer_only_backfill"], True)
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["reviewer_backfill_attempted"], ["M4"])
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["review_subject_count"], 3)
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["reviewer_count"], 3)
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["stage1_backfill_members"], [])
            self.assertEqual(manifest["metadata"]["stage2_reviewers"]["stage2_reviewer_backfill"], ["M4"])
            self.assertEqual(manifest["metadata"]["quorum"]["effective_stage1_members"], ["M1", "M2", "M3"])
            self.assertEqual(
                [r["model"] for r in manifest["stages"]["stage2"]],
                ["M1", "M2", "M3", "M4"],
            )
            backfill_review = manifest["stages"]["stage2"][-1]
            self.assertEqual(backfill_review["reviewer_label"], "R4")
            self.assertEqual(backfill_review["reviewer_source"], "stage2_reviewer_backfill")
            self.assertEqual(backfill_review["attempt_role"], "reviewer_backfill")
            self.assertEqual(backfill_review["parsed_ranking"], ["Response A", "Response B", "Response C"])
            self.assertNotIn("Response D", backfill_review["ranking"])
            self.assertFalse(store.path("stage1", "D.response.md").exists())
            self.assertFalse(store.path("stage2", "D.review.json").exists())
            self.assertTrue(store.path("stage2", "R4.review.json").exists())
            self.assertEqual(
                json.loads(store.path("stage2", "label_to_model.json").read_text(encoding="utf-8")),
                {"Response A": "M1", "Response B": "M2", "Response C": "M3"},
            )
            sidecar_aggregate = json.loads(store.path("stage2", "aggregate.json").read_text(encoding="utf-8"))
            self.assertEqual(sidecar_aggregate, manifest["metadata"]["aggregate_rankings"])
            self.assertEqual([row["rankings_count"] for row in sidecar_aggregate], [3, 3, 3])

        import asyncio
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
