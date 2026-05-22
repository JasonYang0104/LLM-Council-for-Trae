import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from coco_llm_council.council import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    calculate_aggregate_rankings,
    parse_ranking_from_text,
)
from coco_llm_council.html_export import export_html
from coco_llm_council.model_selection import (
    recommend_model_choice,
    resolve_model_tokens,
    select_model_choice_interactively,
)
from coco_llm_council.provider import parse_stream_json
from coco_llm_council.store import ArtifactStore
from coco_llm_council.validation import validate_run


def stage_meta(expected_model="GPT-5.4", actual_model=None):
    return {
        "expected_model": expected_model,
        "actual_model": actual_model or expected_model,
        "response_chars": 2,
        "status": "ok",
        "session_id": "session-1",
        "command": ["traecli", "-p", "<prompt 2 chars>"],
        "exit_code": 0,
        "stdout_path": "A.coco.stream.jsonl",
        "stderr_path": "A.coco.stderr.log",
        "copied_session_files": {},
        "raw_model_markers": [actual_model or expected_model],
        "error": None,
        "captured_at": "2026-05-22T00:00:00Z",
    }


def review_json():
    return {
        "reviewer_label": "A",
        "model": "GPT-5.4",
        "expected_model": "GPT-5.4",
        "actual_model": "GPT-5.4",
        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
        "parsed_ranking": ["Response A", "Response B"],
        "parse_status": "ok",
        "status": "ok",
        "error": None,
        "review_path": "stage2/A.review.md",
        "json_path": "stage2/A.review.json",
    }


def final_json():
    return {
        "model": "GPT-5.4",
        "expected_model": "GPT-5.4",
        "actual_model": "GPT-5.4",
        "response": "Final",
        "status": "ok",
        "error": None,
        "prompt_path": "stage3/chairman.prompt.md",
        "response_path": "stage3/final.md",
        "json_path": "stage3/final.json",
    }


def write_json_text(store, relative, data):
    store.write_text(relative, json.dumps(data) + "\n")


