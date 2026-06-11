from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from llm_council_for_trae.acp_runtime import AcpTraeCliRuntime
from llm_council_for_trae.cli import build_config, build_parser
from llm_council_for_trae.council import CouncilConfig, build_model_runtime, config_to_json
from llm_council_for_trae.provider import DirectTraeCliRuntime, TraeCliProvider


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


if __name__ == "__main__":
    unittest.main()
