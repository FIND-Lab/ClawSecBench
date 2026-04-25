from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autobench.models import ApiProfile, RunConfig, RunSummary
from autobench.pipeline import AutoBenchPipeline


class PipelineGatewayTokenTest(unittest.TestCase):
    def test_generates_ephemeral_gateway_token_before_provisioning(self) -> None:
        token_env = "AUTOBENCH_TEST_GATEWAY_TOKEN"
        os.environ.pop(token_env, None)
        profile = ApiProfile(name="test")
        profile.gateway.token_env = token_env
        profile.provider.api_key_env = "AUTOBENCH_TEST_PROVIDER_KEY"

        with tempfile.TemporaryDirectory() as tmp:
            run_config = RunConfig(
                run_id="token-test",
                cases_dir=Path("cases-v2"),
                output_root=Path(tmp),
                profile=profile,
                verbose=False,
            )
            pipeline = AutoBenchPipeline()
            with patch("autobench.pipeline.load_cases", return_value=[]), patch.object(
                pipeline.provisioner, "provision"
            ) as provision, patch.object(pipeline.provisioner, "teardown"), patch.object(
                pipeline.reporter, "build_summary"
            ) as build_summary:
                runtime = type(
                    "Runtime",
                    (),
                    {
                        "run_dir": Path(tmp),
                        "artifacts_dir": Path(tmp),
                    },
                )()
                provision.return_value = runtime
                build_summary.return_value = RunSummary(
                    run_id="token-test",
                    total_cases=0,
                    finished_cases=0,
                    failed_cases=0,
                    skipped_cases=0,
                    by_sample_type={},
                    outcome_counts={},
                    skip_reason_counts={},
                    result_paths=[],
                )

                pipeline.run(run_config)

        self.assertIn(token_env, os.environ)
        os.environ.pop(token_env, None)


if __name__ == "__main__":
    unittest.main()
