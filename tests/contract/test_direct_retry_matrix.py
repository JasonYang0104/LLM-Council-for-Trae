from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_council_for_trae.provider import TraeCliProvider
from support.runtime_fakes import FakeProcess, RecordingSubprocessFactory, direct_stdout


class DirectRetryMatrixTests(unittest.TestCase):
    def test_runtime_error_retries_once_and_preserves_first_error(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                factory = RecordingSubprocessFactory([
                    FakeProcess(stderr=b"transient failure\n", returncode=1),
                    FakeProcess(stdout_lines=direct_stdout("Model-X", "Recovered")),
                ])
                provider = TraeCliProvider(runtime_command="traecli", query_timeout=180)

                async def no_sleep(_seconds):
                    return None

                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", factory):
                    with patch("llm_council_for_trae.provider.asyncio.sleep", no_sleep):
                        result = await provider.query_model(
                            model="Model-X",
                            prompt="Prompt text",
                            run_id="run-retry",
                            stage="stage1",
                            label="A",
                            output_dir=Path(tmp),
                        )
                return result, factory

        result, factory = asyncio.run(_run())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.response, "Recovered")
        self.assertTrue(result.retried)
        self.assertEqual(result.retry_error, "transient failure")
        self.assertEqual(len(factory.calls), 2)

    def test_model_mismatch_does_not_retry(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                factory = RecordingSubprocessFactory([
                    FakeProcess(stdout_lines=direct_stdout("Other-Model", "Answer")),
                ])
                provider = TraeCliProvider(runtime_command="traecli", query_timeout=180)
                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", factory):
                    result = await provider.query_model(
                        model="Model-X",
                        prompt="Prompt text",
                        run_id="run-no-retry",
                        stage="stage1",
                        label="A",
                        output_dir=Path(tmp),
                    )
                return result, factory

        result, factory = asyncio.run(_run())

        self.assertEqual(result.status, "failed")
        self.assertIn("expected model Model-X", result.error)
        self.assertFalse(result.retried)
        self.assertEqual(len(factory.calls), 1)


if __name__ == "__main__":
    unittest.main()
