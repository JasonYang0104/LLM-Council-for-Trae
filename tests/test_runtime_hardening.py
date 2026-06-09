from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from io import StringIO
from unittest.mock import patch


class RuntimeHardeningTests(unittest.TestCase):
    def test_run_lease_acquire_and_release(self):
        from llm_council_for_trae.runtime import RunLease

        with tempfile.TemporaryDirectory() as tmp:
            store_base = Path(tmp)
            with RunLease.acquire(store_base, "run-test") as lease:
                self.assertTrue(lease.path.exists())
                self.assertEqual(lease.payload["run_id"], "run-test")

            self.assertFalse(lease.path.exists())

    def test_run_lease_rejects_active_lock(self):
        from llm_council_for_trae.runtime import RunLease, RunLeaseError

        with tempfile.TemporaryDirectory() as tmp:
            store_base = Path(tmp)
            with RunLease.acquire(store_base, "run-active"):
                with patch("llm_council_for_trae.runtime.process_is_alive", return_value=True):
                    with self.assertRaises(RunLeaseError) as ctx:
                        RunLease.acquire(store_base, "run-next")

            self.assertIn("another run is active", str(ctx.exception))

    def test_run_lease_overwrites_stale_lock(self):
        from llm_council_for_trae.runtime import RunLease

        with tempfile.TemporaryDirectory() as tmp:
            store_base = Path(tmp)
            runtime_dir = store_base / ".runtime"
            runtime_dir.mkdir()
            (runtime_dir / "run.lock").write_text('{"run_id":"old","pid":999999}\n', encoding="utf-8")

            with patch("llm_council_for_trae.runtime.process_is_alive", return_value=False):
                with RunLease.acquire(store_base, "run-next") as lease:
                    self.assertEqual(lease.payload["run_id"], "run-next")
                    self.assertTrue(lease.stale_replaced)

    def test_run_lease_overwrites_malformed_lock_as_stale(self):
        from llm_council_for_trae.runtime import RunLease

        with tempfile.TemporaryDirectory() as tmp:
            store_base = Path(tmp)
            runtime_dir = store_base / ".runtime"
            runtime_dir.mkdir()
            (runtime_dir / "run.lock").write_text("not json\n", encoding="utf-8")

            with RunLease.acquire(store_base, "run-next") as lease:
                self.assertEqual(lease.payload["run_id"], "run-next")
                self.assertTrue(lease.stale_replaced)

    def test_cli_run_fails_fast_when_run_lease_active(self):
        from llm_council_for_trae.cli import main
        from llm_council_for_trae.runtime import RunLeaseError

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "question.md"
            input_path.write_text("Question\n", encoding="utf-8")
            store_base = Path(tmp) / "runs"

            with patch("llm_council_for_trae.cli.RunLease.acquire", side_effect=RunLeaseError("another run is active: old")):
                with patch("sys.stdout", new=StringIO()) as stdout:
                    rc = main([
                        "--json",
                        "--store",
                        str(store_base),
                        "run",
                        "--input",
                        str(input_path),
                        "--default-models",
                    ])

            self.assertEqual(rc, 1)
            self.assertIn("another run is active", stdout.getvalue())

    def test_stage2_timeout_keeps_completed_reviews_and_marks_pending_failed(self):
        async def _run():
            import asyncio
            from llm_council_for_trae.council import CouncilConfig, stage2_collect_rankings
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s2-timeout")
            config = CouncilConfig(
                members=["M1", "M2"],
                chairman="M1",
                stage2_timeout=0.05,
            )

            async def query_model(**kwargs):
                if kwargs["model"] == "M1":
                    return ModelCallResult(
                        expected_model="M1",
                        actual_model="M1",
                        response="FINAL RANKING:\n1. Response A\n2. Response B",
                        status="ok",
                        session_id="s1",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                    )
                await asyncio.sleep(5)
                return ModelCallResult(
                    expected_model="M2",
                    actual_model="M2",
                    response="FINAL RANKING:\n1. Response A",
                    status="ok",
                    session_id="s2",
                    command=["traecli"],
                    exit_code=0,
                    stdout_path="out.jsonl",
                    stderr_path="err.log",
                )

            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = query_model
            stage1_results = [
                {"label": "Response A", "file_label": "A", "model": "M1", "response": "A", "status": "ok"},
                {"label": "Response B", "file_label": "B", "model": "M2", "response": "B", "status": "ok"},
            ]

            stage2_results, label_to_model = await stage2_collect_rankings("question", stage1_results, config, provider, store)

            self.assertEqual(label_to_model, {"Response A": "M1", "Response B": "M2"})
            self.assertEqual([r["status"] for r in stage2_results], ["ok", "failed"])
            self.assertIn("cancelled_by_stage_timeout", stage2_results[1]["error"])
            self.assertTrue((store.root / "stage2" / "B.traecli.stream.jsonl").exists())
            aggregate = (store.root / "stage2" / "aggregate.json").read_text(encoding="utf-8")
            self.assertIn("M1", aggregate)

        import asyncio
        asyncio.run(_run())

    def test_stage1_records_tool_policy_fields(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, stage1_collect_responses
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore

            forbidden = [{"id": "tc1", "name": "Skill", "arguments": "{}", "turn_index": 1}]
            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage1-policy")
            config = CouncilConfig(members=["M1"], chairman="M1", member_tool_mode="search_enabled")

            async def query_model(**kwargs):
                return ModelCallResult(
                    expected_model="M1",
                    actual_model="M1",
                    response="A",
                    status="failed",
                    session_id="s1",
                    command=["traecli"],
                    exit_code=0,
                    stdout_path="out.jsonl",
                    stderr_path="err.log",
                    error="tool_contaminated: forbidden tool call(s): Skill",
                    member_tool_mode="search_enabled",
                    allowed_tools=["WebSearch", "WebFetch"],
                    disallowed_tools=["Skill", "Agent"],
                    forbidden_tool_calls=forbidden,
                )

            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = query_model

            results = await stage1_collect_responses("question", config, provider, store)

            self.assertEqual(results[0]["member_tool_mode"], "search_enabled")
            self.assertEqual(results[0]["allowed_tools"], ["WebSearch", "WebFetch"])
            self.assertEqual(results[0]["disallowed_tools"], ["Skill", "Agent"])
            self.assertEqual(results[0]["forbidden_tool_calls"], forbidden)

        import asyncio
        asyncio.run(_run())

    def test_stage1_quorum_checkpoint_drains_cancelled_provider_cleanup(self):
        async def _run():
            import asyncio
            from llm_council_for_trae.council import CouncilConfig, stage1_collect_responses
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage1-drain")
            config = CouncilConfig(
                members=["M1", "M2"],
                chairman="Chair",
                min_valid_members=1,
                member_soft_checkpoint=999,
                member_quorum_checkpoint=0,
                member_hard_timeout=30,
            )
            cleanup_done = []

            async def query_model(**kwargs):
                if kwargs["model"] == "M1":
                    return ModelCallResult(
                        expected_model="M1",
                        actual_model="M1",
                        response="answer",
                        status="ok",
                        session_id="s1",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                    )
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    (store.root / "stage1" / "B.traecli.stream.jsonl").write_text("", encoding="utf-8")
                    await asyncio.sleep(0.01)
                    cleanup_done.append(kwargs["model"])
                    raise
                return ModelCallResult(
                    expected_model="M2",
                    actual_model="M2",
                    response="slow answer",
                    status="ok",
                    session_id="s2",
                    command=["traecli"],
                    exit_code=0,
                    stdout_path="out.jsonl",
                    stderr_path="err.log",
                )

            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = query_model

            results = await asyncio.wait_for(
                stage1_collect_responses("question", config, provider, store),
                timeout=5,
            )

            self.assertEqual([r["status"] for r in results], ["ok", "failed"])
            self.assertEqual(cleanup_done, ["M2"])
            meta = (store.root / "stage1" / "B.meta.json").read_text(encoding="utf-8")
            self.assertIn('"status": "failed"', meta)
            self.assertIn("cancelled_by_stage_timeout", meta)
            stream = (store.root / "stage1" / "B.traecli.stream.jsonl").read_text(encoding="utf-8")
            self.assertIn("cancelled_by_stage_timeout", stream)
            self.assertIn("M2", stream)

        import asyncio
        asyncio.run(_run())

    def test_run_full_council_validate_accepts_cancelled_stage1_sidecar(self):
        async def _run():
            import asyncio
            import llm_council_for_trae.council as council_mod
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.html_export import export_html
            from llm_council_for_trae.provider import ModelCallResult, tool_policy_for_mode
            from llm_council_for_trae.store import ArtifactStore
            from llm_council_for_trae.validation import validate_run

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage1-cancelled-sidecar")
            config = CouncilConfig(
                members=["M1", "M2", "M3"],
                chairman="Chair",
                min_valid_members=2,
                target_valid_members=2,
                member_soft_checkpoint=999,
                member_quorum_checkpoint=0,
                member_hard_timeout=30,
                stage1_max_retries=0,
                stage2_timeout=5,
            )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    model = kwargs["model"]
                    if stage == "stage1" and model == "M3":
                        await asyncio.sleep(60)
                    response = {
                        "stage1": f"answer {model}",
                        "stage2": "FINAL RANKING:\n1. Response A\n2. Response B",
                        "stage3": "final",
                    }[stage]
                    allowed_tools, disallowed_tools = tool_policy_for_mode(config.member_tool_mode)
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=model,
                        response=response,
                        status="ok",
                        session_id=f"s-{model}",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path=f"{kwargs['label']}.traecli.stream.jsonl",
                        stderr_path=f"{kwargs['label']}.traecli.stderr.log",
                        member_tool_mode=config.member_tool_mode,
                        allowed_tools=allowed_tools,
                        disallowed_tools=disallowed_tools,
                        forbidden_tool_calls=[],
                    )

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": name} for name in ["M1", "M2", "M3", "Chair"]],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        manifest = await run_full_council("question", config, store)

            self.assertEqual(manifest["status"], "degraded_ok")
            stream = (store.root / "stage1" / "C.traecli.stream.jsonl").read_text(encoding="utf-8")
            self.assertIn("cancelled_by_stage_timeout", stream)
            tool_policy = {
                "member_tool_mode": config.member_tool_mode,
                "allowed_tools": tool_policy_for_mode(config.member_tool_mode)[0],
                "disallowed_tools": tool_policy_for_mode(config.member_tool_mode)[1],
                "forbidden_tool_calls": [],
            }
            stage3 = manifest["stages"]["stage3"]
            store.write_json("stage3/final.meta.json", {
                "expected_model": stage3["expected_model"],
                "actual_model": stage3["actual_model"],
                "response_chars": len(stage3["response"]),
                "status": stage3["status"],
                "session_id": "s-Chair",
                "command": ["traecli"],
                "exit_code": 0,
                "stdout_path": "final.traecli.stream.jsonl",
                "stderr_path": "final.traecli.stderr.log",
                "copied_session_files": {},
                "raw_model_markers": [],
                "error": None,
                "captured_at": "2026-06-04T00:00:00Z",
            } | tool_policy)
            store.write_text("stage3/final.traecli.stream.jsonl", "{}\n")
            export_html(store)
            validation = validate_run(store)
            self.assertEqual(validation["status"], "degraded_ok", validation["failures"])
            self.assertEqual(validation["verdict"], "usable_degraded_final")
            self.assertTrue(validation["usable_final"])

        import asyncio
        asyncio.run(_run())

    def test_run_full_council_validate_accepts_retry_empty_stage1_sidecar(self):
        async def _run():
            import llm_council_for_trae.council as council_mod
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.html_export import export_html
            from llm_council_for_trae.provider import ModelCallResult, tool_policy_for_mode
            from llm_council_for_trae.store import ArtifactStore
            from llm_council_for_trae.validation import validate_run

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-stage1-retry-empty-sidecar")
            config = CouncilConfig(
                members=["M1", "M2", "M3"],
                chairman="Chair",
                min_valid_members=2,
                target_valid_members=2,
                member_quorum_checkpoint=999,
                member_hard_timeout=30,
                stage1_max_retries=1,
                stage2_timeout=5,
            )
            stage1_attempts = {}

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    model = kwargs["model"]
                    label = kwargs["label"]
                    response = ""
                    status = "ok"
                    actual_model = model
                    error = None
                    exit_code = 0
                    if stage == "stage1":
                        attempt = stage1_attempts.get(model, 0) + 1
                        stage1_attempts[model] = attempt
                        if model == "M1":
                            response = "answer M1"
                        elif model == "M2":
                            status = "failed"
                            actual_model = None
                            error = "timeout"
                            exit_code = 1
                            if attempt == 2:
                                (Path(kwargs["output_dir"]) / f"{label}.traecli.stream.jsonl").write_text("", encoding="utf-8")
                        elif model == "M3" and attempt == 1:
                            status = "failed"
                            actual_model = None
                            error = "timeout"
                            exit_code = 1
                        else:
                            response = "answer M3"
                    else:
                        response = {
                            "stage2": "FINAL RANKING:\n1. Response A\n2. Response C",
                            "stage3": "final",
                        }[stage]

                    allowed_tools, disallowed_tools = tool_policy_for_mode(config.member_tool_mode)
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=actual_model,
                        response=response,
                        status=status,
                        session_id=f"s-{model}-{stage}",
                        command=["traecli"],
                        exit_code=exit_code,
                        stdout_path=f"{label}.traecli.stream.jsonl",
                        stderr_path=f"{label}.traecli.stderr.log",
                        error=error,
                        member_tool_mode=config.member_tool_mode,
                        allowed_tools=allowed_tools,
                        disallowed_tools=disallowed_tools,
                        forbidden_tool_calls=[],
                    )

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": name} for name in ["M1", "M2", "M3", "Chair"]],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        manifest = await run_full_council("question", config, store)

            self.assertEqual(manifest["status"], "degraded_ok")
            stream_path = store.root / "stage1" / "B.traecli.stream.jsonl"
            self.assertGreater(stream_path.stat().st_size, 0)
            self.assertIn("timeout", stream_path.read_text(encoding="utf-8"))
            tool_policy = {
                "member_tool_mode": config.member_tool_mode,
                "allowed_tools": tool_policy_for_mode(config.member_tool_mode)[0],
                "disallowed_tools": tool_policy_for_mode(config.member_tool_mode)[1],
                "forbidden_tool_calls": [],
            }
            stage3 = manifest["stages"]["stage3"]
            store.write_json("stage3/final.meta.json", {
                "expected_model": stage3["expected_model"],
                "actual_model": stage3["actual_model"],
                "response_chars": len(stage3["response"]),
                "status": stage3["status"],
                "session_id": "s-Chair",
                "command": ["traecli"],
                "exit_code": 0,
                "stdout_path": "final.traecli.stream.jsonl",
                "stderr_path": "final.traecli.stderr.log",
                "copied_session_files": {},
                "raw_model_markers": [],
                "error": None,
                "captured_at": "2026-06-04T00:00:00Z",
            } | tool_policy)
            store.write_text("stage3/final.traecli.stream.jsonl", "{}\n")
            export_html(store)
            validation = validate_run(store)
            self.assertEqual(validation["verdict"], "usable_degraded_final", validation["failures"])
            self.assertTrue(validation["usable_final"])

        import asyncio
        asyncio.run(_run())

    def test_stage3_uses_chairman_timeout_for_primary_and_fallback(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, stage3_synthesize_final
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-chair-timeout")
            config = CouncilConfig(
                members=["M1"],
                chairman="M1",
                chairman_timeout=777,
                chairman_contribution_enabled=False,
            )
            seen_timeouts = []

            class FakeProvider:
                async def query_model(self, **kwargs):
                    seen_timeouts.append(kwargs.get("query_timeout"))
                    status = "failed" if kwargs["model"] == "M1" else "ok"
                    return ModelCallResult(
                        expected_model=kwargs["model"],
                        actual_model=kwargs["model"] if status == "ok" else None,
                        response="Final" if status == "ok" else "",
                        status=status,
                        session_id="s",
                        command=["traecli"],
                        exit_code=0 if status == "ok" else 1,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                        error=None if status == "ok" else "timeout",
                    )

            await stage3_synthesize_final(
                "question",
                [{"label": "Response A", "model": "M1", "response": "A", "status": "ok"}],
                [{"model": "M1", "ranking": "FINAL RANKING:\n1. Response A", "parsed_ranking": ["Response A"], "status": "ok"}],
                config,
                FakeProvider(),
                store,
                fallback_chain=["M2"],
            )

            self.assertEqual(seen_timeouts, [777, 777])

        import asyncio
        asyncio.run(_run())

    def test_provider_build_command_uses_call_timeout_override(self):
        from llm_council_for_trae.provider import TraeCliProvider

        provider = TraeCliProvider(query_timeout=180)
        cmd = provider._build_command("M1", "prompt", "run", "stage3", "final", "session", query_timeout=777)
        self.assertIn("--query-timeout", cmd)
        self.assertIn("777s", cmd)

    def test_model_call_result_serializes_termination_metadata(self):
        from llm_council_for_trae.provider import ModelCallResult

        result = ModelCallResult(
            expected_model="M1",
            actual_model=None,
            response="",
            status="failed",
            session_id="s1",
            command=["traecli"],
            exit_code=-1,
            stdout_path="out.jsonl",
            stderr_path="err.log",
            error="timeout",
            termination={
                "pid": 123,
                "pgid": 123,
                "terminated": True,
                "termination_reason": "timeout",
                "signals_sent": ["SIGTERM", "SIGKILL"],
                "final_returncode": -9,
            },
        )

        self.assertEqual(result.to_json()["termination"]["termination_reason"], "timeout")
        self.assertEqual(result.to_json()["termination"]["signals_sent"], ["SIGTERM", "SIGKILL"])

    def test_provider_timeout_records_termination_metadata(self):
        async def _run():
            from llm_council_for_trae.provider import TraeCliProvider

            class FakeStdout:
                async def read(self):
                    return b""

            class FakeStderr:
                async def read(self):
                    return b""

            class FakeProc:
                pid = 12345
                returncode = None

                def __init__(self):
                    self.stdout = FakeStdout()
                    self.stderr = FakeStderr()

                async def wait(self):
                    self.returncode = -15
                    return self.returncode

                def kill(self):
                    self.returncode = -9

            provider = TraeCliProvider(query_timeout=1)
            termination = {
                "pid": 12345,
                "pgid": 12345,
                "terminated": True,
                "termination_reason": None,
                "signals_sent": ["SIGTERM"],
                "final_returncode": -15,
            }
            with tempfile.TemporaryDirectory() as tmp:
                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", return_value=FakeProc()):
                    with patch("llm_council_for_trae.provider.monitor_stream_for_budget", side_effect=asyncio.TimeoutError):
                        with patch("llm_council_for_trae.provider.terminate_process_tree", return_value=termination):
                            result = await provider.query_model(
                                model="M1",
                                prompt="prompt",
                                run_id="run-timeout-meta",
                                stage="stage1",
                                label="A",
                                output_dir=Path(tmp),
                            )

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.termination["termination_reason"], "timeout")
            self.assertTrue(result.termination["terminated"])
            self.assertIn("final_returncode", result.termination)

        import asyncio
        asyncio.run(_run())

    def test_provider_marks_forbidden_tool_call_as_failed(self):
        async def _run():
            import json
            from llm_council_for_trae.provider import TraeCliProvider

            class FakeStdout:
                def __init__(self, lines):
                    self.lines = [(line + "\n").encode("utf-8") for line in lines]

                def __aiter__(self):
                    self._iter = iter(self.lines)
                    return self

                async def __anext__(self):
                    try:
                        return next(self._iter)
                    except StopIteration:
                        raise StopAsyncIteration

            class FakeStderr:
                async def read(self):
                    return b""

            class FakeProc:
                pid = 12345
                returncode = 0

                def __init__(self, lines):
                    self.stdout = FakeStdout(lines)
                    self.stderr = FakeStderr()

                async def wait(self):
                    return 0

            stream = [
                json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "M1"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "OK", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "Skill", "arguments": "{\"skill\":\"llm-council-for-trae\"}"}}]}}),
                json.dumps({"type": "result", "result": "OK", "is_error": False}),
            ]

            provider = TraeCliProvider(member_tool_mode="search_enabled")
            with tempfile.TemporaryDirectory() as tmp:
                with patch("llm_council_for_trae.provider.asyncio.create_subprocess_exec", return_value=FakeProc(stream)):
                    result = await provider.query_model(
                        model="M1",
                        prompt="prompt",
                        run_id="run-contaminated",
                        stage="stage1",
                        label="A",
                        output_dir=Path(tmp),
                    )

            self.assertEqual(result.status, "failed")
            self.assertTrue(result.error.startswith("tool_contaminated:"))
            self.assertEqual([call["name"] for call in result.forbidden_tool_calls], ["Skill"])

        import asyncio
        asyncio.run(_run())

    def test_stage3_degrades_to_best_stage1_response_when_all_chairmen_fail(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, stage3_synthesize_final
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-degraded")
            config = CouncilConfig(members=["M1", "M2"], chairman="Chair")

            class FailingProvider:
                async def query_model(self, **kwargs):
                    return ModelCallResult(
                        expected_model=kwargs["model"],
                        actual_model=None,
                        response="",
                        status="failed",
                        session_id="s",
                        command=["traecli"],
                        exit_code=1,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                        error="timeout",
                    )

            final, meta = await stage3_synthesize_final(
                "question",
                [
                    {"label": "Response A", "model": "M1", "response": "weak answer", "status": "ok"},
                    {"label": "Response B", "model": "M2", "response": "best answer", "status": "ok"},
                ],
                [
                    {
                        "model": "M1",
                        "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                        "parsed_ranking": ["Response B", "Response A"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config,
                FailingProvider(),
                store,
                fallback_chain=["Fallback"],
            )

            self.assertEqual(final["status"], "degraded_ok")
            self.assertEqual(final["model"], "M2")
            self.assertEqual(final["response"], "best answer")
            self.assertEqual(final["degraded_source"], "stage2_best_stage1_response")
            self.assertEqual(meta["attempted"], ["Chair", "Fallback"])
            self.assertEqual((store.root / "stage3" / "final.md").read_text(encoding="utf-8").strip(), "best answer")

        import asyncio
        asyncio.run(_run())

    def test_stage3_degraded_final_ignores_failed_stage2_rankings(self):
        from llm_council_for_trae.council import degraded_final_from_stage2

        final = degraded_final_from_stage2(
            [
                {"label": "Response A", "model": "M1", "response": "valid best", "status": "ok"},
                {"label": "Response B", "model": "M2", "response": "failed reviewer favorite", "status": "ok"},
            ],
            [
                {
                    "model": "M2",
                    "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                    "parsed_ranking": ["Response B", "Response A"],
                    "status": "failed",
                    "parse_status": "ok",
                },
                {
                    "model": "M2",
                    "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                    "parsed_ranking": ["Response B", "Response A"],
                    "status": "failed",
                    "parse_status": "ok",
                },
                {
                    "model": "M1",
                    "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                    "parsed_ranking": ["Response A", "Response B"],
                    "status": "ok",
                    "parse_status": "ok",
                },
            ],
        )

        self.assertIsNotNone(final)
        self.assertEqual(final["model"], "M1")
        self.assertEqual(final["response"], "valid best")

    def test_run_full_council_preserves_degraded_ok_stage3_final(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-full-s3-degraded")
            config = CouncilConfig(
                members=["M1", "M2"],
                chairman="Chair",
                min_valid_members=2,
                stage1_max_retries=0,
                stage2_timeout=1,
            )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    model = kwargs["model"]
                    if stage == "stage1":
                        return ModelCallResult(
                            expected_model=model,
                            actual_model=model,
                            response=f"answer {model}",
                            status="ok",
                            session_id="s",
                            command=["traecli"],
                            exit_code=0,
                            stdout_path="out.jsonl",
                            stderr_path="err.log",
                        )
                    if stage == "stage2":
                        return ModelCallResult(
                            expected_model=model,
                            actual_model=model,
                            response="FINAL RANKING:\n1. Response B\n2. Response A",
                            status="ok",
                            session_id="s",
                            command=["traecli"],
                            exit_code=0,
                            stdout_path="out.jsonl",
                            stderr_path="err.log",
                        )
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=None,
                        response="",
                        status="failed",
                        session_id="s",
                        command=["traecli"],
                        exit_code=1,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                        error="timeout",
                    )

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": "M1"}, {"name": "M2"}, {"name": "Chair"}],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        manifest = await run_full_council("question", config, store)

            self.assertEqual(manifest["status"], "degraded_ok")
            self.assertEqual(manifest["stages"]["stage3"]["status"], "degraded_ok")
            self.assertEqual(manifest["stages"]["stage3"]["response"], "answer M2")
            self.assertTrue(any(f.get("stage_record") == "Chair" for f in manifest["failures"]))
            self.assertTrue(any("stage3 degraded" in warning for warning in manifest["warnings"]))

        import asyncio
        asyncio.run(_run())

    def test_direct_provider_defaults_to_isolated_member_cwd(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-isolated-cwd")
            config = CouncilConfig(
                members=["M1"],
                chairman="M1",
                min_valid_members=1,
                stage1_max_retries=0,
                stage2_timeout=1,
            )
            seen = {}

            class MockProvider:
                def __init__(self, runtime_command, query_timeout, runtime_cwd=None, use_yolo=False, member_tool_mode="search_enabled"):
                    seen["runtime_cwd"] = runtime_cwd

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    response = "FINAL RANKING:\n1. Response A" if stage == "stage2" else "answer"
                    return ModelCallResult(
                        expected_model=kwargs["model"],
                        actual_model=kwargs["model"],
                        response=response,
                        status="ok",
                        session_id="s",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                    )

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": "M1"}],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        await run_full_council("question", config, store)

            self.assertIsNotNone(seen["runtime_cwd"])
            self.assertNotEqual(seen["runtime_cwd"], store.root / "runtime" / "member-cwd")
            self.assertIn("lct-run-isolated-cwd-member-cwd-", str(seen["runtime_cwd"]))
            self.assertTrue(seen["runtime_cwd"].exists())
            self.assertEqual((store.root / "runtime" / "member-cwd.path").read_text(encoding="utf-8").strip(), str(seen["runtime_cwd"]))

        import asyncio
        asyncio.run(_run())

    def test_subagent_provider_uses_agent_invocation_tool_policy(self):
        async def _run():
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-subagent-policy")
            config = CouncilConfig(
                members=["M1"],
                chairman="M1",
                provider_mode="subagent",
                runtime_cwd=str(Path(tempfile.mkdtemp())),
                member_agents=["council-m1"],
                chairman_agent="council-m1",
                min_valid_members=1,
                stage1_max_retries=0,
                stage2_timeout=1,
            )
            seen = {}

            class MockProvider:
                def __init__(self, runtime_command, query_timeout, runtime_cwd=None, use_yolo=False, member_tool_mode="search_enabled"):
                    seen["member_tool_mode"] = member_tool_mode

                async def query_model(self, **kwargs):
                    response = "FINAL RANKING:\n1. Response A" if kwargs["stage"] == "stage2" else "answer"
                    return ModelCallResult(
                        expected_model=kwargs["model"],
                        actual_model=kwargs["model"],
                        response=response,
                        status="ok",
                        session_id="s",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                    )

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True,
                    "command": "fake",
                    "version": "1.0",
                    "doctor_exit_code": 0,
                    "doctor": {},
                    "errors": [],
                    "warnings": [],
                    "ignored_errors": [],
                    "models": [{"name": "M1"}],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        await run_full_council("question", config, store)

            self.assertEqual(seen["member_tool_mode"], "subagent_invocation")

        import asyncio
        asyncio.run(_run())

    def test_subagent_agent_frontmatter_declares_tool_policy(self):
        from llm_council_for_trae.utils import PROJECT_ROOT

        agent_paths = sorted((PROJECT_ROOT / ".trae" / "agents").glob("council-*.md"))
        self.assertTrue(agent_paths)
        for path in agent_paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("tools: WebSearch,WebFetch", text)
                self.assertIn("disallowed_tools:", text)
                self.assertIn("Skill", text)
                self.assertIn("Agent", text)
                self.assertIn("Bash", text)

    def test_terminate_process_tree_prefers_process_group(self):
        async def _run():
            import signal
            from llm_council_for_trae.provider import terminate_process_tree

            class FakeProc:
                pid = 123
                returncode = None
                killed = False

                async def wait(self):
                    self.returncode = 0

                def kill(self):
                    self.killed = True

            proc = FakeProc()
            with patch("llm_council_for_trae.provider.os.name", "posix"):
                with patch("llm_council_for_trae.provider.os.getpgid", return_value=456):
                    with patch("llm_council_for_trae.provider.os.killpg") as killpg:
                        await terminate_process_tree(proc)

            killpg.assert_called_once_with(456, signal.SIGTERM)
            self.assertFalse(proc.killed)

        import asyncio
        asyncio.run(_run())

    def test_build_config_accepts_stage2_and_chairman_timeouts(self):
        from llm_council_for_trae.cli import build_config, build_parser, resolve_run_model_choice

        parser = build_parser()
        args = parser.parse_args([
            "run",
            "--input",
            "question.md",
            "--default-models",
            "--stage2-timeout",
            "90",
            "--chairman-timeout",
            "777",
        ])
        args.selected_model_choice = resolve_run_model_choice(args)
        config = build_config(args)
        self.assertEqual(config.stage2_timeout, 90)
        self.assertEqual(config.chairman_timeout, 777)

    def test_validate_accepts_recorded_failed_stage2_in_degraded_run(self):
        import json
        from llm_council_for_trae.store import ArtifactStore
        from llm_council_for_trae.validation import validate_run

        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-degraded-stage2")
            manifest = {
                "schema_version": 1,
                "run_id": "run-degraded-stage2",
                "created_at": "2026-06-01T00:00:00Z",
                "updated_at": "2026-06-01T00:00:00Z",
                "status": "degraded_ok",
                "input_chars": 8,
                "config": {
                    "members": ["M1", "M2"],
                    "chairman": "Chair",
                    "provider_mode": "direct",
                    "runtime_command": "fake",
                    "query_timeout": 180,
                    "export_html": True,
                },
                "artifacts": {"html": "html/index.html"},
                "metadata": {"label_to_model": {"Response A": "M1"}, "aggregate_rankings": [{"model": "M1", "average_rank": 1.0, "rankings_count": 1, "positions": [1]}]},
                "stages": {
                    "stage1": [{"label": "Response A", "file_label": "A", "model": "M1", "expected_model": "M1", "actual_model": "M1", "response": "A", "status": "ok"}],
                    "stage2": [
                        {
                            "reviewer_label": "A", "model": "M1", "expected_model": "M1", "actual_model": "M1",
                            "ranking": "FINAL RANKING:\n1. Response A", "parsed_ranking": ["Response A"],
                            "parse_status": "ok", "status": "ok", "error": None,
                            "review_path": "stage2/A.review.md", "json_path": "stage2/A.review.json",
                        },
                        {
                            "reviewer_label": "B", "model": "M2", "expected_model": "M2", "actual_model": None,
                            "ranking": "", "parsed_ranking": [],
                            "parse_status": "incomplete", "status": "failed", "error": "cancelled_by_stage_timeout",
                            "review_path": "stage2/B.review.md", "json_path": "stage2/B.review.json",
                        },
                    ],
                    "stage3": {
                        "model": "Chair", "expected_model": "Chair", "actual_model": "Chair",
                        "response": "Final", "status": "ok", "error": None,
                        "prompt_path": "stage3/chairman.prompt.md", "response_path": "stage3/final.md", "json_path": "stage3/final.json",
                    },
                },
                "warnings": ["stage2 reviewer timed out"],
                "failures": [{"stage_record": "B", "status": "failed", "error": "cancelled_by_stage_timeout", "expected_model": "M2", "actual_model": None}],
            }
            store.write_manifest(manifest)
            tool_policy = {
                "member_tool_mode": "search_enabled",
                "allowed_tools": ["WebSearch", "WebFetch"],
                "disallowed_tools": ["Skill", "Agent"],
                "forbidden_tool_calls": [],
            }
            manifest["config"] |= {"use_yolo": False, "member_tool_mode": "search_enabled", "member_runtime_cwd_mode": "isolated_temp"}
            manifest["stages"]["stage1"][0] |= tool_policy
            manifest["stages"]["stage2"][0] |= tool_policy
            manifest["stages"]["stage2"][1] |= tool_policy
            manifest["stages"]["stage3"] |= tool_policy
            store.write_manifest(manifest)
            for relative in [
                "input.md", "config.json", "runtime/doctor.json", "runtime/traecli.models.json",
                "stage1/member.prompt.md", "stage1/A.response.md", "stage1/A.traecli.stream.jsonl",
                "stage2/review.prompt.md", "stage2/label_to_model.json", "stage2/aggregate.json",
                "stage2/A.review.md", "stage2/A.traecli.stream.jsonl",
                "stage2/B.review.md",
                "stage3/chairman.prompt.md", "stage3/final.md", "stage3/final.traecli.stream.jsonl",
                "html/index.html",
            ]:
                store.write_text(relative, "{}\n")
            store.write_text("stage2/B.traecli.stream.jsonl", "")

            def write_json(relative, data):
                store.write_text(relative, json.dumps(data) + "\n")

            base_meta = {
                "response_chars": 1, "session_id": "s", "command": ["traecli"], "exit_code": 0,
                "stdout_path": "out.jsonl", "stderr_path": "err.log", "copied_session_files": {},
                "raw_model_markers": [], "error": None, "captured_at": "2026-06-01T00:00:00Z",
            } | tool_policy
            write_json("stage1/A.meta.json", base_meta | {"expected_model": "M1", "actual_model": "M1", "status": "ok"})
            write_json("stage2/A.meta.json", base_meta | {"expected_model": "M1", "actual_model": "M1", "status": "ok"})
            write_json("stage2/B.meta.json", base_meta | {"expected_model": "M2", "actual_model": None, "status": "failed", "error": "cancelled_by_stage_timeout"})
            write_json("stage2/A.review.json", manifest["stages"]["stage2"][0])
            write_json("stage2/B.review.json", manifest["stages"]["stage2"][1])
            write_json("stage3/final.meta.json", base_meta | {"expected_model": "Chair", "actual_model": "Chair", "status": "ok"})
            write_json("stage3/final.json", manifest["stages"]["stage3"])
            write_json("html/export.json", {"run_id": "run-degraded-stage2", "generated_at": "2026-06-01T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})

            validation = validate_run(store)
            self.assertEqual(validation["status"], "degraded_ok", validation["failures"])

    def test_stage_stream_file_check_only_accepts_empty_cancelled_records(self):
        from llm_council_for_trae.validation import stage_stream_file_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = "stage2/B.traecli.stream.jsonl"
            nonempty = "stage2/A.traecli.stream.jsonl"
            (root / "stage2").mkdir()
            (root / empty).write_text("", encoding="utf-8")
            (root / nonempty).write_text("{}\n", encoding="utf-8")

            cancelled_failed = {"status": "failed", "error": "cancelled_by_stage_timeout"}
            non_cancelled_failed = {"status": "failed", "error": "tool_contaminated"}
            cancelled_ok = {"status": "ok", "error": "cancelled_by_stage_timeout"}

            self.assertFalse(stage_stream_file_check(root, "stage2/missing.traecli.stream.jsonl", cancelled_failed)["ok"])
            self.assertFalse(stage_stream_file_check(root, empty, non_cancelled_failed)["ok"])
            self.assertFalse(stage_stream_file_check(root, empty, cancelled_ok)["ok"])
            self.assertTrue(stage_stream_file_check(root, empty, cancelled_failed)["ok"])
            self.assertTrue(stage_stream_file_check(root, nonempty, non_cancelled_failed)["ok"])

    def test_cli_validate_exits_zero_for_degraded_ok(self):
        from argparse import Namespace
        from llm_council_for_trae.cli import cmd_validate

        args = Namespace(store=None, run_id="run-degraded", json_output=False)
        with patch("llm_council_for_trae.cli.ArtifactStore.open", return_value=object()):
            with patch("llm_council_for_trae.cli.resolve_store_base", return_value=Path("/tmp/runs")):
                with patch("llm_council_for_trae.cli.validate_run", return_value={"status": "degraded_ok", "failures": []}):
                    with patch("sys.stdout", new=StringIO()):
                        rc = cmd_validate(args)

        self.assertEqual(rc, 0)

    def test_run_full_council_marks_partial_stage2_failure_as_degraded(self):
        async def _run():
            import asyncio
            from llm_council_for_trae.council import CouncilConfig, run_full_council
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore
            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-partial-s2-degraded")
            config = CouncilConfig(
                members=["M1", "M2"],
                chairman="Chair",
                min_valid_members=2,
                stage1_max_retries=0,
                stage2_timeout=0.05,
            )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    model = kwargs["model"]
                    if stage == "stage2":
                        if model == "M2":
                            return ModelCallResult(
                                expected_model=model,
                                actual_model=None,
                                response="FINAL RANKING:\n1. Response B\n2. Response A",
                                status="failed",
                                session_id="s",
                                command=["traecli"],
                                exit_code=1,
                                stdout_path="out.jsonl",
                                stderr_path="err.log",
                                error="cancelled_by_stage_timeout",
                            )
                        response = "FINAL RANKING:\n1. Response A\n2. Response B"
                    elif stage == "stage3":
                        response = "Final"
                    else:
                        response = f"answer {model}"
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=model,
                        response=response,
                        status="ok",
                        session_id="s",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path="out.jsonl",
                        stderr_path="err.log",
                    )

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True, "command": "fake", "version": "1.0",
                    "doctor_exit_code": 0, "doctor": {}, "errors": [],
                    "warnings": [], "ignored_errors": [],
                    "models": [{"name": "M1"}, {"name": "M2"}, {"name": "Chair"}],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        manifest = await run_full_council("question", config, store)

            self.assertEqual(manifest["status"], "degraded_ok")
            self.assertTrue(any(f.get("stage_record") == "B" for f in manifest["failures"]))
            self.assertEqual(manifest["metadata"]["aggregate_rankings"][0]["model"], "M1")
            self.assertEqual(manifest["metadata"]["aggregate_rankings"][0]["positions"], [1])

        import asyncio
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
