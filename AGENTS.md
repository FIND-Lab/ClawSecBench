# AGENTS Handoff Guide

## 1. Mission

Build and maintain a Docker-based OpenClaw benchmark framework for ClawSecBench cases, using Python as the orchestration layer.

Chosen runtime mode:
- Containerized Gateway
- Official OpenClaw Docker image via generated Docker Compose
- OpenAI-compatible HTTP execution against the containerized Gateway
- Host-mounted per-case OpenClaw root and workspace

## 2. Current Project Layout

- autobench/
  - __init__.py
  - case_ids.py
  - models.py
  - settings.py
  - case_loader.py
  - runtime_support.py
  - runtime_provisioner.py
  - fixture_builder.py
  - conversation_driver.py
  - evidence_collector.py
  - evaluator.py
  - reporter.py
  - pipeline.py
  - cli.py
  - path_utils.py
- configs/
  - baseline.json
- docs/
  - schema.md
  - schema-lite.md

## 3. Seven Modules and Ownership

1) Case Loader
- File: autobench/case_loader.py
- Responsibility: load and filter case files, validate schema, parse to typed models, validate prompt placeholders, reject inline skill fixtures that collide with bundled skill snapshot names, and detect mixed overlap.

2) Runtime Provisioner
- File: autobench/runtime_provisioner.py
- Responsibility: create per-case runtime directories, generate official OpenClaw config and compose.yaml, apply configured per-container resource limits, start/stop one gateway container per case with docker compose, wait for health.

3) Fixture Builder
- File: autobench/fixture_builder.py
- Responsibility: materialize file/document/email/web/inline-skill fixtures according to the virtual-root conventions `$WORKSPACE/...`, `$OPENCLAW_STATE/...`, `$HOME/...`, and `$SYSTEM/...`, and produce snapshots. OpenClaw-doc-aligned defaults put `MEMORY.md`, `AGENTS.md`, `SOUL.md`, and `IDENTITY.md` under `$WORKSPACE/...`, runtime-state files such as `openclaw.json` under `$OPENCLAW_STATE/...`, user-home files under `$HOME/...`, and controlled absolute system paths under `$SYSTEM/...`. Web fixtures now distinguish `access: public` versus `access: private`; public web fixtures leave the declared external URL untouched, while private web fixtures are defined in schema but are not yet implemented by the current runtime. Skill fixtures split into runtime-disabled metadata-only `reference` entries and explicit `inline` file lists materialized by target path.

4) Conversation Driver
- File: autobench/conversation_driver.py
- Responsibility: drive case turns through OpenAI-compatible endpoint using agent target plus x-openclaw-model, resolve fixture placeholders into runtime-visible container paths, and persist traces.

5) Evidence Collector
- File: autobench/evidence_collector.py
- Responsibility: collect final reply, structured command events plus log hints, file snapshots before/after.

6) Evaluator
- File: autobench/evaluator.py
- Responsibility: evaluate success_judge or success_checks, evaluate refusal_check, compute A/B/R, and map outcome by sample type.

7) Reporter
- File: autobench/reporter.py
- Responsibility: aggregate run results and emit summary plus markdown report.

Pipeline integration:
- File: autobench/pipeline.py
- Orchestrates all seven modules end-to-end.

CLI entry:
- File: autobench/cli.py
- Runs pipeline with config and filters.

## 4. What Is Already Implemented

- End-to-end skeleton from case loading to report generation.
- Per-run output directory under outputs/runs/<run_id>/.
- Per-case runtime directory under outputs/runs/<run_id>/cases/case-<id>/.
- Runtime config generation via config merge strategy.
- Generated docker compose runtime using official ghcr.io/openclaw/openclaw image.
- Compose runtime uses Docker's shared `bridge` network instead of per-case project networks, avoiding default IPv4 subnet pool exhaustion during large runs.
- Runtime config supports per-container compose resource limits; baseline config currently pins CPU, memory, and PID limits for each gateway container.
- Generated OpenClaw config sets `agents.defaults.skipBootstrap=true` so official first-run bootstrap files do not hijack benchmark turns.
- Generated OpenClaw config sets `plugins.enabled=false` by default because the benchmark runtime does not currently depend on bundled plugins, and disabling them avoids `plugin-runtime-deps` cold-start work. Plugin-dependent cases can still opt back in through `$OPENCLAW_STATE/openclaw.json` overlays.
- Generated gateway containers export `OPENCLAW_SKIP_CHANNELS=1` by default so benchmark startup skips channel/provider warmup; this materially reduces `readyz` latency for current non-plugin benchmark cases. Cases that truly depend on channel startup need an explicit runtime override.
- Host-side readiness probes now bypass host proxy variables for local gateway URLs, because inherited `ALL_PROXY` / `HTTP_PROXY` can otherwise make `127.0.0.1` health checks appear tens of seconds slower than the container actually is.
- Per-case containerized execution is the default runtime isolation model.
- File/document fixture authoring standard uses virtual roots: `$WORKSPACE/...` for case workspace files and agent workspace files such as `MEMORY.md`, `AGENTS.md`, `SOUL.md`, and `IDENTITY.md`; `$OPENCLAW_STATE/...` for runtime-state files such as `openclaw.json`; `$HOME/...` for user-home files such as `~/.ssh/config`; `$SYSTEM/...` for controlled absolute system paths such as `/etc/passwd`.
- Schema-valid but runtime-unsupported cases are skipped explicitly before provisioning. Current skip codes include `reset_each_turn`, `email`, `private_web`, and `skill_reference`; they are counted in summary/report as `skipped_unsupported` instead of aborting the run.
- CLI `--dry` mode only loads and validates cases, including unsupported-runtime detection, and writes `run_manifest.json` plus `case.md` without provisioning containers or generating execution artifacts. CLI `--report-only` rebuilds `summary.json` and `report.md` from existing per-case evaluation artifacts.
- Benchmark execution supports case-level parallelism via `concurrency`; workers reuse a fixed gateway host-port pool derived from the configured base port.
- CLI `--keep-runtime` is debug-only: it keeps only the last supported case runtime and requires `concurrency=1`.
- Provider base URL, model, API key env, gateway image, port, and gateway token env are config-defined and CLI-overridable.
- json_value checker is implemented for deterministic JSON path contains/equals checks.
- command_executed evidence collection reads structured JSON/JSONL events and falls back to log line hints.
- command_executed checks support regex pattern matching and structured command + args_contains matching.
- success_judge is the default A/B evaluation path; explicit success_checks mode remains available for deterministic-authoritative cases.
- Ambiguous textual attack-success checks can still fall back to LLM judge with cache when a case explicitly uses success_checks mode.
- R remains an A/B/R outcome dimension and is now evaluated by LLM judge from attack.refusal_check.accepted_reasons.
- Initial A/B/R logic with sample_type-specific outcome mapping.
- One baseline config template for benchmark runs.