def write_minimal_valid_direct_run(store):
    manifest = {
        "schema_version": 1,
        "run_id": store.root.name,
        "created_at": "2026-05-22T00:00:00Z",
        "updated_at": "2026-05-22T00:00:00Z",
        "status": "ok",
        "input_chars": 4,
        "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake", "query_timeout": 180, "export_html": True},
        "artifacts": {"html": "html/index.html"},
        "metadata": {"label_to_model": {"Response A": "GPT-5.4"}, "aggregate_rankings": []},
        "stages": {
            "stage1": [{"label": "Response A", "file_label": "A", "model": "GPT-5.4", "expected_model": "GPT-5.4", "actual_model": "GPT-5.4", "response": "A", "status": "ok"}],
            "stage2": [review_json() | {"ranking": "FINAL RANKING:\n1. Response A", "parsed_ranking": ["Response A"]}],
            "stage3": final_json(),
        },
        "warnings": [],
        "failures": [],
    }
    store.write_manifest(manifest)
    for relative in [
        "input.md",
        "config.json",
        "runtime/doctor.json",
        "runtime/coco.models.json",
        "stage1/member.prompt.md",
        "stage1/A.response.md",
        "stage1/A.coco.stream.jsonl",
        "stage2/review.prompt.md",
        "stage2/label_to_model.json",
        "stage2/aggregate.json",
        "stage2/A.review.md",
        "stage2/A.coco.stream.jsonl",
        "stage3/chairman.prompt.md",
        "stage3/final.md",
        "stage3/final.coco.stream.jsonl",
        "html/index.html",
    ]:
        store.write_text(relative, "{}\n")
    write_json_text(store, "stage1/A.meta.json", stage_meta("GPT-5.4"))
    write_json_text(store, "stage2/A.meta.json", stage_meta("GPT-5.4"))
    write_json_text(store, "stage2/A.review.json", manifest["stages"]["stage2"][0])
    write_json_text(store, "stage3/final.meta.json", stage_meta("GPT-5.4"))
    write_json_text(store, "stage3/final.json", final_json())
    write_json_text(store, "html/export.json", {"run_id": store.root.name, "generated_at": "2026-05-22T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})


class CouncilCoreTests(unittest.TestCase):
    def test_parse_ranking_prefers_final_section(self):
        text = """Response A mentions Response B in prose.

FINAL RANKING:
1. Response C
2. Response A
3. Response B
"""
        self.assertEqual(parse_ranking_from_text(text), ["Response C", "Response A", "Response B"])

    def test_calculate_aggregate_rankings(self):
        stage2 = [
            {"ranking": "FINAL RANKING:\n1. Response A\n2. Response B", "parsed_ranking": ["Response A", "Response B"]},
            {"ranking": "FINAL RANKING:\n1. Response B\n2. Response A", "parsed_ranking": ["Response B", "Response A"]},
        ]
        aggregate = calculate_aggregate_rankings(stage2, {"Response A": "GPT-5.4", "Response B": "GLM-5.1"})
        self.assertEqual({item["model"]: item["average_rank"] for item in aggregate}, {"GLM-5.1": 1.5, "GPT-5.4": 1.5})

    def test_default_prompts_are_chinese_reader_facing(self):
        question = "Explain one practical tradeoff."
        stage1_prompt = build_stage1_prompt(question)
        self.assertIn("默认面向中文读者", stage1_prompt)
        self.assertIn("简体中文", stage1_prompt)
        self.assertIn(question, stage1_prompt)

        stage1_results = [{"label": "Response A", "model": "GPT-5.4", "response": "候选回答"}]
        stage2_prompt = build_stage2_prompt(question, stage1_results)
        self.assertIn("默认面向中文读者", stage2_prompt)
        self.assertIn("FINAL RANKING:", stage2_prompt)
        self.assertIn("1. Response A", stage2_prompt)

        stage2_results = [{"model": "GPT-5.4", "ranking": "FINAL RANKING:\n1. Response A"}]
        stage3_prompt = build_stage3_prompt(question, stage1_results, stage2_results)
        self.assertIn("默认面向中文读者", stage3_prompt)
        self.assertIn("最终答案", stage3_prompt)
        self.assertIn(question, stage3_prompt)

    def test_model_recommendation_uses_current_available_models(self):
        models = [
            {"name": "openrouter-2o", "context_window": 168000},
            {"name": "GLM-5.1", "context_window": 184000},
            {"name": "GPT-5.4", "context_window": 240000},
            {"name": "DeepSeek-V4-Pro", "context_window": 184000},
        ]
        choice = recommend_model_choice(models)
        self.assertEqual(choice.members, ["GPT-5.4", "GLM-5.1", "DeepSeek-V4-Pro"])
        self.assertEqual(choice.chairman, "GPT-5.4")

    def test_interactive_model_selection_accepts_recommendation(self):
        models = [{"name": "GPT-5.4"}, {"name": "GLM-5.1"}, {"name": "DeepSeek-V4-Pro"}]
        stderr = StringIO()
        choice = select_model_choice_interactively(models, stdin=StringIO("\n"), stderr=stderr)
        self.assertEqual(choice.members, ["GPT-5.4", "GLM-5.1", "DeepSeek-V4-Pro"])
        self.assertEqual(choice.chairman, "GPT-5.4")
        self.assertIn("CLC 检测到当前 COCO 可用模型", stderr.getvalue())
        self.assertIn("推荐 council 模型套", stderr.getvalue())

    def test_interactive_model_selection_accepts_custom_numbered_models(self):
        models = [{"name": "GPT-5.4"}, {"name": "GLM-5.1"}, {"name": "DeepSeek-V4-Pro"}]
        choice = select_model_choice_interactively(models, stdin=StringIO("c\n1,3\n3\n"), stderr=StringIO())
        self.assertEqual(choice.members, ["GPT-5.4", "DeepSeek-V4-Pro"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")
        self.assertEqual(resolve_model_tokens("2, GPT-5.4", ["GPT-5.4", "GLM-5.1"]), ["GLM-5.1", "GPT-5.4"])

    def test_parse_stream_json_extracts_actual_model_and_result(self):
        stream = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GPT-5.4"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "OK"}}),
                json.dumps({"type": "result", "result": "OK", "is_error": False}),
            ]
        )
        parsed = parse_stream_json(stream)
        self.assertEqual(parsed["actual_model"], "GPT-5.4")
        self.assertEqual(parsed["response"], "OK")

    def test_parse_stream_json_prefers_subagent_source_model(self):
        tool_id = "call_1"
        stream = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GPT-5.4"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "", "tool_calls": [{"id": tool_id, "type": "function", "function": {"name": "Agent", "arguments": json.dumps({"subagent_type": "council-glm51"})}}]}}),
                json.dumps({"type": "assistant", "parent_tool_use_id": tool_id, "message": {"role": "assistant", "content": "OK", "extra": {"_source_model": "GLM-5.1"}}}),
                json.dumps({"type": "user", "subtype": "tool_result", "tool_use_id": tool_id, "tool_name": "Agent", "content": "OK"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "OK", "extra": {"_source_model": "GPT-5.4"}}}),
                json.dumps({"type": "result", "result": "OK", "is_error": False}),
            ]
        )
        parsed = parse_stream_json(stream, expected_agent="council-glm51")
        self.assertEqual(parsed["actual_model"], "GLM-5.1")
        self.assertEqual(parsed["response"], "OK")
        self.assertTrue(parsed["subagent_invocation"]["ok"])

    def test_parse_stream_json_rejects_prompt_only_subagent_claim(self):
        stream = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GLM-5.1"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "OK", "extra": {"_source_model": "GLM-5.1"}}}),
                json.dumps({"type": "result", "result": "OK", "is_error": False}),
            ]
        )
        parsed = parse_stream_json(stream, expected_agent="council-glm51")
        self.assertEqual(parsed["actual_model"], "GLM-5.1")
        self.assertFalse(parsed["subagent_invocation"]["ok"])

    def test_validate_and_export_html_from_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-test")
            manifest = {
                "schema_version": 1,
                "run_id": "run-test",
                "created_at": "2026-05-22T00:00:00Z",
                "updated_at": "2026-05-22T00:00:00Z",
                "status": "ok",
                "input_chars": 4,
                "config": {"members": ["GPT-5.4", "GLM-5.1"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake", "query_timeout": 180, "export_html": True},
                "artifacts": {"html": "html/index.html"},
                "metadata": {
                    "label_to_model": {"Response A": "GPT-5.4", "Response B": "GLM-5.1"},
                    "aggregate_rankings": [{"model": "GPT-5.4", "average_rank": 1.0, "rankings_count": 1, "positions": [1]}],
                },
                "stages": {
                    "stage1": [
                        {"label": "Response A", "file_label": "A", "model": "GPT-5.4", "expected_model": "GPT-5.4", "actual_model": "GPT-5.4", "response": "A", "status": "ok"},
                        {"label": "Response B", "file_label": "B", "model": "GLM-5.1", "expected_model": "GLM-5.1", "actual_model": "GLM-5.1", "response": "B", "status": "ok"},
                    ],
                    "stage2": [
                        review_json()
                    ],
                    "stage3": final_json(),
                },
                "warnings": [],
                "failures": [],
            }
            store.write_manifest(manifest)
            file_contents = {
                "stage3/final.md": "# Final with <tag> & \"quotes\"\n\n- Keep evidence readable\n\n| Field | Value |\n| --- | --- |\n| Status | OK |\n",
                "stage3/chairman.prompt.md": "Prompt with <tag> & \"quotes\"\n",
            }
            plain_files = [
                "input.md",
                "config.json",
                "runtime/doctor.json",
                "runtime/coco.models.json",
                "stage1/member.prompt.md",
                "stage1/A.response.md",
                "stage1/A.coco.stream.jsonl",
                "stage1/B.response.md",
                "stage1/B.coco.stream.jsonl",
                "stage2/review.prompt.md",
                "stage2/label_to_model.json",
                "stage2/aggregate.json",
                "stage2/A.review.md",
                "stage2/A.coco.stream.jsonl",
                "stage3/chairman.prompt.md",
                "stage3/final.md",
                "stage3/final.coco.stream.jsonl",
            ]
            for relative in plain_files:
                store.write_text(relative, file_contents.get(relative, "{}\n"))
            write_json_text(store, "stage1/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage1/B.meta.json", stage_meta("GLM-5.1"))
            write_json_text(store, "stage2/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage2/A.review.json", review_json())
            write_json_text(store, "stage3/final.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage3/final.json", final_json())
            export_html(store)
            validation = validate_run(store)
            self.assertEqual(validation["status"], "ok", validation["failures"])
            html = (store.root / "html" / "index.html").read_text(encoding="utf-8")
            self.assertIn("COCO LLM Council", html)
            self.assertIn('lang="zh-CN"', html)
            self.assertIn("归档副本", html)
            self.assertIn('class="sheet"', html)
            self.assertIn("附录 A · 阶段 1 候选回答", html)
            self.assertIn("已验证<br>阶段 3", html)
            self.assertIn("复制 Markdown", html)
            self.assertIn('id="copy-fallback"', html)
            self.assertIn('<article id="final-answer"', html)
            self.assertIn("<h1>Final with &lt;tag&gt; &amp; &quot;quotes&quot;</h1>", html)
            self.assertIn("<li>Keep evidence readable</li>", html)
            self.assertIn("<table>", html)
            self.assertNotIn("<summary>Stage 3", html)
            self.assertNotIn("<summary>阶段 3", html)
            self.assertNotIn("<pre># Final with", html)
            self.assertIn('<details id="stage1">', html)
            self.assertIn('<details id="stage2">', html)
            self.assertIn('<details id="trace">', html)
            self.assertIn('<details id="metadata">', html)
            self.assertNotIn('<details id="stage1" open>', html)
            marker = '<script type="application/json" id="copy-payloads">'
            start = html.index(marker) + len(marker)
            end = html.index("</script>", start)
            payloads = json.loads(html[start:end])
            self.assertIn('# Final with <tag> & "quotes"', payloads["markdown"])
            self.assertIn('Prompt with <tag> & "quotes"', payloads["prompt"])

    def test_subagent_validate_requires_invocation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-subagent-bad")
            bad_review = review_json() | {
                "reviewer_label": "A",
                "model": "GLM-5.1",
                "expected_model": "GLM-5.1",
                "actual_model": "GLM-5.1",
                "ranking": "FINAL RANKING:\n1. Response A",
                "parsed_ranking": ["Response A"],
                "agent": "council-glm51",
            }
            bad_final = final_json() | {"agent": "council-chairman-gpt54"}
            manifest = {
                "schema_version": 1,
                "run_id": "run-subagent-bad",
                "created_at": "2026-05-22T00:00:00Z",
                "updated_at": "2026-05-22T00:00:00Z",
                "status": "ok",
                "input_chars": 4,
                "config": {
                    "members": ["GLM-5.1"],
                    "chairman": "GPT-5.4",
                    "provider_mode": "subagent",
                    "runtime_command": "fake",
                    "query_timeout": 180,
                    "export_html": True,
                    "member_agents": ["council-glm51"],
                    "chairman_agent": "council-chairman-gpt54",
                },
                "artifacts": {"html": "html/index.html"},
                "metadata": {"label_to_model": {"Response A": "GLM-5.1"}, "aggregate_rankings": []},
                "stages": {
                    "stage1": [
                        {"label": "Response A", "file_label": "A", "model": "GLM-5.1", "expected_model": "GLM-5.1", "actual_model": "GLM-5.1", "agent": "council-glm51", "status": "ok"}
                    ],
                    "stage2": [
                        bad_review
                    ],
                    "stage3": bad_final,
                },
                "warnings": [],
                "failures": [],
            }
            store.write_manifest(manifest)
            for relative in [
                "input.md",
                "config.json",
                "runtime/doctor.json",
                "runtime/coco.models.json",
                "stage1/member.prompt.md",
                "stage1/A.response.md",
                "stage1/A.meta.json",
                "stage1/A.coco.stream.jsonl",
                "stage2/review.prompt.md",
                "stage2/label_to_model.json",
                "stage2/aggregate.json",
                "stage2/A.review.md",
                "stage2/A.review.json",
                "stage2/A.meta.json",
                "stage2/A.coco.stream.jsonl",
                "stage3/chairman.prompt.md",
                "stage3/final.md",
                "stage3/final.json",
                "stage3/final.meta.json",
                "stage3/final.coco.stream.jsonl",
                "html/index.html",
            ]:
                store.write_text(relative, "{}\n")
            write_json_text(store, "stage1/A.meta.json", stage_meta("GLM-5.1"))
            write_json_text(store, "stage2/A.meta.json", stage_meta("GLM-5.1"))
            write_json_text(store, "stage2/A.review.json", bad_review)
            write_json_text(store, "stage3/final.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage3/final.json", bad_final)
            write_json_text(store, "html/export.json", {"run_id": "run-subagent-bad", "generated_at": "2026-05-22T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})
            validation = validate_run(store)
            self.assertEqual(validation["status"], "failed")
            self.assertTrue(any(check["name"].endswith("_subagent_invocation") for check in validation["failures"]))

    def test_validate_fails_when_manifest_required_field_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-missing-manifest-field")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            del manifest["status"]
            store.write_json("manifest.json", manifest)
            validation = validate_run(store)
            self.assertEqual(validation["status"], "failed")
            self.assertTrue(any(check["name"] == "schema:manifest.status" for check in validation["failures"]))

    def test_validate_fails_when_sidecar_required_fields_missing(self):
        cases = [
            ("stage1/A.meta.json", "expected_model", "schema:stage1.A.meta.expected_model"),
            ("stage2/A.review.json", "ranking", "schema:stage2.A.review.ranking"),
            ("stage3/final.json", "response", "schema:stage3.final.response"),
            ("html/export.json", "format", "schema:html.export.format"),
        ]
        for relative, field, expected_failure in cases:
            with self.subTest(relative=relative, field=field):
                with tempfile.TemporaryDirectory() as tmp:
                    store = ArtifactStore.create(Path(tmp), "run-missing-sidecar-field")
                    write_minimal_valid_direct_run(store)
                    path = store.root / relative
                    data = json.loads(path.read_text(encoding="utf-8"))
                    del data[field]
                    path.write_text(json.dumps(data) + "\n", encoding="utf-8")
                    validation = validate_run(store)
                    self.assertEqual(validation["status"], "failed")
                    self.assertTrue(any(check["name"] == expected_failure for check in validation["failures"]), validation["failures"])

    def test_validate_reports_stage_collection_type_errors_without_crashing(self):
        cases = [
            ("stage1", {"bad": "shape"}, "schema:manifest.stages.stage1"),
            ("stage2", {"bad": "shape"}, "schema:manifest.stages.stage2"),
            ("stage1", ["bad item"], "schema:manifest.stages.stage1[0]"),
            ("stage2", ["bad item"], "schema:manifest.stages.stage2[0]"),
        ]
        for stage_name, bad_value, expected_failure in cases:
            with self.subTest(stage_name=stage_name):
                with tempfile.TemporaryDirectory() as tmp:
                    store = ArtifactStore.create(Path(tmp), f"run-bad-{stage_name}-type")
                    write_minimal_valid_direct_run(store)
                    manifest = store.read_manifest()
                    manifest["stages"][stage_name] = bad_value
                    store.write_json("manifest.json", manifest)
                    validation = validate_run(store)
                    self.assertEqual(validation["status"], "failed")
                    self.assertTrue(any(check["name"] == expected_failure for check in validation["failures"]), validation["failures"])


if __name__ == "__main__":
    unittest.main()
