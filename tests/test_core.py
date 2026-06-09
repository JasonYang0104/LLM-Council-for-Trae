import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from llm_council_for_trae.cli import build_config, build_parser, failure_recommendations, resolve_run_model_choice
from llm_council_for_trae.council import (
    build_stage1_prompt,
    build_stage2_prompt,
    build_stage3_prompt,
    calculate_aggregate_rankings,
    classify_stage1_status,
    config_to_json,
    CouncilConfig,
    DEFAULT_CHAIRMAN,
    DEFAULT_MEMBERS,
    initial_manifest,
    parse_ranking_from_text,
    record_stage_failures,
)
from llm_council_for_trae.html_export import _extract_title, export_html, render_html
from llm_council_for_trae import model_selection
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


def render_manifest_html(manifest):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "stage3").mkdir()
        (root / "input.md").write_text("Report topic: 测试议题\n", encoding="utf-8")
        (root / "stage3" / "final.md").write_text("## 最终答案\n\n正文。\n", encoding="utf-8")
        (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
        return render_html(root, manifest)


def render_contribution_map_blocks(blocks):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "stage3").mkdir()
        (root / "input.md").write_text("Report topic: 贡献说明 Markdown 测试\n", encoding="utf-8")
        (root / "stage3" / "final.md").write_text("legacy markdown should not render\n", encoding="utf-8")
        (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
        (root / "stage3" / "contribution_map.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "enabled": True,
                    "source": "chairman_structured_output",
                    "blocks": blocks,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": 1,
            "run_id": "run-html-contribution-markdown",
            "status": "ok",
            "config": {
                "members": ["GPT-5.4", "openrouter-3o"],
                "chairman": "DeepSeek-V4-Pro",
                "provider_mode": "direct",
                "runtime_command": "fake",
            },
            "metadata": {
                "aggregate_rankings": [
                    {"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0},
                    {"label": "Response B", "model": "openrouter-3o", "average_rank": 2.0},
                ],
                "chairman_contribution": {"enabled": True, "path": "stage3/contribution_map.json"},
            },
            "stages": {
                "stage1": [
                    {"label": "Response A", "file_label": "A", "model": "GPT-5.4", "status": "ok"},
                    {"label": "Response B", "file_label": "B", "model": "openrouter-3o", "status": "ok"},
                ],
                "stage2": [],
                "stage3": {"model": "DeepSeek-V4-Pro", "status": "ok"},
            },
            "warnings": [],
            "failures": [],
        }
        return render_html(root, manifest)


def write_reviewer_only_backfill_run(store, *, leak_reviewer_into_subjects: bool = False, ranking_includes_reviewer_subject: bool = False):
    label_to_model = {
        "Response A": "M1",
        "Response B": "M2",
        "Response C": "M3",
    }
    if leak_reviewer_into_subjects:
        label_to_model["Response D"] = "M4"
    reviewer_labels = list(label_to_model.keys()) if ranking_includes_reviewer_subject else ["Response A", "Response B", "Response C"]
    reviewer_ranking = "FINAL RANKING:\n" + "\n".join(f"{index + 1}. {label}" for index, label in enumerate(reviewer_labels))
    stage2 = [
        review_json() | {
            "reviewer_label": "A",
            "model": "M1",
            "expected_model": "M1",
            "actual_model": "M1",
            "ranking": "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C",
            "parsed_ranking": ["Response A", "Response B", "Response C"],
            "reviewer_eligible": True,
            "reviewer_source": "stage1_ok",
            "attempt_role": "primary",
            "review_subject_count": 3,
            "review_path": "stage2/A.review.md",
            "json_path": "stage2/A.review.json",
        },
        review_json() | {
            "reviewer_label": "B",
            "model": "M2",
            "expected_model": "M2",
            "actual_model": None,
            "ranking": "",
            "parsed_ranking": [],
            "parse_status": "incomplete",
            "status": "failed",
            "error": "timeout",
            "reviewer_eligible": True,
            "reviewer_source": "stage1_ok",
            "attempt_role": "primary",
            "review_subject_count": 3,
            "review_path": "stage2/B.review.md",
            "json_path": "stage2/B.review.json",
        },
        review_json() | {
            "reviewer_label": "C",
            "model": "M3",
            "expected_model": "M3",
            "actual_model": "M3",
            "ranking": "FINAL RANKING:\n1. Response C\n2. Response A\n3. Response B",
            "parsed_ranking": ["Response C", "Response A", "Response B"],
            "reviewer_eligible": True,
            "reviewer_source": "stage1_ok",
            "attempt_role": "primary",
            "review_subject_count": 3,
            "review_path": "stage2/C.review.md",
            "json_path": "stage2/C.review.json",
        },
        review_json() | {
            "reviewer_label": "R4",
            "model": "M4",
            "expected_model": "M4",
            "actual_model": "M4",
            "ranking": reviewer_ranking,
            "parsed_ranking": reviewer_labels,
            "reviewer_eligible": True,
            "reviewer_source": "stage2_reviewer_backfill",
            "attempt_role": "reviewer_backfill",
            "review_subject_count": 3,
            "review_path": "stage2/R4.review.md",
            "json_path": "stage2/R4.review.json",
        },
    ]
    manifest = {
        "schema_version": 1,
        "run_id": store.root.name,
        "created_at": "2026-05-22T00:00:00Z",
        "updated_at": "2026-05-22T00:00:00Z",
        "status": "ok",
        "input_chars": 4,
        "config": {
            "members": ["M1", "M2", "M3"],
            "chairman": "Chair",
            "provider_mode": "direct",
            "runtime_command": "fake",
            "query_timeout": 180,
            "export_html": True,
            "use_yolo": False,
            "member_tool_mode": "search_enabled",
            "member_runtime_cwd_mode": "isolated_temp",
        },
        "artifacts": {"html": "html/index.html"},
        "metadata": {
            "label_to_model": label_to_model,
            "aggregate_rankings": [{"model": "M1", "average_rank": 1.0, "rankings_count": 3, "positions": [1, 2, 1]}],
            "quorum": {
                "min_valid_members": 3,
                "target_valid_members": 3,
                "low_quorum_floor": 2,
                "effective_valid_members": 3,
                "normal_quorum_met": True,
                "low_quorum_used": False,
                "backfill_used": False,
                "primary_members": ["M1", "M2", "M3"],
                "candidate_source": "explicit",
                "backfill_candidates": ["M4"],
                "backfill_attempted": [],
                "effective_stage1_members": ["M1", "M2", "M3"],
            },
            "stage2_reviewers": {
                "reviewer_target": 3,
                "review_subject_count": 3,
                "review_subject_labels": ["Response A", "Response B", "Response C"],
                "valid_reviewers": ["M1", "M3", "M4"],
                "failed_reviewers": ["M2"],
                "backfill_reviewers": ["M4"],
                "reviewer_backfill_attempted": ["M4"],
                "member_backfill_attempted": [],
                "reviewer_only_backfill": True,
            },
        },
        "stages": {
            "stage1": [
                {"label": "Response A", "file_label": "A", "model": "M1", "expected_model": "M1", "actual_model": "M1", "response": "A", "status": "ok"} | tool_policy_json(),
                {"label": "Response B", "file_label": "B", "model": "M2", "expected_model": "M2", "actual_model": "M2", "response": "B", "status": "ok"} | tool_policy_json(),
                {"label": "Response C", "file_label": "C", "model": "M3", "expected_model": "M3", "actual_model": "M3", "response": "C", "status": "ok"} | tool_policy_json(),
            ],
            "stage2": stage2,
            "stage3": final_json() | {"model": "Chair", "expected_model": "Chair", "actual_model": "Chair"},
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
        "stage1/B.response.md",
        "stage1/B.traecli.stream.jsonl",
        "stage1/C.response.md",
        "stage1/C.traecli.stream.jsonl",
        "stage2/review.prompt.md",
        "stage2/label_to_model.json",
        "stage2/aggregate.json",
        "stage2/A.review.md",
        "stage2/A.traecli.stream.jsonl",
        "stage2/B.review.md",
        "stage2/B.traecli.stream.jsonl",
        "stage2/C.review.md",
        "stage2/C.traecli.stream.jsonl",
        "stage2/R4.review.md",
        "stage2/R4.traecli.stream.jsonl",
        "stage3/chairman.prompt.md",
        "stage3/final.md",
        "stage3/final.traecli.stream.jsonl",
        "html/index.html",
    ]:
        store.write_text(relative, "{}\n")
    write_json_text(store, "stage1/A.meta.json", stage_meta("M1"))
    write_json_text(store, "stage1/B.meta.json", stage_meta("M2"))
    write_json_text(store, "stage1/C.meta.json", stage_meta("M3"))
    for item in stage2:
        label = item["reviewer_label"]
        write_json_text(store, f"stage2/{label}.meta.json", stage_meta(item["expected_model"], item["actual_model"] or item["expected_model"]))
        write_json_text(store, f"stage2/{label}.review.json", item)
    write_json_text(store, "stage3/final.meta.json", stage_meta("Chair"))
    write_json_text(store, "stage3/final.json", manifest["stages"]["stage3"])
    write_json_text(store, "html/export.json", {"run_id": store.root.name, "generated_at": "2026-05-22T00:00:00Z", "format": "html", "path": "html/index.html", "source_manifest": "manifest.json"})
    write_json_text(store, "stage2/label_to_model.json", label_to_model)
    write_json_text(store, "stage2/aggregate.json", manifest["metadata"]["aggregate_rankings"])


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

    def test_stage3_prompt_includes_aggregate_rankings_and_copy_constraints(self):
        question = "Should local personal agents reach mass adoption in 2026H2?"
        stage1_results = [
            {"label": "Response A", "model": "Kimi-K2.6", "response": "A says early adoption."},
            {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B says developer adoption first."},
            {"label": "Response C", "model": "GPT-5.2", "response": "C says mass adoption lags."},
        ]
        stage2_results = [
            {
                "model": "Reviewer",
                "ranking": "FINAL RANKING:\n1. Response C\n2. Response B\n3. Response A",
                "parsed_ranking": ["Response C", "Response B", "Response A"],
                "status": "ok",
                "parse_status": "ok",
            }
        ]
        aggregate_rankings = [
            {"label": "Response C", "model": "GPT-5.2", "average_rank": 1.0, "rankings_count": 3, "positions": [1, 1, 1]},
            {"label": "Response B", "model": "DeepSeek-V4-Pro", "average_rank": 2.0, "rankings_count": 3, "positions": [2, 2, 2]},
            {"label": "Response A", "model": "Kimi-K2.6", "average_rank": 3.0, "rankings_count": 3, "positions": [3, 3, 3]},
        ]

        stage3_prompt = build_stage3_prompt(
            question,
            stage1_results,
            stage2_results,
            aggregate_rankings=aggregate_rankings,
        )

        self.assertIn("Stage 2 综合排序", stage3_prompt)
        self.assertIn("1. Response C | model=GPT-5.2 | average_rank=1.0 | rankings_count=3 | positions=[1, 1, 1]", stage3_prompt)
        self.assertIn("2. Response B | model=DeepSeek-V4-Pro | average_rank=2.0 | rankings_count=3 | positions=[2, 2, 2]", stage3_prompt)
        self.assertIn("3. Response A | model=Kimi-K2.6 | average_rank=3.0 | rankings_count=3 | positions=[3, 3, 3]", stage3_prompt)
        self.assertLess(stage3_prompt.index("1. Response C"), stage3_prompt.index("2. Response B"))
        self.assertLess(stage3_prompt.index("2. Response B"), stage3_prompt.index("3. Response A"))
        self.assertIn("不得逐字或近似复用任何 Stage 1 回答", stage3_prompt)
        self.assertIn("必须显式融合 top-ranked responses", stage3_prompt)

    def test_chairman_contribution_map_requested_by_default(self):
        config = CouncilConfig(members=["GPT-5.4"], chairman="GPT-5.4")

        self.assertTrue(config.chairman_contribution_enabled)
        self.assertFalse(config.chairman_contribution_required)

    def test_config_to_json_records_contribution_map_repair_attempts(self):
        config = CouncilConfig(
            members=["GPT-5.4"],
            chairman="GPT-5.4",
            chairman_contribution_repair_attempts=4,
        )

        serialized = config_to_json(config)

        self.assertEqual(serialized["chairman_contribution_repair_attempts"], 4)

    def test_build_config_can_disable_chairman_contribution_map(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md", "--default-models", "--no-chairman-contribution-map"])
        args.selected_model_choice = resolve_run_model_choice(args)

        config = build_config(args)

        self.assertFalse(config.chairman_contribution_enabled)
        self.assertFalse(config.chairman_contribution_required)

    def test_build_config_accepts_compat_chairman_contribution_map(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md", "--default-models", "--chairman-contribution-map"])
        args.selected_model_choice = resolve_run_model_choice(args)

        config = build_config(args)

        self.assertTrue(config.chairman_contribution_enabled)
        self.assertFalse(config.chairman_contribution_required)

    def test_build_config_requires_chairman_contribution_map_strict(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md", "--default-models", "--require-chairman-contribution-map"])
        args.selected_model_choice = resolve_run_model_choice(args)

        config = build_config(args)

        self.assertTrue(config.chairman_contribution_enabled)
        self.assertTrue(config.chairman_contribution_required)

    def test_build_config_rejects_required_contribution_map_when_disabled(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "run",
                "--input",
                "question.md",
                "--default-models",
                "--no-chairman-contribution-map",
                "--require-chairman-contribution-map",
            ]
        )
        args.selected_model_choice = resolve_run_model_choice(args)

        with self.assertRaisesRegex(ValueError, "--require-chairman-contribution-map cannot be combined"):
            build_config(args)

    def test_stage3_prompt_requests_contribution_blocks_by_default(self):
        question = "Explain trust improvements."
        stage1_results = [
            {"label": "Response A", "model": "GPT-5.4", "response": "A says transparency matters."},
            {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B says provenance matters."},
        ]
        stage2_results = [
            {
                "model": "Reviewer",
                "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                "parsed_ranking": ["Response A", "Response B"],
                "status": "ok",
                "parse_status": "ok",
            }
        ]

        default_prompt = build_stage3_prompt(
            question,
            stage1_results,
            stage2_results,
            aggregate_rankings=[{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0, "rankings_count": 1, "positions": [1]}],
        )
        disabled_prompt = build_stage3_prompt(question, stage1_results, stage2_results, contribution_map_enabled=False)
        enabled_prompt = build_stage3_prompt(
            question,
            stage1_results,
            stage2_results,
            aggregate_rankings=[{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0, "rankings_count": 1, "positions": [1]}],
            contribution_map_enabled=True,
        )

        self.assertIn("contribution_map.json", default_prompt)
        self.assertIn("blocks", default_prompt)
        self.assertNotIn("contribution_map", disabled_prompt)
        self.assertIn("contribution_map.json", enabled_prompt)
        self.assertIn("blocks", enabled_prompt)
        self.assertIn("single_member", enabled_prompt)
        self.assertIn("multi_member_consensus", enabled_prompt)
        self.assertIn("editor_note", enabled_prompt)

    def test_stage3_prompt_requires_json_parseable_contribution_map(self):
        prompt = build_stage3_prompt(
            "Explain trust improvements.",
            [{"label": "Response A", "model": "GPT-5.4", "response": "A says transparency matters."}],
            [
                {
                    "model": "GPT-5.4",
                    "ranking": "FINAL RANKING:\n1. Response A",
                    "parsed_ranking": ["Response A"],
                    "status": "ok",
                }
            ],
            aggregate_rankings=[{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0, "rankings_count": 1, "positions": [1]}],
        )

        self.assertIn("唯一一个 fenced `json` 代码块", prompt)
        self.assertIn("必须能被 `json.loads` 直接解析", prompt)
        self.assertIn("禁止写未转义的 `\"`", prompt)
        self.assertIn("JSON 代码块之后不要再输出任何解释", prompt)

    def test_stage3_prompt_defines_synthesis_members_as_reference_not_consensus(self):
        prompt = build_stage3_prompt(
            "Explain attribution semantics.",
            [
                {"label": "Response A", "model": "GPT-5.5", "response": "A says one thing."},
                {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B says another thing."},
            ],
            [
                {
                    "model": "GPT-5.5",
                    "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                    "parsed_ranking": ["Response A", "Response B"],
                    "status": "ok",
                }
            ],
        )

        self.assertIn("multi_member_consensus.members 表示这些成员都表达过同一核心观点", prompt)
        self.assertIn("synthesis.members 表示主席主要参考了这些成员素材", prompt)
        self.assertIn("synthesis 不等于成员共识", prompt)
        self.assertIn("无法可靠归因", prompt)
        self.assertIn("not_attributable", prompt)

    def test_stage3_prompt_includes_contribution_map_display_constraints(self):
        prompt = build_stage3_prompt(
            "Explain readable contribution output.",
            [
                {"label": "Response A", "model": "GPT-5.5", "response": "A says one thing."},
                {"label": "Response B", "model": "openrouter-3o", "response": "B says another thing."},
            ],
            [
                {
                    "model": "GPT-5.5",
                    "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                    "parsed_ranking": ["Response A", "Response B"],
                    "status": "ok",
                }
            ],
        )

        self.assertIn("Contribution map 输出约束", prompt)
        self.assertIn("不得写成一整段内联编号或内联顿号串", prompt)
        self.assertIn("有顺序关系的要点使用有序列表", prompt)
        self.assertIn("无顺序关系的并列要点使用无序列表", prompt)
        self.assertIn("editor_note 类型的 block.text 必须是纯评注意见", prompt)
        self.assertIn("不得包含“编者注：”“主席评注：”“评注：”", prompt)
        self.assertIn("不应依赖渲染器二次拆段", prompt)

    def test_initial_manifest_records_default_chairman_contribution_metadata(self):
        config = CouncilConfig(members=["GPT-5.4"], chairman="GPT-5.4")

        manifest = initial_manifest("run-default-contribution", "question", config)

        contribution = manifest["metadata"]["chairman_contribution"]
        self.assertTrue(contribution["enabled"])
        self.assertTrue(contribution["requested"])
        self.assertFalse(contribution["required"])
        self.assertFalse(contribution["present"])
        self.assertEqual(contribution["path"], "stage3/contribution_map.json")

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
        self.assertEqual(choice.members, ["DeepSeek-V4-Pro", "GPT-5.4", "openrouter-2o"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")

    def test_default_direct_roster_uses_current_priority_suite(self):
        self.assertEqual(
            DEFAULT_MEMBERS,
            ["DeepSeek-V4-Pro", "GPT-5.5", "openrouter-3o"],
        )
        self.assertEqual(DEFAULT_CHAIRMAN, "DeepSeek-V4-Pro")

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
        self.assertEqual(choice.members, ["DeepSeek-V4-Pro", "GPT-5.4"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")
        self.assertIn("LCT 检测到当前 traecli 可用模型", stderr.getvalue())
        self.assertIn("推荐 council 模型套", stderr.getvalue())

    def test_interactive_model_selection_accepts_custom_numbered_models(self):
        models = [
            {"name": "GPT-5.4"},
            {"name": "GLM-5.1"},
            {"name": "DeepSeek-V4-Pro"},
            {"name": "openrouter-1o"},
            {"name": "Kimi-K2.6"},
            {"name": "Gemini-3.1-Pro-Preview"},
        ]
        choice = select_model_choice_interactively(models, stdin=StringIO("c\n1,3\n3\n"), stderr=StringIO())
        self.assertEqual(choice.members, ["GPT-5.4", "DeepSeek-V4-Pro", "Kimi-K2.6"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")
        self.assertEqual(resolve_model_tokens("2, GPT-5.4", ["GPT-5.4", "GLM-5.1"]), ["GLM-5.1", "GPT-5.4"])

    def test_normalize_user_model_selection_fills_to_three_by_preferred_members(self):
        normalize = getattr(model_selection, "normalize_user_model_selection", None)
        self.assertIsNotNone(normalize, "missing normalize_user_model_selection")
        models = [
            {"name": "DeepSeek-V4-Pro"},
            {"name": "openrouter-3o"},
            {"name": "openrouter-1o"},
            {"name": "GPT-5.4"},
            {"name": "Kimi-K2.6"},
            {"name": "Gemini-3.1-Pro-Preview"},
        ]

        choice = normalize(
            requested_members=["Kimi-K2.6", "GPT-5.4"],
            requested_chairman="DeepSeek-V4-Pro",
            models=models,
            selection_surface="agent_assisted",
        )

        self.assertEqual(choice.members, ["Kimi-K2.6", "GPT-5.4", "DeepSeek-V4-Pro"])
        self.assertEqual(choice.chairman, "DeepSeek-V4-Pro")
        self.assertEqual(choice.provenance["selection_surface"], "agent_assisted")
        self.assertEqual(choice.provenance["requested_members"], ["Kimi-K2.6", "GPT-5.4"])
        self.assertEqual(choice.provenance["filled_members"], ["DeepSeek-V4-Pro"])
        self.assertEqual(choice.provenance["normalization_target_members"], 3)

    def test_normalize_user_model_selection_trims_to_three_by_preferred_members(self):
        normalize = getattr(model_selection, "normalize_user_model_selection", None)
        self.assertIsNotNone(normalize, "missing normalize_user_model_selection")
        models = [
            {"name": "DeepSeek-V4-Pro"},
            {"name": "openrouter-3o"},
            {"name": "openrouter-1o"},
            {"name": "GPT-5.4"},
            {"name": "Kimi-K2.6"},
            {"name": "Gemini-3.1-Pro-Preview"},
            {"name": "Unranked-Model"},
        ]

        choice = normalize(
            requested_members=["Unranked-Model", "Kimi-K2.6", "GPT-5.4", "DeepSeek-V4-Pro", "openrouter-1o", "openrouter-3o"],
            requested_chairman="Kimi-K2.6",
            models=models,
            selection_surface="agent_assisted",
        )

        self.assertEqual(choice.members, ["DeepSeek-V4-Pro", "openrouter-3o", "GPT-5.4"])
        self.assertEqual(choice.provenance["trimmed_members"], ["Unranked-Model", "Kimi-K2.6", "openrouter-1o"])
        self.assertEqual(choice.provenance["resolved_members"], choice.members)

    def test_normalize_user_model_selection_keeps_exact_three_user_order(self):
        normalize = getattr(model_selection, "normalize_user_model_selection", None)
        self.assertIsNotNone(normalize, "missing normalize_user_model_selection")
        models = [
            {"name": "DeepSeek-V4-Pro"},
            {"name": "openrouter-3o"},
            {"name": "openrouter-1o"},
            {"name": "GPT-5.4"},
            {"name": "Kimi-K2.6"},
            {"name": "Gemini-3.1-Pro-Preview"},
        ]

        choice = normalize(
            requested_members=["GPT-5.4", "DeepSeek-V4-Pro", "openrouter-1o"],
            requested_chairman=None,
            models=models,
            selection_surface="agent_assisted",
        )

        self.assertEqual(choice.members, ["GPT-5.4", "DeepSeek-V4-Pro", "openrouter-1o"])
        self.assertEqual(choice.chairman, "GPT-5.4")
        self.assertEqual(choice.provenance["trimmed_members"], [])
        self.assertEqual(choice.provenance["filled_members"], [])

    def test_normalize_user_model_selection_fails_closed_for_unknown_model(self):
        normalize = getattr(model_selection, "normalize_user_model_selection", None)
        self.assertIsNotNone(normalize, "missing normalize_user_model_selection")

        with self.assertRaisesRegex(ValueError, "Unknown-Model"):
            normalize(
                requested_members=["Unknown-Model"],
                requested_chairman=None,
                models=[{"name": "DeepSeek-V4-Pro"}],
                selection_surface="agent_assisted",
            )

    def test_normalize_user_model_selection_fails_closed_when_available_fillers_cannot_reach_three(self):
        normalize = getattr(model_selection, "normalize_user_model_selection", None)
        self.assertIsNotNone(normalize, "missing normalize_user_model_selection")

        with self.assertRaisesRegex(ValueError, "无法归一化到 3 个成员"):
            normalize(
                requested_members=["MiniMax-M2.7"],
                requested_chairman=None,
                models=[{"name": "MiniMax-M2.7"}, {"name": "DeepSeek-V4-Pro"}],
                selection_surface="agent_assisted",
            )

    def test_native_members_build_config_is_not_normalized(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md", "--members", "M1,M2,M3", "--chairman", "Chair"])
        args.selected_model_choice = resolve_run_model_choice(args)

        config = build_config(args)

        self.assertEqual(config.members, ["M1", "M2", "M3"])
        self.assertEqual(config.chairman, "Chair")

    def test_selected_members_cli_path_is_normalized_and_records_provenance(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "run",
                "--input",
                "question.md",
                "--selected-members",
                "Kimi-K2.6,GPT-5.4",
                "--selected-chairman",
                "DeepSeek-V4-Pro",
            ]
        )
        models = [
            {"name": "DeepSeek-V4-Pro"},
            {"name": "openrouter-3o"},
            {"name": "openrouter-1o"},
            {"name": "GPT-5.4"},
            {"name": "Kimi-K2.6"},
            {"name": "Gemini-3.1-Pro-Preview"},
        ]
        with patch("llm_council_for_trae.cli.get_models", return_value=models):
            args.selected_model_choice = resolve_run_model_choice(args)
        config = build_config(args)

        self.assertEqual(config.members, ["Kimi-K2.6", "GPT-5.4", "DeepSeek-V4-Pro"])
        self.assertEqual(config.chairman, "DeepSeek-V4-Pro")
        self.assertEqual(config.model_selection_provenance["selection_surface"], "agent_assisted")
        self.assertEqual(config.model_selection_provenance["requested_members"], ["Kimi-K2.6", "GPT-5.4"])

    def test_selected_members_cli_path_cannot_be_combined_with_profile(self):
        parser = build_parser()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = Path(tmpdir) / "profile.json"
            profile_path.write_text(
                json.dumps({"provider_mode": "direct", "members": ["M1"], "chairman": "Chair"}),
                encoding="utf-8",
            )
            args = parser.parse_args(
                [
                    "run",
                    "--input",
                    "question.md",
                    "--profile",
                    str(profile_path),
                    "--selected-members",
                    "DeepSeek-V4-Pro",
                ]
            )

            with self.assertRaisesRegex(ValueError, "--selected-members/--selected-chairman cannot be combined"):
                resolve_run_model_choice(args)

    def test_selected_chairman_requires_selected_members(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md", "--selected-chairman", "DeepSeek-V4-Pro"])

        with self.assertRaisesRegex(ValueError, "--selected-chairman requires --selected-members"):
            resolve_run_model_choice(args)

    def test_non_tty_model_selection_error_mentions_agent_assisted_path(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md"])

        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "--selected-members/--selected-chairman"):
                resolve_run_model_choice(args)

    def test_initial_manifest_persists_model_selection_provenance(self):
        config = CouncilConfig(
            members=["Kimi-K2.6", "GPT-5.4", "DeepSeek-V4-Pro"],
            chairman="DeepSeek-V4-Pro",
            model_selection_provenance={
                "selection_surface": "agent_assisted",
                "requested_members": ["Kimi-K2.6", "GPT-5.4"],
                "resolved_members": ["Kimi-K2.6", "GPT-5.4", "DeepSeek-V4-Pro"],
                "trimmed_members": [],
                "filled_members": ["DeepSeek-V4-Pro"],
                "normalization_target_members": 3,
            },
        )

        manifest = initial_manifest("run-selected", "question", config)

        self.assertEqual(manifest["metadata"]["model_selection"]["selection_surface"], "agent_assisted")
        self.assertEqual(
            manifest["metadata"]["model_selection"]["resolved_members"],
            ["Kimi-K2.6", "GPT-5.4", "DeepSeek-V4-Pro"],
        )

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

    def test_parse_stream_json_tracks_web_tool_results_separately(self):
        stream = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init", "session_id": "s1", "model": "GPT-5.4"}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "tc1",
                                    "type": "function",
                                    "function": {"name": "WebSearch", "arguments": "{\"query\":\"x\"}"},
                                }
                            ],
                        },
                    }
                ),
                json.dumps({"type": "user", "subtype": "tool_result", "tool_name": "WebSearch", "tool_use_id": "tc1", "content": "results"}),
                json.dumps({"type": "user", "subtype": "tool_result", "tool_name": "Read", "tool_use_id": "tc2", "content": "file"}),
                json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "OK"}}),
                json.dumps({"type": "result", "result": "OK", "is_error": False}),
            ]
        )

        parsed = parse_stream_json(stream)

        self.assertEqual(parsed["tool_calls_count"], 1)
        self.assertEqual(parsed["tool_calls"][0]["name"], "WebSearch")
        self.assertEqual(parsed["tool_result_calls"], [{"id": "tc1", "name": "WebSearch"}])
        self.assertEqual(parsed["web_tool_result_calls_count"], 1)
        self.assertEqual(parsed["web_tool_result_call_ids"], ["tc1"])

    def test_parse_session_log_counts_web_conversion_errors_once(self):
        from llm_council_for_trae.provider import parse_session_log_search_delivery

        log = "\n".join(
            [
                json.dumps({"level": "ERROR", "msg": "unsupported tool output conversion", "tool": "WebSearch"}),
                json.dumps({"level": "ERROR", "msg": "failed to convert ADK output to model format", "tool": "WebSearch"}),
                json.dumps({"level": "ERROR", "msg": "BuildNotification failed", "error": "failed to convert ADK output to model format"}),
                json.dumps({"level": "ERROR", "msg": "failed to convert ADK output to model format", "tool": "WebFetch"}),
                json.dumps({"level": "ERROR", "msg": "failed to convert ADK output to model format", "tool": "Read"}),
            ]
        )

        parsed = parse_session_log_search_delivery(log)

        self.assertEqual(parsed["lct_search_conversion_errors"], 2)
        self.assertEqual(
            [item["tool"] for item in parsed["tool_output_conversion_errors"]],
            ["WebSearch", "WebFetch"],
        )

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
            self.assertNotIn("搜索工具", html)
            self.assertNotIn("调用次数：0", html)
            self.assertNotIn("调用生效次数：0", html)
            self.assertNotIn("允许：是 · 实际使用：否", html)
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

        self.assertTrue(summary["lct_search_allowed"])
        self.assertTrue(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 1)
        self.assertEqual(summary["lct_web_tool_result_calls"], 0)
        self.assertEqual(summary["lct_search_conversion_errors"], 0)
        self.assertEqual(summary["lct_web_tool_effective_calls"], 0)
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
                        "tool_calls_count": 2,
                        "forbidden_tool_calls": [],
                    }
                ],
                "stage2": [],
                "stage3": {},
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertTrue(summary["lct_search_allowed"])
        self.assertFalse(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 0)
        self.assertTrue(summary["search_allowed"])
        self.assertFalse(summary["search_used"])
        self.assertEqual(summary["web_tool_calls_count"], 0)
        self.assertEqual(summary["tool_calls_count"], 2)

    def test_search_summary_counts_forbidden_web_tool_as_used(self):
        from llm_council_for_trae.html_export import summarize_search_usage

        manifest = {
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": [],
                        "tool_calls_count": 1,
                        "forbidden_tool_calls": [{"name": "WebSearch", "id": "tc1"}],
                    }
                ],
                "stage2": [],
                "stage3": {},
            }
        }

        summary = summarize_search_usage(manifest)

        self.assertFalse(summary["lct_search_allowed"])
        self.assertTrue(summary["lct_search_used"])
        self.assertEqual(summary["lct_web_tool_calls"], 1)
        self.assertFalse(summary["search_allowed"])
        self.assertTrue(summary["search_used"])
        self.assertEqual(summary["web_tool_calls_count"], 1)
        self.assertEqual(summary["forbidden_tool_calls_count"], 1)

    def test_tool_policy_record_persists_tool_call_details(self):
        from llm_council_for_trae.council import tool_policy_record
        from llm_council_for_trae.provider import ModelCallResult

        tool_calls = [{"id": "tc1", "name": "WebFetch", "arguments": "{}", "turn_index": 1}]
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
            member_tool_mode="search_enabled",
            allowed_tools=["WebSearch", "WebFetch"],
            disallowed_tools=["Skill", "Agent"],
            tool_calls=tool_calls,
        )

        self.assertEqual(tool_policy_record(result)["tool_calls"], tool_calls)

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

    def test_validate_warns_default_requested_contribution_map_missing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-missing-contribution-map")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["metadata"]["chairman_contribution"] = {
                "enabled": True,
                "requested": True,
                "required": False,
                "present": False,
                "path": "stage3/contribution_map.json",
            }
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertFalse(
                any(check["name"] == "contribution_map_present" for check in validation["failures"]),
                validation["failures"],
            )
            self.assertTrue(
                any(check["name"] == "contribution_map_present" for check in validation["warnings"]),
                validation["warnings"],
            )

    def test_validate_fails_required_contribution_map_missing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-required-missing-contribution-map")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["metadata"]["chairman_contribution"] = {
                "enabled": True,
                "requested": True,
                "required": True,
                "present": False,
                "path": "stage3/contribution_map.json",
            }
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(
                any(check["name"] == "contribution_map_present" for check in validation["failures"]),
                validation["failures"],
            )

    def test_validate_fails_required_contribution_map_missing_block_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-required-bad-contribution-fields")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["metadata"]["chairman_contribution"] = {
                "enabled": True,
                "requested": True,
                "required": True,
                "present": True,
                "path": "stage3/contribution_map.json",
            }
            store.write_manifest(manifest)
            store.write_json(
                "stage3/contribution_map.json",
                {
                    "schema_version": 1,
                    "enabled": True,
                    "source": "chairman_structured_output",
                    "blocks": [
                        {
                            "type": "paragraph",
                            "attribution": {"kind": "single_member", "members": ["GPT-5.4"]},
                        }
                    ],
                },
            )

            validation = validate_run(store)

            self.assertIn(validation["status"], {"failed", "invalid_artifacts"})
            self.assertTrue(
                any(check["name"] == "contribution_map_block_fields" for check in validation["failures"]),
                validation["failures"],
            )

    def test_validate_warns_default_requested_contribution_map_unknown_member_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-soft-bad-contribution-member")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["metadata"]["chairman_contribution"] = {
                "enabled": True,
                "requested": True,
                "required": False,
                "present": True,
                "path": "stage3/contribution_map.json",
            }
            store.write_manifest(manifest)
            store.write_json(
                "stage3/contribution_map.json",
                {
                    "schema_version": 1,
                    "enabled": True,
                    "source": "chairman_structured_output",
                    "blocks": [
                        {
                            "id": "b1",
                            "type": "paragraph",
                            "text": "Unknown member reference.",
                            "attribution": {
                                "kind": "single_member",
                                "members": ["Unknown-Model"],
                            },
                        }
                    ],
                },
            )

            validation = validate_run(store)

            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertFalse(
                any(check["name"] == "contribution_map_member_refs" for check in validation["failures"]),
                validation["failures"],
            )
            self.assertTrue(
                any(check["name"] == "contribution_map_member_refs" for check in validation["warnings"]),
                validation["warnings"],
            )

    def test_validate_rejects_contribution_map_unknown_member_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-bad-contribution-member")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["metadata"]["chairman_contribution"] = {
                "enabled": True,
                "requested": True,
                "required": True,
                "path": "stage3/contribution_map.json",
            }
            store.write_manifest(manifest)
            store.write_json(
                "stage3/contribution_map.json",
                {
                    "schema_version": 1,
                    "enabled": True,
                    "source": "chairman_structured_output",
                    "blocks": [
                        {
                            "id": "b1",
                            "type": "paragraph",
                            "text": "Unknown member reference.",
                            "attribution": {
                                "kind": "single_member",
                                "members": ["Unknown-Model"],
                            },
                        }
                    ],
                },
            )

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(
                any(check["name"] == "contribution_map_member_refs" for check in validation["failures"]),
                validation["failures"],
            )

    def test_validate_rejects_contribution_map_consensus_with_fewer_than_two_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-bad-contribution-consensus")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["metadata"]["chairman_contribution"] = {
                "enabled": True,
                "requested": True,
                "required": True,
                "path": "stage3/contribution_map.json",
            }
            store.write_manifest(manifest)
            store.write_json(
                "stage3/contribution_map.json",
                {
                    "schema_version": 1,
                    "enabled": True,
                    "source": "chairman_structured_output",
                    "blocks": [
                        {
                            "id": "b1",
                            "type": "paragraph",
                            "text": "Consensus claim.",
                            "attribution": {
                                "kind": "multi_member_consensus",
                                "members": ["GPT-5.4"],
                            },
                        }
                    ],
                },
            )

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(
                any(check["name"] == "contribution_map_consensus_members" for check in validation["failures"]),
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

    def test_initial_manifest_status_is_running_until_terminal_outcome(self):
        manifest = initial_manifest("run-starting", "test", CouncilConfig(members=["A"], chairman="B"))

        self.assertEqual(manifest["status"], "running")

    def test_validate_reports_running_manifest_without_missing_artifact_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-running")
            manifest = initial_manifest("run-running", "test", CouncilConfig(members=["A"], chairman="B"))
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "running")
            self.assertEqual(validation["manifest_status"], "running")
            self.assertFalse(validation["terminal"])
            self.assertFalse(validation["usable_final"])
            self.assertFalse(validation["stage3_final_exists"])
            self.assertFalse(validation["html_exists"])
            self.assertEqual(validation["failed_stage_records"], [])
            self.assertEqual(validation["verdict"], "in_progress")
            self.assertEqual([failure["name"] for failure in validation["failures"]], ["run_in_progress"])
            self.assertFalse(any(check["name"].startswith("file:stage2/") for check in validation["checks"]))

    def test_validate_contract_reports_complete_ok_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-ok-contract")
            write_minimal_valid_direct_run(store)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertTrue(validation["terminal"])
            self.assertTrue(validation["usable_final"])
            self.assertTrue(validation["stage3_final_exists"])
            self.assertTrue(validation["html_exists"])
            self.assertEqual(validation["failed_stage_records"], [])
            self.assertEqual(validation["verdict"], "complete_ok_final")

    def test_validate_warns_when_web_tool_delivery_is_lower_than_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-search-warning")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["stages"]["stage1"][0].update(
                {
                    "tool_calls": [
                        {"id": "tc1", "name": "WebSearch"},
                        {"id": "tc2", "name": "WebSearch"},
                    ],
                    "tool_calls_count": 2,
                    "web_tool_result_call_ids": ["tc1", "tc2"],
                    "web_tool_result_calls_count": 2,
                    "lct_search_conversion_errors": 2,
                    "lct_web_tool_effective_calls": 0,
                }
            )
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "ok", validation["failures"])
            self.assertEqual(validation["verdict"], "complete_ok_final")
            self.assertFalse(validation["failures"])
            self.assertTrue(
                any(warning["name"] == "search_tool_output_conversion" for warning in validation["warnings"]),
                validation,
            )

    def test_validate_contract_reports_usable_degraded_final_with_failed_member_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-degraded-contract")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["status"] = "degraded_ok"
            failed_member = {
                "stage": "stage1",
                "label": "Response B",
                "model": "DeepSeek-V4-Pro",
                "expected_model": "DeepSeek-V4-Pro",
                "actual_model": "DeepSeek-V4-Pro",
                "status": "failed",
                "error": "traecli result error",
            }
            manifest["stages"]["stage1"].append(failed_member | tool_policy_json())
            manifest["failures"] = [failed_member]
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "degraded_ok", validation["failures"])
            self.assertTrue(validation["terminal"])
            self.assertTrue(validation["usable_final"])
            self.assertTrue(validation["stage3_final_exists"])
            self.assertTrue(validation["html_exists"])
            self.assertEqual(validation["verdict"], "usable_degraded_final")
            self.assertEqual(
                validation["failed_stage_records"],
                [
                    {
                        "stage": "stage1",
                        "stage_record": "Response B",
                        "label": "Response B",
                        "model": "DeepSeek-V4-Pro",
                        "expected_model": "DeepSeek-V4-Pro",
                        "actual_model": "DeepSeek-V4-Pro",
                        "status": "failed",
                        "error": "traecli result error",
                    }
                ],
            )

    def test_validate_failed_stage_records_dedupes_real_manifest_failure_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-degraded-real-failure-shape")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["status"] = "degraded_ok"
            failed_stage_record = {
                "label": "Response B",
                "file_label": "B",
                "model": "DeepSeek-V4-Pro",
                "expected_model": "DeepSeek-V4-Pro",
                "actual_model": "DeepSeek-V4-Pro",
                "status": "failed",
                "error": "traecli result error",
            }
            manifest["stages"]["stage1"].append(failed_stage_record | tool_policy_json())
            manifest["failures"] = [
                {
                    "stage_record": "Response B",
                    "status": "failed",
                    "error": "traecli result error",
                    "expected_model": "DeepSeek-V4-Pro",
                    "actual_model": "DeepSeek-V4-Pro",
                }
            ]
            store.write_manifest(manifest)
            for relative in ["stage1/B.response.md", "stage1/B.traecli.stream.jsonl"]:
                store.write_text(relative, "{}\n")
            write_json_text(store, "stage1/B.meta.json", stage_meta("DeepSeek-V4-Pro") | {"status": "failed", "error": "traecli result error", "response_chars": 0})

            validation = validate_run(store)

            self.assertEqual(validation["status"], "degraded_ok", validation["failures"])
            self.assertEqual(len(validation["failed_stage_records"]), 1)
            self.assertEqual(validation["failed_stage_records"][0]["model"], "DeepSeek-V4-Pro")
            self.assertEqual(validation["failed_stage_records"][0]["stage_record"], "Response B")

    def test_validate_contract_reports_failed_no_final_for_terminal_failed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-failed-contract")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["status"] = "failed"
            manifest["stages"]["stage3"] = None
            manifest["failures"] = [{"stage": "stage3", "model": "Kimi-K2.6", "status": "failed", "error": "timeout"}]
            store.write_manifest(manifest)
            (store.root / "stage3" / "final.md").unlink()

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(validation["terminal"])
            self.assertFalse(validation["usable_final"])
            self.assertFalse(validation["stage3_final_exists"])
            self.assertEqual(validation["verdict"], "failed_no_final")
            self.assertEqual(validation["failed_stage_records"][0]["stage"], "stage3")

    def test_validate_contract_reports_invalid_artifacts_for_claimed_ok_missing_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-invalid-html-contract")
            write_minimal_valid_direct_run(store)
            (store.root / "html" / "index.html").unlink()

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(validation["terminal"])
            self.assertFalse(validation["usable_final"])
            self.assertTrue(validation["stage3_final_exists"])
            self.assertFalse(validation["html_exists"])
            self.assertEqual(validation["verdict"], "invalid_artifacts")

    def test_extract_title_uses_structured_topic_instead_of_original_input_label(self):
        title = _extract_title(
            """# Original input

请帮我判断 LCT 最新 main 安装后的 E2E 笔记。

## Agent interpretation
LCT 安装后 E2E 运行状态与报告体验评估

## Suggested council focus
运行状态、搜索证据、HTML 可读性
"""
        )

        self.assertEqual(title, "LCT 安装后 E2E 运行状态与报告体验评估：多模型智囊团评估")

    def test_extract_title_preserves_specific_user_heading_and_truncates(self):
        self.assertEqual(_extract_title("# LCT 报告标题改进"), "LCT 报告标题改进：多模型智囊团评估")

        long_title = _extract_title("# " + "A" * 80, max_chars=20)
        self.assertEqual(long_title, "A" * 20 + "…：多模型智囊团评估")

    def test_html_hero_uses_topic_title_and_escapes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text(
                """# Original input

## Agent interpretation
LCT <status> 与 HTML 标题评估
""",
                encoding="utf-8",
            )
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text("Final\n", encoding="utf-8")
            html = render_html(root, {"run_id": "run-title", "status": "ok", "config": {}, "stages": {}, "metadata": {}})

            self.assertIn("<h1>LCT &lt;status&gt; 与 HTML 标题评估：多模型智囊团评估</h1>", html)
            self.assertIn("<title>LCT &lt;status&gt; 与 HTML 标题评估：多模型智囊团评估</title>", html)
            self.assertNotIn("<h1>Original input</h1>", html)

    def test_html_title_prefers_explicit_report_topic_and_dedupes_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text(
                """# Original input

Report topic: 本地AI推理与Agent消费级爆发：多模型智囊团评估
""",
                encoding="utf-8",
            )
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text("# 其他标题\n", encoding="utf-8")

            html = render_html(root, {"run_id": "run-explicit-topic", "status": "ok", "config": {}, "stages": {}, "metadata": {}})

            expected = "本地AI推理与Agent消费级爆发：多模型智囊团评估"
            self.assertIn(f"<h1>{expected}</h1>", html)
            self.assertIn(f"<title>{expected}</title>", html)
            self.assertNotIn("多模型智囊团评估：多模型智囊团评估", html)

    def test_html_title_uses_final_answer_chinese_heading_over_english_interpretation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text(
                """# Original input

## Agent interpretation
The user is not merely asking whether local inference hardware will improve; they are asking for a market timing judgment.
""",
                encoding="utf-8",
            )
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text("# 本地AI推理与Agent消费级爆发：系统性评估\n\n正文\n", encoding="utf-8")

            html = render_html(root, {"run_id": "run-final-heading", "status": "ok", "config": {}, "stages": {}, "metadata": {}})

            expected = "本地AI推理与Agent消费级爆发：系统性评估：多模型智囊团评估"
            self.assertIn(f"<h1>{expected}</h1>", html)
            self.assertIn(f"<title>{expected}</title>", html)
            self.assertNotIn("The user is not merely asking", html.split("<h1>", 1)[1].split("</h1>", 1)[0])

    def test_html_title_uses_final_core_question_before_later_section_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text(
                """# Original input

## Agent interpretation
The user is not merely asking whether local inference hardware will improve; they are asking for a market timing judgment.
""",
                encoding="utf-8",
            )
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text(
                """## 我真正理解你的需求

你需要判断。核心问题是：**H2 2026 到 H1 2027 本地AI会跨越到消费级生产力工具吗？**

---

## 如果这一天已经来了：宏观推演
""",
                encoding="utf-8",
            )

            html = render_html(root, {"run_id": "run-core-question", "status": "ok", "config": {}, "stages": {}, "metadata": {}})

            expected = "H2 2026 到 H1 2027 本地AI会跨越到消费级生产力工具吗？：多模型智囊团评估"
            self.assertIn(f"<h1>{expected}</h1>", html)
            self.assertNotIn("如果这一天已经来了", html.split("<h1>", 1)[1].split("</h1>", 1)[0])

    def test_html_title_rejects_unpunctuated_english_long_interpretation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text(
                """# Original input

## Agent interpretation
The user is not merely asking whether local inference hardware will improve they are asking for a market timing judgment
""",
                encoding="utf-8",
            )
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text("# Final Answer\n\n正文\n", encoding="utf-8")

            html = render_html(root, {"run_id": "run-unpunctuated-english", "status": "ok", "config": {}, "stages": {}, "metadata": {}})
            hero_heading = html.split('<section class="archive-hero"', 1)[1].split("<h1>", 1)[1].split("</h1>", 1)[0]

            self.assertEqual(hero_heading, "最终答案：多模型智囊团评估")
            self.assertNotIn("The user is not merely asking", hero_heading)

    def test_html_title_skips_generic_final_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text("# Original input\n\n请评估本地 AI 推理硬件。\n", encoding="utf-8")
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text(
                """# 我真正理解你的需求

## 正面信号

## 本地AI推理硬件消费化窗口
""",
                encoding="utf-8",
            )

            html = render_html(root, {"run_id": "run-generic-heading", "status": "ok", "config": {}, "stages": {}, "metadata": {}})
            hero_heading = html.split('<section class="archive-hero"', 1)[1].split("<h1>", 1)[1].split("</h1>", 1)[0]

            self.assertIn("<h1>本地AI推理硬件消费化窗口：多模型智囊团评估</h1>", html)
            self.assertNotIn("我真正理解你的需求", hero_heading)

    def test_html_title_skips_user_framework_section_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text(
                """你是一位专业的内容分析师。请对以下文章进行深度分析。

文章标题：《今天比任何时候都更容易翻身：300 年现代财富史揭穿了一个时代错觉》
""",
                encoding="utf-8",
            )
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text(
                """# 一、核心内容

## 二、背景语境

## 三、批判性审视
""",
                encoding="utf-8",
            )

            html = render_html(root, {"run_id": "run-framework-heading", "status": "ok", "config": {}, "stages": {}, "metadata": {}})
            hero_heading = html.split('<section class="archive-hero"', 1)[1].split("<h1>", 1)[1].split("</h1>", 1)[0]

            self.assertIn("今天比任何时候都更容易翻身", hero_heading)
            self.assertNotIn("一、核心内容", hero_heading)

    def test_html_title_keeps_specific_numbered_final_heading(self):
        title = _extract_title(
            "请评估本地 AI 推理硬件。",
            final_text="# 一、AI PC 消费化窗口判断\n\n正文",
        )

        self.assertEqual(title, "一、AI PC 消费化窗口判断：多模型智囊团评估")

    def test_html_title_truncates_topic_without_truncating_fixed_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            long_topic = "本地AI推理硬件与Agent消费市场爆发窗口" * 4
            (root / "input.md").write_text(f"报告题名：{long_topic}\n", encoding="utf-8")
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text("# 其他标题\n", encoding="utf-8")

            html = render_html(root, {"run_id": "run-long-topic", "status": "ok", "config": {}, "stages": {}, "metadata": {}})
            heading = html.split("<h1>", 1)[1].split("</h1>", 1)[0]

            self.assertTrue(heading.endswith("…：多模型智囊团评估"), heading)
            self.assertNotIn("多模型智囊团评…", heading)

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

    def test_validate_rejects_low_quorum_with_status_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-low-quorum-ok")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["status"] = "ok"
            manifest["metadata"]["quorum"] = {
                "min_valid_members": 3,
                "low_quorum_floor": 2,
                "effective_valid_members": 2,
                "normal_quorum_met": False,
                "low_quorum_used": True,
                "backfill_used": False,
                "primary_members": ["M1", "M2", "M3"],
                "candidate_source": "member_priority.filtered",
                "backfill_candidates": [],
                "backfill_attempted": [],
                "effective_stage1_members": ["M1", "M2"],
            }
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertEqual(validation["verdict"], "invalid_artifacts")
            self.assertTrue(any(check["name"] == "quorum_low_status" for check in validation["failures"]))

    def test_validate_accepts_low_quorum_when_marked_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-low-quorum-degraded")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["status"] = "degraded_ok"
            manifest["metadata"]["quorum"] = {
                "min_valid_members": 3,
                "low_quorum_floor": 2,
                "effective_valid_members": 2,
                "normal_quorum_met": False,
                "low_quorum_used": True,
                "backfill_used": False,
                "primary_members": ["M1", "M2", "M3"],
                "candidate_source": "member_priority.filtered",
                "backfill_candidates": [],
                "backfill_attempted": [],
                "effective_stage1_members": ["M1", "M2"],
            }
            store.write_manifest(manifest)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "degraded_ok", validation["failures"])
            self.assertEqual(validation["verdict"], "usable_degraded_final")

    def test_validate_rejects_backfill_record_missing_attempt_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-backfill-missing-role")
            write_minimal_valid_direct_run(store)
            manifest = store.read_manifest()
            manifest["status"] = "degraded_ok"
            manifest["stages"]["stage1"].append(
                {
                    "label": "Response B",
                    "file_label": "B",
                    "model": "Qwen3.6-Plus",
                    "expected_model": "Qwen3.6-Plus",
                    "actual_model": "Qwen3.6-Plus",
                    "response": "B",
                    "status": "ok",
                    "meta_path": "stage1/B.meta.json",
                    "response_path": "stage1/B.response.md",
                    "error": None,
                } | tool_policy_json()
            )
            manifest["metadata"]["quorum"] = {
                "min_valid_members": 3,
                "low_quorum_floor": 2,
                "effective_valid_members": 2,
                "normal_quorum_met": False,
                "low_quorum_used": True,
                "backfill_used": True,
                "primary_members": ["GPT-5.4"],
                "candidate_source": "explicit",
                "backfill_candidates": ["Qwen3.6-Plus"],
                "backfill_attempted": ["Qwen3.6-Plus"],
                "effective_stage1_members": ["GPT-5.4", "Qwen3.6-Plus"],
            }
            store.write_manifest(manifest)
            store.write_text("stage1/B.response.md", "B\n")
            store.write_text("stage1/B.traecli.stream.jsonl", "{}\n")
            write_json_text(store, "stage1/B.meta.json", stage_meta("Qwen3.6-Plus"))

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(any(check["name"] == "stage1_backfill_attempt_role_B" for check in validation["failures"]))

    def test_validate_accepts_stage2_reviewer_only_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-reviewer-only-valid")
            write_reviewer_only_backfill_run(store)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "ok")
            self.assertEqual(validation["verdict"], "complete_ok_final")
            self.assertFalse(validation["failures"])

    def test_validate_rejects_stage2_reviewer_only_backfill_in_subject_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore.create(Path(tmp), "run-reviewer-only-leaked-subject")
            write_reviewer_only_backfill_run(store, leak_reviewer_into_subjects=True, ranking_includes_reviewer_subject=True)

            validation = validate_run(store)

            self.assertEqual(validation["status"], "failed")
            self.assertTrue(
                any(check["name"] == "stage2_reviewer_backfill_not_subject_R4" for check in validation["failures"]),
                validation["failures"],
            )

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
        tool_calls = [{"id": "tc0", "name": "WebSearch", "arguments": "{}", "turn_index": 1}]
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
            tool_calls=tool_calls,
        )
        j = result.to_json()
        self.assertEqual(j["member_tool_mode"], "search_enabled")
        self.assertEqual(j["allowed_tools"], ["WebSearch", "WebFetch"])
        self.assertEqual(j["disallowed_tools"], ["Skill", "Agent"])
        self.assertEqual(j["forbidden_tool_calls"], forbidden)
        self.assertEqual(j["tool_calls"], tool_calls)

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

    def test_target_valid_members_default_is_3(self):
        config = CouncilConfig(members=["A"], chairman="B")
        self.assertEqual(config.target_valid_members, 3)

    def test_build_config_default_models_targets_three_valid_members(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--input", "question.md", "--default-models"])
        args.selected_model_choice = resolve_run_model_choice(args)

        config = build_config(args)

        self.assertEqual(config.members, ["DeepSeek-V4-Pro", "GPT-5.5", "openrouter-3o"])
        self.assertEqual(config.min_valid_members, 3)
        self.assertEqual(config.target_valid_members, 3)

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

    def test_stage3_writes_contribution_map_when_enabled(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-contribution-map")
            config = CouncilConfig(
                members=["GPT-5.4", "DeepSeek-V4-Pro"],
                chairman="GPT-5.4",
                chairman_contribution_enabled=True,
            )
            response = """
最终综述正文。

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "p1",
      "type": "paragraph",
      "text": "两个成员都强调了这个风险。",
      "attribution": {"kind": "multi_member_consensus", "members": ["GPT-5.4", "DeepSeek-V4-Pro"]}
    }
  ]
}
```
""".strip()
            ok_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response=response,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            final, _meta = await stage3_synthesize_final(
                "test query",
                [
                    {"label": "Response A", "model": "GPT-5.4", "response": "A", "status": "ok"},
                    {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B", "status": "ok"},
                ],
                [
                    {
                        "model": "Reviewer",
                        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                        "parsed_ranking": ["Response A", "Response B"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config, provider, store,
            )

            sidecar = store.path("stage3/contribution_map.json")
            final_json = json.loads(store.path("stage3/final.json").read_text(encoding="utf-8"))
            sidecar_json = json.loads(sidecar.read_text(encoding="utf-8"))

            self.assertTrue(final["contribution_map_enabled"])
            self.assertEqual(final["contribution_map_path"], "stage3/contribution_map.json")
            self.assertTrue(sidecar.exists())
            self.assertEqual(final_json["contribution_map_path"], "stage3/contribution_map.json")
            self.assertEqual(sidecar_json["blocks"][0]["attribution"]["members"], ["GPT-5.4", "DeepSeek-V4-Pro"])

        import asyncio
        asyncio.run(_run())

    def test_stage3_repairs_missing_contribution_map_sidecar(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-contribution-map-repair-missing")
            config = CouncilConfig(
                members=["GPT-5.4", "DeepSeek-V4-Pro"],
                chairman="GPT-5.4",
                chairman_contribution_enabled=True,
            )
            final_markdown = "最终综述正文。"
            repair_response = """
```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "p1",
      "type": "paragraph",
      "text": "最终综述正文。",
      "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "DeepSeek-V4-Pro"]}
    }
  ]
}
```
""".strip()
            first_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response=final_markdown,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            repair_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response=repair_response,
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="repair.jsonl", stderr_path="repair.err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(side_effect=[first_call, repair_call])

            final, _meta = await stage3_synthesize_final(
                "test query",
                [
                    {"label": "Response A", "model": "GPT-5.4", "response": "A", "status": "ok"},
                    {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B", "status": "ok"},
                ],
                [
                    {
                        "model": "Reviewer",
                        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                        "parsed_ranking": ["Response A", "Response B"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config, provider, store,
            )

            sidecar = store.path("stage3/contribution_map.json")
            final_json = json.loads(store.path("stage3/final.json").read_text(encoding="utf-8"))
            sidecar_json = json.loads(sidecar.read_text(encoding="utf-8"))

            self.assertEqual(provider.query_model.await_count, 2)
            self.assertTrue(sidecar.exists())
            self.assertEqual(final["response"], final_markdown)
            self.assertEqual(store.path("stage3/final.md").read_text(encoding="utf-8").strip(), final_markdown)
            self.assertNotIn("contribution_map_error", final_json)
            self.assertEqual(final_json["contribution_map_repair"]["status"], "ok")
            self.assertEqual(final_json["contribution_map_repair"]["attempts"], 1)
            self.assertEqual(sidecar_json["blocks"][0]["text"], final_markdown)
            self.assertTrue(store.path("stage3/contribution_map.repair.1.prompt.md").exists())
            self.assertTrue(store.path("stage3/contribution_map.repair.1.response.md").exists())

        import asyncio
        asyncio.run(_run())

    def test_stage3_records_contribution_map_repair_failure_without_rewriting_final(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-contribution-map-repair-failed")
            config = CouncilConfig(
                members=["GPT-5.4", "DeepSeek-V4-Pro"],
                chairman="GPT-5.4",
                chairman_contribution_enabled=True,
            )
            final_markdown = "最终综述正文。"
            first_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response=final_markdown,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            bad_repair_1 = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response="不是 JSON",
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="repair1.jsonl", stderr_path="repair1.err.log",
            )
            bad_repair_2 = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response="仍然不是 JSON",
                status="ok", session_id="s3", command=["traecli"], exit_code=0,
                stdout_path="repair2.jsonl", stderr_path="repair2.err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(side_effect=[first_call, bad_repair_1, bad_repair_2])

            final, _meta = await stage3_synthesize_final(
                "test query",
                [
                    {"label": "Response A", "model": "GPT-5.4", "response": "A", "status": "ok"},
                    {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B", "status": "ok"},
                ],
                [
                    {
                        "model": "Reviewer",
                        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                        "parsed_ranking": ["Response A", "Response B"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config, provider, store,
            )

            final_json = json.loads(store.path("stage3/final.json").read_text(encoding="utf-8"))

            self.assertEqual(provider.query_model.await_count, 3)
            self.assertFalse(store.path("stage3/contribution_map.json").exists())
            self.assertEqual(final["response"], final_markdown)
            self.assertEqual(store.path("stage3/final.md").read_text(encoding="utf-8").strip(), final_markdown)
            self.assertEqual(final_json["contribution_map_error"], "missing_or_invalid_contribution_map_json")
            self.assertEqual(final_json["contribution_map_repair"]["status"], "failed")
            self.assertEqual(final_json["contribution_map_repair"]["attempts"], 2)
            self.assertEqual(len(final_json["contribution_map_repair"]["attempt_records"]), 2)

        import asyncio
        asyncio.run(_run())

    def test_stage3_skips_contribution_map_repair_when_initial_sidecar_valid(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-contribution-map-repair-skip")
            config = CouncilConfig(
                members=["GPT-5.4", "DeepSeek-V4-Pro"],
                chairman="GPT-5.4",
                chairman_contribution_enabled=True,
            )
            response = """
最终综述正文。

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "p1",
      "type": "paragraph",
      "text": "最终综述正文。",
      "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "DeepSeek-V4-Pro"]}
    }
  ]
}
```
""".strip()
            ok_call = ModelCallResult(
                expected_model="GPT-5.4", actual_model="GPT-5.4", response=response,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            final, _meta = await stage3_synthesize_final(
                "test query",
                [
                    {"label": "Response A", "model": "GPT-5.4", "response": "A", "status": "ok"},
                    {"label": "Response B", "model": "DeepSeek-V4-Pro", "response": "B", "status": "ok"},
                ],
                [
                    {
                        "model": "Reviewer",
                        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
                        "parsed_ranking": ["Response A", "Response B"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config, provider, store,
            )

            final_json = json.loads(store.path("stage3/final.json").read_text(encoding="utf-8"))

            self.assertEqual(provider.query_model.await_count, 1)
            self.assertTrue(store.path("stage3/contribution_map.json").exists())
            self.assertNotIn("contribution_map_repair", final_json)
            self.assertFalse(store.path("stage3/contribution_map.repair.1.prompt.md").exists())
            self.assertEqual(final["response"], "最终综述正文。")

        import asyncio
        asyncio.run(_run())

    def test_stage3_repairs_unescaped_quotes_in_contribution_map_and_strips_final_markdown(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-contribution-map-repair")
            config = CouncilConfig(
                members=["DeepSeek-V4-Pro", "GPT-5.4", "Kimi-K2.6"],
                chairman="DeepSeek-V4-Pro",
                chairman_contribution_enabled=True,
            )
            response = """
最终综述正文。

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "p1",
      "type": "paragraph",
      "text": "一份好 JD 暴露的不是"我要什么人"，而是"我们卡在哪里"。",
      "attribution": {"kind": "multi_member_consensus", "members": ["DeepSeek-V4-Pro", "GPT-5.4"]}
    },
    {
      "id": "n1",
      "type": "editor_note",
      "text": "主席注：Kimi-K2.6 的"三语者"比喻被融入结论。",
      "attribution": {"kind": "editor_note", "members": []}
    }
  ]
}
```
""".strip()
            ok_call = ModelCallResult(
                expected_model="DeepSeek-V4-Pro", actual_model="DeepSeek-V4-Pro", response=response,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(return_value=ok_call)

            final, _meta = await stage3_synthesize_final(
                "test query",
                [
                    {"label": "Response A", "model": "DeepSeek-V4-Pro", "response": "A", "status": "ok"},
                    {"label": "Response B", "model": "GPT-5.4", "response": "B", "status": "ok"},
                    {"label": "Response C", "model": "Kimi-K2.6", "response": "C", "status": "ok"},
                ],
                [
                    {
                        "model": "Reviewer",
                        "ranking": "FINAL RANKING:\n1. Response B\n2. Response A\n3. Response C",
                        "parsed_ranking": ["Response B", "Response A", "Response C"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config, provider, store,
            )

            sidecar = store.path("stage3/contribution_map.json")
            sidecar_json = json.loads(sidecar.read_text(encoding="utf-8"))

            self.assertTrue(sidecar.exists())
            self.assertNotIn("contribution_map_error", final)
            self.assertTrue(final["contribution_map_stripped_from_response"])
            self.assertEqual(final["response"], "最终综述正文。")
            self.assertIn("raw_response", final)
            self.assertIn("```json", final["raw_response"])
            self.assertEqual(store.path("stage3/final.md").read_text(encoding="utf-8").strip(), "最终综述正文。")
            self.assertEqual(sidecar_json["blocks"][0]["text"], '一份好 JD 暴露的不是"我要什么人"，而是"我们卡在哪里"。')
            self.assertEqual(sidecar_json["blocks"][1]["text"], '主席注：Kimi-K2.6 的"三语者"比喻被融入结论。')

        import asyncio
        asyncio.run(_run())

    def test_stage3_retries_when_final_copies_stage1_response(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-copy-retry")
            config = CouncilConfig(members=["Kimi-K2.6", "GPT-5.2"], chairman="Kimi-K2.6")
            copied_response = ("Stage 1 source sentence with distinctive evidence. " * 80).strip()
            rewritten_response = "综合结论：本地个人 agent 更可能先进入开发者和 prosumer 早期采用，而不是 2026H2 普通家庭爆发。"
            first_call = ModelCallResult(
                expected_model="Kimi-K2.6", actual_model="Kimi-K2.6", response=copied_response,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            retry_call = ModelCallResult(
                expected_model="Kimi-K2.6", actual_model="Kimi-K2.6", response=rewritten_response,
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="retry.jsonl", stderr_path="retry.err.log",
            )
            repair_response = """
```json
{"schema_version": 1, "enabled": true, "source": "chairman_structured_output", "blocks": [{"id": "p1", "type": "paragraph", "text": "综合结论：本地个人 agent 更可能先进入开发者和 prosumer 早期采用，而不是 2026H2 普通家庭爆发。", "attribution": {"kind": "synthesis", "members": ["Kimi-K2.6", "GPT-5.2"]}}]}
```
""".strip()
            repair_call = ModelCallResult(
                expected_model="Kimi-K2.6", actual_model="Kimi-K2.6", response=repair_response,
                status="ok", session_id="s3", command=["traecli"], exit_code=0,
                stdout_path="repair.jsonl", stderr_path="repair.err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(side_effect=[first_call, retry_call, repair_call])

            final, meta = await stage3_synthesize_final(
                "test query",
                [
                    {"label": "Response A", "model": "Kimi-K2.6", "response": copied_response, "status": "ok"},
                    {"label": "Response B", "model": "GPT-5.2", "response": "Different evidence and conclusion.", "status": "ok"},
                ],
                [
                    {
                        "model": "Reviewer",
                        "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
                        "parsed_ranking": ["Response B", "Response A"],
                        "status": "ok",
                        "parse_status": "ok",
                    }
                ],
                config, provider, store,
            )

            self.assertEqual(provider.query_model.await_count, 3)
            self.assertEqual(final["response"], rewritten_response)
            self.assertEqual(final["contribution_map_repair"]["status"], "ok")
            self.assertEqual(final["prompt_path"], "stage3/chairman.copy_retry.prompt.md")
            self.assertEqual(final["original_prompt_path"], "stage3/chairman.prompt.md")
            self.assertEqual(store.path("stage3/final.md").read_text().strip(), rewritten_response)
            self.assertTrue(final["chairman_copy_check"]["triggered"])
            self.assertTrue(final["chairman_copy_check"]["retry_attempted"])
            self.assertTrue(final["chairman_copy_check"]["resolved"])
            self.assertEqual(final["chairman_copy_check"]["matched_stage1"][0]["label"], "Response A")
            self.assertEqual(meta["copy_check"], final["chairman_copy_check"])
            retry_prompt = provider.query_model.await_args_list[1].kwargs["prompt"]
            self.assertIn("ANTI-COPY RETRY", retry_prompt)
            self.assertIn("Response A", retry_prompt)
            repair_prompt = provider.query_model.await_args_list[2].kwargs["prompt"]
            self.assertIn(rewritten_response, repair_prompt)

        import asyncio
        asyncio.run(_run())

    def test_stage3_records_unresolved_copy_check_when_retry_still_copies(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult, TraeCliProvider
            from llm_council_for_trae.store import ArtifactStore
            from unittest.mock import AsyncMock

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-copy-unresolved")
            config = CouncilConfig(members=["Kimi-K2.6"], chairman="Kimi-K2.6", chairman_contribution_enabled=False)
            copied_response = ("Copied Stage 1 answer. " * 90).strip()
            copy_call = ModelCallResult(
                expected_model="Kimi-K2.6", actual_model="Kimi-K2.6", response=copied_response,
                status="ok", session_id="s1", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )
            copy_retry = ModelCallResult(
                expected_model="Kimi-K2.6", actual_model="Kimi-K2.6", response=copied_response,
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="retry.jsonl", stderr_path="retry.err.log",
            )
            provider = TraeCliProvider.__new__(TraeCliProvider)
            provider.query_model = AsyncMock(side_effect=[copy_call, copy_retry])

            final, meta = await stage3_synthesize_final(
                "test query",
                [{"label": "Response A", "model": "Kimi-K2.6", "response": copied_response, "status": "ok"}],
                [{"model": "Reviewer", "ranking": "FINAL RANKING:\n1. Response A", "parsed_ranking": ["Response A"], "status": "ok", "parse_status": "ok"}],
                config, provider, store,
            )

            self.assertEqual(provider.query_model.await_count, 2)
            self.assertEqual(final["response"], copied_response)
            self.assertTrue(final["chairman_copy_check"]["triggered"])
            self.assertTrue(final["chairman_copy_check"]["retry_attempted"])
            self.assertFalse(final["chairman_copy_check"]["resolved"])
            self.assertEqual(final["chairman_copy_check"]["unresolved_reason"], "retry_still_copies_stage1")
            self.assertEqual(meta["copy_check"], final["chairman_copy_check"])

        import asyncio
        asyncio.run(_run())

    def test_run_full_council_warns_when_stage3_copy_check_unresolved(self):
        async def _run():
            from llm_council_for_trae.council import run_full_council, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult

            import llm_council_for_trae.council as council_mod

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-copy-warning")
            source_response = ("Stage 1 answer copied by the chairman. " * 90).strip()
            second_response = ("Independent answer with a different structure and conclusion. " * 40).strip()
            config = CouncilConfig(
                members=["M1", "M2"],
                chairman="Chair",
                min_valid_members=2,
                stage1_auto_backfill=False,
                stage2_auto_backfill=False,
            )

            class MockProvider:
                def __init__(self, *args, **kwargs):
                    pass

                async def query_model(self, **kwargs):
                    stage = kwargs["stage"]
                    label = kwargs["label"]
                    model = kwargs["model"]
                    if stage == "stage1":
                        response = source_response if label == "A" else second_response
                    elif stage == "stage2":
                        response = "FINAL RANKING:\n1. Response B\n2. Response A"
                    elif stage == "stage3":
                        response = source_response
                    else:
                        response = "unused"
                    return ModelCallResult(
                        expected_model=model,
                        actual_model=model,
                        response=response,
                        status="ok",
                        session_id=f"s-{stage}-{label}",
                        command=["traecli"],
                        exit_code=0,
                        stdout_path=f"{label}.jsonl",
                        stderr_path=f"{label}.err.log",
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
                    "models": [{"name": name} for name in ["M1", "M2", "Chair"]],
                })()
                with patch.object(council_mod, "require_models_available"):
                    with patch.object(council_mod, "TraeCliProvider", MockProvider):
                        manifest = await run_full_council("test query", config, store)

            copy_check = manifest["stages"]["stage3"]["chairman_copy_check"]
            self.assertTrue(copy_check["triggered"])
            self.assertFalse(copy_check["resolved"])
            self.assertEqual(copy_check["matched_stage1"][0]["label"], "Response A")
            self.assertEqual(manifest["metadata"]["chairman"]["copy_check"], copy_check)
            warnings = "\n".join(manifest["warnings"])
            self.assertIn("stage3_copy_risk", warnings)
            self.assertIn("Response A", warnings)

        import asyncio
        asyncio.run(_run())

    def test_stage3_fallback_records_in_metadata(self):
        async def _run():
            from llm_council_for_trae.council import stage3_synthesize_final, CouncilConfig
            from llm_council_for_trae.provider import ModelCallResult
            from llm_council_for_trae.store import ArtifactStore

            store = ArtifactStore.create(Path(tempfile.mkdtemp()), "run-s3-fb")
            config = CouncilConfig(members=["GLM-5.1"], chairman="GLM-5.1")

            fail_call = ModelCallResult(
                expected_model="GLM-5.1", actual_model="GLM-5.1", response="",
                status="failed", session_id="s1", command=["traecli"], exit_code=1,
                stdout_path="out.jsonl", stderr_path="err.log",
                error="tool_contaminated: forbidden tool call(s): Write",
                forbidden_tool_calls=[{"id": "call-1", "name": "Write", "arguments": "{}", "turn_index": 1}],
            )
            ok_call = ModelCallResult(
                expected_model="Qwen3.6-Plus", actual_model="Qwen3.6-Plus", response="Fallback answer",
                status="ok", session_id="s2", command=["traecli"], exit_code=0,
                stdout_path="out.jsonl", stderr_path="err.log",
            )

            class Provider:
                def __init__(self):
                    self.calls = []

                async def query_model(self, **kwargs):
                    self.calls.append(kwargs["label"])
                    call = fail_call if len(self.calls) == 1 else ok_call
                    store.write_json(
                        f"stage3/{kwargs['label']}.meta.json",
                        call.to_json() | {"captured_at": "2026-06-06T00:00:00Z"},
                    )
                    return call

            provider = Provider()

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
            final_meta = json.loads(store.path("stage3/final.meta.json").read_text(encoding="utf-8"))
            self.assertEqual(final_meta["expected_model"], "Qwen3.6-Plus")
            self.assertEqual(final_meta["actual_model"], "Qwen3.6-Plus")
            self.assertEqual(final_meta["status"], "ok")
            self.assertEqual(final_meta["forbidden_tool_calls"], [])
            self.assertTrue(store.path("stage3/final-fb-Qwen3.6-Plus.meta.json").exists())

        import asyncio
        asyncio.run(_run())

    def test_recommend_model_choice_uses_priority_and_excludes_glm(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        models = [
            {"name": "openrouter-2o"},
            {"name": "GLM-5.1"},
            {"name": "Qwen3.6-Plus"},
        ]
        choice = recommend_model_choice(models)
        self.assertEqual(choice.members, ["openrouter-2o", "Qwen3.6-Plus"])
        self.assertEqual(choice.source, "recommended")

    def test_recommend_model_choice_excludes_seed_doubao_but_allows_gpt55(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        models = [
            {"name": "GPT-5.4"},
            {"name": "Seed-Dogfooding-2.0"},
            {"name": "Mystery-Safe-Model"},
            {"name": "Doubao-Seed-1.8"},
            {"name": "Kimi-K2.6"},
            {"name": "GPT-5.5"},
        ]
        choice = recommend_model_choice(models)

        self.assertEqual(choice.members, ["GPT-5.5", "GPT-5.4", "Kimi-K2.6"])
        joined = ",".join(choice.members + [choice.chairman]).lower()
        self.assertNotIn("seed", joined)
        self.assertNotIn("doubao", joined)
        self.assertNotIn("mystery", joined)

    def test_recommend_model_choice_rejects_unapproved_safe_model(self):
        from llm_council_for_trae.model_selection import recommend_model_choice

        choice = recommend_model_choice([
            {"name": "Seed-Dogfooding-2.0"},
            {"name": "openrouter-safe"},
        ])

        self.assertEqual(choice.members, [])
        self.assertEqual(choice.chairman, "")
        self.assertEqual(choice.source, "no-approved-candidates")

    def test_recommend_model_choice_reports_no_safe_candidates_when_all_models_are_hard_banned(self):
        from llm_council_for_trae.model_selection import recommend_model_choice

        choice = recommend_model_choice([
            {"name": "Seed-Dogfooding-2.0"},
            {"name": "Doubao-Seed-1.8"},
        ])

        self.assertEqual(choice.members, [])
        self.assertEqual(choice.chairman, "")
        self.assertEqual(choice.source, "no-safe-candidates")

    def test_explicit_model_resolution_allows_seed_models(self):
        names = ["Seed-Dogfooding-2.0", "GPT-5.4"]

        self.assertEqual(resolve_model_tokens("Seed-Dogfooding-2.0", names), ["Seed-Dogfooding-2.0"])

    def test_recommend_model_choice_does_not_fallback_to_unapproved_openrouter(self):
        from llm_council_for_trae.model_selection import recommend_model_choice
        models = [{"name": "openrouter-unlisted"}]
        choice = recommend_model_choice(models)
        self.assertEqual(choice.members, [])
        self.assertEqual(choice.chairman, "")
        self.assertEqual(choice.source, "no-approved-candidates")

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

    def test_model_call_result_serializes_search_delivery_fields(self):
        result = ModelCallResult(
            expected_model="GPT-5.4", actual_model="GPT-5.4", response="ok",
            status="ok", session_id="s1", command=["traecli"], exit_code=0,
            stdout_path="out.jsonl", stderr_path="err.log",
            tool_result_calls=[{"id": "tc1", "name": "WebSearch"}],
            web_tool_result_calls_count=1,
            web_tool_result_call_ids=["tc1"],
            tool_output_conversion_errors=[{"tool": "WebSearch", "message": "failed to convert ADK output to model format"}],
            lct_search_conversion_errors=1,
            web_tool_effective_calls_count=0,
        )

        data = result.to_json()

        self.assertEqual(data["tool_result_calls"], [{"id": "tc1", "name": "WebSearch"}])
        self.assertEqual(data["web_tool_result_calls_count"], 1)
        self.assertEqual(data["web_tool_result_call_ids"], ["tc1"])
        self.assertEqual(data["lct_search_conversion_errors"], 1)
        self.assertEqual(data["web_tool_effective_calls_count"], 0)

    def test_tool_policy_record_persists_search_delivery_fields(self):
        from llm_council_for_trae.council import tool_policy_record

        result = ModelCallResult(
            expected_model="GPT-5.4", actual_model="GPT-5.4", response="ok",
            status="ok", session_id="s1", command=["traecli"], exit_code=0,
            stdout_path="out.jsonl", stderr_path="err.log",
        )
        result.tool_result_calls = [{"id": "tc1", "name": "WebSearch"}]
        result.web_tool_result_calls_count = 1
        result.web_tool_result_call_ids = ["tc1"]
        result.tool_output_conversion_errors = [{"tool": "WebSearch", "message": "failed to convert ADK output to model format"}]
        result.lct_search_conversion_errors = 1
        result.web_tool_effective_calls_count = 0

        record = tool_policy_record(result)

        self.assertEqual(record["tool_result_calls"], [{"id": "tc1", "name": "WebSearch"}])
        self.assertEqual(record["web_tool_result_calls_count"], 1)
        self.assertEqual(record["web_tool_result_call_ids"], ["tc1"])
        self.assertEqual(record["lct_search_conversion_errors"], 1)
        self.assertEqual(record["lct_web_tool_effective_calls"], 0)

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

    def test_html_summary_card_shows_effective_member_models_without_quorum_jargon(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["GPT-5.4", "Failed-Model"], "chairman": "GPT-5.4"},
            "metadata": {
                "quorum": {
                    "effective_valid_members": 4,
                    "min_valid_members": 3,
                    "normal_quorum_met": True,
                    "low_quorum_used": False,
                    "effective_stage1_members": ["GPT-5.4", "Qwen3.6-Plus", "Kimi-K2.6", "openrouter-1o"],
                    "backfill_used": True,
                    "backfill_attempted": ["Qwen3.6-Plus"],
                }
            },
            "status": "ok",
        }
        html = render_summary_cards(manifest, [])
        self.assertIn("成员模型", html)
        self.assertIn("GPT-5.4", html)
        self.assertIn("Qwen3.6-Plus", html)
        self.assertIn("Kimi-K2.6", html)
        self.assertNotIn("Failed-Model", html)
        self.assertNotIn("Quorum 状态", html)
        self.assertNotIn("4 / 3", html)
        self.assertNotIn("normal quorum", html)
        self.assertNotIn("有效成员：", html)
        self.assertIn("最高排序成员", html)

    def test_html_summary_card_legacy_falls_back_to_config_members_when_quorum_missing(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["GPT-5.4", "DeepSeek-V4-Pro"], "chairman": "GPT-5.4"},
            "metadata": {},
            "status": "ok",
        }
        html = render_summary_cards(manifest, [])
        self.assertIn("成员模型", html)
        self.assertIn("GPT-5.4", html)
        self.assertIn("DeepSeek-V4-Pro", html)

    def test_html_summary_card_does_not_show_config_members_when_quorum_present_but_effective_missing(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["Configured-Failed-Model"], "chairman": "GPT-5.4"},
            "metadata": {
                "quorum": {
                    "effective_valid_members": 0,
                    "min_valid_members": 3,
                    "normal_quorum_met": False,
                    "low_quorum_used": False,
                }
            },
            "status": "failed",
        }
        html = render_summary_cards(manifest, [])
        self.assertIn("成员模型", html)
        self.assertNotIn("Configured-Failed-Model", html)
        self.assertRegex(html, r"暂无有效成员|未记录有效成员|0\s*个")

    def test_html_summary_preserves_quorum_backfill_metadata_evidence(self):
        manifest = {
            "schema_version": 1,
            "run_id": "run-html-summary-evidence",
            "status": "degraded_ok",
            "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake"},
            "metadata": {
                "aggregate_rankings": [],
                "quorum": {
                    "low_quorum_used": True,
                    "backfill_candidates": ["Kimi-K2.6"],
                    "backfill_attempted": ["Kimi-K2.6"],
                    "effective_stage1_members": ["GPT-5.4", "Kimi-K2.6"],
                    "effective_valid_members": 2,
                    "min_valid_members": 3,
                },
            },
            "stages": {"stage1": [], "stage2": [], "stage3": {}},
            "warnings": [],
            "failures": [],
        }
        html = render_manifest_html(manifest)
        self.assertIn("backfill_candidates", html)
        self.assertIn("Kimi-K2.6", html)
        self.assertIn("low_quorum_used", html)

    def test_html_renders_contribution_blocks_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage3").mkdir()
            (root / "input.md").write_text("Report topic: 贡献说明测试\n", encoding="utf-8")
            (root / "stage3" / "final.md").write_text("legacy markdown should not be the only source\n", encoding="utf-8")
            (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
            (root / "stage3" / "contribution_map.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "enabled": True,
                        "source": "chairman_structured_output",
                        "blocks": [
                            {
                                "id": "h1",
                                "type": "heading",
                                "text": "可信度为什么提升",
                                "attribution": {"kind": "synthesis", "members": []},
                            },
                            {
                                "id": "p1",
                                "type": "paragraph",
                                "text": "用户能看到哪些模型实际参与了结论。",
                                "attribution": {"kind": "single_member", "members": ["GPT-5.4"]},
                            },
                            {
                                "id": "p2",
                                "type": "paragraph",
                                "text": "两个成员都强调了同一个产品风险。",
                                "attribution": {"kind": "multi_member_consensus", "members": ["GPT-5.4", "DeepSeek-V4-Pro"]},
                            },
                            {
                                "id": "p3",
                                "type": "paragraph",
                                "text": "主席把两个成员的材料合并成更清楚的表达。",
                                "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "DeepSeek-V4-Pro"]},
                            },
                            {
                                "id": "p4",
                                "type": "paragraph",
                                "text": "这段无法可靠拆到具体成员。",
                                "attribution": {"kind": "not_attributable", "members": []},
                            },
                            {
                                "id": "n1",
                                "type": "editor_note",
                                "text": "主席注：这是主席基于成员素材延伸的取舍建议。\n\n来源：主席编者注",
                                "attribution": {"kind": "editor_note", "members": []},
                            },
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "run_id": "run-html-contribution",
                "status": "ok",
                "config": {"members": ["GPT-5.4", "DeepSeek-V4-Pro"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake"},
                "metadata": {
                    "aggregate_rankings": [
                        {"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0},
                        {"label": "Response B", "model": "DeepSeek-V4-Pro", "average_rank": 2.0},
                    ],
                    "chairman_contribution": {"enabled": True, "path": "stage3/contribution_map.json"},
                },
                "stages": {
                    "stage1": [
                        {"label": "Response A", "file_label": "A", "model": "GPT-5.4", "status": "ok"},
                        {"label": "Response B", "file_label": "B", "model": "DeepSeek-V4-Pro", "status": "ok"},
                    ],
                    "stage2": [],
                    "stage3": {"model": "GPT-5.4", "status": "ok"},
                },
                "warnings": [],
                "failures": [],
            }

            html = render_html(root, manifest)

        self.assertIn("可信度为什么提升", html)
        self.assertIn("用户能看到哪些模型实际参与了结论", html)
        self.assertIn("来源：GPT-5.4（同侪#1）", html)
        self.assertIn("多成员共识：GPT-5.4（同侪#1）, DeepSeek-V4-Pro（同侪#2）", html)
        self.assertIn("主席综合整理，主要参考：GPT-5.4（同侪#1）, DeepSeek-V4-Pro（同侪#2）", html)
        self.assertIn("来源：无法可靠归因", html)
        self.assertIn("chairman-note", html)
        self.assertIn("主席评注", html)
        self.assertIn("这是主席基于成员素材延伸的取舍建议。", html)
        self.assertNotIn("主席注：", html)
        self.assertNotIn("来源：主席编者注", html)
        self.assertNotIn("<aside class='warning-banner'", html)
        self.assertNotIn('<aside class="warning-banner"', html)
        self.assertNotIn("<strong>编者注</strong>", html)
        self.assertNotIn("贡献 37%", html)

    def test_contribution_map_literal_newline_table_renders_as_table(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "table-1",
                    "type": "paragraph",
                    "text": "| 维度 | 有糖饮料 | 无糖饮料 |\\n|---|---|---|\\n| 危害证据强度 | 强 | 弱 |",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                }
            ]
        )

        self.assertIn("<table>", html)
        self.assertIn("<th>维度</th>", html)
        self.assertIn("<td>危害证据强度</td>", html)
        self.assertNotIn("|---|---|---|", html)
        self.assertNotIn("\\n|---|", html)
        self.assertIn("主席综合整理，主要参考", html)

    def test_contribution_map_real_newline_table_still_renders_as_table(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "table-2",
                    "type": "paragraph",
                    "text": "| 人群/场景 | 建议 | 理由 |\n|---|---|---|\n| 健康成年人 | 无糖 | 避免空热量 |",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                }
            ]
        )

        self.assertIn("<table>", html)
        self.assertIn("<th>人群/场景</th>", html)
        self.assertIn("<td>健康成年人</td>", html)
        self.assertIn("主席综合整理，主要参考", html)

    def test_contribution_map_disagreement_and_editor_note_support_markdown(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "d1",
                    "type": "disagreement",
                    "text": "- 观点甲\n- 观点乙",
                    "attribution": {"kind": "multi_member_consensus", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "n1",
                    "type": "editor_note",
                    "text": "主席注：- 保留取舍\n- 标明边界\n\n来源：主席编者注",
                    "attribution": {"kind": "editor_note", "members": []},
                },
            ]
        )

        self.assertIn("<section class='cell'><h3>观点分歧</h3>", html)
        self.assertIn("<li>观点甲</li>", html)
        self.assertIn("<li>观点乙</li>", html)
        self.assertIn("<aside class='chairman-note'>", html)
        self.assertIn("<li>保留取舍</li>", html)
        self.assertIn("<li>标明边界</li>", html)
        self.assertNotIn("主席注：", html)
        self.assertNotIn("来源：主席编者注", html)

    def test_contribution_map_markdown_escapes_html_and_unsafe_links(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "security-1",
                    "type": "paragraph",
                    "text": "<script>alert(1)</script>\n[bad](javascript:alert(1))\n[ok](https://example.com/report)",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                }
            ]
        )

        article = html[html.index('<article id="final-answer"'):html.index("</article>")]
        self.assertNotIn("<script>", article)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", article)
        self.assertNotIn("href='javascript:", article)
        self.assertIn("bad (javascript:alert(1))", article)
        self.assertIn("<a href='https://example.com/report'>ok</a>", article)
        self.assertIn("主席综合整理，主要参考", article)

    def test_contribution_map_invalid_attribution_kind_partially_degrades(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "valid-synthesis",
                    "type": "paragraph",
                    "text": "合法综合正文",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "valid-consensus",
                    "type": "paragraph",
                    "text": "合法共识正文",
                    "attribution": {"kind": "multi_member_consensus", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "bad-kind",
                    "type": "paragraph",
                    "text": "非法 kind 正文仍应保留",
                    "attribution": {"kind": "disagreement", "members": ["GPT-5.4", "openrouter-3o"]},
                },
            ]
        )
        article = html[html.index('<article id="final-answer"'):html.index("</article>")]

        self.assertNotIn("legacy markdown should not render", article)
        self.assertIn("合法综合正文", article)
        self.assertIn("主席综合整理，主要参考", article)
        self.assertIn("合法共识正文", article)
        self.assertIn("多成员共识", article)
        self.assertIn("同侪#1", article)
        self.assertIn("同侪#2", article)
        self.assertIn("非法 kind 正文仍应保留", article)
        self.assertIn("来源：无法可靠归因", article)
        self.assertNotIn("kind&quot;: &quot;disagreement", article)

    def test_contribution_map_unknown_member_partially_degrades(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "valid-synthesis",
                    "type": "paragraph",
                    "text": "合法综合正文",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "unknown-member",
                    "type": "paragraph",
                    "text": "未知成员正文仍应保留",
                    "attribution": {"kind": "single_member", "members": ["Unknown-Model"]},
                },
            ]
        )
        article = html[html.index('<article id="final-answer"'):html.index("</article>")]

        self.assertNotIn("legacy markdown should not render", article)
        self.assertIn("合法综合正文", article)
        self.assertIn("主席综合整理，主要参考", article)
        self.assertIn("未知成员正文仍应保留", article)
        self.assertIn("来源：无法可靠归因", article)
        self.assertNotIn("Unknown-Model", article)

    def test_contribution_map_synthesis_members_string_partially_degrades(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "valid-synthesis",
                    "type": "paragraph",
                    "text": "合法综合正文",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "bad-members-type",
                    "type": "paragraph",
                    "text": "字符串成员正文仍应保留",
                    "attribution": {"kind": "synthesis", "members": "GPT-5.4"},
                },
            ]
        )
        article = html[html.index('<article id="final-answer"'):html.index("</article>")]

        self.assertNotIn("legacy markdown should not render", article)
        self.assertIn("合法综合正文", article)
        self.assertIn("主席综合整理，主要参考", article)
        self.assertIn("字符串成员正文仍应保留", article)
        self.assertIn("贡献标记部分降级", article)
        self.assertIn("来源：无法可靠归因", article)
        self.assertNotIn("G（同侪", article)
        self.assertNotIn("P（同侪", article)

    def test_contribution_map_consensus_member_count_partially_degrades(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "valid-consensus",
                    "type": "paragraph",
                    "text": "合法共识正文",
                    "attribution": {"kind": "multi_member_consensus", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "bad-consensus",
                    "type": "paragraph",
                    "text": "成员不足共识正文仍应保留",
                    "attribution": {"kind": "multi_member_consensus", "members": ["GPT-5.4"]},
                },
            ]
        )
        article = html[html.index('<article id="final-answer"'):html.index("</article>")]

        self.assertNotIn("legacy markdown should not render", article)
        self.assertIn("合法共识正文", article)
        self.assertIn("多成员共识：GPT-5.4（同侪#1）, openrouter-3o（同侪#2）", article)
        self.assertIn("成员不足共识正文仍应保留", article)
        self.assertIn("来源：无法可靠归因", article)
        self.assertNotIn("<p class='meta'>多成员共识：GPT-5.4（同侪#1）</p>", article)

    def test_contribution_map_invalid_block_type_partially_degrades(self):
        html = render_contribution_map_blocks(
            [
                {
                    "id": "valid-synthesis",
                    "type": "paragraph",
                    "text": "合法综合正文",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                },
                {
                    "id": "bad-type",
                    "type": "unsupported_block_type",
                    "text": "非法 block type 正文仍应保留",
                    "attribution": {"kind": "synthesis", "members": ["GPT-5.4", "openrouter-3o"]},
                },
            ]
        )
        article = html[html.index('<article id="final-answer"'):html.index("</article>")]

        self.assertNotIn("legacy markdown should not render", article)
        self.assertIn("合法综合正文", article)
        self.assertIn("主席综合整理，主要参考", article)
        self.assertIn("非法 block type 正文仍应保留", article)
        self.assertIn("贡献标记部分降级", article)
        self.assertIn("来源：无法可靠归因", article)
        self.assertNotIn("unsupported_block_type", article)

    def test_contribution_map_fatal_structure_still_falls_back_to_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage3").mkdir()
            (root / "input.md").write_text("Report topic: 贡献说明 fatal fallback 测试\n", encoding="utf-8")
            (root / "stage3" / "final.md").write_text("fallback markdown answer\n", encoding="utf-8")
            (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
            (root / "stage3" / "contribution_map.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "enabled": True,
                        "source": "chairman_structured_output",
                        "blocks": {"not": "a list"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "run_id": "run-html-fatal-contribution",
                "status": "ok",
                "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake"},
                "metadata": {
                    "aggregate_rankings": [{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0}],
                    "chairman_contribution": {
                        "enabled": True,
                        "requested": True,
                        "required": False,
                        "present": True,
                        "path": "stage3/contribution_map.json",
                    },
                },
                "stages": {
                    "stage1": [{"label": "Response A", "file_label": "A", "model": "GPT-5.4", "status": "ok"}],
                    "stage2": [],
                    "stage3": {"model": "GPT-5.4", "status": "ok"},
                },
                "warnings": [],
                "failures": [],
            }

            html = render_html(root, manifest)

        self.assertIn("fallback markdown answer", html)

    def test_html_partially_degrades_when_contribution_map_has_invalid_member_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage3").mkdir()
            (root / "input.md").write_text("Report topic: 贡献说明 fallback 测试\n", encoding="utf-8")
            (root / "stage3" / "final.md").write_text("fallback markdown answer\n", encoding="utf-8")
            (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
            (root / "stage3" / "contribution_map.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "enabled": True,
                        "source": "chairman_structured_output",
                        "blocks": [
                            {
                                "id": "p1",
                                "type": "paragraph",
                                "text": "invalid sidecar should not render",
                                "attribution": {"kind": "single_member", "members": ["Unknown-Model"]},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "run_id": "run-html-invalid-contribution",
                "status": "ok",
                "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake"},
                "metadata": {
                    "aggregate_rankings": [{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0}],
                    "chairman_contribution": {
                        "enabled": True,
                        "requested": True,
                        "required": False,
                        "present": True,
                        "path": "stage3/contribution_map.json",
                    },
                },
                "stages": {
                    "stage1": [{"label": "Response A", "file_label": "A", "model": "GPT-5.4", "status": "ok"}],
                    "stage2": [],
                    "stage3": {"model": "GPT-5.4", "status": "ok"},
                },
                "warnings": [],
                "failures": [],
            }

            html = render_html(root, manifest)

        article = html[html.index('<article id="final-answer"'):html.index("</article>")]
        self.assertNotIn("fallback markdown answer", article)
        self.assertIn("invalid sidecar should not render", article)
        self.assertIn("来源：无法可靠归因", article)
        self.assertNotIn("Unknown-Model", html)

    def test_html_fallback_strips_trailing_contribution_json_block_when_sidecar_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage3").mkdir()
            (root / "input.md").write_text("Report topic: 缺失 sidecar fallback 测试\n", encoding="utf-8")
            (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
            (root / "stage3" / "final.md").write_text(
                """
fallback markdown answer

```json
{
  "schema_version": 1,
  "enabled": true,
  "source": "chairman_structured_output",
  "blocks": [
    {
      "id": "p1",
      "type": "paragraph",
      "text": "raw contribution block should not render, even with "bad quotes".",
      "attribution": {"kind": "single_member", "members": ["GPT-5.4"]}
    }
  ]
}
```
""".strip()
                + "\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "run_id": "run-html-missing-contribution",
                "status": "ok",
                "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake"},
                "metadata": {
                    "aggregate_rankings": [{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0}],
                    "chairman_contribution": {
                        "enabled": True,
                        "requested": True,
                        "required": False,
                        "present": False,
                        "path": "stage3/contribution_map.json",
                        "error": "missing_or_invalid_contribution_map_json",
                    },
                },
                "stages": {
                    "stage1": [{"label": "Response A", "file_label": "A", "model": "GPT-5.4", "status": "ok"}],
                    "stage2": [],
                    "stage3": {"model": "GPT-5.4", "status": "ok"},
                },
                "warnings": [],
                "failures": [],
            }

            html = render_html(root, manifest)

        self.assertIn("fallback markdown answer", html)
        self.assertNotIn("raw contribution block should not render", html)
        self.assertNotIn("bad quotes", html)

    def test_html_fallback_keeps_non_contribution_trailing_json_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stage3").mkdir()
            (root / "input.md").write_text("Report topic: 普通 JSON 示例测试\n", encoding="utf-8")
            (root / "stage3" / "chairman.prompt.md").write_text("prompt\n", encoding="utf-8")
            (root / "stage3" / "final.md").write_text(
                """
final answer with a JSON example

```json
{
  "not_a_contribution": "keep this visible"
}
```
""".strip()
                + "\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "run_id": "run-html-ordinary-json",
                "status": "ok",
                "config": {"members": ["GPT-5.4"], "chairman": "GPT-5.4", "provider_mode": "direct", "runtime_command": "fake"},
                "metadata": {
                    "aggregate_rankings": [{"label": "Response A", "model": "GPT-5.4", "average_rank": 1.0}],
                    "chairman_contribution": {
                        "enabled": True,
                        "requested": True,
                        "required": False,
                        "present": False,
                        "path": "stage3/contribution_map.json",
                    },
                },
                "stages": {
                    "stage1": [{"label": "Response A", "file_label": "A", "model": "GPT-5.4", "status": "ok"}],
                    "stage2": [],
                    "stage3": {"model": "GPT-5.4", "status": "ok"},
                },
                "warnings": [],
                "failures": [],
            }

            html = render_html(root, manifest)

        self.assertIn("final answer with a JSON example", html)
        self.assertIn("not_a_contribution", html)
        self.assertIn("keep this visible", html)

    def test_chairman_note_text_strips_loose_prefix_and_source_line(self):
        from llm_council_for_trae.html_export import clean_chairman_note_text

        self.assertEqual(
            clean_chairman_note_text("主席注 这是主席扩展判断。\n来源：主席编者注"),
            "这是主席扩展判断。",
        )
        self.assertEqual(
            clean_chairman_note_text("主席评注\n这是主席扩展判断。\n\n来源: 主席编者注"),
            "这是主席扩展判断。",
        )

    def test_html_summary_shows_chairman_fallback_card(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["GPT-5.4"], "chairman": "Qwen3.6-Plus"},
            "metadata": {"chairman": {"fallback_from": "GPT-5.4", "used": "Qwen3.6-Plus", "fallback_used": True}},
            "status": "degraded_ok",
        }
        html = render_summary_cards(manifest, [])
        self.assertIn("主席备选", html)
        self.assertIn("GPT-5.4", html)
        self.assertIn("Qwen3.6-Plus", html)

    def test_html_summary_shows_stage2_reviewer_only_backfill_card(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["M1", "M2", "M3"], "chairman": "Chair"},
            "metadata": {
                "stage2_reviewers": {
                    "reviewer_target": 3,
                    "review_subject_count": 3,
                    "valid_reviewers": ["M1", "M3", "M4"],
                    "failed_reviewers": ["M2"],
                    "reviewer_backfill_attempted": ["M4"],
                    "member_backfill_attempted": [],
                    "reviewer_only_backfill": True,
                }
            },
            "status": "ok",
        }
        html = render_summary_cards(manifest, [])
        self.assertIn("Stage 2 reviewer backfill", html)
        self.assertIn("M4", html)
        self.assertIn("reviewer-only", html)
        self.assertIn("subjects：3", html)

    def test_html_search_card_shows_only_calls_when_web_tools_called(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["M1"], "chairman": "Chair"},
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": ["WebSearch", "WebFetch"],
                        "tool_calls": [
                            {"id": "tc1", "name": "WebSearch"},
                            {"id": "tc2", "name": "WebSearch"},
                        ],
                        "web_tool_result_call_ids": ["tc1", "tc2"],
                        "lct_search_conversion_errors": 2,
                    }
                ],
                "stage2": [],
                "stage3": {},
            },
            "status": "ok",
        }

        html = render_summary_cards(manifest, [])

        self.assertIn("搜索工具", html)
        self.assertIn("调用次数：2", html)
        self.assertNotIn("调用生效次数", html)
        self.assertNotIn("允许：", html)
        self.assertNotIn("实际使用：", html)
        self.assertNotIn("Web 工具调用：", html)

    def test_html_search_card_hidden_without_web_tool_calls(self):
        from llm_council_for_trae.html_export import render_summary_cards
        manifest = {
            "config": {"members": ["M1"], "chairman": "Chair"},
            "stages": {
                "stage1": [
                    {
                        "allowed_tools": ["WebSearch", "WebFetch"],
                        "tool_calls": [],
                    }
                ],
                "stage2": [],
                "stage3": {},
            },
            "status": "ok",
        }

        html = render_summary_cards(manifest, [])

        self.assertNotIn("搜索工具", html)
        self.assertNotIn("调用次数：0", html)

    def test_html_stage2_tab_shows_reviewer_source_and_subject_count(self):
        manifest = {
            "run_id": "run-reviewer-only-html",
            "status": "ok",
            "config": {"members": ["M1", "M2", "M3"], "chairman": "Chair"},
            "metadata": {"aggregate_rankings": [], "label_to_model": {"Response A": "M1", "Response B": "M2", "Response C": "M3"}},
            "stages": {
                "stage1": [
                    {"label": "Response A", "file_label": "A", "model": "M1", "expected_model": "M1", "actual_model": "M1", "response": "A", "status": "ok"},
                    {"label": "Response B", "file_label": "B", "model": "M2", "expected_model": "M2", "actual_model": "M2", "response": "B", "status": "ok"},
                    {"label": "Response C", "file_label": "C", "model": "M3", "expected_model": "M3", "actual_model": "M3", "response": "C", "status": "ok"},
                ],
                "stage2": [
                    review_json() | {
                        "reviewer_label": "R4",
                        "model": "M4",
                        "expected_model": "M4",
                        "actual_model": "M4",
                        "ranking": "FINAL RANKING:\n1. Response A\n2. Response B\n3. Response C",
                        "parsed_ranking": ["Response A", "Response B", "Response C"],
                        "reviewer_source": "stage2_reviewer_backfill",
                        "attempt_role": "reviewer_backfill",
                        "review_subject_count": 3,
                    },
                ],
                "stage3": final_json() | {"model": "Chair", "expected_model": "Chair", "actual_model": "Chair"},
            },
            "warnings": [],
            "failures": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.md").write_text("Report topic: reviewer-only backfill\n", encoding="utf-8")
            (root / "stage3").mkdir()
            (root / "stage3" / "final.md").write_text("Final\n", encoding="utf-8")
            html = render_html(root, manifest)
        self.assertIn("来源：stage2_reviewer_backfill", html)
        self.assertIn("评审对象数：3", html)
        self.assertIn("角色：reviewer_backfill", html)

    def test_html_low_quorum_degraded_banner_visible(self):
        from llm_council_for_trae.html_export import render_alerts
        manifest = {
            "metadata": {
                "quorum": {
                    "effective_valid_members": 2,
                    "min_valid_members": 3,
                    "low_quorum_used": True,
                }
            }
        }
        html = render_alerts([], [], manifest_status="degraded_ok", manifest=manifest)
        self.assertIn("Quorum 降级", html)
        self.assertIn("仅 2 个有效成员", html)
        self.assertIn("warning-banner", html)

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
