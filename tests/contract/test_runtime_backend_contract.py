from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from llm_council_for_trae.acp_runtime import AcpTraeCliRuntime
from llm_council_for_trae.cli import build_config, build_parser
from llm_council_for_trae.council import (
    CouncilConfig,
    build_model_runtime,
    config_to_json,
    ensure_stage1_stream_sidecar,
    stage2_collect_rankings,
    synthetic_failed_call,
)
from llm_council_for_trae.provider import DirectTraeCliRuntime, ModelCallResult, TraeCliProvider
from llm_council_for_trae.store import ArtifactStore


class FakeAcpRuntime:
    async def query_model(self, *, model, prompt, run_id, stage, label, output_dir, agent=None, query_timeout=None):
        transcript_path = Path(output_dir) / f"{label}.acp.transcript.jsonl"
        transcript_path.write_text(
            "\n".join(
                [
                    json.dumps({"direction": "client_to_server", "method": "initialize", "id": 1}),
                    json.dumps({"direction": "client_to_server", "method": "session/new", "id": 2}),
                    json.dumps({"direction": "client_to_server", "method": "session/prompt", "id": 3, "params": {"model": model}}),
                    json.dumps(
                        {
                            "direction": "server_to_client",
                            "method": "session/update",
                            "params": {
                                "model": model,
                                "content": "Review.\n\nFINAL RANKING:\n1. Response A",
                            },
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return ModelCallResult(
            expected_model=model,
            actual_model=model,
            response="Review.\n\nFINAL RANKING:\n1. Response A",
            status="ok",
            session_id=f"{run_id}-{stage}-{label}",
            command=["fake-traecli", "acp", "serve"],
            exit_code=0,
            stdout_path=transcript_path.name,
            stderr_path=f"{label}.acp.stderr.log",
            member_tool_mode="answer_only",
            runtime_backend="acp",
            enforcement_method="acp_disabled_tool_permission_broker",
            enforcement_proof="transcript_permission_evidence",
            disabled_tools=["WebSearch", "Bash"],
            acp_transcript_path=f"{Path(output_dir).name}/{transcript_path.name}",
            acp_startup_status="ok",
        )


class RuntimeBackendContractTests(unittest.TestCase):
    def test_council_config_defaults_to_direct_runtime_backend(self):
        config = CouncilConfig(members=["M1"], chairman="Chair")

        self.assertEqual(config.runtime_backend, "direct")
        self.assertEqual(config.acp_startup_timeout, 30)

    def test_build_config_accepts_runtime_backend_and_acp_startup_timeout(self):
        args = build_parser().parse_args([
            "run",
            "--input",
            "question.md",
            "--default-models",
            "--runtime-backend",
            "acp",
            "--acp-startup-timeout",
            "12",
        ])

        config = build_config(args)

        self.assertEqual(config.runtime_backend, "acp")
        self.assertEqual(config.acp_startup_timeout, 12)

    def test_config_to_json_records_runtime_backend(self):
        config = CouncilConfig(
            members=["M1"],
            chairman="Chair",
            runtime_backend="acp",
            acp_startup_timeout=12,
        )

        payload = config_to_json(config)

        self.assertEqual(payload["runtime_backend"], "acp")
        self.assertEqual(payload["acp_startup_timeout"], 12)

    def test_acp_runtime_backend_rejects_subagent_provider_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "subagent-profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "provider_mode": "subagent",
                        "members": [{"agent": "council-a", "model": "M1"}],
                        "chairman": {"agent": "chair", "model": "Chair"},
                    }
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args([
                "run",
                "--input",
                "question.md",
                "--profile",
                str(profile_path),
                "--runtime-backend",
                "acp",
            ])

            with self.assertRaisesRegex(ValueError, "runtime_backend=acp.*provider_mode=subagent"):
                build_config(args)

    def test_direct_runtime_backend_is_current_traecli_provider(self):
        self.assertIs(DirectTraeCliRuntime, TraeCliProvider)

        runtime = build_model_runtime(
            CouncilConfig(members=["M1"], chairman="Chair", runtime_backend="direct"),
            provider_runtime_cwd=None,
            provider_member_tool_mode="answer_only",
        )

        self.assertIsInstance(runtime, TraeCliProvider)
        self.assertEqual(runtime.member_tool_mode, "answer_only")

    def test_acp_runtime_backend_builds_experimental_acp_runtime(self):
        runtime = build_model_runtime(
            CouncilConfig(members=["M1"], chairman="Chair", runtime_backend="acp", acp_startup_timeout=12),
            provider_runtime_cwd=None,
            provider_member_tool_mode="answer_only",
        )

        self.assertIsInstance(runtime, AcpTraeCliRuntime)
        self.assertEqual(runtime.member_tool_mode, "answer_only")
        self.assertEqual(runtime.acp_startup_timeout, 12)

    def test_acp_stage1_sidecar_does_not_synthesize_direct_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-acp-stage1")
            call = ModelCallResult(
                expected_model="M1",
                actual_model="M1",
                response="Answer",
                status="ok",
                session_id="session",
                command=["fake-traecli", "acp", "serve"],
                exit_code=0,
                stdout_path="A.acp.transcript.jsonl",
                stderr_path="A.acp.stderr.log",
                runtime_backend="acp",
                enforcement_method="acp_disabled_tool_permission_broker",
                enforcement_proof="transcript_permission_evidence",
                acp_transcript_path="stage1/A.acp.transcript.jsonl",
                acp_startup_status="ok",
            )

            ensure_stage1_stream_sidecar(store, "A", call)

            self.assertFalse((store.root / "stage1" / "A.traecli.stream.jsonl").exists())

    def test_acp_stage2_sidecar_does_not_synthesize_direct_stream(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                store = ArtifactStore.create(Path(tmp), "run-acp-stage2")
                config = CouncilConfig(
                    members=["M1"],
                    chairman="Chair",
                    runtime_backend="acp",
                    member_tool_mode="answer_only",
                )
                stage1_results = [
                    {
                        "label": "Response A",
                        "file_label": "A",
                        "model": "M1",
                        "status": "ok",
                        "response": "Stage 1 answer",
                        "attempt_role": "primary",
                    }
                ]

                await stage2_collect_rankings("Question", stage1_results, config, FakeAcpRuntime(), store)

                return (
                    (store.root / "stage2" / "A.acp.transcript.jsonl").exists(),
                    (store.root / "stage2" / "A.traecli.stream.jsonl").exists(),
                )

        acp_transcript_exists, direct_stream_exists = asyncio.run(_run())

        self.assertTrue(acp_transcript_exists)
        self.assertFalse(direct_stream_exists)

    def test_acp_synthetic_failed_call_uses_acp_evidence_defaults(self):
        config = CouncilConfig(
            members=["M1"],
            chairman="Chair",
            runtime_backend="acp",
            member_tool_mode="answer_only",
        )

        call = synthetic_failed_call(
            "M1",
            "cancelled_by_stage_timeout",
            config,
            stdout_path="A.acp.transcript.jsonl",
            stderr_path="A.acp.stderr.log",
            acp_transcript_path="stage1/A.acp.transcript.jsonl",
        )

        self.assertEqual(call.runtime_backend, "acp")
        self.assertEqual(call.permission_mode, "acp_permission_broker")
        self.assertEqual(call.enforcement_method, "acp_disabled_tool_permission_broker")
        self.assertEqual(call.enforcement_proof, "transcript_permission_evidence")
        self.assertEqual(call.disabled_tools, call.disallowed_tools)
        self.assertEqual(call.acp_transcript_path, "stage1/A.acp.transcript.jsonl")
        self.assertEqual(call.acp_startup_status, "ok")


if __name__ == "__main__":
    unittest.main()
