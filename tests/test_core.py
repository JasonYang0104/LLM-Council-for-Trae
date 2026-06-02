import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from llm_council_for_trae.cli import failure_recommendations
from llm_council_for_trae.council import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    calculate_aggregate_rankings,
    classify_stage1_status,
    CouncilConfig,
    initial_manifest,
    parse_ranking_from_text,
    record_stage_failures,
)
from llm_council_for_trae.html_export import export_html
from llm_council_for_trae.model_benchmark import (
    BenchmarkTask,
    benchmark_record_from_call,
    recommend_rosters_from_scorecard,
    scorecard_rows,
)
from llm_council_for_trae.model_selection import (
    recommend_model_choice,
    resolve_model_tokens,
    select_model_choice_interactively,
)
from llm_council_for_trae.models import doctor as runtime_doctor
from llm_council_for_trae.provider import ModelCallResult, monitor_stream_for_budget, parse_stream_json
from llm_council_for_trae.store import ArtifactStore
from llm_council_for_trae.validation import validate_run


def stage_meta(expected_model="GPT-5.4", actual_model=None):
    return {
        "expected_model": expected_model,
        "actual_model": actual_model or expected_model,
        "response_chars": 2,
        "status": "ok",
        "session_id": "session-1",
        "command": ["traecli", "-p", "<prompt 2 chars>"],
        "exit_code": 0,
        "stdout_path": "A.traecli.stream.jsonl",
        "stderr_path": "A.traecli.stderr.log",
        "copied_session_files": {},
        "raw_model_markers": [actual_model or expected_model],
        "error": None,
        "member_tool_mode": "search_enabled",
        "allowed_tools": ["WebSearch", "WebFetch"],
        "disallowed_tools": ["Skill", "Agent"],
        "forbidden_tool_calls": [],
        "captured_at": "2026-05-22T00:00:00Z",
    }


