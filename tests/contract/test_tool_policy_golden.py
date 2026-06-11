from __future__ import annotations

import unittest

from llm_council_for_trae.provider import tool_policy_for_mode


EXPECTED_TOOL_POLICIES = {
    "answer_only": {
        "allowed": [],
        "disallowed": [
            "Skill", "Agent", "TaskCreate", "TaskList", "TaskGet", "TaskUpdate", "TodoWrite",
            "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash",
            "Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch",
        ],
    },
    "search_enabled": {
        "allowed": ["WebSearch", "WebFetch"],
        "disallowed": [
            "Skill", "Agent", "TaskCreate", "TaskList", "TaskGet", "TaskUpdate", "TodoWrite",
            "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash",
            "Read", "Glob", "Grep", "LS",
        ],
    },
    "workspace_enabled": {
        "allowed": ["Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch"],
        "disallowed": [
            "Skill", "Agent", "TaskCreate", "TaskList", "TaskGet", "TaskUpdate", "TodoWrite",
            "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash",
        ],
    },
    "subagent_invocation": {
        "allowed": ["Agent"],
        "disallowed": [
            "Skill", "TaskCreate", "TaskList", "TaskGet", "TaskUpdate", "TodoWrite",
            "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash",
            "Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch",
        ],
    },
}


class ToolPolicyGoldenTests(unittest.TestCase):
    def test_all_tool_modes_match_frozen_allowed_and_disallowed_lists(self):
        for mode, expected in EXPECTED_TOOL_POLICIES.items():
            with self.subTest(mode=mode):
                allowed, disallowed = tool_policy_for_mode(mode)
                self.assertEqual(allowed, expected["allowed"])
                self.assertEqual(disallowed, expected["disallowed"])


if __name__ == "__main__":
    unittest.main()
