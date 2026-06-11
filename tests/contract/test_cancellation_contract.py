from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_council_for_trae.provider import TraeCliProvider
from support.runtime_fakes import FakeProcess, RecordingSubprocessFactory


class CancellationContractTests(unittest.TestCase):
    def test_in_flight_direct_query_propagates_cancel_and_writes_failed_sidecars(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                process = FakeProcess(blocking_stdout=True, returncode=None)
                factory = RecordingSubprocessFactory([process])
                provider = TraeCliProvider(runtime_command="traecli", query_timeout=180)

                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", factory):
                    task = asyncio.create_task(
                        provider.query_model(
                            model="Model-X",
                            prompt="Prompt text",
                            run_id="run-cancel",
                            stage="stage1",
                            label="A",
                            output_dir=output_dir,
                        )
                    )
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                meta = json.loads((output_dir / "A.meta.json").read_text(encoding="utf-8"))
                stream_exists = (output_dir / "A.traecli.stream.jsonl").exists()
                stderr_text = (output_dir / "A.traecli.stderr.log").read_text(encoding="utf-8")
                return process, meta, stream_exists, stderr_text

        process, meta, stream_exists, stderr_text = asyncio.run(_run())

        self.assertTrue(process.killed)
        self.assertEqual(meta["status"], "failed")
        self.assertEqual(meta["error"], "cancelled")
        self.assertEqual(meta["termination"]["termination_reason"], "cancelled")
        self.assertTrue(stream_exists)
        self.assertIn("Cancelled while waiting for traecli.", stderr_text)


if __name__ == "__main__":
    unittest.main()
