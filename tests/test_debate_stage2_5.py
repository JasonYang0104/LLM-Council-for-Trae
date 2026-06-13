from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_council_for_trae.cli import build_config, build_parser
from llm_council_for_trae.council import (
    CouncilConfig,
    build_stage2_5_prompt,
    build_stage3_prompt,
    run_full_council,
)
from llm_council_for_trae.html_export import export_html, render_html
from llm_council_for_trae.models import RuntimeHealth
from llm_council_for_trae.store import ArtifactStore
from llm_council_for_trae.validation import validate_run
from support.runtime_fakes import FakeRuntime, ScriptedReply


def health_for(models: list[str]) -> RuntimeHealth:
    return RuntimeHealth(
        ok=True,
        command="fake-traecli",
        version="fake 1.0",
        doctor_exit_code=0,
        doctor={"status": "ok"},
        models=[{"name": model} for model in models],
        errors=[],
        warnings=[],
        ignored_errors=[],
    )


def direct_script(
    *,
    rebuttal_b_status: str = "ok",
    all_rebuttals_fail: bool = False,
) -> dict[tuple[str, str], ScriptedReply]:
    status_a = "failed" if all_rebuttals_fail else "ok"
    status_b = "failed" if all_rebuttals_fail else rebuttal_b_status
    status_c = "failed" if all_rebuttals_fail else "ok"
    return {
        ("stage1", "A"): ScriptedReply("A answer."),
        ("stage1", "B"): ScriptedReply("B answer."),
        ("stage1", "C"): ScriptedReply("C answer."),
        ("stage2", "A"): ScriptedReply("Response B misses a caveat.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"),
        ("stage2", "B"): ScriptedReply("Response A is strong.\n\nFINAL RANKING:\n1. Response A\n2. Response C\n3. Response B"),
        ("stage2", "C"): ScriptedReply("Response C is concise.\n\nFINAL RANKING:\n1. Response C\n2. Response A\n3. Response B"),
        ("stage2_5", "A"): ScriptedReply("A rebuttal: I accept one criticism.", status=status_a, error=None if status_a == "ok" else "rebuttal failed"),
        ("stage2_5", "B"): ScriptedReply("B rebuttal: I revise the caveat.", status=status_b, error=None if status_b == "ok" else "rebuttal failed"),
        ("stage2_5", "C"): ScriptedReply("C rebuttal: I maintain my position.", status=status_c, error=None if status_c == "ok" else "rebuttal failed"),
        ("stage3", "final"): ScriptedReply("Final with rebuttal context."),
    }


