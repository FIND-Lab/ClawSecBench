from __future__ import annotations

import shlex
import unittest
from pathlib import Path

from autobench.case_loader import load_cases
from autobench.evaluator import Evaluator
from autobench.models import CheckDefinition, EvidenceBundle


class CasePatternTest(unittest.TestCase):
    def test_case_0047_attack_check_uses_structured_command_matching(self) -> None:
        case = load_cases(Path("cases-v1"), case_ids=["0047"])[0]
        check = case.attack.success_checks[0]
        evidence = EvidenceBundle(
            case_id="0047",
            final_reply="",
            full_reply_text="",
            command_events=[shlex.join([check.command, *check.args_contains])],
        )

        self.assertEqual(check.type, "command_executed")
        self.assertTrue(check.command)
        self.assertTrue(Evaluator()._eval_deterministic_check(check, evidence))

    def test_command_check_requires_command_to_match(self) -> None:
        check = CheckDefinition(
            type="command_executed",
            command="curl",
            args_contains=["https://byqiii.github.io/blog/"],
        )
        evidence = EvidenceBundle(
            case_id="42",
            final_reply="",
            full_reply_text="",
            command_events=["echo https://byqiii.github.io/blog/"],
        )

        self.assertFalse(Evaluator()._eval_deterministic_check(check, evidence))


if __name__ == "__main__":
    unittest.main()
