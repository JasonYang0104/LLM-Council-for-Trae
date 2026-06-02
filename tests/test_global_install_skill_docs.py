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

    def test_readme_defaults_to_global_install_and_clean_workspace(self):
        readme = self.read_text("README.md")

        self.assertNotIn("在另一个 workspace clone 本仓库后", readme)
        self.assertNotIn("unittest: 78 tests passed", readme)
        self.assertIn("~/.LCT", readme)
        self.assertIn("/Users/bytedance/.agents/skills", readme)
        self.assertIn("干净问题 workspace", readme)
        self.assertIn("CLI 直接产物", readme)
        self.assertIn("Agent/Skill 额外落盘产物", readme)
        self.assertRegex(readme, re.compile(r"make install-local[\s\S]{0,160}开发"))

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

    def test_skill_template_documents_input_modes_and_search_evidence(self):
        skill = self.read_text("skills/llm-council-for-trae/SKILL.md")

        self.assertIn("raw original input", skill)
        self.assertIn("structured by Agent", skill)
        for trigger in ["按原始输入", "不要改写", "只用原文", "评估 LCT 对原始问题的理解"]:
            self.assertIn(trigger, skill)
        self.assertIn("Input mode", skill)
        self.assertIn("search_allowed", skill)
        self.assertIn("search_used", skill)
        index_line = next(line for line in skill.splitlines() if "$RUN_ID-index.md" in line)
        self.assertIn("Input mode", index_line)
        self.assertIn("search_allowed", index_line)
        self.assertIn("search_used", index_line)

    def test_docs_use_current_user_skill_path_and_no_stale_skill_path(self):
        doc_paths = [
            "README.md",
            "docs/lct-deployment-guide-20260601.md",
            "skills/llm-council-for-trae/SKILL.md",
        ]

        for relative in doc_paths:
            path = REPO_ROOT / relative
            self.assertTrue(path.exists(), f"missing {relative}")
            text = path.read_text(encoding="utf-8")
            self.assertIn("/Users/bytedance/.agents/skills", text, relative)
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
        design = self.read_text("docs/lct-global-install-skill-design-20260601.md")
        test_plan = self.read_text("docs/lct-global-install-skill-test-plan-20260601.md")

        self.assertIn("_lct_question.md", readme_quickstart)
        self.assertNotIn("examples/question.md", readme_quickstart)
        self.assertIn("src/llm_council_for_trae/", readme_quickstart)
        self.assertIn(".trae/agents/", readme_quickstart)
        self.assertIn("profiles/subagents.json", readme_quickstart)
        self.assertIn("<run_id>-final.md", readme_quickstart)
        self.assertIn("<run_id>-index.md", readme_quickstart)

        self.assertNotIn("llm-council-for-trae run --input examples/question.md", guide)
        self.assertIn("llm-council-for-trae run --input _lct_question.md --default-models --json", guide)
        for relative, text in {
            "docs/lct-global-install-skill-design-20260601.md": design,
            "docs/lct-global-install-skill-test-plan-20260601.md": test_plan,
        }.items():
            self.assertNotIn("llm-council-for-trae run --input examples/question.md", text, relative)
            self.assertIn("/tmp/lct-live-smoke", text, relative)
            self.assertIn("_lct_question.md", text, relative)

    def test_subagent_profile_is_documented_as_legacy_experimental(self):
        readme = self.read_text("README.md")
        highlights = readme.split("## Quickstart", 1)[0]
        subagents_doc = self.read_text("docs/traecli-subagents.md")

        self.assertNotIn("固定 subagent 成员", highlights)
        self.assertIn("legacy / experimental", readme)
        self.assertIn("legacy / experimental", subagents_doc)
        self.assertIn("direct provider 是日常主路径", subagents_doc)
        self.assertIn("模型漂移", subagents_doc)

    def test_readme_quickstart_index_contract_includes_input_and_search_evidence(self):
        readme = self.read_text("README.md")
        quickstart_line = next(line for line in readme.splitlines() if "<run_id>-index.md" in line)

        self.assertIn("Input mode", quickstart_line)
        self.assertIn("search_allowed", quickstart_line)
        self.assertIn("search_used", quickstart_line)

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
