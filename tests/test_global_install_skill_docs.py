from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class GlobalInstallSkillDocsTests(unittest.TestCase):
    def read_text(self, relative: str) -> str:
        return (REPO_ROOT / relative).read_text(encoding="utf-8")

    def assert_window_contains(self, text: str, anchor: str, terms: list[str], window: int = 1400) -> None:
        anchor_index = text.find(anchor)
        self.assertNotEqual(anchor_index, -1, f"missing anchor: {anchor}")
        excerpt = text[max(0, anchor_index - 200) : anchor_index + window]
        for term in terms:
            self.assertIn(term, excerpt)

    def runtime_override_main_docs(self) -> list[str]:
        return [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]

    def runtime_override_support_docs(self) -> list[str]:
        return [
            "docs/lct-deployment-guide-20260601.md",
        ]

    def test_readme_defaults_to_global_install_and_clean_workspace(self):
        readme = self.read_text("README.md")

        self.assertNotIn("在另一个 workspace clone 本仓库后", readme)
        self.assertNotIn("unittest: 78 tests passed", readme)
        self.assertIn("~/.LCT", readme)
        self.assertIn("~/.agents/skills", readme)
        self.assertNotIn("/Users/bytedance/.agents/skills", readme)
        self.assertIn("干净问题 workspace", readme)
        self.assertIn("CLI 直接产物", readme)
        self.assertIn("Agent/Skill 额外落盘产物", readme)
        self.assertRegex(readme, re.compile(r"make install-local[\s\S]{0,160}开发"))

    def test_docs_require_fresh_github_main_global_install_verification(self):
        main_required_terms = [
            "从 GitHub main 全局安装最新版 LCT",
            "https://github.com/JasonYang0104/LLM-Council-for-Trae.git",
            "make -C",
            "install-global",
            "llm-council-for-trae --version",
            "freshness checks",
            "git -C \"$HOME/.LCT\" remote get-url origin",
            "git ls-remote https://github.com/JasonYang0104/LLM-Council-for-Trae.git refs/heads/main",
            "~/.LCT HEAD == GitHub refs/heads/main",
            ".LCT/src",
            "uv tool",
            "site-packages",
            "extract_contribution_map",
            "strip_contribution_map_fence",
            "notes.md",
            "actual command",
            "exit code",
            "key stdout/stderr",
            "pass/fail",
        ]
        for relative in self.runtime_override_main_docs():
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in main_required_terms:
                    self.assertIn(term, text)

        deployment = self.read_text("docs/lct-deployment-guide-20260601.md")
        for term in [
            "git -C ~/.LCT rev-parse HEAD",
            "git -C ~/.LCT rev-parse origin/main",
            "git -C ~/.LCT remote get-url origin",
            "git ls-remote https://github.com/JasonYang0104/LLM-Council-for-Trae.git refs/heads/main",
            "~/.LCT HEAD == GitHub refs/heads/main",
            "grep -F '.LCT/src'",
            "llm-council-for-trae --version",
            "uv tool wrapper",
            "site-packages",
            "extract_contribution_map",
            "strip_contribution_map_fence",
            "actual command",
            "exit code",
            "key stdout/stderr",
            "pass/fail",
        ]:
            self.assertIn(term, deployment)

    def test_latest_install_intent_routes_to_lct_checkout_not_uv_tool(self):
        anchor = "请从 GitHub 仓库 https://github.com/JasonYang0104/LLM-Council-for-Trae 的最新版 LCT"
        required_terms = [
            "等同于从 GitHub main 安装或更新",
            "~/.LCT",
            "install-global",
            "不得使用 `uv tool install`",
            "安装成功必须同时证明",
            "`~/.LCT HEAD == GitHub refs/heads/main`",
            "wrapper 包含 `.LCT/src`",
            "Skill symlink 指向 `~/.LCT/skills/llm-council-for-trae`",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
            "docs/lct-deployment-guide-20260601.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                self.assert_window_contains(text, anchor, required_terms)

    def test_readme_includes_copyable_agent_install_prompt(self):
        readme = self.read_text("README.md")
        prompt = "请从 GitHub 仓库 https://github.com/JasonYang0104/LLM-Council-for-Trae 安装最新版 LCT。"

        self.assertIn(prompt, readme)
        self.assert_window_contains(
            readme,
            prompt,
            [
                "可以直接对 Agent 说",
                "等同于从 GitHub main 安装或更新",
                "~/.LCT + make install-global",
                "不得使用 `uv tool install`",
            ],
        )

    def test_docs_document_runtime_override_without_silent_fallback(self):
        required_terms = [
            "runtime override",
            "--runtime-command coco",
            "traecli models --json",
            "空列表",
            "coco models --json",
            "非空",
            "不是 CLI silent fallback",
        ]
        forbidden_patterns = [
            r"自动切换到\s*`?coco`?",
            r"默认(?:\s+runtime)?\s*改成\s*`?coco`?",
            r"自动\s*fallback\s*到\s*`?coco`?",
        ]
        for relative in self.runtime_override_main_docs():
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for pattern in forbidden_patterns:
                    self.assertIsNone(re.search(pattern, text, re.IGNORECASE), pattern)

    def test_docs_require_runtime_override_evidence_in_index(self):
        required_fields = [
            "runtime_default_command",
            "runtime_default_models_status",
            "runtime_override_used",
            "runtime_override_command",
            "runtime_override_reason",
            "runtime_used_by_lct",
        ]
        for relative in self.runtime_override_main_docs():
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for field in required_fields:
                    self.assertIn(field, text)

    def test_docs_require_same_runtime_command_for_override_run_and_validate(self):
        required_terms = [
            "llm-council-for-trae --runtime-command coco run",
            "llm-council-for-trae --runtime-command coco validate",
        ]
        for relative in self.runtime_override_main_docs():
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_docs_preserve_traecli_as_default_runtime(self):
        required_terms = [
            "默认 runtime 仍是 traecli",
            "coco 只在显式 override 中使用",
        ]
        for relative in self.runtime_override_main_docs() + self.runtime_override_support_docs():
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_docs_probe_recommendation_object_for_override(self):
        required_terms = [
            "llm-council-for-trae --runtime-command coco models --recommend --json",
            "recommendation.members",
            "recommendation.chairman",
        ]
        for relative in self.runtime_override_main_docs() + self.runtime_override_support_docs():
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skill_removes_stale_recommendation_backfill_wording(self):
        stale_phrase = "先记录推荐阵容，作为同一个 run 内 auto-backfill 的 backfill candidates 来源"
        replacement_phrase = "先记录推荐阵容，作为当前模型可用性和推荐安全过滤参考"
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                self.assertNotIn(stale_phrase, text)
                self.assertIn(replacement_phrase, text)

    def test_skill_template_has_required_workflow_contract(self):
        skill_path = REPO_ROOT / "skills" / "llm-council-for-trae" / "SKILL.md"
        self.assertTrue(skill_path.exists(), "missing canonical LCT Skill template")
        skill = skill_path.read_text(encoding="utf-8")

        self.assertRegex(skill, re.compile(r"^---\n[\s\S]*name:\s*llm-council-for-trae", re.MULTILINE))
        self.assertIn("description:", skill)
        self.assertIn("--default-models", skill)
        self.assertIn("--json", skill)
        self.assertIn("validate", skill)
        self.assertIn("src/llm_council_for_trae/", skill)
        self.assertIn(".trae/agents/", skill)
        self.assertIn("profiles/subagents.json", skill)
        self.assertIn("不要把 fake runtime 结果说成 live traecli 结果", skill)

    def test_canonical_and_trae_skill_templates_stay_in_sync(self):
        canonical = self.read_text("skills/llm-council-for-trae/SKILL.md")
        trae = self.read_text(".trae/skills/llm-council-for-trae/SKILL.md")
        self.assertEqual(canonical, trae)

    def test_validate_status_contract_is_documented_in_readme_and_skills(self):
        required_terms = [
            "terminal manifest",
            "validate <run_id> --json",
            "usable_final",
            "stage3_final_exists",
            "html_exists",
            "failed_stage_records",
            "verdict",
            "complete_ok_final",
            "usable_degraded_final",
            "in_progress",
            "failed_no_final",
            "invalid_artifacts",
            "degraded_ok 是可用结果",
            "成员失败不等于 run 失败",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skills_no_longer_instruct_full_recommended_rerun_as_primary_recovery(self):
        forbidden_terms = [
            "$RUN_ID-recommended",
            "recommended_rerun_status",
            "recommended_rerun_run_id",
            "不属于 CLI 内部自动行为",
        ]
        required_terms = [
            "同一个 run",
            "auto-backfill",
            "backfill candidates",
            "--backfill-members",
            "不整轮重跑",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skills_require_auto_backfill_and_effective_member_reporting(self):
        required_terms = [
            "valid_stage1_models",
            "quorum_default",
            "quorum_effective",
            "low_quorum_used",
            "backfill_attempts",
            "stage2_reviewers",
            "chairman_fallback_used",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_docs_distinguish_stage1_member_and_stage2_reviewer_backfill(self):
        required_terms = [
            "member backfill",
            "reviewer-only backfill",
            "stage1_backfill_members",
            "stage2_reviewer_backfill",
            "review_subject_count",
            "reviewer_count",
            "只有 Stage 1 quorum 不足",
            "不新增候选答案",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skills_require_fact_pack_inline_and_notes_md_boundary(self):
        required_terms = [
            "fact pack",
            "直接嵌入 _lct_question.md",
            "notes.md",
            "只由外层 Agent 维护",
            "模型不要创建或修改 notes",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                self.assertNotIn("请读取 _lct_fact_pack.md", text)

    def test_skills_separate_council_input_from_operator_envelope(self):
        required_terms = [
            "council input",
            "operator envelope",
            "_lct_question.md",
            "外层执行指令不得写入 _lct_question.md",
            "Report topic",
            "报告元数据",
            "维护 notes.md",
            "不得把它写入 council input",
        ]
        forbidden_member_tasks = [
            "要求 council 成员维护 notes.md",
            "要求模型维护 notes.md",
            "让模型维护 notes.md",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for term in forbidden_member_tasks:
                    self.assertNotIn(term, text)

    def test_docs_include_short_operator_envelope_stripping_example(self):
        anchor = "使用LCT回答：\"\"\""
        required_terms = [
            "反例",
            "不要写入",
            "_lct_question.md",
            "正确",
            "真实问题",
            "分析解读这个 JD。先意图理解我为何有这个需求，而不是直接动手。",
            "外层 Agent",
            "安装",
            "validate",
            "notes.md",
            "HTML",
            "Git/PR",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
            "docs/lct-deployment-guide-20260601.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                self.assert_window_contains(text, anchor, required_terms)

    def test_skills_preserve_raw_input_by_default_unless_agent_shaping_is_requested(self):
        required_terms = [
            "默认保留用户原始实质问题",
            "只有当用户明确要求",
            "structured by Agent",
            "Original input",
            "Agent interpretation",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                self.assertNotIn("默认使用 `structured by Agent` 模式", text)
                self.assertNotIn("默认使用 structured by Agent 模式", text)

    def test_readme_quickstart_documents_council_facing_question_boundary(self):
        readme = self.read_text("README.md")
        quickstart = readme.split("### 1. 确认 traecli 可用", 1)[0]

        required_terms = [
            "council-facing 问题",
            "必要事实背景",
            "输出要求",
            "外层执行指令不得写入 _lct_question.md",
            "维护 notes.md",
            "Git/PR/测试职责",
            "Report topic",
            "报告元数据",
        ]
        for term in required_terms:
            self.assertIn(term, quickstart)

    def test_readme_and_skills_preserve_agent_tool_mode_judgment(self):
        required_terms = [
            "answer_only 是可选工具模式",
            "不强制 answer_only",
            "外层 Agent 可以自行判断",
            "search_enabled 只表示搜索被允许，不表示模型实际搜索了",
            "agent_external_search_used",
        ]
        forbidden_terms = [
            "必须使用 --member-tool-mode answer_only",
            "默认使用 --member-tool-mode answer_only",
            "强制使用 answer_only",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)

    def test_skills_require_fact_pack_sources_without_execution_instructions(self):
        required_terms = [
            "fact pack",
            "标注来源",
            "只包含事实背景和来源",
            "不能包含执行指令",
            "不要要求成员读取 sidecar 文件",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_readme_and_skills_require_explicit_chinese_report_topic(self):
        required_terms = [
            "Report topic",
            "中文议题",
            "多模型智囊团评估",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_trae_skill_has_source_repo_guard_and_clean_workspace_contract(self):
        skill = self.read_text(".trae/skills/llm-council-for-trae/SKILL.md")

        self.assertIn("确认当前目录不是 LCT 源码 repo", skill)
        self.assertIn("src/llm_council_for_trae/", skill)
        self.assertIn(".trae/agents/", skill)
        self.assertIn("profiles/subagents.json", skill)
        self.assertIn("干净问题 workspace", skill)
        self.assertNotIn("在仓库根目录执行", skill)

    def test_skill_template_documents_input_modes_and_search_evidence(self):
        skill = self.read_text("skills/llm-council-for-trae/SKILL.md")

        self.assertIn("raw original input", skill)
        self.assertIn("structured by Agent", skill)
        for trigger in ["按原始输入", "不要改写", "只用原文", "评估 LCT 对原始问题的理解"]:
            self.assertIn(trigger, skill)
        self.assertIn("Input mode", skill)
        self.assertIn("lct_search_allowed", skill)
        self.assertIn("lct_search_used", skill)
        self.assertIn("agent_external_search_used", skill)
        self.assertIn("final_answer_source", skill)
        index_line = next(line for line in skill.splitlines() if "$RUN_ID-index.md" in line and "lct_search_allowed" in line)
        self.assertIn("Input mode", index_line)
        self.assertIn("lct_search_allowed", index_line)
        self.assertIn("lct_search_used", index_line)
        self.assertIn("agent_external_search_used", index_line)

    def test_skill_documents_raw_input_trigger_matrix(self):
        required_terms = [
            "raw original input",
            "不要改写",
            "按原文",
            "只用原始输入",
            "评估 LCT 对原问题的理解",
            "只追加 `Report topic`",
            "不得加 `Agent interpretation`",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skill_documents_structured_input_trigger_matrix(self):
        required_terms = [
            "structured by Agent",
            "先想我真正需要什么",
            "站在架构师角度评估",
            "fact pack",
            "最新资料",
            "来源",
            "必须保留 `Original input`",
            "直接内嵌并标来源",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skill_documents_negative_triggers_do_not_imply_rewrite(self):
        required_terms = [
            "详细分析",
            "深入一点",
            "给完整方案",
            "不得单凭字面触发结构化改写",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skill_documents_operator_envelope_never_enters_lct_question(self):
        required_terms = [
            "operator envelope",
            "notes.md",
            "validate",
            "Git/PR",
            "测试职责",
            "开 branch",
            "提交代码",
            "绝不进 `_lct_question.md`",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skill_documents_selected_model_agent_assisted_path(self):
        required_terms = [
            "用户明确要挑成员",
            "指定主席",
            "AskUserQuestionTool",
            "文本 fallback",
            "--selected-members",
            "--selected-chairman",
            "不要复用原生 `--members`",
            "selection_surface=agent_assisted",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_readme_and_skills_document_default_on_chairman_contribution_map(self):
        required_terms = [
            "主席贡献说明默认开启",
            "不需要追加 `--chairman-contribution-map`",
            "--no-chairman-contribution-map",
            "--require-chairman-contribution-map",
            "默认 requested",
            "required=true",
            "warning",
            "fallback",
            "metadata.chairman_contribution",
            "同侪#n",
            "常见未转义英文双引号",
            "复制 Markdown",
            "尾部 contribution JSON 块",
        ]
        forbidden_terms = [
            "默认不要打开主席贡献说明",
            "默认关闭路径",
            "默认关闭。需要让 HTML",
            "Default off.",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)

    def test_readme_and_skills_document_model_selection_intent_boundaries(self):
        required_terms = [
            "用户只问“有什么模型”",
            "不擅自启动 run",
            "想指定模型但没有给具体模型",
            "先读取当前模型清单",
            "追问",
            "--selected-members",
            "--selected-chairman",
            "非 TTY run 必须显式指定模型路径",
            "--default-models",
            "--members/--chairman",
            "--profile",
        ]
        forbidden_terms = [
            "必须使用 `--default-models`：Agent 非 TTY 场景不能交互选择模型",
            "Agent 非 TTY 场景不能交互选择模型",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)

    def test_current_docs_describe_default_three_and_synthesis_reference_semantics(self):
        required_terms = [
            "DeepSeek-V4-Pro, GPT-5.5, openrouter-3o",
            "归一化到 3",
            "补到 3",
            "synthesis.members",
            "主要参考",
            "不是共识",
        ]
        forbidden_terms = [
            "归一化到 4",
            "direct 默认 4 成员",
            "镜像 direct 默认 4 成员",
            "DeepSeek-V4-Pro, GPT-5.4, openrouter-3o, Kimi-K2.6",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
            "docs/design.md",
            "docs/traecli-subagents.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)

    def test_skills_do_not_treat_beta_or_hot_queue_as_auto_exclusions(self):
        required_terms = [
            "硬排除 Seed/Doubao/GLM",
        ]
        forbidden_terms = [
            "beta 或 hot queue",
            "Beta 或 Queue heat",
            "Beta 和 Queue heat",
            "hot queue 模型伪装成可用候补",
            "beta 或 hot queue 模型伪装成可用候补",
            "Queue heat 过高模型",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)

    def test_design_documents_agent_assisted_selected_model_path(self):
        text = self.read_text("docs/design.md")

        self.assertIn("--selected-members", text)
        self.assertIn("--selected-chairman", text)
        self.assertIn("agent-assisted", text)
        self.assertIn("原生 `--members` / `--chairman`", text)
        self.assertIn("--selected-members/--selected-chairman", text)
        self.assertNotIn("只能 `--default-models`", text)
        self.assertNotIn("只用 `--default-models`", text)

    def test_historical_process_docs_are_archived_not_current_readme_entries(self):
        readme = self.read_text("README.md")

        self.assertIn("docs/archive/", readme)
        self.assertIn("benchmark", readme)
        self.assertIn("docs/archive/README.md", readme)
        for old_entry in [
            "docs/lct-experience-upgrade-test-plan-20260606.md",
            "docs/lct-experience-upgrade-implementation-spec-20260606.md",
            "docs/lct-auto-backfill-implementation-brief-20260603.md",
            "docs/runtime-hardening-handoff-20260601.md",
            "notes.md |",
        ]:
            self.assertNotIn(old_entry, readme)
            archived = "docs/archive/" + old_entry.removeprefix("docs/")
            if old_entry != "notes.md |":
                self.assertTrue((REPO_ROOT / archived).exists(), archived)

        self.assertTrue((REPO_ROOT / "docs/archive/notes-20260606.md").exists())
        archive_readme = self.read_text("docs/archive/README.md")
        self.assertIn("只用于追溯", archive_readme)
        self.assertIn("不是当前安装、日常运行或接手开发入口", archive_readme)

    def test_current_docs_do_not_point_to_historical_goal_prompt_as_entry(self):
        current_docs = [
            "README.md",
            "docs/design.md",
            "docs/lct-deployment-guide-20260601.md",
            "docs/llm-council-parity.md",
            "docs/traecli-installation-and-paths.md",
            "docs/traecli-subagents.md",
        ]

        for relative in current_docs:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                self.assertNotIn("docs/goal-prompt.md", text)
                self.assertNotIn("docs/director-brief-20260522.md", text)

    def test_docs_use_portable_user_skill_path_and_no_stale_skill_path(self):
        doc_paths = [
            "README.md",
            "docs/lct-deployment-guide-20260601.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]

        for relative in doc_paths:
            path = REPO_ROOT / relative
            self.assertTrue(path.exists(), f"missing {relative}")
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("/Users/bytedance", text, relative)
            self.assertRegex(text, r"(?:~|\$HOME)/\.agents/skills", relative)
            self.assertNotIn("~/.trae/skills", text, relative)

        guide = self.read_text("docs/lct-deployment-guide-20260601.md")
        self.assertIn("~/.LCT", guide)
        self.assertIn("干净问题 workspace", guide)
        self.assertIn("开发仓库", guide)
        self.assertIn("不要把 fake runtime", guide)
        self.assertIn("live smoke", guide)

    def test_clean_workspace_examples_do_not_use_repo_example_input(self):
        readme_quickstart = self.read_text("README.md").split("## Council Protocol", 1)[0]
        guide = self.read_text("docs/lct-deployment-guide-20260601.md")

        self.assertIn("_lct_question.md", readme_quickstart)
        self.assertNotIn("examples/question.md", readme_quickstart)
        self.assertIn("src/llm_council_for_trae/", readme_quickstart)
        self.assertIn(".trae/agents/", readme_quickstart)
        self.assertIn("profiles/subagents.json", readme_quickstart)
        self.assertIn("<run_id>-final.md", readme_quickstart)
        self.assertIn("<run_id>-index.md", readme_quickstart)

        self.assertNotIn("llm-council-for-trae run --input examples/question.md", guide)
        self.assertIn("llm-council-for-trae run --input _lct_question.md --default-models --json", guide)

    def test_subagent_profile_is_documented_as_legacy_experimental(self):
        readme = self.read_text("README.md")
        highlights = readme.split("## Quickstart", 1)[0]
        subagents_doc = self.read_text("docs/traecli-subagents.md")

        self.assertNotIn("固定 subagent 成员", highlights)
        self.assertIn("legacy / experimental", readme)
        self.assertIn("legacy / experimental", subagents_doc)
        self.assertIn("降级方案", readme)
        self.assertIn("历史尝试", readme)
        self.assertIn("降级方案", subagents_doc)
        self.assertIn("历史尝试", subagents_doc)
        self.assertIn("direct provider 是日常主路径", subagents_doc)
        self.assertIn("模型漂移", subagents_doc)

    def test_readme_quickstart_index_contract_includes_input_and_search_evidence(self):
        readme = self.read_text("README.md")
        quickstart_line = next(line for line in readme.splitlines() if "<run_id>-index.md" in line)

        self.assertIn("Input mode", quickstart_line)
        self.assertIn("lct_search_allowed", quickstart_line)
        self.assertIn("lct_search_used", quickstart_line)
        self.assertIn("lct_web_tool_effective_calls", quickstart_line)
        self.assertIn("lct_search_conversion_errors", quickstart_line)
        self.assertIn("agent_external_search_used", quickstart_line)

    def test_readme_and_skills_require_manifest_sourced_backfill_candidates(self):
        required_terms = [
            "metadata.quorum.backfill_candidates",
            "terminal manifest",
            "not recorded",
            "不得从默认成员阵容",
            "不得从 models --recommend --json 的 primary roster",
            "不得从实际有效 Stage 1 成员",
        ]
        for relative in [
            "README.md",
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_skills_index_contract_includes_search_delivery_fields(self):
        required_terms = [
            "lct_web_tool_effective_calls",
            "lct_search_conversion_errors",
            "backfill_candidates",
        ]
        for relative in [
            "skills/llm-council-for-trae/SKILL.md",
            ".trae/skills/llm-council-for-trae/SKILL.md",
        ]:
            with self.subTest(relative=relative):
                text = self.read_text(relative)
                index_line = next(line for line in text.splitlines() if "$RUN_ID-index.md" in line and "lct_search_allowed" in line)
                for term in required_terms:
                    self.assertIn(term, index_line)

    def test_make_install_global_writes_global_wrapper_and_skill_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lct_dir = tmp_path / "LCT"
            bin_dir = tmp_path / "bin"
            skills_dir = tmp_path / "agent-skills"
            (lct_dir / "src" / "llm_council_for_trae").mkdir(parents=True)
            skill_src = lct_dir / "skills" / "llm-council-for-trae"
            skill_src.mkdir(parents=True)
            (skill_src / "SKILL.md").write_text("---\nname: llm-council-for-trae\n---\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "make",
                    "install-global",
                    f"LCT_DIR={lct_dir}",
                    f"BIN_DIR={bin_dir}",
                    f"SKILLS_DIR={skills_dir}",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            wrapper = bin_dir / "llm-council-for-trae"
            self.assertTrue(wrapper.exists())
            wrapper_text = wrapper.read_text(encoding="utf-8")
            self.assertIn(f'PYTHONPATH="{lct_dir}/src${{PYTHONPATH:+:$PYTHONPATH}}"', wrapper_text)
            self.assertNotIn(str(REPO_ROOT / "src"), wrapper_text)

            skill_link = skills_dir / "llm-council-for-trae"
            self.assertTrue(skill_link.is_symlink())
            self.assertEqual(skill_link.resolve(), skill_src.resolve())

    def test_make_install_global_refuses_missing_skill_without_writing_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lct_dir = tmp_path / "LCT"
            bin_dir = tmp_path / "bin"
            skills_dir = tmp_path / "agent-skills"
            lct_dir.mkdir()

            result = subprocess.run(
                [
                    "make",
                    "install-global",
                    f"LCT_DIR={lct_dir}",
                    f"BIN_DIR={bin_dir}",
                    f"SKILLS_DIR={skills_dir}",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing", result.stderr)
            self.assertFalse((bin_dir / "llm-council-for-trae").exists())

    def test_make_install_global_refuses_missing_src_without_writing_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            lct_dir = tmp_path / "LCT"
            bin_dir = tmp_path / "bin"
            skills_dir = tmp_path / "agent-skills"
            skill_src = lct_dir / "skills" / "llm-council-for-trae"
            skill_src.mkdir(parents=True)
            (skill_src / "SKILL.md").write_text("---\nname: llm-council-for-trae\n---\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "make",
                    "install-global",
                    f"LCT_DIR={lct_dir}",
                    f"BIN_DIR={bin_dir}",
                    f"SKILLS_DIR={skills_dir}",
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing", result.stderr)
            self.assertIn("src/llm_council_for_trae", result.stderr)
            self.assertFalse((bin_dir / "llm-council-for-trae").exists())


if __name__ == "__main__":
    unittest.main()