async def run_fake_debate(script: dict[tuple[str, str], ScriptedReply]) -> tuple[dict, ArtifactStore, FakeRuntime, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    store = ArtifactStore.create(Path(tmp.name), "run-debate")
    fake_runtime = FakeRuntime(script, member_tool_mode="search_enabled")
    config = CouncilConfig(
        members=["Model-A", "Model-B", "Model-C"],
        chairman="Chair-Model",
        runtime_command="fake-traecli",
        runtime_cwd="/tmp/lct-debate-cwd",
        runtime_backend="direct",
        min_valid_members=3,
        target_valid_members=3,
        chairman_fallback=[],
        stage2_timeout=30,
        chairman_timeout=45,
        chairman_contribution_enabled=False,
        debate_enabled=True,
    )
    with patch(
        "llm_council_for_trae.council.runtime_doctor",
        return_value=health_for(["Model-A", "Model-B", "Model-C", "Chair-Model"]),
    ):
        with patch("llm_council_for_trae.council.build_model_runtime", return_value=fake_runtime):
            manifest = await run_full_council("Report topic: Debate\n\nQuestion.", config, store)
    return manifest, store, fake_runtime, tmp


class DebateStage25Tests(unittest.TestCase):
    maxDiff = None

    def test_cli_accepts_debate_flag_and_default_is_false(self):
        parser = build_parser()
        default_args = parser.parse_args(["run", "--input", "question.md", "--default-models"])
        debate_args = parser.parse_args(["run", "--input", "question.md", "--default-models", "--debate"])

        self.assertFalse(build_config(default_args).debate_enabled)
        self.assertTrue(build_config(debate_args).debate_enabled)
        self.assertFalse(any(action.dest == "debate_rounds" for action in parser._actions))

    def test_rebuttal_prompt_strips_rankings_and_model_names(self):
        stage1 = [
            {"label": "Response A", "file_label": "A", "model": "Model-A", "response": "Model-A says alpha.", "status": "ok"},
            {"label": "Response B", "file_label": "B", "model": "Model-B", "response": "Model-B says beta.", "status": "ok"},
        ]
        stage2 = [
            {
                "model": "Model-A",
                "status": "ok",
                "ranking": "Model-B critique for Response B.\n\nFINAL RANKING:\n1. Response A\n2. Response B",
            }
        ]

        prompt = build_stage2_5_prompt("Question mentioning Model-A", stage1[1], stage2, stage1)

        self.assertIn("你的匿名回答标签：Response B", prompt)
        self.assertIn("评审 1", prompt)
        self.assertNotIn("FINAL RANKING:", prompt)
        self.assertNotIn("Model-A", prompt)
        self.assertNotIn("Model-B", prompt)

    def test_stage3_prompt_none_rebuttals_is_byte_identical(self):
        stage1 = [{"label": "Response A", "model": "Model-A", "response": "Answer A"}]
        stage2 = [{"model": "Model-A", "ranking": "Review\n\nFINAL RANKING:\n1. Response A"}]

        without_arg = build_stage3_prompt("Question", stage1, stage2, contribution_map_enabled=False)
        with_none = build_stage3_prompt("Question", stage1, stage2, contribution_map_enabled=False, rebuttal_results=None)

        self.assertEqual(with_none, without_arg)

    def test_debate_direct_fake_run_writes_artifacts_and_validates(self):
        manifest, store, runtime, tmp = asyncio.run(run_fake_debate(direct_script()))
        try:
            export_html(store)
            validation = validate_run(store)
            self.assertEqual(manifest["status"], "ok", manifest.get("failures"))
            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertEqual(len(manifest["stages"]["stage2_5"]), 3)
            self.assertEqual(manifest["metadata"]["debate"]["completed"], ["Model-A", "Model-B", "Model-C"])
            self.assertTrue((store.root / "stage2_5" / "B.rebuttal.prompt.md").exists())
            self.assertTrue((store.root / "stage2_5" / "B.rebuttal.md").exists())
            self.assertTrue((store.root / "stage2_5" / "B.meta.json").exists())
            self.assertTrue((store.root / "stage2_5" / "B.traecli.stream.jsonl").exists())
            self.assertIn("阶段 2.5 - 成员答辩", (store.root / "stage3" / "chairman.prompt.md").read_text(encoding="utf-8"))
            self.assertEqual([call["label"] for call in runtime.calls if call["stage"] == "stage2_5"], ["A", "B", "C"])
        finally:
            tmp.cleanup()

    def test_rebuttal_failure_warns_but_does_not_degrade_run(self):
        manifest, store, _runtime, tmp = asyncio.run(run_fake_debate(direct_script(rebuttal_b_status="failed")))
        try:
            export_html(store)
            validation = validate_run(store)
            self.assertEqual(manifest["status"], "ok", manifest.get("failures"))
            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertIn("Model-B", manifest["metadata"]["debate"]["failed"])
            self.assertTrue(any("stage2_5 rebuttal unavailable" in warning for warning in manifest["warnings"]))
            self.assertFalse(manifest["metadata"]["debate"]["failed_all"])
        finally:
            tmp.cleanup()

    def test_all_rebuttals_failed_continue_without_stage3_rebuttal_section(self):
        manifest, store, _runtime, tmp = asyncio.run(run_fake_debate(direct_script(all_rebuttals_fail=True)))
        try:
            export_html(store)
            validation = validate_run(store)
            self.assertEqual(manifest["status"], "ok", manifest.get("failures"))
            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertTrue(manifest["metadata"]["debate"]["failed_all"])
            self.assertNotIn("阶段 2.5 - 成员答辩", (store.root / "stage3" / "chairman.prompt.md").read_text(encoding="utf-8"))
        finally:
            tmp.cleanup()

    def test_html_renders_debate_section_and_summary(self):
        manifest = {
            "run_id": "run-html-debate",
            "status": "ok",
            "config": {"members": ["Model-A"], "chairman": "Chair", "runtime_backend": "direct", "debate_enabled": True},
            "metadata": {
                "aggregate_rankings": [],
                "debate": {"enabled": True, "rounds": 1, "completed": ["Model-A"], "failed": []},
            },
            "stages": {
                "stage1": [],
                "stage2": [],
                "stage2_5": [
                    {"label": "Response A", "file_label": "A", "model": "Model-A", "status": "ok", "response": "Rebuttal text."}
                ],
                "stage3": {"model": "Chair", "status": "ok"},
            },
            "warnings": [],
            "failures": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage3").mkdir()
            (root / "input.md").write_text("Report topic: Debate HTML\n", encoding="utf-8")
            (root / "stage3" / "final.md").write_text("Final\n", encoding="utf-8")
            (root / "stage3" / "chairman.prompt.md").write_text("Prompt\n", encoding="utf-8")

            html = render_html(root, manifest)

        self.assertIn('id="stage2_5"', html)
        self.assertIn("成员答辩", html)
        self.assertIn("Rebuttal text.", html)
        self.assertIn("completed 1", html)

    def test_validate_routes_stage2_5_acp_records_through_evidence_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-acp-stage2-5-missing-transcript")
            manifest = {
                "schema_version": 1,
                "run_id": store.root.name,
                "created_at": "2026-06-13T00:00:00Z",
                "updated_at": "2026-06-13T00:00:00Z",
                "status": "ok",
                "input_chars": 8,
                "config": {
                    "members": ["Model-A"],
                    "chairman": "Chair",
                    "provider_mode": "direct",
                    "runtime_command": "fake",
                    "query_timeout": 180,
                    "export_html": True,
                    "runtime_backend": "acp",
                    "debate_enabled": True,
                },
                "artifacts": {"html": "html/index.html"},
                "metadata": {
                    "label_to_model": {"Response A": "Model-A"},
                    "aggregate_rankings": [],
                    "debate": {
                        "enabled": True,
                        "rounds": 1,
                        "participants": ["Model-A"],
                        "completed": ["Model-A"],
                        "failed": [],
                        "failed_all": False,
                    },
                },
                "stages": {
                    "stage1": [
                        acp_stage_record("stage1/A.acp.transcript.jsonl") | {"label": "Response A", "file_label": "A", "response": "A answer."}
                    ],
                    "stage2": [
                        acp_stage_record("stage2/A.acp.transcript.jsonl")
                        | {
                            "reviewer_label": "A",
                            "ranking": "FINAL RANKING:\n1. Response A",
                            "parsed_ranking": ["Response A"],
                            "parse_status": "ok",
                            "review_path": "stage2/A.review.md",
                            "json_path": "stage2/A.review.json",
                        }
                    ],
                    "stage2_5": [
                        acp_stage_record("stage2_5/A.acp.transcript.jsonl")
                        | {
                            "label": "Response A",
                            "file_label": "A",
                            "response": "A rebuttal.",
                            "prompt_path": "stage2_5/A.rebuttal.prompt.md",
                            "response_path": "stage2_5/A.rebuttal.md",
                            "meta_path": "stage2_5/A.meta.json",
                        }
                    ],
                    "stage3": acp_stage_record("stage3/final.acp.transcript.jsonl")
                    | {
                        "model": "Chair",
                        "expected_model": "Chair",
                        "actual_model": "Chair",
                        "response": "Final",
                        "prompt_path": "stage3/chairman.prompt.md",
                        "response_path": "stage3/final.md",
                        "json_path": "stage3/final.json",
                    },
                },
                "warnings": [],
                "failures": [],
            }
            store.write_manifest(manifest)
            for relative in [
                "input.md",
                "config.json",
                "events.jsonl",
                "runtime/doctor.json",
                "runtime/traecli.models.json",
                "stage1/member.prompt.md",
                "stage1/A.response.md",
                "stage2/review.prompt.md",
                "stage2/label_to_model.json",
                "stage2/aggregate.json",
                "stage2/A.review.md",
                "stage2_5/A.rebuttal.prompt.md",
                "stage2_5/A.rebuttal.md",
                "stage3/chairman.prompt.md",
                "stage3/final.md",
                "html/index.html",
            ]:
                store.write_text(relative, "{}\n")
            transcript = acp_transcript()
            store.write_text("stage1/A.acp.transcript.jsonl", transcript)
            store.write_text("stage2/A.acp.transcript.jsonl", transcript)
            store.write_text("stage3/final.acp.transcript.jsonl", transcript)
            store.write_json("stage1/A.meta.json", acp_meta("stage1/A.acp.transcript.jsonl"))
            store.write_json("stage2/A.meta.json", acp_meta("stage2/A.acp.transcript.jsonl"))
            store.write_json("stage2/A.review.json", manifest["stages"]["stage2"][0])
            store.write_json("stage2_5/A.meta.json", acp_meta("stage2_5/A.acp.transcript.jsonl"))
            store.write_json("stage3/final.meta.json", acp_meta("stage3/final.acp.transcript.jsonl", model="Chair"))
            store.write_json("stage3/final.json", manifest["stages"]["stage3"])
            store.write_json("html/export.json", {"run_id": store.root.name, "generated_at": "2026-06-13T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})

            validation = validate_run(store)

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(
            any(check["name"] == "stage2_5.A_acp_transcript_file" for check in validation["failures"]),
            validation["failures"],
        )


def acp_transcript(model: str = "Model-A") -> str:
    events = [
        {"direction": "client_to_server", "method": "initialize", "id": 1},
        {"direction": "client_to_server", "method": "session/new", "id": 2},
        {"direction": "client_to_server", "method": "session/prompt", "id": 3, "params": {"model": model}},
        {"direction": "server_to_client", "method": "session/update", "params": {"model": model, "content": "answer"}},
    ]
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"


def acp_policy(transcript_path: str) -> dict:
    return {
        "member_tool_mode": "search_enabled",
        "allowed_tools": ["WebSearch", "WebFetch"],
        "disallowed_tools": ["Skill", "Agent"],
        "forbidden_tool_calls": [],
        "tool_calls": [],
        "tool_calls_count": 0,
        "turns_count": 1,
        "runtime_backend": "acp",
        "enforcement_method": "acp_disabled_tool_permission_broker",
        "enforcement_proof": "transcript_permission_evidence",
        "disabled_tools": ["Skill", "Agent"],
        "tool_permission_requests": [],
        "acp_transcript_path": transcript_path,
        "acp_startup_status": "ok",
    }


def acp_stage_record(transcript_path: str) -> dict:
    return {
        "model": "Model-A",
        "expected_model": "Model-A",
        "actual_model": "Model-A",
        "status": "ok",
        "error": None,
    } | acp_policy(transcript_path)


def acp_meta(transcript_path: str, model: str = "Model-A") -> dict:
    return {
        "expected_model": model,
        "actual_model": model,
        "response_chars": 6,
        "status": "ok",
        "session_id": "session",
        "command": ["traecli", "acp", "serve"],
        "exit_code": 0,
        "stdout_path": Path(transcript_path).name,
        "stderr_path": "stderr.log",
        "copied_session_files": {},
        "raw_model_markers": [model],
        "error": None,
        "captured_at": "2026-06-13T00:00:00Z",
        "permission_mode": "acp_permission_broker",
        "tool_budget_status": "ok",
        "assistant_content_chars_total": 6,
        "last_assistant_content_chars": 6,
        "raw_partial_recoverable": False,
    } | acp_policy(transcript_path)


if __name__ == "__main__":
    unittest.main()
