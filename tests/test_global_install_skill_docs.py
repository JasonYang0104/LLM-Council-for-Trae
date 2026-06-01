from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class GlobalInstallSkillDocsTests(unittest.TestCase):
    def read_text(self, relative: str) -> str:
        return (REPO_ROOT / relative).read_text(encoding="utf-8")

    def test_readme_defaults_to_global_install_and_clean_workspace(self):
        readme = self.read_text("README.md")

        self.assertNotIn("在另一个 workspace clone 本仓库后", readme)
        self.assertIn("~/.LCT", readme)
        self.assertIn("/Users/bytedance/.agents/skills", readme)
        self.assertIn("干净问题 workspace", readme)
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


if __name__ == "__main__":
    unittest.main()
