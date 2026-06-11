from __future__ import annotations

import asyncio
import inspect
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .acp_transcript import canonical_tool_name, parse_acp_transcript_text
from .provider import (
    ModelCallResult,
    copy_traecli_session_files,
    forbidden_tool_calls_for_mode,
    missing_subagent_invocation,
    terminate_process_tree,
    termination_with_reason,
    tool_policy_for_mode,
)
from .utils import DEFAULT_TRAECLI, slugify, utc_now, write_json, write_text


SERVER_STDERR_TAIL_CHARS = 10_000


class AcpStartupError(RuntimeError):
    pass


class _ServerClosedError(RuntimeError):
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


@dataclass
class AcpLiveOutcome:
    transcript_text: str
    command: list[str]
    terminal_error: str | None = None
    termination: dict[str, Any] = field(default_factory=dict)
    server_stderr: str = ""
    acp_session_id: str | None = None


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
        acp_prompt_grace: int = 30,
        transcript_provider: TranscriptProvider | None = None,
    ):
        self.runtime_command = os.environ.get("LLM_COUNCIL_FOR_TRAE_TRAECLI", runtime_command)
        self.query_timeout = query_timeout
        self.runtime_cwd = runtime_cwd
        self.use_yolo = use_yolo
        self.member_tool_mode = member_tool_mode
        self.acp_startup_timeout = acp_startup_timeout
        self.acp_prompt_grace = acp_prompt_grace
        self.transcript_provider = transcript_provider
        self.allowed_tools, self.disallowed_tools = tool_policy_for_mode(member_tool_mode)

    def _build_command(self) -> list[str]:
        return [self.runtime_command, "acp", "serve"]

    def _build_live_command(self, request: AcpQueryRequest) -> list[str]:
        command = list(request.command)
        command += ["-c", f"model.name={request.model}"]
        command += ["--query-timeout", f"{int(round(float(request.query_timeout)))}s"]
        for tool in request.allowed_tools:
            command += ["--allowed-tool", tool]
        for tool in request.disabled_tools:
            command += ["--disallowed-tool", tool]
        if self.use_yolo:
            command.append("--yolo")
        return command

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

        terminal_error: str | None = None
        termination: dict[str, Any] = {}
        server_stderr = ""
        copied_session_files: dict[str, str] = {}
        try:
            if self.transcript_provider is not None:
                transcript_text = await self._get_transcript(request)
            else:
                outcome = await _AcpLiveSession(self, request, transcript_path).run()
                transcript_text = outcome.transcript_text
                command = outcome.command
                terminal_error = outcome.terminal_error
                termination = outcome.termination
                server_stderr = outcome.server_stderr
                if outcome.acp_session_id:
                    copied_session_files = copy_traecli_session_files(
                        outcome.acp_session_id, output_dir, label
                    )
        except AcpStartupError as exc:
            error = f"acp_startup_failed: {exc}"
            if not transcript_path.exists():
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
            if not transcript_path.exists():
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
        if terminal_error:
            status = "failed"
            error = terminal_error
        elif parsed.protocol_errors:
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

        stderr_text = (error + "\n") if error else ""
        if server_stderr.strip():
            stderr_text += "--- acp server stderr ---\n" + server_stderr[-SERVER_STDERR_TAIL_CHARS:]
        write_text(stderr_path, stderr_text)
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
            copied_session_files=copied_session_files,
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
            termination=termination,
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


