from __future__ import annotations

import json
import unittest

from llm_council_for_trae.acp_transcript import parse_acp_transcript_text


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"


def live_handshake(*, current_model: str = "Qwen3.6-Plus", available: list[str] | None = None) -> list[dict]:
    models = [{"modelId": name, "name": name} for name in (available or [current_model])]
    return [
        {"direction": "client_to_server", "method": "initialize", "id": 101, "params": {"protocolVersion": 1}},
        {"direction": "server_to_client", "id": 101, "result": {"protocolVersion": 1}},
        {"direction": "client_to_server", "method": "session/new", "id": 102, "params": {"cwd": "/tmp", "mcpServers": []}},
        {
            "direction": "server_to_client",
            "id": 102,
            "result": {"sessionId": "sess-live", "models": {"availableModels": models, "currentModelId": current_model}},
        },
        {
            "direction": "client_to_server",
            "method": "session/prompt",
            "id": 103,
            "params": {"sessionId": "sess-live", "prompt": [{"type": "text", "text": "Q"}]},
        },
    ]


def update(payload: dict) -> dict:
    return {
        "direction": "server_to_client",
        "method": "session/update",
        "params": {"sessionId": "sess-live", "update": payload},
    }


def message_chunk(text: str) -> dict:
    return update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}})


def thought_chunk(text: str) -> dict:
    return update({"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": text}})


def tool_call(title: str, call_id: str, raw_input: dict) -> dict:
    return update(
        {
            "sessionUpdate": "tool_call",
            "status": "in_progress",
            "title": title,
            "toolCallId": call_id,
            "rawInput": raw_input,
        }
    )


def tool_call_update(call_id: str, status: str) -> dict:
    return update({"sessionUpdate": "tool_call_update", "status": status, "toolCallId": call_id})


def prompt_end(stop_reason: str = "end_turn") -> dict:
    return {"direction": "server_to_client", "id": 103, "result": {"stopReason": stop_reason}}


def permission_exchange(title: str, call_id: str, option_id: str, *, request_id: int = 1) -> list[dict]:
    return [
        {
            "direction": "server_to_client",
            "method": "session/request_permission",
            "id": request_id,
            "params": {
                "sessionId": "sess-live",
                "options": [
                    {"kind": "allow_once", "optionId": "allow", "name": "Allow once"},
                    {"kind": "reject_once", "optionId": "reject", "name": "Reject"},
                ],
                "toolCall": {"title": title, "toolCallId": call_id, "rawInput": {"command": "pwd"}},
            },
        },
        {
            "direction": "client_to_server",
            "id": request_id,
            "result": {"outcome": {"outcome": "selected", "optionId": option_id}},
        },
    ]


class AcpLiveTranscriptParserTests(unittest.TestCase):
    def test_live_message_chunks_concatenate_and_thoughts_are_excluded(self):
        parsed = parse_acp_transcript_text(
            jsonl(
                *live_handshake(),
                thought_chunk("The user wants"),
                thought_chunk(" a short answer."),
                message_chunk("PROBE"),
                message_chunk("_MODEL_OK"),
                prompt_end(),
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(parsed.response, "PROBE_MODEL_OK")

    def test_live_actual_model_falls_back_to_session_new_current_model(self):
        parsed = parse_acp_transcript_text(
            jsonl(*live_handshake(current_model="Qwen3.6-Plus"), message_chunk("hi"), prompt_end())
        )

        self.assertEqual(parsed.actual_model, "Qwen3.6-Plus")

    def test_live_tool_call_uses_canonical_tool_name(self):
        parsed = parse_acp_transcript_text(
            jsonl(
                *live_handshake(),
                tool_call("bash", "call_1", {"Command": "pwd"}),
                tool_call_update("call_1", "completed"),
                message_chunk("done"),
                prompt_end(),
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(len(parsed.tool_calls), 1)
        self.assertEqual(parsed.tool_calls[0]["name"], "Bash")
        self.assertEqual(parsed.tool_calls[0]["id"], "call_1")
        self.assertEqual(parsed.tool_calls_count, 1)

    def test_live_denied_tool_call_is_not_counted_as_used(self):
        parsed = parse_acp_transcript_text(
            jsonl(
                *live_handshake(),
                tool_call("bash", "call_1", {"command": "pwd"}),
                *permission_exchange("bash", "call_1", "reject"),
                tool_call_update("call_1", "failed"),
                message_chunk("I could not run that."),
                prompt_end(),
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(parsed.tool_calls, [])
        self.assertEqual(parsed.tool_calls_count, 0)
        self.assertEqual(len(parsed.tool_permission_requests), 1)
        permission = parsed.tool_permission_requests[0]
        self.assertEqual(permission["tool_name"], "Bash")
        self.assertEqual(permission["decision"], "deny")

    def test_live_allowed_permission_records_allow_and_keeps_tool_call(self):
        parsed = parse_acp_transcript_text(
            jsonl(
                *live_handshake(),
                tool_call("WebSearch", "call_2", {"query": "Eiffel"}),
                *permission_exchange("WebSearch", "call_2", "allow"),
                tool_call_update("call_2", "completed"),
                message_chunk("1889."),
                prompt_end(),
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(len(parsed.tool_calls), 1)
        self.assertEqual(parsed.tool_calls[0]["name"], "WebSearch")
        self.assertEqual(parsed.tool_permission_requests[0]["decision"], "allow")

    def test_live_message_blocks_split_around_tool_calls(self):
        parsed = parse_acp_transcript_text(
            jsonl(
                *live_handshake(),
                message_chunk("Let me check."),
                tool_call("WebSearch", "call_3", {"query": "x"}),
                tool_call_update("call_3", "completed"),
                message_chunk("Answer: 42."),
                prompt_end(),
            )
        )

        self.assertEqual(parsed.response, "Let me check.\nAnswer: 42.")

    def test_live_available_commands_update_is_ignored(self):
        parsed = parse_acp_transcript_text(
            jsonl(
                *live_handshake(),
                update({"availableCommands": [{"name": "init", "description": "x"}]}),
                message_chunk("ok"),
                prompt_end(),
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(parsed.response, "ok")
        self.assertEqual(parsed.tool_calls, [])

    def test_live_prompt_response_id_reuse_does_not_clobber_permission_decision(self):
        # server-side permission id may collide with a later response id; the
        # recorded decision must stay attached to the permission exchange.
        events = jsonl(
            *live_handshake(),
            tool_call("bash", "call_4", {"command": "pwd"}),
            *permission_exchange("bash", "call_4", "reject", request_id=103),
            tool_call_update("call_4", "failed"),
            message_chunk("denied"),
            prompt_end(),
        )
        parsed = parse_acp_transcript_text(events)

        self.assertEqual(parsed.tool_permission_requests[0]["decision"], "deny")


if __name__ == "__main__":
    unittest.main()
