from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_council_for_trae.provider import TraeCliProvider
from support.runtime_fakes import FakeProcess, RecordingSubprocessFactory, direct_stdout


class DirectSpawnContractTests(unittest.TestCase):
    def test_query_model_uses_frozen_subprocess_spawn_kwargs(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                runtime_cwd = Path(tmp) / "runtime-cwd"
                runtime_cwd.mkdir()
                factory = RecordingSubprocessFactory([
                    FakeProcess(stdout_lines=direct_stdout("Model-X", "Answer"))
                ])
                provider = TraeCliProvider(
                    runtime_command="traecli",
                    query_timeout=180,
                    runtime_cwd=runtime_cwd,
                    member_tool_mode="search_enabled",
                )
                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", factory):
                    await provider.query_model(
                        model="Model-X",
                        prompt="Prompt text",
                        run_id="run-spawn",
                        stage="stage1",
                        label="A",
                        output_dir=Path(tmp) / "out",
                    )
                return factory.calls

        calls = asyncio.run(_run())

        self.assertEqual(len(calls), 1)
        cmd, kwargs = calls[0]
        self.assertEqual(cmd[:8], (
            "traecli", "-p", "Prompt text", "-c", "model.name=Model-X",
            "--output-format", "stream-json", "--query-timeout",
        ))
        self.assertEqual(cmd[8], "180s")
        self.assertEqual(kwargs["stdout"], asyncio.subprocess.PIPE)
        self.assertEqual(kwargs["stderr"], asyncio.subprocess.PIPE)
        self.assertTrue(str(kwargs["cwd"]).endswith("runtime-cwd"))
        self.assertEqual(kwargs["limit"], 10 * 1024 * 1024)
        self.assertEqual(kwargs["start_new_session"], os.name != "nt")

    def test_runtime_command_environment_override_is_part_of_direct_contract(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                factory = RecordingSubprocessFactory([
                    FakeProcess(stdout_lines=direct_stdout("Model-X", "Answer"))
                ])
                with patch.dict(os.environ, {"LLM_COUNCIL_FOR_TRAE_TRAECLI": "/custom/traecli"}):
                    provider = TraeCliProvider(runtime_command="traecli")
                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", factory):
                    await provider.query_model(
                        model="Model-X",
                        prompt="Prompt text",
                        run_id="run-env",
                        stage="stage1",
                        label="A",
                        output_dir=Path(tmp),
                    )
                return factory.calls

        calls = asyncio.run(_run())

        self.assertEqual(calls[0][0][0], "/custom/traecli")


if __name__ == "__main__":
    unittest.main()