class _AcpLiveSession:
    """One live `traecli acp serve` process driving a single query.

    Process-per-query: spawn -> initialize -> session/new (model validation)
    -> session/prompt -> permission broker loop -> stop reason mapping.
    Every JSON-RPC message in both directions is appended to the transcript
    file as it happens, so a crash or kill still leaves honest evidence.

    Anti-fallback evidence note (probe 2026-06-11): live `session/update`
    events carry no model field, so the actual-model evidence ceiling is
    `session/new`'s `currentModelId` (driven by `-c model.name=...`) plus the
    `availableModels` pre-flight check below; this is declared in the probe
    report and weaker than direct's per-message stream-json model markers.
    """

    def __init__(self, runtime: AcpTraeCliRuntime, request: AcpQueryRequest, transcript_path: Path):
        self.runtime = runtime
        self.request = request
        self.transcript_path = transcript_path
        self.command = runtime._build_live_command(request)
        self.proc: asyncio.subprocess.Process | None = None
        self.next_request_id = 100
        self.transcript_lines: list[str] = []
        self.transcript_file = None
        self.stderr_task: asyncio.Task | None = None

    async def run(self) -> AcpLiveOutcome:
        terminal_error: str | None = None
        termination: dict[str, Any] = {}
        acp_session_id: str | None = None
        self.transcript_file = self.transcript_path.open("w", encoding="utf-8")
        try:
            try:
                self.proc = await asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.request.runtime_cwd) if self.request.runtime_cwd else None,
                    limit=10 * 1024 * 1024,
                    start_new_session=os.name != "nt",
                )
            except (OSError, ValueError) as exc:
                raise AcpStartupError(f"spawn failed: {exc}") from exc
            self.stderr_task = asyncio.create_task(self.proc.stderr.read())

            loop = asyncio.get_running_loop()
            startup_deadline = loop.time() + self.request.startup_timeout
            try:
                await self._rpc(
                    "initialize",
                    {
                        "protocolVersion": 1,
                        "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
                    },
                    startup_deadline,
                )
                new_response = await self._rpc(
                    "session/new",
                    {
                        "cwd": str(self.request.runtime_cwd) if self.request.runtime_cwd else os.getcwd(),
                        "mcpServers": [],
                    },
                    startup_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise AcpStartupError(
                    f"server did not complete initialize/session-new within "
                    f"{self.request.startup_timeout}s (acp_startup_timeout)"
                ) from exc
            except _ServerClosedError as exc:
                raise AcpStartupError(f"server closed stream during startup: {exc}") from exc

            if "error" in new_response:
                raise AcpStartupError(f"session/new failed: {_compact(new_response.get('error'))[:500]}")
            new_result = new_response.get("result") if isinstance(new_response.get("result"), dict) else {}
            session_value = new_result.get("sessionId")
            acp_session_id = session_value if isinstance(session_value, str) and session_value else None
            terminal_error = self._validate_models(new_result)
            if terminal_error is None and acp_session_id is None:
                terminal_error = "acp_protocol_error: session/new returned no sessionId"

            if terminal_error is None:
                prompt_deadline = (
                    loop.time() + float(self.request.query_timeout) + self.runtime.acp_prompt_grace
                )
                try:
                    prompt_response = await self._rpc(
                        "session/prompt",
                        {
                            "sessionId": acp_session_id,
                            "prompt": [{"type": "text", "text": self.request.prompt}],
                        },
                        prompt_deadline,
                    )
                except asyncio.TimeoutError:
                    termination = termination_with_reason(
                        await terminate_process_tree(self.proc), "timeout"
                    )
                    terminal_error = "timeout"
                except _ServerClosedError as exc:
                    terminal_error = f"acp_protocol_error: server closed stream during prompt: {exc}"
                else:
                    terminal_error, termination = await self._map_prompt_response(prompt_response)
        except asyncio.CancelledError:
            if self.proc is not None:
                await terminate_process_tree(self.proc)
            raise
        finally:
            if self.proc is not None:
                await terminate_process_tree(self.proc)
            server_stderr = await self._collect_stderr()
            self.transcript_file.close()

        return AcpLiveOutcome(
            transcript_text="".join(self.transcript_lines),
            command=self.command,
            terminal_error=terminal_error,
            termination=termination,
            server_stderr=server_stderr,
            acp_session_id=acp_session_id,
        )

    def _validate_models(self, new_result: dict[str, Any]) -> str | None:
        models = new_result.get("models") if isinstance(new_result.get("models"), dict) else {}
        available = {
            item.get("modelId")
            for item in models.get("availableModels") or []
            if isinstance(item, dict) and isinstance(item.get("modelId"), str)
        }
        if self.request.model not in available:
            return f"invalid_model: {self.request.model} not in ACP availableModels"
        current = models.get("currentModelId")
        if current != self.request.model:
            return f"expected model {self.request.model}, actual model {current or 'unknown'}"
        return None

    async def _map_prompt_response(
        self, prompt_response: dict[str, Any]
    ) -> tuple[str | None, dict[str, Any]]:
        if "error" in prompt_response:
            blob = _compact(prompt_response.get("error"))
            if "context deadline exceeded" in blob:
                termination = termination_with_reason(
                    await terminate_process_tree(self.proc), "timeout"
                )
                return "timeout", termination
            return f"acp_prompt_error: {blob[:500]}", {}
        result = prompt_response.get("result") if isinstance(prompt_response.get("result"), dict) else {}
        stop_reason = result.get("stopReason")
        if stop_reason != "end_turn":
            return f"acp_stop_reason: {stop_reason}", {}
        return None, {}

    async def _rpc(self, method: str, params: dict[str, Any], deadline: float) -> dict[str, Any]:
        self.next_request_id += 1
        request_id = self.next_request_id
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = await self._read_message(deadline)
            if message.get("id") == request_id and ("result" in message or "error" in message):
                return message
            if "method" in message and "id" in message:
                await self._handle_server_request(message)
            # notifications (session/update etc.) are logged by _read_message

    async def _read_message(self, deadline: float) -> dict[str, Any]:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=remaining)
            if not line:
                raise _ServerClosedError(f"stdout EOF (returncode={self.proc.returncode})")
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            self._log("server_to_client", message)
            return message

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method == "session/request_permission":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            outcome = self._decide_permission(params)
            await self._send({"jsonrpc": "2.0", "id": message.get("id"), "result": outcome})
            return
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32601, "message": "Method not found", "data": {"method": method}},
            }
        )

    def _decide_permission(self, params: dict[str, Any]) -> dict[str, Any]:
        tool_call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
        title = tool_call.get("title") or params.get("tool_name") or params.get("name") or ""
        name = canonical_tool_name(title)
        allowed = set(self.request.allowed_tools)
        disallowed = set(self.request.disabled_tools)
        allow = bool(name) and name in allowed and name not in disallowed
        options = [option for option in params.get("options") or [] if isinstance(option, dict)]
        option_id = self._pick_option(options, allow)
        if option_id is None:
            return {"outcome": {"outcome": "cancelled"}}
        return {"outcome": {"outcome": "selected", "optionId": option_id}}

    @staticmethod
    def _pick_option(options: list[dict[str, Any]], allow: bool) -> Any:
        kind = "allow_once" if allow else "reject_once"
        hint = "allow" if allow else "reject"
        exact = [option for option in options if option.get("kind") == kind]
        for option in exact:
            if str(option.get("optionId", "")).lower() == hint:
                return option.get("optionId")
        if exact:
            return exact[0].get("optionId")
        for option in options:
            if hint in str(option.get("optionId", "")).lower():
                return option.get("optionId")
        return None

    async def _send(self, message: dict[str, Any]) -> None:
        self._log("client_to_server", message)
        self.proc.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

    def _log(self, direction: str, message: dict[str, Any]) -> None:
        record = {"ts": utc_now(), "direction": direction} | message
        line = json.dumps(record, ensure_ascii=False) + "\n"
        self.transcript_lines.append(line)
        self.transcript_file.write(line)
        self.transcript_file.flush()

    async def _collect_stderr(self) -> str:
        if self.stderr_task is None:
            return ""
        try:
            data = await asyncio.wait_for(asyncio.shield(self.stderr_task), timeout=2)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            self.stderr_task.cancel()
            return ""
        return data.decode("utf-8", errors="replace")


def _compact(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)
