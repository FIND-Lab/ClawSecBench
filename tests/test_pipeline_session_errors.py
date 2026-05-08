from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autobench.case_ids import case_artifact_name
from autobench.models import ApiProfile, CaseDefinition, ConversationTrace, EvidenceBundle, RunConfig, RuntimeHandle, TurnRecord
from autobench.pipeline import AutoBenchPipeline


class PipelineSessionErrorsTest(unittest.TestCase):
    def _case(self) -> CaseDefinition:
        return CaseDefinition.from_dict(
            {
                "metadata": {
                    "id": "9997",
                    "sample_type": "benign",
                    "threat_layer": "decision_alignment",
                    "attack_category": "intent_misunderstanding",
                },
                "procedure": {
                    "session_mode": "single_session",
                    "turns": [{"role": "user", "content": "Write MEMORY.md"}],
                    "environment": [],
                },
                "benign_task": {
                    "goal": "Write MEMORY.md.",
                    "success_mode": "judge",
                    "success_judge": {"rubric": "Write MEMORY.md."},
                    "success_policy": "all",
                    "success_checks": [],
                },
            }
        )

    def _runtime(self, root: Path) -> RuntimeHandle:
        runtime = RuntimeHandle(
            run_dir=root,
            runtime_dir=root / "runtime",
            artifacts_dir=root / "artifacts",
            workspace_dir=root / "workspace",
            state_dir=root / "openclaw-state",
            home_dir=root / "home",
            system_dir=root / "system",
            logs_dir=root / "logs",
            network_name="test-net",
            container_name="test-container",
            openclaw_config_path=root / "openclaw-state" / "openclaw.json",
            gateway_url="http://127.0.0.1:18789",
        )
        for path in (
            runtime.runtime_dir,
            runtime.artifacts_dir,
            runtime.workspace_dir,
            runtime.state_dir,
            runtime.home_dir,
            runtime.system_dir,
            runtime.logs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return runtime

    def test_session_error_short_circuits_to_runtime_error_even_with_partial_output(self) -> None:
        profile = ApiProfile(name="test")
        profile.gateway.request_timeout_sec = 300
        profile.gateway.agent_target = "openclaw/default"
        profile.provider.model = "openai/test-model"
        case = self._case()

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            runtime = self._runtime(run_dir)
            run_config = RunConfig(
                run_id="session-error-test",
                cases_dir=Path("cases-v1"),
                output_root=run_dir,
                profile=profile,
                verbose=False,
            )
            trace = ConversationTrace(
                case_id=case.metadata.id,
                session_key="case-9997-test",
                turns=[TurnRecord(role="user", prompt="Write MEMORY.md", response_text="partial output")],
            )
            evidence = EvidenceBundle(
                case_id=case.metadata.id,
                final_reply="timeout message",
                full_reply_text="partial output\ntimeout message",
                command_events=["echo hello > MEMORY.md"],
                file_snapshot_before={},
                file_snapshot_after={"$WORKSPACE/MEMORY.md": "abc123"},
                session_diagnostics=[
                    {
                        "error": True,
                        "session_id": "session-1",
                        "session_key": trace.session_key,
                        "trajectory_file": str(runtime.state_dir / "agents" / "main" / "sessions" / "session-1.trajectory.jsonl"),
                        "final_status": "error",
                        "session_status": "error",
                        "timed_out": True,
                        "idle_timed_out": True,
                        "timed_out_during_compaction": False,
                        "external_abort": False,
                        "aborted": True,
                        "prompt_error": "LLM idle timeout (120s): no response from model",
                        "prompt_error_source": "prompt",
                        "assistant_texts_count": 0,
                    }
                ],
                artifacts={
                    "trace_file": str(runtime.artifacts_dir / case_artifact_name(case.metadata.id, "trace")),
                    "workspace": str(runtime.workspace_dir),
                    "openclaw_state_dir": str(runtime.state_dir),
                    "home_dir": str(runtime.home_dir),
                    "system_dir": str(runtime.system_dir),
                },
                trace=trace,
            )
            evidence_path = runtime.artifacts_dir / case_artifact_name(case.metadata.id, "evidence")
            evidence_path.write_text(json.dumps(dataclasses.asdict(evidence), ensure_ascii=False, indent=2), encoding="utf-8")

            pipeline = AutoBenchPipeline()
            with patch.object(pipeline.provisioner, "provision", return_value=runtime), patch.object(
                pipeline.provisioner, "teardown"
            ), patch.object(
                pipeline.fixture_builder, "build", return_value={"case_workspace": str(runtime.workspace_dir)}
            ), patch.object(
                pipeline.driver, "run_case", return_value=trace
            ), patch.object(
                pipeline.collector, "collect", return_value=evidence
            ), patch.object(
                pipeline.evaluator, "evaluate"
            ) as evaluate:
                result = pipeline._run_supported_case(
                    run_config,
                    run_dir,
                    case,
                    total_cases=1,
                    case_position=1,
                    supported_position=1,
                    supported_case_count=1,
                    gateway_token="token",
                )

        self.assertEqual(result.evaluation.outcome, "runtime_error")
        self.assertEqual(result.evaluation.check_details[0]["error_type"], "OpenClawSessionError")
        self.assertEqual(result.evaluation.check_details[0]["session_status"], "error")
        self.assertTrue(result.evaluation.check_details[0]["timed_out"])
        evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