def tool_policy_json():
    return {
        "member_tool_mode": "search_enabled",
        "allowed_tools": ["WebSearch", "WebFetch"],
        "disallowed_tools": ["Skill", "Agent"],
        "forbidden_tool_calls": [],
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
    } | tool_policy_json()


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
    } | tool_policy_json()


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
        "config": {
            "members": ["GPT-5.4"],
            "chairman": "GPT-5.4",
            "provider_mode": "direct",
            "runtime_command": "fake",
            "query_timeout": 180,
            "export_html": True,
            "use_yolo": False,
            "member_tool_mode": "search_enabled",
            "member_runtime_cwd_mode": "isolated_temp",
        },
        "artifacts": {"html": "html/index.html"},
        "metadata": {"label_to_model": {"Response A": "GPT-5.4"}, "aggregate_rankings": []},
        "stages": {
            "stage1": [{"label": "Response A", "file_label": "A", "model": "GPT-5.4", "expected_model": "GPT-5.4", "actual_model": "GPT-5.4", "response": "A", "status": "ok"} | tool_policy_json()],
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
        "runtime/traecli.models.json",
        "stage1/member.prompt.md",
        "stage1/A.response.md",
        "stage1/A.traecli.stream.jsonl",
        "stage2/review.prompt.md",
        "stage2/label_to_model.json",
        "stage2/aggregate.json",
        "stage2/A.review.md",
        "stage2/A.traecli.stream.jsonl",
        "stage3/chairman.prompt.md",
        "stage3/final.md",
        "stage3/final.traecli.stream.jsonl",
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
        self.assertIn("综述答案", stage3_prompt)
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
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")

    def test_doctor_downgrades_mcp_only_errors_when_models_work(self):
        doctor_payload = {
            "checks": [
                {"name": "binary", "severity": "info", "message": "ok"},
                {"name": "mcp", "severity": "error", "message": "2 MCP server(s) failed to initialize"},
            ]
        }
        models_payload = [{"name": "GLM-5.1"}]
        with patch(
            "llm_council_for_trae.models.run_command",
            side_effect=[
                CompletedProcess(["fake", "--version"], 0, stdout="fake version", stderr=""),
                CompletedProcess(["fake", "doctor", "--json"], 2, stdout=json.dumps(doctor_payload), stderr=""),
                CompletedProcess(["fake", "models", "--json"], 0, stdout=json.dumps(models_payload), stderr=""),
            ],
        ):
            health = runtime_doctor("fake")
        self.assertTrue(health.ok)
        self.assertEqual(health.errors, [])
        self.assertIn("MCP-only", health.warnings[0])
        self.assertEqual(health.ignored_errors, ["mcp: 2 MCP server(s) failed to initialize"])

    def test_doctor_keeps_non_mcp_errors_as_failures(self):
        doctor_payload = {
            "checks": [
                {"name": "auth", "severity": "error", "message": "not logged in"},
            ]
        }
        models_payload = [{"name": "GLM-5.1"}]
        with patch(
            "llm_council_for_trae.models.run_command",
            side_effect=[
                CompletedProcess(["fake", "--version"], 0, stdout="fake version", stderr=""),
                CompletedProcess(["fake", "doctor", "--json"], 2, stdout=json.dumps(doctor_payload), stderr=""),
                CompletedProcess(["fake", "models", "--json"], 0, stdout=json.dumps(models_payload), stderr=""),
            ],
        ):
            health = runtime_doctor("fake")
        self.assertFalse(health.ok)
        self.assertTrue(health.errors)
        self.assertEqual(health.ignored_errors, [])

    def test_failure_recommendations_explain_model_timeout(self):
        manifest = {
            "failures": [
                {
                    "stage_record": "Response A",
                    "status": "failed",
                    "error": "model 'GPT-5.4': context deadline exceeded",
                    "expected_model": "GPT-5.4",
                    "actual_model": "GPT-5.4",
                }
            ],
            "stages": {
                "stage1": [
                    {"model": "GPT-5.4", "status": "failed"},
                    {"model": "GLM-5.1", "status": "ok"},
                    {"model": "DeepSeek-V4-Pro", "status": "ok"},
                ]
            },
        }
        recommendations = failure_recommendations(manifest)
        self.assertEqual(len(recommendations), 1)
        self.assertIn("GPT-5.4 超时", recommendations[0])
        self.assertIn("提高 --timeout", recommendations[0])
        self.assertIn("GLM-5.1, DeepSeek-V4-Pro", recommendations[0])

    def test_benchmark_record_tracks_latency_and_parse_status(self):
        task = BenchmarkTask(
            name="stage2_ranking",
            stage="stage2",
            role="reviewer",
            prompt="Rank responses.",
            parse_kind="ranking",
            valid_labels=["Response A", "Response B"],
        )
        call = ModelCallResult(
            expected_model="GLM-5.1",
            actual_model="GLM-5.1",
            response="FINAL RANKING:\n1. Response B\n2. Response A",
            status="ok",
            session_id="s1",
            command=["traecli"],
            exit_code=0,
            stdout_path="out.jsonl",
            stderr_path="err.log",
        )
        record = benchmark_record_from_call(task, "GLM-5.1", 1, call, latency_seconds=2.345)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["latency_seconds"], 2.35)
        self.assertTrue(record["parse_ok"])
        self.assertEqual(record["response_chars"], len(call.response))

    def test_scorecard_and_rosters_prioritize_stability_then_latency(self):
        records = [
            {"model": "fast", "role": "member", "stage": "stage1", "status": "ok", "parse_ok": True, "latency_seconds": 10, "actual_model": "fast", "expected_model": "fast"},
            {"model": "fast", "role": "reviewer", "stage": "stage2", "status": "ok", "parse_ok": True, "latency_seconds": 12, "actual_model": "fast", "expected_model": "fast"},
            {"model": "stable-chair", "role": "chairman", "stage": "stage3", "status": "ok", "parse_ok": True, "latency_seconds": 20, "actual_model": "stable-chair", "expected_model": "stable-chair"},
            {"model": "slow", "role": "member", "stage": "stage1", "status": "ok", "parse_ok": True, "latency_seconds": 95, "actual_model": "slow", "expected_model": "slow"},
            {"model": "flaky", "role": "member", "stage": "stage1", "status": "failed", "parse_ok": False, "latency_seconds": 30, "actual_model": None, "expected_model": "flaky"},
        ]
        rows = scorecard_rows(records)
        by_model = {row["model"]: row for row in rows}
        self.assertEqual(by_model["fast"]["success_rate"], "1.00")
        self.assertEqual(by_model["flaky"]["success_rate"], "0.00")

        rosters = recommend_rosters_from_scorecard(rows)
        self.assertEqual(rosters["chairman"], "stable-chair")
        self.assertIn("fast", rosters["fast_default_members"])
        self.assertNotIn("slow", rosters["fast_default_members"])
        self.assertIn("slow", rosters["research_stress_members"])

    def test_interactive_model_selection_accepts_recommendation(self):
        models = [{"name": "GPT-5.4"}, {"name": "GLM-5.1"}, {"name": "DeepSeek-V4-Pro"}]
        stderr = StringIO()
        choice = select_model_choice_interactively(models, stdin=StringIO("\n"), stderr=stderr)
        self.assertEqual(choice.members, ["GPT-5.4", "GLM-5.1", "DeepSeek-V4-Pro"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")
        self.assertIn("LCT 检测到当前 traecli 可用模型", stderr.getvalue())
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
                "runtime/traecli.models.json",
                "stage1/member.prompt.md",
                "stage1/A.response.md",
                "stage1/A.traecli.stream.jsonl",
                "stage1/B.response.md",
                "stage1/B.traecli.stream.jsonl",
                "stage2/review.prompt.md",
                "stage2/label_to_model.json",
                "stage2/aggregate.json",
                "stage2/A.review.md",
                "stage2/A.traecli.stream.jsonl",
                "stage3/chairman.prompt.md",
                "stage3/final.md",
                "stage3/final.traecli.stream.jsonl",
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
            self.assertIn("LLM Council for Trae", html)
            self.assertIn('lang="zh-CN"', html)
            self.assertIn("归档副本", html)
            self.assertIn('class="sheet"', html)
            self.assertIn('<details id="input-prompt" class="question-context">', html)
            self.assertIn("<summary>输入提示词</summary>", html)
            self.assertNotIn('<details id="input-prompt" class="question-context" open>', html)
            self.assertNotIn('<p class="question-context">', html)
            self.assertIn("附录 A · 阶段 1 候选回答", html)
            self.assertIn("搜索工具", html)
            self.assertIn("允许：是 · 实际使用：否", html)
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
            self.assertIn("## 输入\n\n{}", payloads["markdown"])
            self.assertIn('Prompt with <tag> & "quotes"', payloads["prompt"])

    def test_search_summary_separates_allowed_from_used(self):
        from llm_council_for_trae.html_export import summarize_search_usage

        manifest = {
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": ["WebSearch", "WebFetch"],
                        "tool_calls_count": 0,
                        "tool_calls": [],
                        "forbidden_tool_calls": [],
                    }
                ],
                "stage2": [],
                "stage3": {
                    "allowed_tools": ["WebSearch", "WebFetch"],
                    "tool_calls_count": 1,
                    "tool_calls": [{"name": "WebSearch", "id": "tc1"}],
                    "forbidden_tool_calls": [],
                },
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertTrue(summary["search_allowed"])
        self.assertTrue(summary["search_used"])
        self.assertEqual(summary["web_tool_calls_count"], 1)
        self.assertEqual(summary["tool_calls_count"], 1)
        self.assertEqual(summary["forbidden_tool_calls_count"], 0)

    def test_search_summary_does_not_infer_search_from_allowed_tools_only(self):
        from llm_council_for_trae.html_export import summarize_search_usage

        manifest = {
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": ["WebSearch", "WebFetch"],
                        "tool_calls_count": 0,
                        "tool_calls": [],
                        "forbidden_tool_calls": [],
                    }
                ],
                "stage2": [],
                "stage3": {},
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertTrue(summary["search_allowed"])
        self.assertFalse(summary["search_used"])
        self.assertEqual(summary["web_tool_calls_count"], 0)

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
                "runtime/traecli.models.json",
                "stage1/member.prompt.md",
                "stage1/A.response.md",
                "stage1/A.meta.json",
                "stage1/A.traecli.stream.jsonl",
                "stage2/review.prompt.md",
                "stage2/label_to_model.json",
                "stage2/aggregate.json",
                "stage2/A.review.md",
                "stage2/A.review.json",
                "stage2/A.meta.json",
                "stage2/A.traecli.stream.jsonl",
                "stage3/chairman.prompt.md",
                "stage3/final.md",
                "stage3/final.json",
                "stage3/final.meta.json",
                "stage3/final.traecli.stream.jsonl",
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

    def test_validate_rejects_ok_manifest_with_forbidden_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-contaminated-ok")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["stages"]["stage1"][0]["forbidden_tool_calls"] = [
                {"id": "tc1", "name": "Skill", "arguments": "{}", "turn_index": 1}
            ]
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(
                any(check["name"] == "tool_contamination_manifest_ok" for check in validation["failures"]),
                validation["failures"],
            )

    def test_validate_accepts_legacy_meta_missing_tool_policy_fields(self):
        legacy_missing_fields = ("member_tool_mode", "allowed_tools", "disallowed_tools", "forbidden_tool_calls")
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-legacy-meta")
            write_minimal_valid_direct_run(store)
            for relative in ("stage1/A.meta.json", "stage2/A.meta.json", "stage3/final.meta.json"):
                path = store.root / relative
                data = json.loads(path.read_text(encoding="utf-8"))
                for field in legacy_missing_fields:
                    data.pop(field, None)
                path.write_text(json.dumps(data) + "\n", encoding="utf-8")

            validation = validate_run(store)

            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertFalse(
                any(
                    failure["name"].startswith("schema:stage")
                    and any(field in failure["name"] for field in legacy_missing_fields)
                    for failure in validation["failures"]
                ),
                validation["failures"],
            )

    def test_validate_rejects_meta_only_forbidden_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-meta-contaminated-ok")
            write_minimal_valid_direct_run(store)
            path = store.root / "stage1/A.meta.json"
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["forbidden_tool_calls"] = [
                {"id": "tc1", "name": "Skill", "arguments": "{}", "turn_index": 1}
            ]
            path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            failure_names = {check["name"] for check in validation["failures"]}
            self.assertIn("tool_contamination_manifest_ok", failure_names)
            self.assertIn("stage1.A.meta_tool_contamination_status", failure_names)

    def test_provider_omits_yolo_by_default(self):
        from llm_council_for_trae.provider import TraeCliProvider
        provider = TraeCliProvider()
        cmd = provider._build_command("GPT-5.4", "test prompt", "run-1", "stage1", "A", "sess-1")
        self.assertNotIn("--yolo", cmd)
        self.assertNotIn("-y", cmd)

    def test_provider_includes_yolo_when_explicitly_enabled(self):
        from llm_council_for_trae.provider import TraeCliProvider
        provider = TraeCliProvider(use_yolo=True)
        self.assertIn("--yolo", provider._build_command("GPT-5.4", "test prompt", "run-1", "stage1", "A", "sess-1"))

    def test_model_call_result_includes_permission_mode(self):
        from llm_council_for_trae.provider import ModelCallResult
        result = ModelCallResult(
            expected_model="GPT-5.4",
            actual_model="GPT-5.4",
            response="ok",
            status="ok",
            session_id="s1",
            command=["traecli"],
            exit_code=0,
            stdout_path="out.jsonl",
            stderr_path="err.log",
            permission_mode="bypass_permissions",
        )
        self.assertEqual(result.to_json()["permission_mode"], "bypass_permissions")

    def test_stage_meta_schema_validates_permission_mode(self):
        from llm_council_for_trae.schema_contract import validate_schema, STAGE_META_SCHEMA
        meta = stage_meta()
        meta["permission_mode"] = "bypass_permissions"
        checks = validate_schema("meta", meta, STAGE_META_SCHEMA)
        perm_check = [c for c in checks if c["name"] == "schema:meta.permission_mode"]
        self.assertTrue(perm_check)
        self.assertTrue(perm_check[0]["ok"])

    def test_classify_stage1_status_ok_when_all_succeed(self):
        results = [{"status": "ok"} for _ in range(5)]
        self.assertEqual(classify_stage1_status(results, min_valid_members=4), "ok")

    def test_classify_stage1_status_degraded_ok_when_quorum_met(self):
        results = [{"status": "ok"}] * 5 + [{"status": "failed"}] * 3
        self.assertEqual(classify_stage1_status(results, min_valid_members=4), "degraded_ok")

    def test_classify_stage1_status_failed_when_quorum_not_met(self):
        results = [{"status": "ok"}] * 3 + [{"status": "failed"}] * 5
        self.assertEqual(classify_stage1_status(results, min_valid_members=4), "failed")

    def test_chairman_metadata_records_fallback(self):
        from llm_council_for_trae.council import stage3_synthesize_final
        metadata = {
            "attempted": ["GLM-5.1", "Qwen3.6-Plus"],
            "used": "Qwen3.6-Plus",
            "fallback_from": "GLM-5.1",
        }
        self.assertIsNotNone(metadata["fallback_from"])
        self.assertEqual(metadata["used"], "Qwen3.6-Plus")

    def test_validate_accepts_degraded_ok_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-degraded")
            manifest = {
                "schema_version": 1,
                "run_id": "run-degraded",
                "created_at": "2026-05-22T00:00:00Z",
                "updated_at": "2026-05-22T00:00:00Z",
                "status": "degraded_ok",
                "input_chars": 4,
                "config": {"members": ["GPT-5.4", "GLM-5.1"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake", "query_timeout": 180, "export_html": True, "min_valid_members": 4, "target_valid_members": 5},
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
                "input.md", "config.json", "runtime/doctor.json", "runtime/traecli.models.json",
                "stage1/member.prompt.md", "stage1/A.response.md", "stage1/A.traecli.stream.jsonl",
                "stage2/review.prompt.md", "stage2/label_to_model.json", "stage2/aggregate.json",
                "stage2/A.review.md", "stage2/A.traecli.stream.jsonl",
                "stage3/chairman.prompt.md", "stage3/final.md", "stage3/final.traecli.stream.jsonl",
                "html/index.html",
            ]:
                store.write_text(relative, "{}\n")
            write_json_text(store, "stage1/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage2/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage2/A.review.json", manifest["stages"]["stage2"][0])
            write_json_text(store, "stage3/final.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage3/final.json", final_json())
            write_json_text(store, "html/export.json", {"run_id": "run-degraded", "generated_at": "2026-05-22T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})
            validation = validate_run(store)
            self.assertEqual(validation["status"], "degraded_ok")

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


    def test_parse_stream_json_counts_tool_calls(self):
        stream = "\n".join([
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GPT-5.4"}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "Let me search", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "WebSearch", "arguments": "{}"}}]}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "Found it"}}),
            json.dumps({"type": "result", "result": "Done", "is_error": False}),
        ])
        parsed = parse_stream_json(stream)
        self.assertEqual(parsed["tool_calls_count"], 1)
        self.assertEqual(parsed["turns_count"], 2)

    def test_parse_stream_json_extracts_tool_call_details(self):
        stream = "\n".join([
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GPT-5.4"}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "Searching", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "WebSearch", "arguments": "{\"query\":\"Trae CN\"}"}}]}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "Calling skill", "tool_calls": [{"id": "tc2", "type": "function", "function": {"name": "Skill", "arguments": "{\"skill\":\"llm-council-for-trae\"}"}}]}}),
            json.dumps({"type": "result", "result": "Done", "is_error": False}),
        ])
        parsed = parse_stream_json(stream)
        self.assertEqual(
            parsed["tool_calls"],
            [
                {"id": "tc1", "name": "WebSearch", "arguments": "{\"query\":\"Trae CN\"}", "turn_index": 1},
                {"id": "tc2", "name": "Skill", "arguments": "{\"skill\":\"llm-council-for-trae\"}", "turn_index": 2},
            ],
        )

    def test_parse_stream_json_extracts_partial_output_metrics(self):
        stream = "\n".join([
            json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GPT-5.4"}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "A" * 100}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "B" * 50}}),
            json.dumps({"type": "result", "result": "", "is_error": True}),
        ])
        parsed = parse_stream_json(stream)
        self.assertEqual(parsed["assistant_content_chars_total"], 150)
        self.assertEqual(parsed["last_assistant_content_chars"], 50)
        self.assertTrue(parsed["raw_partial_recoverable"])

    def test_model_call_result_includes_tool_budget_status(self):
        from llm_council_for_trae.provider import ModelCallResult
        result = ModelCallResult(
            expected_model="GPT-5.4",
            actual_model="GPT-5.4",
            response="ok",
            status="ok",
            session_id="s1",
            command=["traecli"],
            exit_code=0,
            stdout_path="out.jsonl",
            stderr_path="err.log",
            tool_budget_status="ok",
        )
        self.assertEqual(result.to_json()["tool_budget_status"], "ok")

    def test_model_call_result_includes_tool_policy_fields(self):
        from llm_council_for_trae.provider import ModelCallResult
        forbidden = [{"id": "tc1", "name": "Skill", "arguments": "{}", "turn_index": 1}]
        result = ModelCallResult(
            expected_model="GPT-5.4",
            actual_model="GPT-5.4",
            response="ok",
            status="failed",
            session_id="s1",
            command=["traecli"],
            exit_code=0,
            stdout_path="out.jsonl",
            stderr_path="err.log",
            member_tool_mode="search_enabled",
            allowed_tools=["WebSearch", "WebFetch"],
            disallowed_tools=["Skill", "Agent"],
            forbidden_tool_calls=forbidden,
        )
        j = result.to_json()
        self.assertEqual(j["member_tool_mode"], "search_enabled")
        self.assertEqual(j["allowed_tools"], ["WebSearch", "WebFetch"])
        self.assertEqual(j["disallowed_tools"], ["Skill", "Agent"])
        self.assertEqual(j["forbidden_tool_calls"], forbidden)

    def test_model_call_result_includes_partial_output_fields(self):
        from llm_council_for_trae.provider import ModelCallResult
        result = ModelCallResult(
            expected_model="GPT-5.4",
            actual_model="GPT-5.4",
            response="ok",
            status="ok",
            session_id="s1",
            command=["traecli"],
            exit_code=0,
            stdout_path="out.jsonl",
            stderr_path="err.log",
            assistant_content_chars_total=500,
            last_assistant_content_chars=200,
            raw_partial_recoverable=False,
        )
        j = result.to_json()
        self.assertEqual(j["assistant_content_chars_total"], 500)
        self.assertEqual(j["last_assistant_content_chars"], 200)
        self.assertFalse(j["raw_partial_recoverable"])

    def test_record_stage_failures_does_not_override_quorum_status(self):
        manifest = initial_manifest("run-quorum-test", "test", CouncilConfig(members=["A", "B", "C"], chairman="X"))
        manifest["status"] = "degraded_ok"
        records = [
            {"label": "Response A", "model": "A", "status": "ok"},
            {"label": "Response B", "model": "B", "status": "failed", "error": "timeout"},
            {"label": "Response C", "model": "C", "status": "ok"},
        ]
        record_stage_failures(manifest, records)
        self.assertEqual(manifest["status"], "degraded_ok")
        self.assertEqual(len(manifest["failures"]), 1)
        self.assertEqual(manifest["failures"][0]["stage_record"], "Response B")

    def test_min_valid_members_default_is_3(self):
        config = CouncilConfig(members=["A"], chairman="B")
        self.assertEqual(config.min_valid_members, 3)

    def test_target_valid_members_default_is_8(self):
        config = CouncilConfig(members=["A"], chairman="B")
        self.assertEqual(config.target_valid_members, 8)

    def test_use_yolo_default_is_false(self):
        config = CouncilConfig(members=["A"], chairman="B")
        self.assertFalse(config.use_yolo)

    def test_build_config_defaults_to_search_enabled_without_yolo(self):
        from llm_council_for_trae.cli import build_config, build_parser

        args = build_parser().parse_args(["run", "--input", "question.md", "--default-models"])
        config = build_config(args)

        self.assertFalse(config.use_yolo)
        self.assertEqual(config.member_tool_mode, "search_enabled")
        self.assertEqual(config.member_runtime_cwd_mode, "isolated_temp")

    def test_build_config_yolo_is_explicit_opt_in(self):
        from llm_council_for_trae.cli import build_config, build_parser

        args = build_parser().parse_args(["run", "--input", "question.md", "--default-models", "--yolo", "--member-tool-mode", "answer_only"])
        config = build_config(args)

        self.assertTrue(config.use_yolo)
        self.assertEqual(config.member_tool_mode, "answer_only")

    def test_build_config_no_yolo_overrides_yolo_for_compatibility(self):
        from llm_council_for_trae.cli import build_config, build_parser

        args = build_parser().parse_args(["run", "--input", "question.md", "--default-models", "--yolo", "--no-yolo"])
        config = build_config(args)

        self.assertFalse(config.use_yolo)

    def test_member_tool_mode_default_is_search_enabled(self):
        config = CouncilConfig(members=["A"], chairman="B")
        self.assertEqual(config.member_tool_mode, "search_enabled")

    def test_provider_search_enabled_builds_tool_policy(self):
        from llm_council_for_trae.provider import TraeCliProvider

        provider = TraeCliProvider(member_tool_mode="search_enabled")
        cmd = provider._build_command("GPT-5.4", "test prompt", "run-1", "stage1", "A", "sess-1")

        self.assertIn("--allowed-tool", cmd)
        self.assertIn("WebSearch", cmd)
        self.assertIn("WebFetch", cmd)
        self.assertIn("--disallowed-tool", cmd)
        self.assertIn("Skill", cmd)
        self.assertIn("Agent", cmd)

    def test_provider_answer_only_disallows_web_and_workspace_tools(self):
        from llm_council_for_trae.provider import TraeCliProvider

        provider = TraeCliProvider(member_tool_mode="answer_only")
        cmd = provider._build_command("GPT-5.4", "test prompt", "run-1", "stage1", "A", "sess-1")

        self.assertNotIn("--allowed-tool", cmd)
        for tool in ["WebSearch", "WebFetch", "Read", "Bash", "Skill", "Agent"]:
            self.assertIn(tool, cmd)

    def test_provider_workspace_enabled_allows_readonly_tools_only(self):
        from llm_council_for_trae.provider import TraeCliProvider

        provider = TraeCliProvider(member_tool_mode="workspace_enabled")
        cmd = provider._build_command("GPT-5.4", "test prompt", "run-1", "stage1", "A", "sess-1")

        for tool in ["Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch"]:
            allowed_index = cmd.index(tool)
            self.assertEqual(cmd[allowed_index - 1], "--allowed-tool")
        for tool in ["Skill", "Agent", "Write", "Edit", "Bash"]:
            denied_index = cmd.index(tool)
            self.assertEqual(cmd[denied_index - 1], "--disallowed-tool")

    def test_provider_subagent_invocation_policy_allows_agent_tool(self):
        from llm_council_for_trae.provider import TraeCliProvider, forbidden_tool_calls_for_mode

        provider = TraeCliProvider(member_tool_mode="subagent_invocation")
        cmd = provider._build_command("GPT-5.4", "@council test", "run-1", "stage1", "A", "sess-1")

        agent_index = cmd.index("Agent")
        self.assertEqual(cmd[agent_index - 1], "--allowed-tool")
        self.assertNotEqual(cmd[agent_index - 1], "--disallowed-tool")
        self.assertEqual(forbidden_tool_calls_for_mode([{"name": "Agent", "id": "tc1", "arguments": "{}", "turn_index": 1}], "subagent_invocation"), [])

    def test_forbidden_tool_calls_respect_member_tool_mode(self):
        from llm_council_for_trae.provider import forbidden_tool_calls_for_mode

        calls = [
            {"id": "tc1", "name": "WebSearch", "arguments": "{}", "turn_index": 1},
            {"id": "tc2", "name": "Skill", "arguments": "{\"skill\":\"llm-council-for-trae\"}", "turn_index": 2},
            {"id": "tc3", "name": "Read", "arguments": "{\"file_path\":\"notes.md\"}", "turn_index": 3},
            {"id": "tc4", "name": "Bash", "arguments": "{\"command\":\"ls\"}", "turn_index": 4},
        ]

        self.assertEqual([c["name"] for c in forbidden_tool_calls_for_mode(calls, "search_enabled")], ["Skill", "Read", "Bash"])
        self.assertEqual([c["name"] for c in forbidden_tool_calls_for_mode(calls, "answer_only")], ["WebSearch", "Skill", "Read", "Bash"])
        self.assertEqual([c["name"] for c in forbidden_tool_calls_for_mode(calls, "workspace_enabled")], ["Skill", "Bash"])

    def test_chairman_excluded_from_quorum_count(self):
        results = [
            {"model": "GLM-5.1", "status": "ok"},
            {"model": "Qwen3.6-Plus", "status": "ok"},
            {"model": "Kimi-K2.6", "status": "ok"},
            {"model": "DeepSeek-V4-Pro", "status": "ok"},
            {"model": "GPT-5.4", "status": "ok"},
            {"model": "MiniMax-M2.7", "status": "ok"},
            {"model": "Gemini-3.1", "status": "ok"},
            {"model": "openrouter-2o", "status": "failed"},
        ]
        status = classify_stage1_status(results, min_valid_members=6, chairman_model="GLM-5.1")
        self.assertEqual(status, "degraded_ok")

    def test_chairman_in_members_but_excluded_quorum_fails_if_rest_insufficient(self):
        results = [
            {"model": "GLM-5.1", "status": "ok"},
            {"model": "Qwen3.6-Plus", "status": "ok"},
            {"model": "Kimi-K2.6", "status": "ok"},
            {"model": "DeepSeek-V4-Pro", "status": "failed"},
            {"model": "GPT-5.4", "status": "failed"},
            {"model": "MiniMax-M2.7", "status": "failed"},
            {"model": "Gemini-3.1", "status": "failed"},
        ]
        status = classify_stage1_status(results, min_valid_members=6, chairman_model="GLM-5.1")
        self.assertEqual(status, "failed")

    def test_classify_stage1_status_ok_with_chairman_excluded(self):
        results = [
            {"model": "GLM-5.1", "status": "ok"},
            {"model": "Qwen3.6-Plus", "status": "ok"},
        ]
        status = classify_stage1_status(results, min_valid_members=2, chairman_model="GLM-5.1")
        self.assertEqual(status, "ok")

    def test_stage2_all_failed_sets_manifest_failed(self):
        manifest = initial_manifest("run-s2-fail", "test", CouncilConfig(members=["A", "B"], chairman="C"))
        manifest["status"] = "ok"
        stage2_results = [
            {"reviewer_label": "A", "model": "A", "status": "failed", "error": "timeout"},
            {"reviewer_label": "B", "model": "B", "status": "failed", "error": "timeout"},
        ]
        record_stage_failures(manifest, stage2_results)
        valid_s2 = [r for r in stage2_results if r.get("status") == "ok"]
        if not valid_s2:
            manifest["status"] = "failed"
        self.assertEqual(manifest["status"], "failed")

    def test_stage3_chairman_failed_sets_manifest_failed(self):
        manifest = initial_manifest("run-s3-fail", "test", CouncilConfig(members=["A"], chairman="C"))
        manifest["status"] = "ok"
        stage3_result = {"model": "C", "status": "failed", "error": "timeout"}
        record_stage_failures(manifest, [stage3_result])
        if stage3_result.get("status") != "ok":
            manifest["status"] = "failed"
        self.assertEqual(manifest["status"], "failed")

    def test_degraded_ok_preserved_with_partial_stage2_failures(self):
        manifest = initial_manifest("run-deg-s2", "test", CouncilConfig(members=["A", "B", "C"], chairman="D"))
        manifest["status"] = "degraded_ok"
        stage2_results = [
            {"reviewer_label": "A", "model": "A", "status": "ok"},
            {"reviewer_label": "B", "model": "B", "status": "failed", "error": "timeout"},
        ]
        record_stage_failures(manifest, stage2_results)
        valid_s2 = [r for r in stage2_results if r.get("status") == "ok"]
        if not valid_s2:
            manifest["status"] = "failed"
        self.assertEqual(manifest["status"], "degraded_ok")

    def test_monitor_stream_detects_budget_exceeded(self):
        async def _run():
            lines = []
            for i in range(5):
                tc = [{"id": f"tc{i}", "type": "function", "function": {"name": "WebSearch", "arguments": "{}"}}]
                lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": f"step {i}", "tool_calls": tc}}).encode())
            lines.append(json.dumps({"type": "result", "result": "done", "is_error": False}).encode())

            async def stream():
                for line in lines:
                    yield line

            collected, tool_calls_seen, budget_exceeded = await monitor_stream_for_budget(stream(), tool_limit=3)
            self.assertTrue(budget_exceeded)
            self.assertGreater(tool_calls_seen, 3)
            self.assertGreater(len(collected), 0)

        import asyncio
        asyncio.run(_run())

    def test_monitor_stream_ok_under_budget(self):
        async def _run():
            lines = []
            for i in range(2):
                tc = [{"id": f"tc{i}", "type": "function", "function": {"name": "WebSearch", "arguments": "{}"}}]
                lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": f"step {i}", "tool_calls": tc}}).encode())
            lines.append(json.dumps({"type": "result", "result": "done", "is_error": False}).encode())

            async def stream():
                for line in lines:
                    yield line

            collected, tool_calls_seen, budget_exceeded = await monitor_stream_for_budget(stream(), tool_limit=30)
            self.assertFalse(budget_exceeded)
            self.assertEqual(tool_calls_seen, 2)
            self.assertEqual(len(collected), 3)

        import asyncio
        asyncio.run(_run())

    def test_monitor_stream_handles_malformed_lines(self):
        async def _run():
            lines = [
                b"not json\n",
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "ok"}}).encode(),
                b"\n",
            ]

            async def stream():
                for line in lines:
                    yield line

            collected, tool_calls_seen, budget_exceeded = await monitor_stream_for_budget(stream(), tool_limit=30)
            self.assertFalse(budget_exceeded)
            self.assertEqual(len(collected), 3)

        import asyncio
        asyncio.run(_run())

    def test_model_performance_summary_in_html_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-perf-summary")
            manifest = {
                "schema_version": 1,
                "run_id": "run-perf-summary",
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
                        {"label": "Response A", "file_label": "A", "model": "GPT-5.4", "expected_model": "GPT-5.4", "actual_model": "GPT-5.4", "response": "A", "status": "ok", "tool_calls_count": 2, "turns_count": 3},
                        {"label": "Response B", "file_label": "B", "model": "GLM-5.1", "expected_model": "GLM-5.1", "actual_model": "GLM-5.1", "response": "B", "status": "ok", "tool_calls_count": 0, "turns_count": 1},
                    ],
                    "stage2": [
                        review_json() | {"tool_calls_count": 1, "turns_count": 2},
                    ],
                    "stage3": final_json() | {"tool_calls_count": 0, "turns_count": 1},
                },
                "warnings": ["test warning"],
                "failures": [],
            }
            store.write_manifest(manifest)
            plain_files = [
                "input.md", "config.json", "runtime/doctor.json", "runtime/traecli.models.json",
                "stage1/member.prompt.md", "stage1/A.response.md", "stage1/A.traecli.stream.jsonl",
                "stage1/B.response.md", "stage1/B.traecli.stream.jsonl",
                "stage2/review.prompt.md", "stage2/label_to_model.json", "stage2/aggregate.json",
                "stage2/A.review.md", "stage2/A.traecli.stream.jsonl",
                "stage3/chairman.prompt.md", "stage3/final.md", "stage3/final.traecli.stream.jsonl",
            ]
            for relative in plain_files:
                store.write_text(relative, "{}\n")
            write_json_text(store, "stage1/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage1/B.meta.json", stage_meta("GLM-5.1"))
            write_json_text(store, "stage2/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage2/A.review.json", review_json())
            write_json_text(store, "stage3/final.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage3/final.json", final_json())
            export_html(store)
            html_text = (store.root / "html" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("模型表现摘要", html_text)
            self.assertNotIn("class='model-performance'", html_text)
            self.assertNotIn('id="decision-detail"', html_text)
            self.assertNotIn("存在警告", html_text)
            summary_pos = html_text.index("decision-summary")
            final_pos = html_text.index("final-answer")
            evidence_pos = html_text.index('id="evidence"')
            self.assertLess(summary_pos, final_pos)
            self.assertLess(final_pos, evidence_pos)

    def test_stage3_returns_tuple_with_required_fields(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-tuple")
            config = CouncilConfig(members=["GLM-5.1"], chairman="GLM-5.1")

            ok_call = ModelCallResult(
                expected_model="GLM-5.1", actual_model="GLM-5.1", response="Final answer",
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            final, meta = await stage3_synthesize_final(
                "test query",
                [{"label": "Response A", "model": "GLM-5.1", "response": "A", "status": "ok"}],
                [{"model": "GLM-5.1", "ranking": "1. Response A", "parsed_ranking": ["Response A"], "status": "ok"}],
                config, provider, store,
            )
            self.assertIsInstance(final, dict)
            self.assertIsInstance(meta, dict)
            self.assertIn("model", final)
            self.assertIn("status", final)
            self.assertIn("response", final)
            self.assertEqual(final["status"], "ok")
            self.assertIn("attempted", meta)
            self.assertIn("used", meta)
            self.assertIn("fallback_from", meta)
            self.assertIsNone(meta["fallback_from"])

        import asyncio
        asyncio.run(_run())

    def test_stage3_fallback_records_in_metadata(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-fb")
            config = CouncilConfig(members=["GLM-5.1"], chairman="GLM-5.1")

            fail_call = ModelCallResult(
                expected_model="GLM-5.1", actual_model=None, response="",
                status="failed", session_id="s1", command=["traecli"], exit_code=1,
                stdout_path="out.jsonl", stderr_path="err.log", error="timeout",
            )
            ok_call = ModelCallResult(
                expected_model="Qwen3.6-Plus", actual_model="Qwen3.6-Plus", response="Fallback answer",
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(side_effect=[fail_call, ok_call])

            final, meta = await stage3_synthesize_final(
                "test query",
                [{"label": "Response A", "model": "GLM-5.1", "response": "A", "status": "ok"}],
                [{"model": "GLM-5.1", "ranking": "1. Response A", "parsed_ranking": ["Response A"], "status": "ok"}],
                config, provider, store,
                fallback_chain=["Qwen3.6-Plus"],
            )
            self.assertEqual(final["model"], "Qwen3.6-Plus")
            self.assertEqual(final["status"], "ok")
            self.assertEqual(meta["used"], "Qwen3.6-Plus")
            self.assertEqual(meta["fallback_from"], "GLM-5.1")
            self.assertEqual(meta["attempted"], ["GLM-5.1", "Qwen3.6-Plus"])

        import asyncio
        asyncio.run(_run())

    def test_recommend_model_choice_prefers_non_openrouter(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        models = [
            {"name": "openrouter-2o"},
            {"name": "GLM-5.1"},
            {"name": "Qwen3.6-Plus"},
        ]
        choice = recommend_model_choice(models)
        self.assertNotIn("openrouter-2o", choice.members)
        self.assertEqual(choice.source, "recommended")

    def test_recommend_model_choice_fallback_to_openrouter(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        models = [{"name": "openrouter-2o"}]
        choice = recommend_model_choice(models)
        self.assertEqual(choice.members, ["openrouter-2o"])

    def test_recommend_model_choice_empty_models(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        choice = recommend_model_choice([])
        self.assertEqual(choice.source, "static-default")

    def test_recommend_model_chairman_from_preferred(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        models = [
            {"name": "GLM-5.1"},
            {"name": "Qwen3.6-Plus"},
            {"name": "GPT-5.4"},
            {"name": "Kimi-K2.6"},
        ]
        choice = recommend_model_choice(models)
        self.assertEqual(choice.chairman, "Kimi-K2.6")

    def test_stage1_hard_timeout_cancels_remaining(self):
        async def _run():
            from llm_council_for_trae.council import stage1_collect_responses, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-hard-to")
            config = CouncilConfig(
                members=["A", "B", "C"],
                chairman="X",
                member_soft_checkpoint=1,
                member_quorum_checkpoint=2,
                member_hard_timeout=3,
            )

            async def slow_query(**kwargs):
                await asyncio.sleep(10)
                return ModelCallResult(
                    expected_model=kwargs["model"], actual_model=kwargs["model"],
                    response="ok", status="ok", session_id="s1",
                    command=[], exit_code=0, stdout_path="", stderr_path="",
                )

            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = slow_query

            results = await asyncio.wait_for(
                stage1_collect_responses("test", config, provider, store),
                timeout=15,
            )
            failed = [r for r in results if r["status"] == "failed"]
            self.assertGreater(len(failed), 0)
            self.assertTrue(any("cancelled_by_stage_timeout" in (r.get("error") or "") for r in results))

        import asyncio
        asyncio.run(_run())

    def test_stage1_quorum_checkpoint_skips_when_sufficient(self):
        async def _run():
            from llm_council_for_trae.council import stage1_collect_responses, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-quorum-to")
            config = CouncilConfig(
                members=["A", "B", "C", "D"],
                chairman="X",
                min_valid_members=2,
                member_soft_checkpoint=1,
                member_quorum_checkpoint=2,
                member_hard_timeout=30,
            )
            call_count = 0

            async def quick_then_slow(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return ModelCallResult(
                        expected_model=kwargs["model"], actual_model=kwargs["model"],
                        response="ok", status="ok", session_id="s1",
                        command=[], exit_code=0, stdout_path="", stderr_path="",
                    )
                await asyncio.sleep(60)
                return ModelCallResult(
                    expected_model=kwargs["model"], actual_model=kwargs["model"],
                    response="ok", status="ok", session_id="s1",
                    command=[], exit_code=0, stdout_path="", stderr_path="",
                )

            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = quick_then_slow

            results = await asyncio.wait_for(
                stage1_collect_responses("test", config, provider, store),
                timeout=20,
            )
            ok_results = [r for r in results if r["status"] == "ok"]
            self.assertGreaterEqual(len(ok_results), 2)

        import asyncio
        asyncio.run(_run())

    def test_model_call_result_new_fields(self):
        result = ModelCallResult(
            expected_model="GPT-5.4", actual_model="GPT-5.4", response="ok",
            status="ok", session_id="s1", command=["traecli"], exit_code=0,
            stdout_path="out.jsonl", stderr_path="err.log",
        )
        self.assertEqual(result.tool_calls_count, 0)
        self.assertEqual(result.turns_count, 0)
        self.assertFalse(result.retried)
        self.assertIsNone(result.retry_error)
        j = result.to_json()
        self.assertEqual(j["tool_calls_count"], 0)
        self.assertEqual(j["turns_count"], 0)
        self.assertFalse(j["retried"])
        self.assertIsNone(j["retry_error"])

        result2 = ModelCallResult(
            expected_model="GPT-5.4", actual_model="GPT-5.4", response="ok",
            status="ok", session_id="s1", command=["traecli"], exit_code=0,
            stdout_path="out.jsonl", stderr_path="err.log",
            tool_calls_count=5, turns_count=3, retried=True, retry_error="first error",
        )
        self.assertEqual(result2.tool_calls_count, 5)
        self.assertEqual(result2.turns_count, 3)
        self.assertTrue(result2.retried)
        self.assertEqual(result2.retry_error, "first error")

    def test_stage1_result_dict_has_metrics(self):
        async def _run():
            from llm_council_for_trae.council import stage1_collect_responses, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s1-metrics")
            config = CouncilConfig(members=["GLM-5.1"], chairman="X")

            ok_call = ModelCallResult(
                expected_model="GLM-5.1", actual_model="GLM-5.1", response="Answer",
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
                tool_calls_count=3, turns_count=5,
                tool_budget_status="ok", raw_partial_recoverable=False,
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            results = await stage1_collect_responses("test", config, provider, store)
            self.assertEqual(len(results), 1)
            r = results[0]
            self.assertEqual(r["tool_calls_count"], 3)
            self.assertEqual(r["turns_count"], 5)
            self.assertEqual(r["tool_budget_status"], "ok")
            self.assertFalse(r["raw_partial_recoverable"])

        import asyncio
        asyncio.run(_run())

    def test_stage2_result_dict_has_metrics(self):
        async def _run():
            from llm_council_for_trae.council import stage2_collect_rankings, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s2-metrics")
            config = CouncilConfig(members=["GLM-5.1"], chairman="X")

            ok_call = ModelCallResult(
                expected_model="GLM-5.1", actual_model="GLM-5.1",
                response="FINAL RANKING:\n1. Response A",
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
                tool_calls_count=1, turns_count=2,
                tool_budget_status="ok", raw_partial_recoverable=False,
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            stage1_results = [{"label": "Response A", "model": "GLM-5.1", "response": "A", "status": "ok"}]
            results, _label_map = await stage2_collect_rankings("test", stage1_results, config, provider, store)
            self.assertEqual(len(results), 1)
            r = results[0]
            self.assertEqual(r["tool_calls_count"], 1)
            self.assertEqual(r["turns_count"], 2)
            self.assertEqual(r["tool_budget_status"], "ok")
            self.assertFalse(r["raw_partial_recoverable"])

        import asyncio
        asyncio.run(_run())

    def test_stage3_result_dict_has_metrics(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-metrics")
            config = CouncilConfig(members=["GLM-5.1"], chairman="GLM-5.1")

            ok_call = ModelCallResult(
                expected_model="GLM-5.1", actual_model="GLM-5.1", response="Final answer",
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
                tool_calls_count=0, turns_count=1,
                tool_budget_status="ok", raw_partial_recoverable=False,
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            final, meta = await stage3_synthesize_final(
                "test query",
                [{"label": "Response A", "model": "GLM-5.1", "response": "A", "status": "ok"}],
                [{"model": "GLM-5.1", "ranking": "1. Response A", "parsed_ranking": ["Response A"], "status": "ok"}],
                config, provider, store,
            )
            self.assertEqual(final["tool_calls_count"], 0)
            self.assertEqual(final["turns_count"], 1)
            self.assertEqual(final["tool_budget_status"], "ok")
            self.assertFalse(final["raw_partial_recoverable"])

        import asyncio
        asyncio.run(_run())

    def test_retry_on_runtime_error(self):
        async def _run():
            from llm_council_for_trae.provider import TraeCliProvider, ModelCallResult
            from unittest.mock import AsyncMock, patch

            provider = TraeCliProvider.__new__(TraeCliProvider)

            fail_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model=None, response="",
                status="failed", session_id="s1", command=["traecli"], exit_code=1,
                stdout_path="out.jsonl", stderr_path="err.log",
                error="traecli result error",
            )
            ok_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response="OK",
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )

            with patch.object(provider, '_query_model_once', new_callable=AsyncMock) as mock_once:
                mock_once.side_effect = [fail_call, ok_call]
                with patch('llm_council_for_trae.provider.asyncio.sleep', new_callable=AsyncMock):
                    result = await provider.query_model(
                        model="GPT-5.4", prompt="test", run_id="r1",
                        stage="stage1", label="A", output_dir=Path(tempfile.mkdtemp()),
                    )

            self.assertEqual(result.status, "ok")
            self.assertTrue(result.retried)
            self.assertEqual(result.retry_error, "traecli result error")

        import asyncio
        asyncio.run(_run())

    def test_no_retry_on_model_error(self):
        async def _run():
            from llm_council_for_trae.provider import TraeCliProvider, ModelCallResult
            from unittest.mock import AsyncMock, patch

            provider = TraeCliProvider.__new__(TraeCliProvider)

            fail_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response="",
                status="failed", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
                error="empty model response",
            )

            with patch.object(provider, '_query_model_once', new_callable=AsyncMock) as mock_once:
                mock_once.return_value = fail_call
                result = await provider.query_model(
                    model="GPT-5.4", prompt="test", run_id="r1",
                    stage="stage1", label="A", output_dir=Path(tempfile.mkdtemp()),
                )

            self.assertEqual(result.status, "failed")
            self.assertFalse(result.retried)
            self.assertEqual(mock_once.call_count, 1)

        import asyncio
        asyncio.run(_run())

    def test_no_retry_on_budget_kill(self):
        async def _run():
            from llm_council_for_trae.provider import TraeCliProvider, ModelCallResult
            from unittest.mock import AsyncMock, patch

            provider = TraeCliProvider.__new__(TraeCliProvider)

            budget_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response="partial",
                status="failed", session_id="s1", command=["traecli"], exit_code=1,
                stdout_path="out.jsonl", stderr_path="err.log",
                error="dropped_tool_budget: killed after 50 tool calls (limit 45)",
                tool_budget_status="dropped",
            )

            with patch.object(provider, '_query_model_once', new_callable=AsyncMock) as mock_once:
                mock_once.return_value = budget_call
                result = await provider.query_model(
                    model="GPT-5.4", prompt="test", run_id="r1",
                    stage="stage1", label="A", output_dir=Path(tempfile.mkdtemp()),
                )

            self.assertEqual(result.status, "failed")
            self.assertFalse(result.retried)
            self.assertEqual(mock_once.call_count, 1)

        import asyncio
        asyncio.run(_run())

    def test_html_no_quorum_status_card(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4"},
            "status": "ok",
        }
        html = render_summary_cards(manifest, [])
        self.assertNotIn("Quorum 状态", html)
        self.assertIn("最高排序成员", html)
        self.assertIn("成员模型", html)
        self.assertIn("主席模型", html)

    def test_html_no_chairman_fallback_card(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["GPT-5.4"], "chairman": "Qwen3.6-Plus"},
            "metadata": {"chairman": {"fallback_from": "GPT-5.4", "used": "Qwen3.6-Plus"}},
            "status": "ok",
        }
        html = render_summary_cards(manifest, [])
        self.assertNotIn("主席降级", html)
        self.assertNotIn("fallback_from", html)

    def test_html_no_degraded_banner(self):
        from llm_council_for_trae.html_export import render_alerts
        html = render_alerts([], [], manifest_status="degraded_ok")
        self.assertNotIn("Quorum 降级", html)
        self.assertNotIn("warning-banner", html)
        self.assertEqual(html, "")

    def test_html_summary_cards_above_final_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-c3-layout")
            manifest = {
                "schema_version": 1,
                "run_id": "run-c3-layout",
                "created_at": "2026-05-22T00:00:00Z",
                "updated_at": "2026-05-22T00:00:00Z",
                "status": "ok",
                "input_chars": 4,
                "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake", "query_timeout": 180, "export_html": True},
                "artifacts": {"html": "html/index.html"},
                "metadata": {
                    "label_to_model": {"Response A": "GPT-5.4"},
                    "aggregate_rankings": [{"model": "GPT-5.4", "average_rank": 1.0, "rankings_count": 1, "positions": [1]}],
                },
                "stages": {
                    "stage1": [
                        {"label": "Response A", "file_label": "A", "model": "GPT-5.4", "expected_model": "GPT-5.4", "actual_model": "GPT-5.4", "response": "A", "status": "ok", "tool_calls_count": 0, "turns_count": 1},
                    ],
                    "stage2": [
                        review_json() | {"tool_calls_count": 0, "turns_count": 1},
                    ],
                    "stage3": final_json() | {"tool_calls_count": 0, "turns_count": 1},
                },
                "warnings": [],
                "failures": [],
            }
            store.write_manifest(manifest)
            plain_files = [
                "input.md", "config.json", "runtime/doctor.json", "runtime/traecli.models.json",
                "stage1/member.prompt.md", "stage1/A.response.md", "stage1/A.traecli.stream.jsonl",
                "stage2/review.prompt.md", "stage2/label_to_model.json", "stage2/aggregate.json",
                "stage2/A.review.md", "stage2/A.traecli.stream.jsonl",
                "stage3/chairman.prompt.md", "stage3/final.md", "stage3/final.traecli.stream.jsonl",
            ]
            for relative in plain_files:
                store.write_text(relative, "{}\n")
            write_json_text(store, "stage1/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage2/A.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage2/A.review.json", review_json())
            write_json_text(store, "stage3/final.meta.json", stage_meta("GPT-5.4"))
            write_json_text(store, "stage3/final.json", final_json())
            export_html(store)
            html_text = (store.root / "html" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn('id="decision-detail"', html_text)
            self.assertNotIn("class='model-performance'", html_text)
            self.assertNotIn("模型表现摘要", html_text)
            summary_pos = html_text.index("decision-summary")
            final_pos = html_text.index("final-answer")
            evidence_pos = html_text.index('id="evidence"')
            self.assertLess(summary_pos, final_pos)
            self.assertLess(final_pos, evidence_pos)

    def test_degraded_ok_exit_code_zero(self):
        from llm_council_for_trae.cli import emit
        payload = {"run_id": "test", "status": "degraded_ok", "degraded": True}
        exit_code = emit(payload, as_json=False, ok=True, text="degraded_ok")
        self.assertEqual(exit_code, 0)

    def test_degraded_ok_json_has_degraded_flag(self):
        from llm_council_for_trae.cli import emit
        import sys
        payload = {"run_id": "test", "status": "degraded_ok", "degraded": True}
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        exit_code = emit(payload, as_json=True, ok=True, text="degraded_ok")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertEqual(exit_code, 0)
        data = json.loads(output)
        self.assertTrue(data.get("degraded"))

    def test_chairman_as_member_ok_counts_toward_quorum(self):
        results = [
            {"model": "GPT-5.4", "status": "ok"},
            {"model": "GLM-5.1", "status": "ok"},
            {"model": "Qwen3.6-Plus", "status": "ok"},
            {"model": "Kimi-K2.6", "status": "ok"},
            {"model": "DeepSeek-V4", "status": "ok"},
            {"model": "Llama4-M", "status": "ok"},
            {"model": "Mistral-L", "status": "failed"},
        ]
        status = classify_stage1_status(results, min_valid_members=6, chairman_model="GPT-5.4")
        self.assertEqual(status, "degraded_ok")
        status_without_chairman_counting = classify_stage1_status(
            [r for r in results if r["model"] != "GPT-5.4"],
            min_valid_members=6,
            chairman_model="GPT-5.4",
        )
        self.assertEqual(status_without_chairman_counting, "failed")

    def test_chairman_as_member_failed_is_free(self):
        results = [
            {"model": "GPT-5.4", "status": "failed"},
            {"model": "GLM-5.1", "status": "ok"},
            {"model": "Qwen3.6-Plus", "status": "ok"},
            {"model": "Kimi-K2.6", "status": "ok"},
            {"model": "DeepSeek-V4", "status": "ok"},
            {"model": "Llama4-M", "status": "ok"},
        ]
        status = classify_stage1_status(results, min_valid_members=6, chairman_model="GPT-5.4")
        self.assertEqual(status, "ok")

    def test_chairman_independent_still_excluded(self):
        results = [
            {"model": "GPT-5.4", "status": "ok"},
            {"model": "GLM-5.1", "status": "ok"},
            {"model": "Qwen3.6-Plus", "status": "ok"},
            {"model": "Kimi-K2.6", "status": "ok"},
            {"model": "DeepSeek-V4", "status": "failed"},
            {"model": "Llama4-M", "status": "failed"},
            {"model": "Mistral-L", "status": "failed"},
        ]
        status = classify_stage1_status(results, min_valid_members=6, chairman_model="Claude-4")
        self.assertEqual(status, "failed")

    def _make_stage2_stage3_mocks(self, council_mod):
        async def mock_stage2(user_query, stage1_results, config, provider, store):
            label_to_model = {r["label"]: r["model"] for r in stage1_results}
            stage2_results = []
            for i, model in enumerate(config.members):
                label = chr(65 + i)
                labels_list = list(label_to_model.keys())
                ranking_text = "FINAL RANKING:\n" + "\n".join(f"{j+1}. {l}" for j, l in enumerate(labels_list))
                stage2_results.append({
                    "reviewer_label": label,
                    "model": model,
                    "expected_model": model,
                    "actual_model": model,
                    "ranking": ranking_text,
                    "parsed_ranking": labels_list,
                    "parse_status": "ok",
                    "status": "ok",
                    "error": None,
                    "review_path": f"stage2/{label}.review.md",
                    "json_path": f"stage2/{label}.review.json",
                    "tool_calls_count": 0,
                    "turns_count": 1,
                    "tool_budget_status": "ok",
                    "raw_partial_recoverable": False,
                    "retried": False,
                    "retry_error": None,
                })
            return stage2_results, label_to_model

        async def mock_stage3(user_query, stage1_results, stage2_results, config, provider, store, fallback_chain=None):
            final = {
                "model": config.chairman,
                "expected_model": config.chairman,
                "actual_model": config.chairman,
                "response": "Final answer",
                "status": "ok",
                "error": None,
                "prompt_path": "stage3/chairman.prompt.md",
                "response_path": "stage3/final.md",
                "json_path": "stage3/final.json",
                "tool_calls_count": 0,
                "turns_count": 1,
                "tool_budget_status": "ok",
                "raw_partial_recoverable": False,
                "retried": False,
                "retry_error": None,
            }
            meta = {"attempted": [config.chairman], "used": config.chairman, "fallback_from": None}
            return final, meta

        return mock_stage2, mock_stage3

    def test_stage1_quorum_retry_recovers_failed_members(self):
        async def _run():
            from llm_council_for_trae.council import run_full_council, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s1-retry-ok")
            config = CouncilConfig(
                members=["M1", "M2", "M3", "M4"],
                chairman="M1",
                min_valid_members=3,
                stage1_max_retries=1,
                member_soft_checkpoint=999,
                member_quorum_checkpoint=999,
                member_hard_timeout=999,
            )

            import llm_council_for_trae.council as council_mod
            call_count = {"count": 0}

            async def query_side_effect(**kwargs):
                model = kwargs["model"]
                stage = kwargs["stage"]
                call_count["count"] += 1
                if stage == "stage1" and model in ("M2", "M3") and call_count["count"] <= 4:
                    return ModelCallResult(
                        expected_model=model, actual_model=None, response="",
                        status="failed", session_id="s1", command=["traecli"], exit_code=1,
                        stdout_path="out.jsonl", stderr_path="err.log", error="traecli result error",
                    )
                return ModelCallResult(
                    expected_model=model, actual_model=model,
                    response=f"Answer from {model}", status="ok",
                    session_id=f"s-{model}", command=["traecli"], exit_code=0,
                    stdout_path="out.jsonl", stderr_path="err.log",
                )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass
                async def query_model(self, **kwargs):
                    return await query_side_effect(**kwargs)

            mock_s2, mock_s3 = self._make_stage2_stage3_mocks(council_mod)

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True, "command": "fake", "version": "1.0",
                    "doctor_exit_code": 0, "doctor": {}, "errors": [],
                    "warnings": [], "ignored_errors": [],
                    "models": [{"name": "M1"}, {"name": "M2"}, {"name": "M3"}, {"name": "M4"}],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        with patch.object(council_mod, "stage2_collect_rankings", mock_s2):
                            with patch.object(council_mod, "stage3_synthesize_final", mock_s3):
                                manifest = await run_full_council("test query", config, store)
                                self.assertIn(manifest["status"], ("ok", "degraded_ok"))
                                stage1 = manifest["stages"]["stage1"]
                                ok_count = sum(1 for r in stage1 if r["status"] == "ok")
                                self.assertGreaterEqual(ok_count, 3)
                                self.assertTrue(any(r.get("retried") for r in stage1))

        import asyncio
        asyncio.run(_run())

    def test_stage1_quorum_retry_excludes_chairman_failed(self):
        async def _run():
            from llm_council_for_trae.council import run_full_council, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s1-retry-chair-fail")
            config = CouncilConfig(
                members=["M1", "M2", "M3", "M4"],
                chairman="M1",
                min_valid_members=3,
                stage1_max_retries=1,
                member_soft_checkpoint=999,
                member_quorum_checkpoint=999,
                member_hard_timeout=999,
            )

            import llm_council_for_trae.council as council_mod

            async def query_side_effect(**kwargs):
                model = kwargs["model"]
                stage = kwargs["stage"]
                if stage == "stage1" and model == "M1":
                    return ModelCallResult(
                        expected_model="M1", actual_model=None, response="",
                        status="failed", session_id="s1", command=["traecli"], exit_code=1,
                        stdout_path="out.jsonl", stderr_path="err.log", error="timeout",
                    )
                return ModelCallResult(
                    expected_model=model, actual_model=model,
                    response=f"Answer from {model}", status="ok",
                    session_id=f"s-{model}", command=["traecli"], exit_code=0,
                    stdout_path="out.jsonl", stderr_path="err.log",
                )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass
                async def query_model(self, **kwargs):
                    return await query_side_effect(**kwargs)

            mock_s2, mock_s3 = self._make_stage2_stage3_mocks(council_mod)

            with patch.object(council_mod, "runtime_doctor") as mock_doctor:
                mock_doctor.return_value = type("Health", (), {
                    "ok": True, "command": "fake", "version": "1.0",
                    "doctor_exit_code": 0, "doctor": {}, "errors": [],
                    "warnings": [], "ignored_errors": [],
                    "models": [{"name": "M1"}, {"name": "M2"}, {"name": "M3"}, {"name": "M4"}],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        with patch.object(council_mod, "stage2_collect_rankings", mock_s2):
                            with patch.object(council_mod, "stage3_synthesize_final", mock_s3):
                                manifest = await run_full_council("test query", config, store)
                                self.assertIn(manifest["status"], ("ok", "degraded_ok"))
                                stage1 = manifest["stages"]["stage1"]
                                m1 = [r for r in stage1 if r["model"] == "M1"][0]
                                self.assertEqual(m1["status"], "failed")
                                self.assertFalse(m1.get("retried"))
                                ok_count = sum(1 for r in stage1 if r["status"] == "ok")
                                self.assertEqual(ok_count, 3)

        import asyncio
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
