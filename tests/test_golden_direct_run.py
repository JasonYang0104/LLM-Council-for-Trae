from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_council_for_trae.council import CouncilConfig, run_full_council
from llm_council_for_trae.html_export import export_html
from llm_council_for_trae.models import RuntimeHealth
from llm_council_for_trae.store import ArtifactStore
from support.golden import snapshot_run
from support.runtime_fakes import FakeRuntime, ScriptedReply


GOLDEN_PATH = Path(__file__).parent / "golden" / "direct_full_run" / "snapshot.json"


STAGE3_FINAL_RESPONSE = """最终综合答案：A 和 B 的共同判断最可靠。

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "b1",
      "type": "paragraph",
      "text": "最终综合答案：A 和 B 的共同判断最可靠。",
      "attribution": {
        "kind": "multi_member_consensus",
        "members": ["Model-A", "Model-B"]
      }
    }
  ]
}
```
"""


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


async def build_direct_snapshot() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        store = ArtifactStore.create(Path(tmp), "direct-golden-run")
        script = {
            ("stage1", "A"): ScriptedReply("Response A: clear answer."),
            ("stage1", "B"): ScriptedReply("Response B: useful answer."),
            ("stage1", "C"): ScriptedReply("Response C: concise answer."),
            ("stage2", "A"): ScriptedReply("Review A.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C"),
            ("stage2", "B"): ScriptedReply("Review B.\n\nFINAL RANKING:\n1. Response B\n2. Response A\n3. Response C"),
            ("stage2", "C"): ScriptedReply("Review C.\n\nFINAL RANKING:\n1. Response A\n2. Response C\n3. Response B"),
            ("stage3", "final"): ScriptedReply(STAGE3_FINAL_RESPONSE),
        }
        fake_runtime = FakeRuntime(script, member_tool_mode="search_enabled")

        def runtime_factory(*args, **kwargs):
            fake_runtime.runtime_command = args[0] if args else kwargs.get("runtime_command", "fake-traecli")
            fake_runtime.query_timeout = args[1] if len(args) > 1 else kwargs.get("query_timeout", 180)
            fake_runtime.runtime_cwd = kwargs.get("runtime_cwd")
            fake_runtime.use_yolo = kwargs.get("use_yolo", False)
            fake_runtime.member_tool_mode = kwargs.get("member_tool_mode", "search_enabled")
            return fake_runtime

        config = CouncilConfig(
            members=["Model-A", "Model-B", "Model-C"],
            chairman="Chair-Model",
            runtime_command="fake-traecli",
            runtime_cwd="/tmp/lct-direct-golden-cwd",
            min_valid_members=3,
            target_valid_members=3,
            chairman_fallback=[],
            member_soft_checkpoint=30,
            member_quorum_checkpoint=60,
            member_hard_timeout=90,
            stage2_timeout=30,
            chairman_timeout=45,
        )
        with patch(
            "llm_council_for_trae.council.runtime_doctor",
            return_value=health_for(["Model-A", "Model-B", "Model-C", "Chair-Model"]),
        ):
            with patch("llm_council_for_trae.council.TraeCliProvider", runtime_factory):
                await run_full_council("Report topic: Direct golden\n\n请评估这个基线。", config, store)
        export_html(store)
        return snapshot_run(store.root)


class GoldenDirectRunTests(unittest.TestCase):
    maxDiff = None

    def test_direct_full_run_snapshot_matches_golden(self):
        snapshot = asyncio.run(build_direct_snapshot())
        expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

        self.assertEqual(snapshot, expected)

    def test_direct_full_run_snapshot_is_deterministic(self):
        first = asyncio.run(build_direct_snapshot())
        second = asyncio.run(build_direct_snapshot())

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
