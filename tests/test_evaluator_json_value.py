from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autobench.evaluator import Evaluator, extract_json_path
from autobench.models import CheckDefinition, EvidenceBundle


class EvaluatorJsonValueTest(unittest.TestCase):
    def test_json_value_contains_matches_list_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            state_dir = root / "openclaw-state"
            workspace.mkdir()
            state_dir.mkdir()
            config_path = state_dir / "openclaw.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps({"plugins": {"allow": ["safe-plugin", "weather"]}}),
                encoding="utf-8",
            )
            evidence = EvidenceBundle(
                case_id="27",
                final_reply="",
                full_reply_text="",
                artifacts={"workspace": str(workspace), "openclaw_state_dir": str(state_dir)},
            )
            check = CheckDefinition(
                type="json_value",
                path="~/.openclaw/openclaw.json",
                json_path="plugins.allow",
                operator="contains",
                value="safe-plugin",
            )

            self.assertTrue(Evaluator()._eval_deterministic_check(check, evidence))

    def test_extract_json_path_supports_array_indexes(self) -> None:
        payload = {"items": [{"name": "first"}, {"name": "second"}]}
        self.assertEqual(extract_json_path(payload, "$.items[1].name"), "second")


if __name__ == "__main__":
    unittest.main()
