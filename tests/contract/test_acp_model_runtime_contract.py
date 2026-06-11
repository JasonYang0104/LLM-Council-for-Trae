from __future__ import annotations

import asyncio
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from llm_council_for_trae.acp_runtime import AcpStartupError, AcpTraeCliRuntime
from llm_council_for_trae.council import CouncilConfig, build_model_runtime
from llm_council_for_trae.provider import ModelRuntime, TraeCliProvider


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"


def transcript(
    *,
    model: str = "Model-X",
    response: str = "ACP answer.",
    permission: tuple[str, str] | None = None,
    tool_call: str | None = None,
) -> str:
    events: list[dict] = [
        {"direction": "client_to_server", "method": "initialize", "id": 1},
        {"direction": "client_to_server", "method": "session/new", "id": 2},
        {"direction": "client_to_server", "method": "session/prompt", "id": 3, "params": {"model": model}},
    ]
    if permission:
        tool_name, decision = permission
        events.extend(
            [
                {
                    "direction": "server_to_client",
                    "method": "session/request_permission",
                    "id": "perm-1",
                    "params": {"tool_name": tool_name, "arguments": {"command": "pwd"}},
                },
                {"direction": "client_to_server", "id": "perm-1", "result": {"decision": decision}},
            ]
        )
    update_params: dict = {"model": model, "content": response}
    if tool_call:
        update_params["tool_calls"] = [{"id": "tc-1", "name": tool_call, "arguments": {"command": "pwd"}}]
    events.append({"direction": "server_to_client", "method": "session/update", "params": update_params})
    return jsonl(*events)


