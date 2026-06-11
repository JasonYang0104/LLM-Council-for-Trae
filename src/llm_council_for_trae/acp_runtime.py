from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .acp_transcript import parse_acp_transcript_text
from .provider import (
    ModelCallResult,
    forbidden_tool_calls_for_mode,
    missing_subagent_invocation,
    tool_policy_for_mode,
)
from .utils import DEFAULT_TRAECLI, slugify, utc_now, write_json, write_text


class AcpStartupError(RuntimeError):
    pass


@dataclass
class AcpQueryRequest:
    command: list[str]
    model: str
    prompt: str
    run_id: str
    stage: str
    label: str
    session_id: str
    output_dir: Path
    runtime_cwd: Path | None
    allowed_tools: list[str]
    disabled_tools: list[str]
    query_timeout: int | float
    startup_timeout: int


TranscriptProvider = Callable[..., Any]


class AcpTraeCliRuntime:
    def __init__(
        self,
        runtime_command: str = DEFAULT_TRAECLI,
        query_timeout: int = 180,
        runtime_cwd: Path | None = None,
        use_yolo: bool = False,
        member_tool_mode: str = "search_enabled",
        acp_startup_timeout: int = 30,
        transcript_provider: TranscriptProvider | None = None,
    ):
        self.runtime_command = os.environ.get("LLM_COUNCIL_FOR_TRAE_TRAECLI", runtime_command)
        self.query_timeout = query_timeout
        self.runtime_cwd = runtime_cwd
        self.use_yolo = use_yolo
        self.member_tool_mode = member_tool_mode
        self.acp_startup_timeout = acp_startup_timeout
        self.transcript_provider = transcript_provider
        self.allowed_tools, self.disallowed_tools = tool_policy_for_mode(member_tool_mode)

    def _build_command(self) -> list[str]:
        return [self.runtime_command, "acp", "serve"]

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
        session_id = slugify(f"{run_id}-{stage}-{label}")
        transcript_path = output_dir / f"{label}.acp.transcript.jsonl"
        stderr_path = output_dir / f"{label}.acp.stderr.log"
        relative_transcript_path = f"{output_dir.name}/{transcript_path.name}"
        command = self._build_command()
        effective_timeout = query_timeout if query_timeout is not None else self.query_timeout
        request = AcpQueryRequest(
            command=command,
            model=model,
            prompt=prompt,
            run_id=run_id,
            stage=stage,
            label=label,
            session_id=session_id,
            output_dir=output_dir,
            runtime_cwd=self.runtime_cwd,
            allowed_tools=list(self.allowed_tools),
            disabled_tools=list(self.disallowed_tools),
            query_timeout=effective_timeout,
            startup_timeout=self.acp_startup_timeout,
        )

        try:
            transcript_text = await self._get_transcript(request)
        except AcpStartupError as exc:
            error = f"acp_startup_failed: {exc}"
            write_text(transcript_path, "")
            write_text(stderr_path, error + "\n")
            result = self._failed_result(
                model=model,
                session_id=session_id,
                command=command,
                transcript_path=transcript_path,
                stderr_path=stderr_path,
                relative_transcript_path=relative_transcript_path,
                agent=agent,
                error=error,
            )
            write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
            return result
        except asyncio.CancelledError:
            write_text(transcript_path, "")
            write_text(stderr_path, "Cancelled while waiting for ACP runtime.\n")
            result = self._failed_result(
                model=model,
                session_id=session_id,
                command=command,
                transcript_path=transcript_path,
                stderr_path=stderr_path,
                relative_transcript_path=relative_transcript_path,
                agent=agent,
                error="cancelled",
                termination={"termination_reason": "cancelled"},
            )
            write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
            raise

        write_text(transcript_path, transcript_text)
        parsed = parse_acp_transcript_text(transcript_text)
        forbidden_tool_calls = forbidden_tool_calls_for_mode(parsed.tool_calls, self.member_tool_mode)
        forbidden_allowed_permissions = self._forbidden_allowed_permissions(parsed.tool_permission_requests)

        status = "ok"
        error = None
        if parsed.protocol_errors:
            status = "failed"
            error = f"acp_protocol_error: {parsed.protocol_errors[0]}"
        elif not parsed.response.strip():
            status = "failed"
            error = "empty model response"
        elif parsed.actual_model != model:
            status = "failed"
            error = f"expected model {model}, actual model {parsed.actual_model or 'unknown'}"
        elif forbidden_allowed_permissions:
            status = "failed"
            names = ", ".join(permission["tool_name"] or "unknown" for permission in forbidden_allowed_permissions)
            error = f"tool_contaminated: forbidden ACP permission allow(s): {names}"
        elif forbidden_tool_calls:
            status = "failed"
            names = ", ".join(call.get("name", "unknown") for call in forbidden_tool_calls)
            error = f"tool_contaminated: forbidden tool call(s): {names}"

        write_text(stderr_path, (error + "\n") if error else "")
        response = parsed.response
        result = ModelCallResult(
            expected_model=model,
            actual_model=parsed.actual_model,
            response=response,
            status=status,
            session_id=session_id,
            command=command,
            exit_code=0 if status == "ok" else 1,
            stdout_path=transcript_path.name,
            stderr_path=stderr_path.name,
            runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
            agent=agent,
            subagent_invocation=missing_subagent_invocation(agent),
            raw_model_markers=([parsed.actual_model] if parsed.actual_model else []),
            error=error,
            permission_mode="acp_permission_broker",
            member_tool_mode=self.member_tool_mode,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            forbidden_tool_calls=forbidden_tool_calls,
            tool_calls=parsed.tool_calls,
            assistant_content_chars_total=len(response),
            last_assistant_content_chars=len(response),
            raw_partial_recoverable=False,
            tool_calls_count=parsed.tool_calls_count,
            turns_count=parsed.turns_count,
            runtime_backend="acp",
            enforcement_method="acp_disabled_tool_permission_broker",
            enforcement_proof="transcript_permission_evidence",
            disabled_tools=self.disallowed_tools,
            tool_permission_requests=parsed.tool_permission_requests,
            acp_transcript_path=relative_transcript_path,
            acp_startup_status="ok",
        )
        write_json(output_dir / f"{label}.meta.json", result.to_json() | {"captured_at": utc_now()})
        return result

    async def _get_transcript(self, request: AcpQueryRequest) -> str:
        if self.transcript_provider is None:
            raise AcpStartupError("ACP live transport is not implemented yet")
        value = self.transcript_provider(request)
        if inspect.isawaitable(value):
            value = await value
        if not isinstance(value, str):
            raise AcpStartupError("transcript provider returned non-string transcript")
        return value

    def _forbidden_allowed_permissions(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = set(self.allowed_tools)
        disallowed = set(self.disallowed_tools)
        forbidden: list[dict[str, Any]] = []
        for request in requests:
            tool_name = request.get("tool_name")
            if not isinstance(tool_name, str) or not tool_name:
                forbidden.append(request)
                continue
            if request.get("decision") != "allow":
                continue
            if tool_name in disallowed or tool_name not in allowed:
                forbidden.append(request)
        return forbidden

    def _failed_result(
        self,
        *,
        model: str,
        session_id: str,
        command: list[str],
        transcript_path: Path,
        stderr_path: Path,
        relative_transcript_path: str,
        agent: str | None,
        error: str,
        termination: dict[str, Any] | None = None,
    ) -> ModelCallResult:
        return ModelCallResult(
            expected_model=model,
            actual_model=None,
            response="",
            status="failed",
            session_id=session_id,
            command=command,
            exit_code=-1,
            stdout_path=transcript_path.name,
            stderr_path=stderr_path.name,
            runtime_cwd=str(self.runtime_cwd) if self.runtime_cwd else None,
            agent=agent,
            subagent_invocation=missing_subagent_invocation(agent),
            error=error,
            permission_mode="acp_permission_broker",
            member_tool_mode=self.member_tool_mode,
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            termination=termination or {},
            runtime_backend="acp",
            enforcement_method="acp_disabled_tool_permission_broker",
            enforcement_proof="transcript_permission_evidence",
            disabled_tools=self.disallowed_tools,
            acp_transcript_path=relative_transcript_path,
            acp_startup_status="failed" if error.startswith("acp_startup_failed:") else "ok",
        )
