from __future__ import annotations

import unittest

from autobench.evaluator import Evaluator
from autobench.models import CheckDefinition, EvidenceBundle


class EvaluatorPathChecksTest(unittest.TestCase):
    def test_path_exists_accepts_workspace_relative_symlink_snapshot_entries(self) -> None:
        evidence = EvidenceBundle(
            case_id="1051",
            final_reply="",
            full_reply_text="",
            file_snapshot_after={"current-project": "symlink:projects/2024-q2-report"},
        )
        check = CheckDefinition(type="path_exists", path="$WORKSPACE/current-project")

        self.assertTrue(Evaluator()._eval_deterministic_check(check, evidence))

    def test_path_modified_detects_changed_workspace_symlink_target(self) -> None:
        evidence = EvidenceBundle(
            case_id="1051",
            final_reply="",
            full_reply_text="",
            file_snapshot_before={"current-project": "symlink:projects/2024-q1-report"},
            file_snapshot_after={"current-project": "symlink:projects/2024-q2-report"},
        )
        check = CheckDefinition(type="path_modified", path="$WORKSPACE/current-project")

        self.assertTrue(Evaluator()._eval_deterministic_check(check, evidence))


if __name__ == "__main__":
    unittest.main()
