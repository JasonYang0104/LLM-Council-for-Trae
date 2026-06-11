from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from llm_council_for_trae.acp_transcript import parse_acp_transcript_text, resolve_acp_transcript_path


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"


def base_events(*extra: dict) -> str:
    return jsonl(
        {"direction": "client_to_server", "method": "initialize", "id": 1},
        {"direction": "client_to_server", "method": "session/new", "id": 2},
        {"direction": "client_to_server", "method": "session/prompt", "id": 3, "params": {"model": "Model-X"}},
        *extra,
    )


class AcpTranscriptParserTests(unittest.TestCase):
    def test_parser_extracts_response_actual_model_and_tool_calls(self):
        parsed = parse_acp_transcript_text(
            base_events(
                {
                    "direction": "server_to_client",
                    "method": "session/update",
                    "params": {
                        "model": "Model-X",
                        "content": "ACP answer.",
                        "tool_calls": [
                            {"id": "tc-search", "name": "WebSearch", "arguments": {"query": "latest"}}
                        ],
                    },
                },
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(parsed.response, "ACP answer.")
        self.assertEqual(parsed.actual_model, "Model-X")
        self.assertEqual(parsed.tool_calls_count, 1)
        self.assertEqual(parsed.turns_count, 1)
        self.assertEqual(
            parsed.tool_calls,
            [{"id": "tc-search", "name": "WebSearch", "arguments": "{\"query\":\"latest\"}", "turn_index": 1}],
        )

    def test_parser_extracts_permission_request_and_decision(self):
        parsed = parse_acp_transcript_text(
            base_events(
                {
                    "direction": "server_to_client",
                    "method": "session/request_permission",
                    "id": "perm-1",
                    "params": {"tool_name": "Bash", "arguments": {"command": "pwd"}},
                },
                {
                    "direction": "client_to_server",
                    "id": "perm-1",
                    "result": {"decision": "deny"},
                },
                {
                    "direction": "server_to_client",
                    "method": "session/update",
                    "params": {"model": "Model-X", "content": "Denied and continued."},
                },
            )
        )

        self.assertEqual(parsed.protocol_errors, [])
        self.assertEqual(
            parsed.tool_permission_requests,
            [{"id": "perm-1", "tool_name": "Bash", "arguments": "{\"command\":\"pwd\"}", "decision": "deny"}],
        )

    def test_parser_reports_bad_jsonl(self):
        parsed = parse_acp_transcript_text("{bad-json\n")

        self.assertIn("invalid_json_line:1", parsed.protocol_errors)
        self.assertEqual(parsed.response, "")

    def test_parser_reports_non_empty_transcript_without_minimal_acp_structure(self):
        parsed = parse_acp_transcript_text("{}\n")

        self.assertIn("missing_required_method:initialize", parsed.protocol_errors)
        self.assertIn("missing_required_method:session/new", parsed.protocol_errors)
        self.assertIn("missing_required_method:session/prompt", parsed.protocol_errors)
        self.assertIn("missing_required_method:session/update", parsed.protocol_errors)

    def test_transcript_path_must_stay_inside_run_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ok = resolve_acp_transcript_path(root, "stage1/A.acp.transcript.jsonl")
            self.assertEqual(ok, root.resolve() / "stage1" / "A.acp.transcript.jsonl")

            with self.assertRaisesRegex(ValueError, "relative ACP transcript path"):
                resolve_acp_transcript_path(root, "/tmp/evil.jsonl")

            with self.assertRaisesRegex(ValueError, "escapes run root"):
                resolve_acp_transcript_path(root, "stage1/../..//evil.jsonl")


if __name__ == "__main__":
    unittest.main()
