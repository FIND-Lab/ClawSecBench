from __future__ import annotations

import unittest

from autobench.llm_judge import parse_judge_json, provider_api_model_name


class LlmJudgeTest(unittest.TestCase):
    def test_provider_api_model_name_strips_provider_prefix(self) -> None:
        self.assertEqual(provider_api_model_name("dashscope/qwen3.6-plus"), "qwen3.6-plus")
        self.assertEqual(provider_api_model_name("gpt-5.4"), "gpt-5.4")

    def test_parse_judge_json_accepts_fenced_json(self) -> None:
        parsed = parse_judge_json('```json\n{"pass": false, "confidence": "high", "rationale": "quoted"}\n```')
        self.assertFalse(parsed["pass"])
        self.assertEqual(parsed["confidence"], "high")


if __name__ == "__main__":
    unittest.main()
