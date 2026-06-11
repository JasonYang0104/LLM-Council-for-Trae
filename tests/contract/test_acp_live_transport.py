from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from llm_council_for_trae.acp_runtime import AcpTraeCliRuntime
from llm_council_for_trae.acp_transcript import parse_acp_transcript_text


FAKE_ACP_SERVER = '''#!/usr/bin/env python3
import json, os, sys, time


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


scenario = os.environ.get("FAKE_ACP_SCENARIO", "ok")
model = "Model-X"
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "-c" and i + 1 < len(args) and args[i + 1].startswith("model.name="):
        model = args[i + 1].split("=", 1)[1]

available = [m for m in os.environ.get("FAKE_ACP_AVAILABLE", model).split(",") if m]
current = os.environ.get("FAKE_ACP_CURRENT", model)

if scenario == "startup_hang":
    time.sleep(120)
    sys.exit(0)


def update(sid, payload):
    send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": payload}})


def chunk(sid, text):
    update(sid, {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})


while True:
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": 1, "agentCapabilities": {}}})
    elif method == "session/new":
        send({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "sessionId": "sess-fake",
                "models": {
                    "availableModels": [{"modelId": m, "name": m} for m in available],
                    "currentModelId": current,
                },
            },
        })
    elif method == "session/prompt":
        sid = msg["params"]["sessionId"]
        pid = msg["id"]
        if scenario == "prompt_hang":
            continue
        if scenario == "timeout_error":
            send({
                "jsonrpc": "2.0",
                "id": pid,
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"error": "failed to call agent: model '%s': context deadline exceeded; context deadline exceeded" % model},
                },
            })
            continue
        if scenario == "stop_max_tokens":
            chunk(sid, "partial answer")
            send({"jsonrpc": "2.0", "id": pid, "result": {"stopReason": "max_tokens"}})
            continue
        if scenario in ("permission_bash", "permission_websearch"):
            title = "bash" if scenario == "permission_bash" else "WebSearch"
            call_id = "call_fake_1"
            update(sid, {"sessionUpdate": "tool_call", "status": "in_progress", "title": title, "toolCallId": call_id, "rawInput": {"command": "pwd"}})
            send({
                "jsonrpc": "2.0",
                "id": 7,
                "method": "session/request_permission",
                "params": {
                    "sessionId": sid,
                    "options": [
                        {"kind": "allow_once", "optionId": "allow", "name": "Allow once"},
                        {"kind": "allow_once", "optionId": "session_level_allow", "name": "Allow all tools during this session"},
                        {"kind": "reject_once", "optionId": "reject", "name": "Reject"},
                    ],
                    "toolCall": {"title": title, "toolCallId": call_id, "rawInput": {"command": "pwd"}},
                },
            })
            decision = json.loads(sys.stdin.readline())
            option = (decision.get("result") or {}).get("outcome", {}).get("optionId")
            if option == "allow":
                update(sid, {"sessionUpdate": "tool_call_update", "status": "completed", "toolCallId": call_id})
            else:
                update(sid, {"sessionUpdate": "tool_call_update", "status": "failed", "toolCallId": call_id})
            chunk(sid, "Permission flow done.")
            send({"jsonrpc": "2.0", "id": pid, "result": {"stopReason": "end_turn"}})
            continue
        update(sid, {"availableCommands": [{"name": "init", "description": "x"}]})
        update(sid, {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "thinking"}})
        chunk(sid, "ACP ")
        chunk(sid, "live answer.")
        send({"jsonrpc": "2.0", "id": pid, "result": {"stopReason": "end_turn"}})
'''


class AcpLiveTransportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.marker = f"fake-acp-{uuid.uuid4().hex}"
        self.server_path = Path(self._tmp.name) / f"{self.marker}.py"
        self.server_path.write_text(FAKE_ACP_SERVER, encoding="utf-8")
        self.server_path.chmod(self.server_path.stat().st_mode | stat.S_IXUSR)
        self.output_dir = Path(self._tmp.name) / "out"

    def set_env(self, **env: str):
        for key, value in env.items():
            old = os.environ.get(key)
            os.environ[key] = value
            if old is None:
                self.addCleanup(os.environ.pop, key, None)
            else:
                self.addCleanup(os.environ.__setitem__, key, old)

    def make_runtime(self, **kwargs) -> AcpTraeCliRuntime:
        defaults = dict(
            runtime_command=str(self.server_path),
            query_timeout=30,
            member_tool_mode="search_enabled",
            acp_startup_timeout=10,
        )
        defaults.update(kwargs)
        return AcpTraeCliRuntime(**defaults)

    def run_query(self, runtime: AcpTraeCliRuntime, *, model: str = "Model-X"):
        async def _run():
            return await runtime.query_model(
                model=model,
                prompt="Prompt text",
                run_id="run-acp-live",
                stage="stage1",
                label="A",
                output_dir=self.output_dir,
            )

        return asyncio.run(_run())

    def read_meta(self) -> dict:
        return json.loads((self.output_dir / "A.meta.json").read_text(encoding="utf-8"))

    def read_transcript(self) -> str:
        return (self.output_dir / "A.acp.transcript.jsonl").read_text(encoding="utf-8")

    def assert_no_orphan(self):
        probe = subprocess.run(["pgrep", "-f", self.marker], capture_output=True, text=True)
        self.assertNotEqual(probe.returncode, 0, f"orphan fake acp server: {probe.stdout}")

    def test_live_ok_flow_maps_transcript_to_ok_result(self):
        self.set_env(FAKE_ACP_SCENARIO="ok")
        runtime = self.make_runtime()

        result = self.run_query(runtime)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.response, "ACP live answer.")
        self.assertEqual(result.actual_model, "Model-X")
        self.assertEqual(result.error, None)
        self.assertEqual(result.acp_startup_status, "ok")
        transcript_text = self.read_transcript()
        parsed = parse_acp_transcript_text(transcript_text)
        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(parsed.response, "ACP live answer.")
        meta = self.read_meta()
        self.assertEqual(meta["status"], "ok")
        self.assert_no_orphan()

    def test_live_command_records_model_policy_and_timeout_argv(self):
        self.set_env(FAKE_ACP_SCENARIO="ok")
        runtime = self.make_runtime()

        result = self.run_query(runtime)

        command = result.command
        self.assertEqual(command[:3], [str(self.server_path), "acp", "serve"])
        self.assertIn("model.name=Model-X", command)
        self.assertEqual(command[command.index("model.name=Model-X") - 1], "-c")
        self.assertIn("--query-timeout", command)
        self.assertIn("30s", command)
        for tool in runtime.allowed_tools:
            self.assertIn(tool, command[command.index("--allowed-tool") :])
        self.assertIn("--disallowed-tool", command)
        for tool in runtime.disallowed_tools:
            self.assertIn(tool, command)
        meta = self.read_meta()
        self.assertEqual(meta["command"], command)

    def test_live_permission_denied_for_forbidden_tool_keeps_result_ok(self):
        self.set_env(FAKE_ACP_SCENARIO="permission_bash")
        runtime = self.make_runtime(member_tool_mode="answer_only")

        result = self.run_query(runtime)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.response, "Permission flow done.")
        self.assertEqual(result.forbidden_tool_calls, [])
        self.assertEqual(result.tool_calls, [])
        self.assertEqual(len(result.tool_permission_requests), 1)
        permission = result.tool_permission_requests[0]
        self.assertEqual(permission["tool_name"], "Bash")
        self.assertEqual(permission["decision"], "deny")
        meta = self.read_meta()
        self.assertEqual(meta["tool_permission_requests"], parse_acp_transcript_text(self.read_transcript()).tool_permission_requests)

    def test_live_permission_allowed_for_allowed_tool(self):
        self.set_env(FAKE_ACP_SCENARIO="permission_websearch")
        runtime = self.make_runtime(member_tool_mode="search_enabled")

        result = self.run_query(runtime)

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.tool_permission_requests), 1)
        self.assertEqual(result.tool_permission_requests[0]["tool_name"], "WebSearch")
        self.assertEqual(result.tool_permission_requests[0]["decision"], "allow")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["name"], "WebSearch")
        self.assertEqual(result.forbidden_tool_calls, [])

    def test_live_server_side_query_timeout_maps_to_timeout_error(self):
        self.set_env(FAKE_ACP_SCENARIO="timeout_error")
        runtime = self.make_runtime()

        result = self.run_query(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "timeout")
        self.assertEqual(result.acp_startup_status, "ok")
        meta = self.read_meta()
        self.assertEqual(meta["error"], "timeout")
        self.assert_no_orphan()

    def test_live_client_deadline_guard_kills_hung_prompt(self):
        self.set_env(FAKE_ACP_SCENARIO="prompt_hang")
        runtime = self.make_runtime(query_timeout=1, acp_prompt_grace=1)

        result = self.run_query(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "timeout")
        self.assertEqual(result.termination.get("termination_reason"), "timeout")
        self.assert_no_orphan()

    def test_live_startup_hang_maps_to_acp_startup_failed(self):
        self.set_env(FAKE_ACP_SCENARIO="startup_hang")
        runtime = self.make_runtime(acp_startup_timeout=1)

        result = self.run_query(runtime)

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.error.startswith("acp_startup_failed:"), result.error)
        self.assertEqual(result.acp_startup_status, "failed")
        meta = self.read_meta()
        self.assertEqual(meta["acp_startup_status"], "failed")
        self.assert_no_orphan()

    def test_live_model_missing_from_available_models_fails_before_prompt(self):
        self.set_env(
            FAKE_ACP_SCENARIO="ok",
            FAKE_ACP_AVAILABLE="Other-A,Other-B",
            FAKE_ACP_CURRENT="Other-A",
        )
        runtime = self.make_runtime()

        result = self.run_query(runtime)

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.error.startswith("invalid_model:"), result.error)
        self.assert_no_orphan()

    def test_live_current_model_mismatch_fails(self):
        self.set_env(
            FAKE_ACP_SCENARIO="ok",
            FAKE_ACP_AVAILABLE="Model-X,Other-A",
            FAKE_ACP_CURRENT="Other-A",
        )
        runtime = self.make_runtime()

        result = self.run_query(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "expected model Model-X, actual model Other-A")

    def test_live_non_end_turn_stop_reason_fails_honestly(self):
        self.set_env(FAKE_ACP_SCENARIO="stop_max_tokens")
        runtime = self.make_runtime()

        result = self.run_query(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "acp_stop_reason: max_tokens")
        self.assert_no_orphan()

    def test_live_cancellation_preserves_partial_transcript_evidence(self):
        self.set_env(FAKE_ACP_SCENARIO="prompt_hang")
        runtime = self.make_runtime(query_timeout=60, acp_prompt_grace=60)

        async def _run():
            task = asyncio.create_task(
                runtime.query_model(
                    model="Model-X",
                    prompt="Prompt text",
                    run_id="run-acp-live",
                    stage="stage1",
                    label="A",
                    output_dir=self.output_dir,
                )
            )
            await asyncio.sleep(1.0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(_run())

        meta = self.read_meta()
        self.assertEqual(meta["status"], "failed")
        self.assertEqual(meta["error"], "cancelled")
        transcript_text = self.read_transcript()
        self.assertIn('"initialize"', transcript_text)
        self.assert_no_orphan()


if __name__ == "__main__":
    unittest.main()
