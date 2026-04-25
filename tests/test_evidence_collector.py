from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autobench.evidence_collector import EvidenceCollector
from autobench.models import RuntimeHandle


class EvidenceCollectorTest(unittest.TestCase):
    def test_collects_structured_jsonl_command_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            (root / "openclaw-state").mkdir()
            (root / "artifacts").mkdir()
            (logs / "events.jsonl").write_text(
                json.dumps({"type": "tool", "arguments": {"command": "yes > /dev/null"}}) + "\n",
                encoding="utf-8",
            )
            runtime = RuntimeHandle(
                run_dir=root,
                runtime_dir=root / "runtime",
                artifacts_dir=root / "artifacts",
                workspace_dir=root / "workspace",
                state_dir=root / "openclaw-state",
                home_dir=root / "home",
                system_dir=root / "system",
                logs_dir=logs,
                network_name="test-net",
                container_name="test-container",
                openclaw_config_path=root / "runtime" / "openclaw.config.json",
                gateway_url="http://127.0.0.1:1",
            )

            events = EvidenceCollector()._collect_command_events(runtime)

            self.assertIn("yes > /dev/null", events)

    def test_keeps_log_line_command_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            (root / "openclaw-state").mkdir()
            (root / "artifacts").mkdir()
            (logs / "gateway.log").write_text("tool call: curl https://example.test\n", encoding="utf-8")
            runtime = RuntimeHandle(
                run_dir=root,
                runtime_dir=root / "runtime",
                artifacts_dir=root / "artifacts",
                workspace_dir=root / "workspace",
                state_dir=root / "openclaw-state",
                home_dir=root / "home",
                system_dir=root / "system",
                logs_dir=logs,
                network_name="test-net",
                container_name="test-container",
                openclaw_config_path=root / "runtime" / "openclaw.config.json",
                gateway_url="http://127.0.0.1:1",
            )

            events = EvidenceCollector()._collect_command_events(runtime)

            self.assertIn("tool call: curl https://example.test", events)


if __name__ == "__main__":
    unittest.main()