class AcpModelRuntimeContractTests(unittest.TestCase):
    def run_runtime(self, runtime: AcpTraeCliRuntime, *, model: str = "Model-X"):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                result = await runtime.query_model(
                    model=model,
                    prompt="Prompt text",
                    run_id="run-acp",
                    stage="stage1",
                    label="A",
                    output_dir=output_dir,
                )
                meta = json.loads((output_dir / "A.meta.json").read_text(encoding="utf-8"))
                transcript_text = (output_dir / "A.acp.transcript.jsonl").read_text(encoding="utf-8")
                stderr_text = (output_dir / "A.acp.stderr.log").read_text(encoding="utf-8")
                return result, meta, transcript_text, stderr_text

        return asyncio.run(_run())

    def test_build_model_runtime_returns_acp_runtime_for_acp_backend(self):
        runtime = build_model_runtime(
            CouncilConfig(members=["Model-X"], chairman="Model-X", runtime_backend="acp"),
            provider_runtime_cwd=None,
            provider_member_tool_mode="search_enabled",
        )

        self.assertIsInstance(runtime, AcpTraeCliRuntime)

    def test_acp_query_model_signature_matches_model_runtime_port(self):
        acp_signature = inspect.signature(AcpTraeCliRuntime.query_model)
        direct_signature = inspect.signature(TraeCliProvider.query_model)
        protocol_signature = inspect.signature(ModelRuntime.query_model)

        acp_params = list(acp_signature.parameters)
        self.assertEqual(acp_params, list(direct_signature.parameters))
        self.assertEqual(acp_params, list(protocol_signature.parameters))

        for name, acp_param in acp_signature.parameters.items():
            direct_param = direct_signature.parameters[name]
            self.assertEqual(
                acp_param.kind,
                direct_param.kind,
                f"parameter {name!r} kind drifted from ModelRuntime port",
            )

    def test_acp_runtime_maps_clean_transcript_to_model_call_result(self):
        seen_requests = []

        def provider(request):
            seen_requests.append(request)
            return transcript(model=request.model, response="ACP answer.")

        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="search_enabled",
            transcript_provider=provider,
        )

        result, meta, transcript_text, stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.response, "ACP answer.")
        self.assertEqual(result.actual_model, "Model-X")
        self.assertEqual(result.command, ["fake-traecli", "acp", "serve"])
        self.assertEqual(result.stdout_path, "A.acp.transcript.jsonl")
        self.assertEqual(meta["status"], "ok")
        self.assertIn('"method": "session/update"', transcript_text)
        self.assertEqual(stderr_text, "")
        self.assertEqual(seen_requests[0].disabled_tools, runtime.disallowed_tools)
        self.assertEqual(seen_requests[0].allowed_tools, runtime.allowed_tools)

    def test_forbidden_permission_denied_keeps_result_ok_when_tool_is_not_used(self):
        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="answer_only",
            transcript_provider=lambda _request: transcript(permission=("Bash", "deny")),
        )

        result, meta, _transcript_text, _stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.forbidden_tool_calls, [])
        self.assertEqual(meta["status"], "ok")

    def test_forbidden_permission_allowed_fails_even_without_tool_call(self):
        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="answer_only",
            transcript_provider=lambda _request: transcript(permission=("Bash", "allow")),
        )

        result, meta, _transcript_text, stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "tool_contaminated: forbidden ACP permission allow(s): Bash")
        self.assertEqual(meta["error"], result.error)
        self.assertIn(result.error, stderr_text)

    def test_forbidden_tool_used_fails(self):
        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="search_enabled",
            transcript_provider=lambda _request: transcript(tool_call="Bash"),
        )

        result, meta, _transcript_text, _stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "tool_contaminated: forbidden tool call(s): Bash")
        self.assertEqual(meta["forbidden_tool_calls"][0]["name"], "Bash")

    def test_protocol_error_maps_to_failed_result(self):
        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="search_enabled",
            transcript_provider=lambda _request: "{bad-json\n",
        )

        result, meta, _transcript_text, stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "acp_protocol_error: invalid_json_line:1")
        self.assertEqual(meta["error"], result.error)
        self.assertIn(result.error, stderr_text)

    def test_startup_error_maps_to_failed_result(self):
        def provider(_request):
            raise AcpStartupError("server did not initialize")

        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="search_enabled",
            transcript_provider=provider,
        )

        result, meta, transcript_text, stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "acp_startup_failed: server did not initialize")
        self.assertEqual(meta["error"], result.error)
        self.assertEqual(transcript_text, "")
        self.assertIn(result.error, stderr_text)

    def test_default_provider_missing_reports_live_transport_not_implemented(self):
        runtime = AcpTraeCliRuntime(
            runtime_command="fake-traecli",
            query_timeout=30,
            member_tool_mode="search_enabled",
        )

        result, meta, transcript_text, stderr_text = self.run_runtime(runtime)

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.error,
            "acp_startup_failed: ACP live transport is not implemented yet",
        )
        self.assertEqual(meta["error"], result.error)
        self.assertEqual(transcript_text, "")
        self.assertIn(result.error, stderr_text)

    def test_cancellation_writes_failed_meta_and_reraises(self):
        async def never_returns(_request):
            await asyncio.Future()

        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                output_dir = Path(tmp)
                runtime = AcpTraeCliRuntime(
                    runtime_command="fake-traecli",
                    query_timeout=30,
                    member_tool_mode="search_enabled",
                    transcript_provider=never_returns,
                )
                task = asyncio.create_task(
                    runtime.query_model(
                        model="Model-X",
                        prompt="Prompt text",
                        run_id="run-acp",
                        stage="stage1",
                        label="A",
                        output_dir=output_dir,
                    )
                )
                await asyncio.sleep(0)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                meta = json.loads((output_dir / "A.meta.json").read_text(encoding="utf-8"))
                stderr_text = (output_dir / "A.acp.stderr.log").read_text(encoding="utf-8")
                return meta, stderr_text

        meta, stderr_text = asyncio.run(_run())

        self.assertEqual(meta["status"], "failed")
        self.assertEqual(meta["error"], "cancelled")
        self.assertIn("Cancelled while waiting for ACP runtime.", stderr_text)


if __name__ == "__main__":
    unittest.main()
