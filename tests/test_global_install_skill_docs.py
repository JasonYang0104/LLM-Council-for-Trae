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


if __name__ == "__main__":
    unittest.main()