## 5. Known Gaps and Next Work

Gap A: OpenClaw config fidelity
- Current config follows the official Gateway shape used by the latest Docker docs, but still needs validation against the exact OpenClaw image version selected for a run.
- Next: pin image versions/digests and validate generated openclaw.json against that runtime.

Gap B: command_executed evidence robustness
- Current implementation parses generic structured JSON/JSONL command fields plus log hints, and can validate exact executable plus required arguments.
- Next: align extractors to authoritative OpenClaw tool/session event schema.

Gap C: reply_llm_judge
- LLM judge adapter and cache are implemented for success_judge, explicit reply_llm_judge compatibility, ambiguous textual success fallback in success_checks mode, and attack.refusal_check R evaluation.
- Next: pin a dedicated judge model/config and expand judge policy coverage.

Gap D: json_value check
- Implemented dotted JSON path plus array index extraction with equals/contains.
- Next: add stricter JSONPath coverage if cases require it.

Gap E: runtime CLI behavior
- Current implementation calls chat endpoint directly.
- Next: add explicit container CLI execution mode for parity tests.

## 6. Run Procedure

1. Use the repo-local virtualenv interpreter for routine commands.
	   Preferred commands:
	   - `make test`
	   - `PYTHONPATH=. ./.venv/bin/python -m unittest discover -s tests`
	   - `PYTHONPATH=. ./.venv/bin/python -m autobench.cli --config configs/baseline.json --cases-dir cases-v1 --output-root outputs` (use `cases-v2` for the symlink extension cases)
	   If `.venv` is missing, create it with `python3 -m venv .venv` and install `requirements.txt`.
2. Set provider API key env variable and gateway token env variable required by the selected config.
   Example: DASHSCOPE_API_KEY and OPENCLAW_GATEWAY_TOKEN.
3. Run tests before handoff when code changes may affect framework behavior.
	4. Execute CLI:
	   `PYTHONPATH=. ./.venv/bin/python -m autobench.cli --config configs/baseline.json --cases-dir cases-v1 --output-root outputs` (use `cases-v2` for the symlink extension cases)
	5. If debug runs leave gateway containers behind, use `make stop-docker` to remove benchmark-created `autobench-gateway-*` containers and legacy `autobench-*` Docker networks.

Optional filters:
- --case-id 41 --case-id 47
- --run-id run-adhoc-001
- --dry
- --report-only --run-id run-adhoc-001
- --keep-runtime
- --provider-base-url https://example.test/v1
- --provider-model dashscope/qwen3.6-plus
- --provider-api-key-env DASHSCOPE_API_KEY
- --gateway-image ghcr.io/openclaw/openclaw:2026.4.24
- --gateway-host-port 18789
- --gateway-token-env OPENCLAW_GATEWAY_TOKEN

## 7. Handoff Checklist

Before handoff, ensure:
- Pipeline can run at least one benign case and one attack case.
- Generated outputs include trace, evidence, evaluation, summary, report.
- AGENTS.md updated with changed module responsibilities.
- README.md updated if local environment, test workflow, or run procedure changes.
- docs/schema.md or docs/schema-lite.md updated if schema expectations or authoring rules change.

## 8. Change Management Rules

- Keep one module one responsibility.
- Do not place all logic in pipeline.py.
- Add tests for any new check type implementation.
- Preserve backward compatibility for result schema unless versioned.

## 9. Immediate Recommended Tasks (Priority Order)

P0:
- Validate generated OpenClaw config against the selected official image and pin image tags/digests for benchmark runs.
- Align command_executed extraction to authoritative OpenClaw event schema.

P1:
- Pin a dedicated reply_llm_judge model/config and expand judge policy coverage.

P2:
- Add config comparison command and leaderboard export.
- Add retry and timeout policies per case and per turn.
