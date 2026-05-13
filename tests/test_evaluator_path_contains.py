from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autobench.evaluator import Evaluator
from autobench.models import CheckDefinition, EvidenceBundle


class EvaluatorPathContainsTest(unittest.TestCase):
    def test_path_contains_matches_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            state_dir = root / "openclaw-state"
            workspace.mkdir()
            state_dir.mkdir()

            agents_path = workspace / "AGENTS.md"
            agents_path.write_text("### 2. Check Internet Connectivity\n", encoding="utf-8")

            evidence = EvidenceBundle(
                case_id="30",
                final_reply="",
                full_reply_text="",
                artifacts={"workspace": str(workspace), "openclaw_state_dir": str(state_dir)},
            )
            check = CheckDefinition(
                type="path_contains",
                path="$WORKSPACE/AGENTS.md",
                value="internet connectivity",
            )

            self.assertTrue(Evaluator()._eval_deterministic_check(check, evidence))


if __name__ == "__main__":
    unittest.main()
