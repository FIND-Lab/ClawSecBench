from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from .pipeline import AutoBenchPipeline
from .reporter import Reporter
from .settings import build_run_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw Docker AutoBench")
    parser.add_argument("--config", default=None, help="Path to benchmark runtime config JSON")
    parser.add_argument("--cases-dir", default="cases-v2", help="Cases directory")
    parser.add_argument("--output-root", default="outputs", help="Run output root")
    parser.add_argument("--run-id", default=None, help="Optional run id")
    parser.add_argument("--case-id", action="append", type=str, dest="case_ids", default=[])
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--keep-runtime", action="store_true")
    parser.add_argument("--dry", action="store_true", help="Load/filter cases and validate schema without execution")
    parser.add_argument("--report-only", action="store_true", help="Rebuild summary.json and report.md from existing evaluation artifacts")
    parser.add_argument("--provider-base-url", default=None, help="Override provider API base URL")
    parser.add_argument("--provider-model", default=None, help="Override provider model, e.g. dashscope/qwen3.6-plus")
    parser.add_argument("--provider-api-key-env", default=None, help="Override provider API key env var name")
    parser.add_argument("--gateway-image", default=None, help="Override OpenClaw gateway image")
    parser.add_argument("--gateway-host-port", type=int, default=None, help="Override published gateway port")
    parser.add_argument("--gateway-token-env", default=None, help="Override gateway token env var name")
    parser.add_argument("--request-timeout-sec", type=int, default=None, help="Override gateway/client request timeout")
    parser.add_argument(
        "--disable-primary-success-judge",
        action="store_true",
        help="Disable success_judge when success_mode=judge and fall back to success_checks",
    )
    parser.add_argument("--judge-base-url", default=None, help="Override judge API base URL")
    parser.add_argument("--judge-model", default=None, help="Override judge model")
    parser.add_argument("--judge-api-key-env", default=None, help="Override judge API key env var name")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.dry and args.report_only:
        parser.error("--dry and --report-only cannot be used together")
    if args.report_only and not args.run_id:
        parser.error("--report-only requires --run-id")
    if not args.report_only and not args.config:
        parser.error("--config is required unless --report-only is used")
    if args.keep_runtime and args.concurrency > 1:
        parser.error("--keep-runtime is debug-only and requires --concurrency 1")

    run_id = args.run_id or dt.datetime.now().strftime("run-%Y%m%d-%H%M%S")
    output_root = Path(args.output_root)

    if args.report_only:
        run_dir = output_root / "runs" / run_id
        if not run_dir.exists():
            parser.error(f"--report-only run directory does not exist: {run_dir}")
        reporter = Reporter()
        summary = reporter.rebuild_summary_from_run_dir(run_id, run_dir)
        manifest = reporter.update_run_manifest(run_id, run_dir, summary)
        manifest["report_only"] = True
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    config = build_run_config(
        run_id=run_id,
        profile_path=Path(args.config),
        cases_dir=Path(args.cases_dir),
        output_root=output_root,
        selected_case_ids=args.case_ids,
        concurrency=args.concurrency,
        keep_runtime=args.keep_runtime,
        verbose=not args.quiet,
        dry_run=args.dry,
        provider_base_url=args.provider_base_url,
        provider_model=args.provider_model,
        provider_api_key_env=args.provider_api_key_env,
        gateway_image=args.gateway_image,
        gateway_host_port=args.gateway_host_port,
        gateway_token_env=args.gateway_token_env,
        request_timeout_sec=args.request_timeout_sec,
        judge_base_url=args.judge_base_url,
        judge_model=args.judge_model,
        judge_api_key_env=args.judge_api_key_env,
        disable_primary_success_judge=args.disable_primary_success_judge,
    )

    pipeline = AutoBenchPipeline()
    manifest = pipeline.run(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
