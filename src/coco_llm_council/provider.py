from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import DEFAULT_TRAECLI, slugify, utc_now, write_json, write_text


@dataclass
class ModelCallResult:
    expected_model: str
    actual_model: str | None
    response: str
    status: str
    session_id: str
    command: list[str]
    exit_code: int
    stdout_path: str
    stderr_path: str
    runtime_cwd: str | None = None
    agent: str | None = None
    subagent_invocation: dict[str, Any] | None = None
    copied_session_files: dict[str, str] = field(default_factory=dict)
    raw_model_markers: list[str] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "expected_model": self.expected_model,
            "actual_model": self.actual_model,
            "response_chars": len(self.response),
            "status": self.status,
            "session_id": self.session_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "runtime_cwd": self.runtime_cwd,
            "agent": self.agent,
            "subagent_invocation": self.subagent_invocation,
            "copied_session_files": self.copied_session_files,
            "raw_model_markers": self.raw_model_markers,
            "error": self.error,
        }


class TraeCliProvider:
    def __init__(
        self,
        runtime_command: str = DEFAULT_TRAECLI,
        query_timeout: int = 180,
        runtime_cwd: Path | None = None,
    ):
        self.runtime_command = os.environ.get("COCO_LLM_COUNCIL_TRAECLI", runtime_command)
        self.query_timeout = query_timeout
        self.runtime_cwd = runtime_cwd

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
    ) -> ModelCallResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        session_id = slugify(f"{run_id}-{stage}-{label}")
        stream_path = output_dir / f"{label}.coco.stream.jsonl"
        stderr_path = output_dir / f"{label}.coco.stderr.log"
        runtime_prompt = f"@{agent} {prompt}" if agent else prompt
        cmd = [
            self.runtime_command,
            "-p",
            runtime_prompt,
            "-c",
            f"model.name={model}",
            "--output-format",
            "stream-json",
            "--query-timeout",
            f"{self.query_timeout}s",
            "--session-id",
            session_id,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self.query_timeout + 30)
        except asyncio.TimeoutError:
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace") + "\nTimed out while waiting for traecli."
            write_text(stream_path, stdout)
            write_text(stderr_path, stderr)
            return ModelCallResult(
                expected_model=model,
                actual_model=None,
                response="",
                status="failed",
                session_id=session_id,
                command=safe_command(cmd),
                exit_code=-1,
                stdout_path=stream_path.name,
                stderr_path=stderr_path.name,
                runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
                agent=agent,
                subagent_invocation=missing_subagent_invocation(agent),
                error="timeout",
            )

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        write_text(stream_path, stdout)
        write_text(stderr_path, stderr)

        parsed = parse_stream_json(stdout, expected_agent=agent)
        actual_model = parsed["actual_model"]
        response = parsed["response"]
        raw_model_markers = parsed["raw_model_markers"]
        subagent_invocation = parsed["subagent_invocation"]
        status = "ok"
        error = None
        if proc.returncode != 0:
            status = "failed"
            error = stderr.strip() or parsed.get("error") or f"traecli exited {proc.returncode}"
        elif not response.strip():
            status = "failed"
            error = "empty model response"
        elif actual_model != model:
            status = "failed"
            error = f"expected model {model}, actual model {actual_model or 'unknown'}"
        elif agent and not subagent_invocation.get("ok"):
            status = "failed"
            error = f"expected subagent {agent} invocation evidence, got {subagent_invocation}"

        copied = copy_coco_session_files(session_id, output_dir, label)
        result = ModelCallResult(
            expected_model=model,
            actual_model=actual_model,
            response=response,
            status=status,
            session_id=session_id,
            command=safe_command(cmd),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout_path=stream_path.name,
            stderr_path=stderr_path.name,
            runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
            agent=agent,
            subagent_invocation=subagent_invocation,
            copied_session_files=copied,
            raw_model_markers=raw_model_markers,
            error=error,
        )
        write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
        return result


def safe_command(cmd: list[str]) -> list[str]:
    safe = list(cmd)
    if len(safe) > 2:
        safe[2] = f"<prompt {len(cmd[2])} chars>"
    return safe


