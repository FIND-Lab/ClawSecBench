from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import shutil
import os
from queue import Queue
import secrets
import traceback
from dataclasses import asdict

from .case_loader import load_cases
from .case_ids import case_artifact_name, case_dirname, case_label
from .conversation_driver import ConversationDriver
from .evaluator import Evaluator
from .evidence_collector import EvidenceCollector
from .evaluation_records import (
    evaluation_result_from_record,
    is_resume_reusable_record,
    load_evaluation_record,
)
from .fixture_builder import FixtureBuilder
from .llm_judge import LLMJudge
from .logging_utils import ProgressLogger
from .models import CaseDefinition, CaseRunResult, RunConfig
from .reporter import Reporter
from .runtime_provisioner import RuntimeProvisioner
from .runtime_support import UnsupportedRuntimeFeature, detect_unsupported_runtime_features


class AutoBenchPipeline:
    def __init__(self) -> None:
        self.logger = ProgressLogger()
        self.provisioner = RuntimeProvisioner(logger=self.logger)
        self.fixture_builder = FixtureBuilder()
        self.driver = ConversationDriver(logger=self.logger)
        self.collector = EvidenceCollector()
        self.evaluator = Evaluator()
        self.reporter = Reporter()

    def run(self, run_config: RunConfig) -> dict:
        if run_config.keep_runtime and run_config.concurrency > 1:
            raise ValueError("keep_runtime is debug-only and requires concurrency=1")
        self.logger.enabled = run_config.verbose
        self.provisioner.logger = self.logger
        self.driver.logger = self.logger
        cases = load_cases(
            run_config.cases_dir,
            case_ids=run_config.selected_case_ids if run_config.selected_case_ids else None,
        )
        self.logger.info(
            f"loaded {len(cases)} case(s) from {run_config.cases_dir}; "
            f"config={run_config.profile.name}; provider_model={run_config.profile.model}"
        )
        case_support = [(case, detect_unsupported_runtime_features(case)) for case in cases]

        if run_config.dry_run:
            self.logger.info("dry run enabled: skipping runtime provisioning and execution")
            return self._build_dry_run_manifest(run_config, case_support)

        run_dir = run_config.output_root / "runs" / run_config.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        sample_report_path = self.reporter.build_sample_distribution_report(run_config.run_id, case_support, run_dir)

        gateway_token = os.environ.get(run_config.profile.gateway.token_env)
        if gateway_token:
            self.logger.info(f"gateway token env present: {run_config.profile.gateway.token_env}")
        else:
            gateway_token = secrets.token_urlsafe(32)
            os.environ[run_config.profile.gateway.token_env] = gateway_token
            self.logger.info(f"generated ephemeral gateway token for env: {run_config.profile.gateway.token_env}")

        provider_key_env = run_config.profile.provider.api_key_env
        if os.environ.get(provider_key_env):
            self.logger.info(f"provider API key env present: {provider_key_env}")
        else:
            self.logger.info(f"provider API key env missing: {provider_key_env}")

        self.evaluator.llm_judge = LLMJudge.from_profile(
            run_config.profile,
            cache_dir=run_dir / "judge-cache",
            logger=self.logger,
        )
        self.evaluator.disable_primary_success_judge = run_config.disable_primary_success_judge
        results_by_index: list[CaseRunResult | None] = [None] * len(case_support)
        supported_entries: list[tuple[int, int, CaseDefinition]] = []

        for index, (case, unsupported_features) in enumerate(case_support, start=1):
            existing = self._load_existing_case_result(run_dir, case)
            if existing is not None:
                self.logger.info(
                    f"case {index}/{len(cases)} resume: "
                    f"id={case.metadata.id} outcome={existing.evaluation.outcome}; skipping rerun"
                )
                results_by_index[index - 1] = existing
                continue

            if unsupported_features:
                self.logger.info(
                    f"case {index}/{len(cases)} start: "
                    f"id={case.metadata.id} type={case.metadata.sample_type.value} "
                    f"layer={case.metadata.threat_layer}"
                )
                result = self._build_unsupported_case_result(case, run_dir, unsupported_features)
                results_by_index[index - 1] = result
                self.logger.info(
                    f"{case_label(case.metadata.id)} skipped: "
                    + ", ".join(feature.code for feature in unsupported_features)
                )
                continue
            supported_entries.append((index - 1, index, case))

        supported_case_count = len(supported_entries)
        if supported_entries:
            port_pool: Queue[int] = Queue()
            for offset in range(run_config.concurrency):
                port_pool.put(run_config.profile.gateway_host_port + offset)

            with ThreadPoolExecutor(max_workers=run_config.concurrency) as executor:
                future_to_index = {
                    executor.submit(
                        self._run_supported_case,
                        run_config,
                        run_dir,
                        case,
                        total_cases=len(cases),
                        case_position=case_position,
                        supported_position=supported_position,
                        supported_case_count=supported_case_count,
                        gateway_token=gateway_token,
                        port_pool=port_pool,
                    ): result_index
                    for supported_position, (result_index, case_position, case) in enumerate(supported_entries, start=1)
                }
                for future in as_completed(future_to_index):
                    results_by_index[future_to_index[future]] = future.result()

        results = [result for result in results_by_index if result is not None]
        return self._finalize_run(run_config, run_dir, results, sample_report_path)

    def _run_supported_case(
        self,
        run_config: RunConfig,
        run_dir,
        case: CaseDefinition,
        *,
        total_cases: int,
        case_position: int,
        supported_position: int,
        supported_case_count: int,
        gateway_token: str | None,
        port_pool: Queue[int],
    ) -> CaseRunResult:
        self.logger.info(
            f"case {case_position}/{total_cases} start: "
            f"id={case.metadata.id} type={case.metadata.sample_type.value} "
            f"layer={case.metadata.threat_layer}"
        )
        keep_runtime = run_config.keep_runtime and supported_position == supported_case_count
        gateway_host_port = port_pool.get()
        runtime = None
        stage = "provision"
        try:
            self._reset_case_run_dir(run_dir, case.metadata.id)
            runtime = self.provisioner.provision(
                run_config,
                case=case,
                case_id=case.metadata.id,
                gateway_host_port=gateway_host_port,
            )
            stage = "fixture_build"
            fixture_manifest = self.fixture_builder.build(case, runtime)
            self.logger.info(
                f"{case_label(case.metadata.id)}: fixtures ready "
                f"files={len(fixture_manifest.get('snapshot_before', {}))}"
            )
            stage = "conversation"
            request_timeout_sec = case.procedure.request_timeout_sec or run_config.profile.gateway.request_timeout_sec
            trace = self.driver.run_case(
                case,
                runtime,
                fixture_manifest,
                agent_target=run_config.profile.gateway.agent_target,
                backend_model=run_config.profile.model,
                gateway_token=gateway_token,
                request_timeout_sec=request_timeout_sec,
            )
            stage = "evidence_collect"
            evidence = self.collector.collect(case, runtime, fixture_manifest, trace)
            stage = "evaluate"
            evaluation = self.evaluator.evaluate(case, evidence, runtime.artifacts_dir)

            evidence_path = runtime.artifacts_dir / case_artifact_name(case.metadata.id, "evidence")
            evaluation_path = runtime.artifacts_dir / case_artifact_name(case.metadata.id, "evaluation")
            self.logger.info(
                f"{case_label(case.metadata.id)} done: outcome={evaluation.outcome} "
                f"A={evaluation.A} B={evaluation.B} R={evaluation.R} "
                f"commands={len(evidence.command_events)}"
            )
            return CaseRunResult(
                case=case,
                evaluation=evaluation,
                evidence_path=evidence_path,
                evaluation_path=evaluation_path,
            )
        except Exception as exc:
            result = self._build_runtime_error_case_result(
                case,
                run_dir,
                stage=stage,
                exc=exc,
                runtime=runtime,
            )
            self.logger.info(
                f"{case_label(case.metadata.id)} failed: "
                f"stage={stage} error={type(exc).__name__}: {exc}"
            )
            return result
        finally:
            try:
                if runtime is not None:
                    try:
                        self.provisioner.teardown(runtime, keep_runtime=keep_runtime)
                    except Exception as exc:
                        self.logger.info(
                            f"{case_label(case.metadata.id)} teardown failed: "
                            f"{type(exc).__name__}: {exc}"
                        )
            finally:
                if not keep_runtime:
                    port_pool.put(gateway_host_port)

    def _finalize_run(self, run_config: RunConfig, run_dir, results: list[CaseRunResult], sample_report_path) -> dict:
        summary = self.reporter.build_summary(run_config.run_id, results, run_dir)
        self.logger.info(
            f"run complete: finished={summary.finished_cases}/{summary.total_cases} "
            f"summary={run_dir / 'summary.json'} report={run_dir / 'report.md'}"
        )

        manifest = {
            "run_id": run_config.run_id,
            "dry_run": run_config.dry_run,
            "disable_primary_success_judge": run_config.disable_primary_success_judge,
            "config": asdict(run_config.profile),
            "case_count": len(results),
            "summary": asdict(summary),
            "sample_report_path": str(sample_report_path),
        }
        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def _build_dry_run_manifest(
        self,
        run_config: RunConfig,
        case_support: list[tuple[CaseDefinition, list[UnsupportedRuntimeFeature]]],
    ) -> dict:
        run_dir = run_config.output_root / "runs" / run_config.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        reason_counts: dict[str, int] = {}
        unsupported_cases: list[dict[str, object]] = []
        for case, features in case_support:
            if not features:
                continue
            for feature in features:
                reason_counts[feature.code] = reason_counts.get(feature.code, 0) + 1
            unsupported_cases.append(
                {
                    "case_id": case.metadata.id,
                    "unsupported_features": [
                        {"code": feature.code, "message": feature.message} for feature in features
                    ],
                }
            )

        sample_report_path = self.reporter.build_sample_distribution_report(run_config.run_id, case_support, run_dir)
        manifest = {
            "run_id": run_config.run_id,
            "dry_run": True,
            "disable_primary_success_judge": run_config.disable_primary_success_judge,
            "checked_cases": len(case_support),
            "supported_case_count": sum(1 for _, features in case_support if not features),
            "unsupported_case_count": len(unsupported_cases),
            "unsupported_reason_counts": reason_counts,
            "unsupported_cases": unsupported_cases,
            "sample_report_path": str(sample_report_path),
        }
        manifest_path = run_dir / "run_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def _reset_case_run_dir(self, run_dir, case_id: str) -> None:
        case_dir = run_dir / "cases" / case_dirname(case_id)
        if case_dir.exists():
            shutil.rmtree(case_dir)

    def _load_existing_case_result(self, run_dir, case: CaseDefinition) -> CaseRunResult | None:
        case_dir = run_dir / "cases" / case_dirname(case.metadata.id)
        artifacts_dir = case_dir / "artifacts"
        evaluation_path = artifacts_dir / case_artifact_name(case.metadata.id, "evaluation")
        evidence_path = artifacts_dir / case_artifact_name(case.metadata.id, "evidence")
        if not evaluation_path.exists():
            return None

        raw = load_evaluation_record(evaluation_path)
        if raw is None:
            return None

        if not is_resume_reusable_record(raw):
            return None

        evaluation = evaluation_result_from_record(raw)
        if evaluation is None:
            return None

        if evaluation.case_id != case.metadata.id:
            return None

        return CaseRunResult(
            case=case,
            evaluation=evaluation,
            evidence_path=evidence_path,
            evaluation_path=evaluation_path,
            executed=False,
        )

    def _build_unsupported_case_result(
        self,
        case,
        run_dir,
        unsupported_features: list[UnsupportedRuntimeFeature],
    ) -> CaseRunResult:
        self._reset_case_run_dir(run_dir, case.metadata.id)
        case_dir = run_dir / "cases" / case_dirname(case.metadata.id)
        artifacts_dir = case_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        evidence_payload = {
            "case_id": case.metadata.id,
            "status": "skipped_unsupported",
            "unsupported_features": [
                {"code": feature.code, "message": feature.message} for feature in unsupported_features
            ],
        }
        evidence_path = artifacts_dir / case_artifact_name(case.metadata.id, "evidence")
        evidence_path.write_text(json.dumps(evidence_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        evaluation = self.evaluator.skipped_unsupported(case, unsupported_features)
        evaluation_path = artifacts_dir / case_artifact_name(case.metadata.id, "evaluation")
        evaluation_path.write_text(json.dumps(asdict(evaluation), ensure_ascii=False, indent=2), encoding="utf-8")

        return CaseRunResult(
            case=case,
            evaluation=evaluation,
            evidence_path=evidence_path,
            evaluation_path=evaluation_path,
            executed=False,
        )

    def _build_runtime_error_case_result(self, case, run_dir, *, stage: str, exc: Exception, runtime) -> CaseRunResult:
        case_dir = run_dir / "cases" / case_dirname(case.metadata.id)
        artifacts_dir = runtime.artifacts_dir if runtime is not None else case_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        traceback_text = traceback.format_exc()
        evidence_payload = {
            "case_id": case.metadata.id,
            "status": "runtime_error",
            "stage": stage,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback_text,
        }
        evidence_path = artifacts_dir / case_artifact_name(case.metadata.id, "evidence")
        evidence_path.write_text(json.dumps(evidence_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        evaluation = self.evaluator.runtime_error(
            case,
            stage=stage,
            error_type=type(exc).__name__,
            message=str(exc),
            traceback_text=traceback_text,
        )
        evaluation_path = artifacts_dir / case_artifact_name(case.metadata.id, "evaluation")
        evaluation_path.write_text(json.dumps(asdict(evaluation), ensure_ascii=False, indent=2), encoding="utf-8")

        return CaseRunResult(
            case=case,
            evaluation=evaluation,
            evidence_path=evidence_path,
            evaluation_path=evaluation_path,
            executed=False,
        )
