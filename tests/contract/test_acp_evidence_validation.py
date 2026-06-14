from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from llm_council_for_trae.html_export import render_html
from llm_council_for_trae.store import ArtifactStore
from llm_council_for_trae.validation import validate_run


MODEL = "GPT-5.4"
DISABLED_TOOLS = ["Skill", "Agent", "Bash", "Read"]


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"


def acp_transcript(
    *,
    response: str = "ACP answer.",
    permission: tuple[str, str] | None = None,
    tool_call: str | None = None,
) -> str:
    events: list[dict] = [
        {"direction": "client_to_server", "method": "initialize", "id": 1},
        {"direction": "client_to_server", "method": "session/new", "id": 2},
        {"direction": "client_to_server", "method": "session/prompt", "id": 3, "params": {"model": MODEL}},
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
    update: dict[str, Any] = {"model": MODEL, "content": response}
    if tool_call:
        update["tool_calls"] = [{"id": "tc-1", "name": tool_call, "arguments": {"command": "pwd"}}]
    events.append({"direction": "server_to_client", "method": "session/update", "params": update})
    return jsonl(*events)


def acp_policy(
    *,
    transcript_path: str,
    requests: list[dict[str, Any]] | None = None,
    backend: str = "acp",
) -> dict[str, Any]:
    return {
        "runtime_backend": backend,
        "enforcement_method": "acp_disabled_tool_permission_broker",
        "enforcement_proof": "transcript_permission_evidence",
        "disabled_tools": DISABLED_TOOLS,
        "tool_permission_requests": requests or [],
        "acp_transcript_path": transcript_path,
        "acp_startup_status": "ok",
    }


def tool_policy() -> dict[str, Any]:
    return {
        "member_tool_mode": "search_enabled",
        "allowed_tools": ["WebSearch", "WebFetch"],
        "disallowed_tools": DISABLED_TOOLS,
        "forbidden_tool_calls": [],
        "tool_calls": [],
        "tool_calls_count": 0,
        "turns_count": 1,
    }


def stage_meta(*, transcript_path: str, requests: list[dict[str, Any]] | None = None, backend: str = "acp") -> dict[str, Any]:
    return {
        "expected_model": MODEL,
        "actual_model": MODEL,
        "response_chars": 11,
        "status": "ok",
        "session_id": "session-1",
        "command": ["traecli", "acp", "serve"],
        "exit_code": 0,
        "stdout_path": Path(transcript_path).name,
        "stderr_path": "A.acp.stderr.log",
        "copied_session_files": {},
        "raw_model_markers": [MODEL],
        "error": None,
        "captured_at": "2026-06-04T00:00:00Z",
        "permission_mode": "acp_permission_broker",
        "tool_budget_status": "ok",
        "assistant_content_chars_total": 11,
        "last_assistant_content_chars": 11,
        "raw_partial_recoverable": False,
    } | tool_policy() | acp_policy(transcript_path=transcript_path, requests=requests, backend=backend)


def decision_summary(html: str) -> str:
    start = html.index('id="decision-summary"')
    end = html.index('id="final-answer"')
    return html[start:end]


def stage_record(*, label: str, transcript_path: str, response: str = "ACP answer.", requests: list[dict[str, Any]] | None = None, backend: str = "acp") -> dict[str, Any]:
    return {
        "label": f"Response {label}",
        "file_label": label,
        "reviewer_label": label,
        "model": MODEL,
        "expected_model": MODEL,
        "actual_model": MODEL,
        "response": response,
        "ranking": "FINAL RANKING:\n1. Response A",
        "parsed_ranking": ["Response A"],
        "parse_status": "ok",
        "status": "ok",
        "error": None,
        "review_path": f"stage2/{label}.review.md",
        "json_path": f"stage2/{label}.review.json",
        "prompt_path": "stage3/chairman.prompt.md",
        "response_path": "stage3/final.md",
    } | tool_policy() | acp_policy(transcript_path=transcript_path, requests=requests, backend=backend)


def write_acp_run(
    store: ArtifactStore,
    *,
    config_backend: str = "acp",
    stage1_transcript: str | None = None,
    stage1_requests: list[dict[str, Any]] | None = None,
    stage1_record_overrides: dict[str, Any] | None = None,
    stage1_meta_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transcript_paths = {
        "stage1": "stage1/A.acp.transcript.jsonl",
        "stage2": "stage2/A.acp.transcript.jsonl",
        "stage3": "stage3/final.acp.transcript.jsonl",
    }
    stage1 = stage_record(label="A", transcript_path=transcript_paths["stage1"], requests=stage1_requests)
    if stage1_record_overrides:
        for key, value in stage1_record_overrides.items():
            if value is None:
                stage1.pop(key, None)
            else:
                stage1[key] = value
    stage2 = stage_record(label="A", transcript_path=transcript_paths["stage2"])
    final = {
        "model": MODEL,
        "expected_model": MODEL,
        "actual_model": MODEL,
        "response": "Final",
        "status": "ok",
        "error": None,
        "prompt_path": "stage3/chairman.prompt.md",
        "response_path": "stage3/final.md",
        "json_path": "stage3/final.json",
    } | tool_policy() | acp_policy(transcript_path=transcript_paths["stage3"])
    manifest = {
        "schema_version": 1,
        "run_id": store.root.name,
        "created_at": "2026-06-04T00:00:00Z",
        "updated_at": "2026-06-04T00:00:00Z",
        "status": "ok",
        "input_chars": 4,
        "config": {
            "members": [MODEL],
            "chairman": MODEL,
            "provider_mode": "direct",
            "runtime_command": "fake",
            "query_timeout": 180,
            "export_html": True,
            "runtime_backend": config_backend,
            "acp_startup_timeout": 30,
        },
        "artifacts": {"html": "html/index.html"},
        "metadata": {"label_to_model": {"Response A": MODEL}, "aggregate_rankings": []},
        "stages": {"stage1": [stage1], "stage2": [stage2], "stage3": final},
        "warnings": [],
        "failures": [],
    }
    store.write_manifest(manifest)
    for relative in [
        "input.md",
        "config.json",
        "runtime/doctor.json",
        "runtime/traecli.models.json",
        "stage1/member.prompt.md",
        "stage1/A.response.md",
        "stage2/review.prompt.md",
        "stage2/label_to_model.json",
        "stage2/aggregate.json",
        "stage2/A.review.md",
        "stage3/chairman.prompt.md",
        "stage3/final.md",
        "html/index.html",
    ]:
        store.write_text(relative, "{}\n")
    clean = acp_transcript()
    store.write_text(transcript_paths["stage1"], stage1_transcript if stage1_transcript is not None else clean)
    store.write_text(transcript_paths["stage2"], clean)
    store.write_text(transcript_paths["stage3"], clean)
    stage1_meta = stage_meta(transcript_path=transcript_paths["stage1"], requests=stage1_requests)
    if stage1_meta_overrides:
        for key, value in stage1_meta_overrides.items():
            if value is None:
                stage1_meta.pop(key, None)
            else:
                stage1_meta[key] = value
    store.write_json("stage1/A.meta.json", stage1_meta)
    store.write_json("stage2/A.meta.json", stage_meta(transcript_path=transcript_paths["stage2"]))
    store.write_json("stage2/A.review.json", stage2)
    store.write_json("stage3/final.meta.json", stage_meta(transcript_path=transcript_paths["stage3"]))
    store.write_json("stage3/final.json", final)
    store.write_json("html/export.json", {"run_id": store.root.name, "generated_at": "2026-06-04T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})
    return manifest


class AcpEvidenceValidationTests(unittest.TestCase):
    def validate_fixture(self, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-acp-evidence")
            write_acp_run(store, **kwargs)
            return validate_run(store)

    def test_validate_accepts_clean_acp_artifact(self):
        validation = self.validate_fixture()

        self.assertEqual(validation["status"], "ok", validation["failures"])
        self.assertFalse(validation["failures"])

    def test_validate_rejects_acp_meta_missing_transcript_path(self):
        validation = self.validate_fixture(stage1_meta_overrides={"acp_transcript_path": None})

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "stage1.A.meta_acp_transcript_path" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_acp_transcript_path_escape(self):
        validation = self.validate_fixture(stage1_meta_overrides={"acp_transcript_path": "../evil.jsonl"})

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "stage1.A.meta_acp_transcript_path_safe" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_bad_jsonl_transcript(self):
        validation = self.validate_fixture(stage1_transcript="{bad-json\n")

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "stage1.A_acp_transcript_protocol" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_non_structured_transcript(self):
        validation = self.validate_fixture(stage1_transcript="{}\n")

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "stage1.A_acp_transcript_protocol" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_forbidden_permission_allowed(self):
        permission = [{"id": "perm-1", "tool_name": "Bash", "arguments": "{\"command\":\"pwd\"}", "decision": "allow"}]
        validation = self.validate_fixture(stage1_transcript=acp_transcript(permission=("Bash", "allow")), stage1_requests=permission)

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "stage1.A_acp_forbidden_permission_allowed" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_meta_permission_request_mismatch(self):
        permission = [{"id": "perm-1", "tool_name": "Bash", "arguments": "{\"command\":\"pwd\"}", "decision": "deny"}]
        validation = self.validate_fixture(stage1_transcript=acp_transcript(permission=("Bash", "allow")), stage1_requests=permission)

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "stage1.A_acp_permission_requests_match" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_config_acp_missing_stage_record_evidence(self):
        validation = self.validate_fixture(stage1_record_overrides={"runtime_backend": None, "enforcement_method": None})

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "manifest.stage1.A_runtime_backend_acp" for check in validation["failures"]), validation["failures"])

    def test_validate_rejects_record_claiming_acp_when_config_is_direct(self):
        validation = self.validate_fixture(config_backend="direct")

        self.assertEqual(validation["status"], "failed")
        self.assertTrue(any(check["name"] == "manifest.stage1.A_acp_config_consistency" for check in validation["failures"]), validation["failures"])

    def test_html_shows_acp_five_state_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-acp-html")
            permission = [{"id": "perm-1", "tool_name": "Bash", "arguments": "{\"command\":\"pwd\"}", "decision": "deny"}]
            manifest = write_acp_run(
                store,
                stage1_transcript=acp_transcript(permission=("Bash", "deny"), tool_call="WebSearch"),
                stage1_requests=permission,
            )

            rendered = render_html(store.root, manifest)

        summary = decision_summary(rendered)
        self.assertIn("ACP 工具证据", summary)
        self.assertIn("Allowed", summary)
        self.assertIn("Disabled", summary)
        self.assertIn("Requested", summary)
        self.assertIn("Denied", summary)
        self.assertIn("Used", summary)
        self.assertIn("Requested 1", summary)
        self.assertIn("Denied 1", summary)

    def test_html_hides_direct_acp_state_not_applicable_from_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-direct-html")
            manifest = write_acp_run(store, config_backend="direct", stage1_record_overrides={"runtime_backend": "direct"})
            manifest["stages"]["stage2"][0]["runtime_backend"] = "direct"
            manifest["stages"]["stage3"]["runtime_backend"] = "direct"

            rendered = render_html(store.root, manifest)

        summary = decision_summary(rendered)
        self.assertNotIn("ACP 工具证据", summary)
        self.assertNotIn("not_applicable", summary)


if __name__ == "__main__":
    unittest.main()
