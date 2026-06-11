from __future__ import annotations

import unittest

from llm_council_for_trae.provider import ModelCallResult
from support.runtime_contract import EXPECTED_META_KEYS


class MetaKeysetGoldenTests(unittest.TestCase):
    def test_model_call_result_json_keyset_is_frozen(self):
        result = ModelCallResult(
            expected_model="Model-X",
            actual_model="Model-X",
            response="Answer",
            status="ok",
            session_id="sid",
            command=["traecli"],
            exit_code=0,
            stdout_path="out.jsonl",
            stderr_path="err.log",
        )

        self.assertEqual(sorted(result.to_json().keys()), EXPECTED_META_KEYS)


if __name__ == "__main__":
    unittest.main()
