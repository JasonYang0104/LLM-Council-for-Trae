from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_council_for_trae.provider import TraeCliProvider
from support.runtime_fakes import FakeProcess, RecordingSubprocessFactory, direct_stdout


class DirectStatusMatrixTests(unittest.TestCase):
    def run_provider(
        self,
        process: FakeProcess,
        *,
        model: str = "Model-X",
        member_tool_mode: str = "search_enabled",
    ):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                factory = RecordingSubprocessFactory([process])
                provider = TraeCliProvider(
                    runtime_command="traecli",
                    query_timeout=180,
                    member_tool_mode=member_tool_mode,
                )
                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", factory):
                    result = await provider._query_model_once(
                        model=model,
                        prompt="Prompt text",
                        run_id="run-status",
                        stage="stage1",
                        label="A",
                        output_dir=output_dir,
                    )
                meta = json.loads((output_dir / "A.meta.json").read_text(encoding="utf-8"))
                return result, meta

        return asyncio.run(_run())

    def test_nonzero_exit_code_uses_stderr_error(self):
        result, meta = self.run_provider(FakeProcess(stderr=b"runtime failed\n", returncode=1))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "runtime failed")
        self.assertEqual(meta["error"], "runtime failed")

    def test_empty_response_is_failed(self):
        result, _meta = self.run_provider(FakeProcess(stdout_lines=direct_stdout("Model-X", "")))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "empty model response")

    def test_model_mismatch_is_failed(self):
        result, _meta = self.run_provider(FakeProcess(stdout_lines=direct_stdout("Other-Model", "Answer")))

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "expected model Model-X, actual model Other-Model")

    def test_forbidden_tool_call_overrides_clean_response(self):
        result, meta = self.run_provider(
            FakeProcess(
                stdout_lines=direct_stdout(
                    "Model-X",
                    "Answer",
                    [{"id": "tc1", "name": "Bash", "arguments": "{\"command\":\"pwd\"}", "turn_index": 1}],
                )
            ),
            member_tool_mode="answer_only",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "tool_contaminated: forbidden tool call(s): Bash")
        self.assertEqual(meta["forbidden_tool_calls"][0]["name"], "Bash")

    def test_tool_budget_kill_records_budget_status_but_keeps_process_exit_error(self):
        tool_calls = [
            {"id": f"tc{i}", "name": "WebSearch", "arguments": "{}", "turn_index": 1}
            for i in range(46)
        ]
        result, meta = self.run_provider(
            FakeProcess(stdout_lines=direct_stdout("Model-X", "Answer", tool_calls), returncode=None)
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "traecli exited -9")
        self.assertEqual(meta["tool_budget_status"], "dropped_tool_budget")


if __name__ == "__main__":
    unittest.main()
