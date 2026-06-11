from __future__ import annotations

import unittest

from contract.test_tool_policy_golden import EXPECTED_TOOL_POLICIES
from llm_council_for_trae.provider import TraeCliProvider


class DirectCommandGoldenTests(unittest.TestCase):
    def test_build_command_matches_frozen_argv_for_each_tool_mode(self):
        for mode, policy in EXPECTED_TOOL_POLICIES.items():
            with self.subTest(mode=mode):
                provider = TraeCliProvider(
                    runtime_command="traecli",
                    query_timeout=180,
                    member_tool_mode=mode,
                )

                command = provider._build_command(
                    model="Model-X",
                    prompt="Prompt text",
                    run_id="run",
                    stage="stage1",
                    label="A",
                    session_id="sid",
                    query_timeout=42,
                )

                expected = [
                    "traecli", "-p", "Prompt text", "-c", "model.name=Model-X",
                    "--output-format", "stream-json", "--query-timeout", "42s",
                    "--session-id", "sid",
                ]
                for tool in policy["allowed"]:
                    expected.extend(["--allowed-tool", tool])
                for tool in policy["disallowed"]:
                    expected.extend(["--disallowed-tool", tool])
                self.assertEqual(command, expected)

    def test_build_command_appends_yolo_only_when_requested(self):
        provider = TraeCliProvider(
            runtime_command="traecli",
            query_timeout=180,
            use_yolo=True,
            member_tool_mode="answer_only",
        )

        command = provider._build_command(
            model="Model-X",
            prompt="Prompt text",
            run_id="run",
            stage="stage1",
            label="A",
            session_id="sid",
            query_timeout=42,
        )

        self.assertEqual(command[-1], "--yolo")


if __name__ == "__main__":
    unittest.main()
