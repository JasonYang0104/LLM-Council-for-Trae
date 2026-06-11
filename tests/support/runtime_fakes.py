from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llm_council_for_trae.provider import (
    ModelCallResult,
    forbidden_tool_calls_for_mode,
    tool_policy_for_mode,
)
from llm_council_for_trae.utils import write_json


FIXED_CAPTURED_AT = "2026-06-04T00:00:00Z"


@dataclass
class ScriptedReply:
    response: str
    status: str = "ok"
    actual_model: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class FakeRuntime:
    def __init__(
        self,
        script: dict[tuple[str, str], ScriptedReply],
        *,
        runtime_command: str = "fake-traecli",
        query_timeout: int = 180,
        runtime_cwd: Path | str | None = None,
        use_yolo: bool = False,
        member_tool_mode: str = "search_enabled",
    ):
        self.script = script
        self.runtime_command = runtime_command
        self.query_timeout = query_timeout
        self.runtime_cwd = Path(runtime_cwd) if runtime_cwd else None
        self.use_yolo = use_yolo
        self.member_tool_mode = member_tool_mode
        self.allowed_tools, self.disallowed_tools = tool_policy_for_mode(member_tool_mode)
        self.calls: list[dict[str, Any]] = []

    async def query_model(
        self,
        *,
        model: str,
        prompt: str,
        run_id: str,
        stage: str,
        label: str,
        output_dir: Path,
        agent: str | None = None,
        query_timeout: int | float | None = None,
    ) -> ModelCallResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        reply = self.script[(stage, label)]
        actual_model = reply.actual_model or model
        forbidden = forbidden_tool_calls_for_mode(reply.tool_calls, self.member_tool_mode)
        status = reply.status
        error = reply.error
        if forbidden:
            status = "failed"
            names = ", ".join(call.get("name", "unknown") for call in forbidden)
            error = f"tool_contaminated: forbidden tool call(s): {names}"

        stream_path = output_dir / f"{label}.traecli.stream.jsonl"
        stderr_path = output_dir / f"{label}.traecli.stderr.log"
        stream_path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in stream_json_events(actual_model, reply.response, reply.tool_calls))
            + "\n",
            encoding="utf-8",
        )
        stderr_path.write_text((error or "") + ("\n" if error else ""), encoding="utf-8")

        result = ModelCallResult(
            expected_model=model,
            actual_model=actual_model,
            response=reply.response,
            status=status,
            session_id=f"{run_id}-{stage}-{label}",
            command=["fake-traecli", stage, label, model],
            exit_code=0 if status == "ok" else 1,
            stdout_path=stream_path.name,
            stderr_path=stderr_path.name,
            runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
            agent=agent,
            error=error,
            permission_mode="bypass_permissions" if self.use_yolo else "default",
            member_tool_mode=self.member_tool_mode,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            forbidden_tool_calls=forbidden,
            tool_calls=reply.tool_calls,
            tool_calls_count=len(reply.tool_calls),
            turns_count=1 if reply.response or reply.tool_calls else 0,
            assistant_content_chars_total=len(reply.response),
            last_assistant_content_chars=len(reply.response),
        )
        write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": FIXED_CAPTURED_AT})
        self.calls.append(
            {
                "model": model,
                "prompt": prompt,
                "run_id": run_id,
                "stage": stage,
                "label": label,
                "query_timeout": query_timeout,
            }
        )
        await asyncio.sleep(0)
        return result


def stream_json_events(model: str, response: str, tool_calls: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    tool_call_events = [
        {
            "id": call.get("id", ""),
            "function": {
                "name": call.get("name", ""),
                "arguments": call.get("arguments", ""),
            },
        }
        for call in (tool_calls or [])
    ]
    return [
        {
            "type": "assistant",
            "model": model,
            "message": {
                "content": response,
                "tool_calls": tool_call_events,
            },
        },
        {"type": "result", "model": model, "result": response},
    ]


def direct_stdout(model: str, response: str, tool_calls: list[dict[str, Any]] | None = None) -> list[bytes]:
    return [
        (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        for event in stream_json_events(model, response, tool_calls)
    ]


class FakeAsyncStream:
    def __init__(self, chunks: Iterable[bytes]):
        self._chunks = list(chunks)

    def __aiter__(self) -> FakeAsyncStream:
        return self

    async def __anext__(self) -> bytes:
        await asyncio.sleep(0)
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class BlockingAsyncStream:
    def __aiter__(self) -> BlockingAsyncStream:
        return self

    async def __anext__(self) -> bytes:
        await asyncio.Future()
        raise StopAsyncIteration


class FakePipe:
    def __init__(self, payload: bytes = b""):
        self.payload = payload

    async def read(self) -> bytes:
        await asyncio.sleep(0)
        return self.payload


class FakeProcess:
    def __init__(
        self,
        *,
        stdout_lines: Iterable[bytes] = (),
        stderr: bytes = b"",
        returncode: int | None = 0,
        blocking_stdout: bool = False,
        pid: int | None = None,
    ):
        self.stdout = BlockingAsyncStream() if blocking_stdout else FakeAsyncStream(stdout_lines)
        self.stderr = FakePipe(stderr)
        self.returncode = returncode
        self.pid = pid
        self.killed = False

    async def wait(self) -> int:
        await asyncio.sleep(0)
        if self.returncode is None:
            await asyncio.Future()
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class RecordingSubprocessFactory:
    def __init__(self, processes: list[FakeProcess]):
        self.processes = list(processes)
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def __call__(self, *cmd: Any, **kwargs: Any) -> FakeProcess:
        self.calls.append((cmd, kwargs))
        if not self.processes:
            raise AssertionError("no fake process left for create_subprocess_exec")
        return self.processes.pop(0)