def parse_stream_json(stdout: str, expected_agent: str | None = None) -> dict[str, Any]:
    assistant_messages: list[str] = []
    result_text: str | None = None
    actual_model: str | None = None
    top_level_model: str | None = None
    subagent_source_models: list[str] = []
    assistant_source_models: list[str] = []
    agent_tool_call_ids: list[str] = []
    agent_tool_call_subagent_types: list[str] = []
    agent_tool_result_ids: list[str] = []
    subagent_message_tool_ids: list[str] = []
    markers: list[str] = []
    error: str | None = None

    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        model = event.get("model")
        if isinstance(model, str):
            markers.append(model)
            if top_level_model is None:
                top_level_model = model
        updates = event.get("updates")
        if isinstance(updates, dict):
            model_name = updates.get("model_name")
            if isinstance(model_name, str):
                markers.append(model_name)
                actual_model = actual_model or model_name
        if event.get("type") == "assistant":
            message = event.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                assistant_messages.append(message["content"])
            if isinstance(message, dict):
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call.get("function") if isinstance(tool_call, dict) else None
                    if not isinstance(function, dict) or function.get("name") != "Agent":
                        continue
                    tool_id = tool_call.get("id")
                    if isinstance(tool_id, str):
                        agent_tool_call_ids.append(tool_id)
                    arguments = function.get("arguments")
                    if isinstance(arguments, str):
                        try:
                            parsed_arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            parsed_arguments = {}
                        subagent_type = parsed_arguments.get("subagent_type")
                        if isinstance(subagent_type, str):
                            agent_tool_call_subagent_types.append(subagent_type)
            extra = message.get("extra") if isinstance(message, dict) else None
            if isinstance(extra, dict):
                source_model = extra.get("_source_model")
                if isinstance(source_model, str):
                    markers.append(source_model)
                    assistant_source_models.append(source_model)
                    if event.get("parent_tool_use_id"):
                        subagent_source_models.append(source_model)
                        parent_tool_use_id = event.get("parent_tool_use_id")
                        if isinstance(parent_tool_use_id, str):
                            subagent_message_tool_ids.append(parent_tool_use_id)
        if event.get("subtype") == "tool_result" and event.get("tool_name") == "Agent":
            tool_use_id = event.get("tool_use_id")
            if isinstance(tool_use_id, str):
                agent_tool_result_ids.append(tool_use_id)
        if event.get("type") == "result":
            if isinstance(event.get("result"), str):
                result_text = event["result"]
            if event.get("is_error"):
                error = event.get("result") if isinstance(event.get("result"), str) else "traecli result error"

    actual_model = (
        subagent_source_models[-1]
        if subagent_source_models
        else (top_level_model or (assistant_source_models[-1] if assistant_source_models else None))
    )
    response = result_text or (assistant_messages[-1] if assistant_messages else "")
    subagent_invocation = {
        "required": bool(expected_agent),
        "expected_agent": expected_agent,
        "tool_call_seen": bool(agent_tool_call_ids),
        "tool_call_ids": agent_tool_call_ids,
        "tool_call_subagent_types": sorted(set(agent_tool_call_subagent_types)),
        "tool_result_seen": bool(agent_tool_result_ids),
        "tool_result_ids": agent_tool_result_ids,
        "subagent_message_seen": bool(subagent_message_tool_ids),
        "subagent_message_tool_ids": subagent_message_tool_ids,
        "subagent_source_models": subagent_source_models,
    }
    if expected_agent:
        subagent_invocation["ok"] = (
            expected_agent in agent_tool_call_subagent_types
            and bool(set(agent_tool_call_ids) & set(agent_tool_result_ids))
            and bool(set(agent_tool_call_ids) & set(subagent_message_tool_ids))
            and bool(subagent_source_models)
        )
    else:
        subagent_invocation["ok"] = True
    return {
        "actual_model": actual_model,
        "response": response.strip(),
        "raw_model_markers": sorted(set(markers)),
        "subagent_invocation": subagent_invocation,
        "error": error,
    }


def missing_subagent_invocation(expected_agent: str | None) -> dict[str, Any]:
    return {
        "required": bool(expected_agent),
        "expected_agent": expected_agent,
        "tool_call_seen": False,
        "tool_call_ids": [],
        "tool_call_subagent_types": [],
        "tool_result_seen": False,
        "tool_result_ids": [],
        "subagent_message_seen": False,
        "subagent_message_tool_ids": [],
        "subagent_source_models": [],
        "ok": not bool(expected_agent),
    }


def copy_coco_session_files(session_id: str, output_dir: Path, label: str) -> dict[str, str]:
    session_root = Path.home() / "Library" / "Caches" / "coco" / "sessions" / session_id
    copied: dict[str, str] = {}
    for name in ("session.json", "session.log", "events.jsonl", "traces.jsonl"):
        src = session_root / name
        if src.exists():
            dest = output_dir / f"{label}.coco.{name}"
            dest.write_bytes(src.read_bytes())
            copied[name] = dest.name
    return copied
