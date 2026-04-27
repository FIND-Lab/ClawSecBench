from __future__ import annotations

import json
import http.client
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .case_ids import case_dirname
from .logging_utils import ProgressLogger
from .models import ApiProfile, CaseDefinition, EnvironmentItem, RunConfig, RuntimeHandle
from .path_utils import HOME_TOKEN, SYSTEM_TOKEN, logical_path_key, resolve_runtime_path


class RuntimeProvisionerError(RuntimeError):
    pass


class RuntimeProvisioner:
    def __init__(self, docker_bin: str = "docker", logger: ProgressLogger | None = None) -> None:
        self.docker_bin = docker_bin
        self.logger = logger or ProgressLogger()

    def provision(
        self,
        config: RunConfig,
        *,
        case: CaseDefinition | None = None,
        case_id: str | None = None,
        gateway_host_port: int | None = None,
    ) -> RuntimeHandle:
        if config.profile.runtime.mode != "compose":
            raise RuntimeProvisionerError(f"unsupported runtime mode: {config.profile.runtime.mode}")

        run_root = config.output_root / "runs" / config.run_id
        run_root.mkdir(parents=True, exist_ok=True)
        if case_id is None:
            run_dir = run_root
        else:
            run_dir = run_root / "cases" / case_dirname(case_id)

        runtime_dir = run_dir / "runtime"
        artifacts_dir = run_dir / "artifacts"
        workspace_dir = run_dir / "workspace"
        state_dir = run_dir / "openclaw-state"
        home_dir = run_dir / "home"
        system_dir = run_dir / "system"
        logs_dir = run_dir / "logs"

        for path in (runtime_dir, artifacts_dir, workspace_dir, state_dir, home_dir, system_dir, logs_dir):
            path.mkdir(parents=True, exist_ok=True)

        runtime_suffix = f"{config.run_id}-{case_dirname(case_id)}" if case_id is not None else config.run_id
        project_name = _safe_name(f"autobench-{runtime_suffix}")
        container_name = _safe_name(f"autobench-gateway-{runtime_suffix}")
        network_name = f"{project_name}_default"
        published_port = gateway_host_port if gateway_host_port is not None else config.profile.gateway_host_port
        gateway_url = f"http://127.0.0.1:{published_port}"

        openclaw_config_path = state_dir / "openclaw.json"
        openclaw_config = self._build_openclaw_config(config.profile)
        openclaw_config_path.write_text(json.dumps(openclaw_config, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info(f"wrote OpenClaw config: {openclaw_config_path}")

        compose_path = runtime_dir / "compose.yaml"
        system_mounts = self._prepare_system_mounts(case, workspace_dir=workspace_dir, state_dir=state_dir, home_dir=home_dir, system_dir=system_dir)
        compose_payload = self._build_compose_file(
            config.profile,
            container_name=container_name,
            workspace_dir=workspace_dir,
            state_dir=state_dir,
            home_dir=home_dir,
            logs_dir=logs_dir,
            gateway_host_port=published_port,
            system_mounts=system_mounts,
        )
        compose_path.write_text(json.dumps(compose_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info(f"wrote Docker Compose file: {compose_path}")

        handle = RuntimeHandle(
            run_dir=run_dir,
            runtime_dir=runtime_dir,
            artifacts_dir=artifacts_dir,
            workspace_dir=workspace_dir,
            state_dir=state_dir,
            home_dir=home_dir,
            system_dir=system_dir,
            logs_dir=logs_dir,
            network_name=network_name,
            container_name=container_name,
            openclaw_config_path=openclaw_config_path,
            gateway_url=gateway_url,
            compose_path=compose_path,
            compose_project_name=project_name,
        )

        try:
            self.logger.info(
                f"starting OpenClaw gateway image={config.profile.runtime.gateway_image} "
                f"port=127.0.0.1:{published_port}"
            )
            self._compose(handle, ["down", "--remove-orphans"], ignore_error=True)
            self._compose(handle, ["up", "-d"])
            self.logger.info(f"waiting for gateway readiness: {gateway_url}/readyz")
            self._wait_for_gateway_health(handle)
        except Exception as exc:
            diagnostics = ""
            try:
                diagnostics = self._compose_diagnostics(handle)
            except Exception:
                diagnostics = "runtime diagnostics unavailable"
            try:
                self.teardown(handle, keep_runtime=False)
            except Exception:
                pass
            if isinstance(exc, RuntimeProvisionerError):
                raise RuntimeProvisionerError(f"{exc}\n\n{diagnostics}") from exc
            raise
        self.logger.info("gateway is ready")

        return handle

    def teardown(self, handle: RuntimeHandle, *, keep_runtime: bool = False) -> None:
        if keep_runtime:
            self.logger.info(f"keeping runtime alive: compose={handle.compose_path}")
            return
        if handle.compose_path and handle.compose_project_name:
            self.logger.info("stopping OpenClaw gateway")
            self._compose(handle, ["down", "--remove-orphans"], ignore_error=True)
            return
        self._run([self.docker_bin, "rm", "-f", handle.container_name], ignore_error=True)
        self._run([self.docker_bin, "network", "rm", handle.network_name], ignore_error=True)

    def _build_openclaw_config(self, profile: ApiProfile) -> dict[str, Any]:
        provider_model_id = profile.provider.model.split("/", 1)[-1]
        base: dict[str, Any] = {
            "gateway": {
                "mode": "local",
                "bind": profile.runtime.gateway_bind,
                "auth": {
                    "mode": "token",
                    "token": "${OPENCLAW_GATEWAY_TOKEN}",
                },
                "http": {
                    "endpoints": {
                        "chatCompletions": {"enabled": True},
                        "responses": {"enabled": True},
                    }
                },
                "reload": {"mode": "off"},
            },
            "agents": {
                "defaults": {
                    "workspace": "~/.openclaw/workspace",
                    # Benchmarks should start directly from the case turn instead of
                    # being hijacked by OpenClaw's first-run identity bootstrap flow.
                    "skipBootstrap": True,
                    "timeoutSeconds": profile.gateway.request_timeout_sec,
                    "model": {"primary": profile.provider.model},
                    "models": {
                        profile.provider.model: {
                            "alias": f"benchmark-{profile.provider.name}-{provider_model_id}",
                        }
                    },
                }
            },
            "models": {
                "mode": "merge",
                "providers": {
                    profile.provider.name: {
                        "baseUrl": profile.provider.base_url,
                        "apiKey": f"${{{profile.provider.api_key_env}}}",
                        "api": profile.provider.api,
                        "auth": profile.provider.auth,
                        "models": [
                            {
                                "id": provider_model_id,
                                "name": provider_model_id,
                                "reasoning": False,
                                "input": ["text"],
                                "cost": {
                                    "input": 0,
                                    "output": 0,
                                    "cacheRead": 0,
                                    "cacheWrite": 0,
                                },
                                "contextWindow": 128000,
                                "contextTokens": 128000,
                                "maxTokens": 32000,
                            }
                        ],
                    }
                },
            },
            "discovery": {
                # Benchmark workers only talk to the published localhost port,
                # so mDNS advertisement adds no value and has crashed in Docker.
                "mdns": {"mode": "off"},
            },
            "plugins": {
                "entries": {
                    # The bundled bonjour discovery plugin can crash inside
                    # containerized runs with CIAO probing failures.
                    "bonjour": {"enabled": False},
                }
            },
        }
        return deep_merge(base, profile.openclaw_extra_config)

    def _build_compose_file(
        self,
        profile: ApiProfile,
        *,
        container_name: str,
        workspace_dir: Path,
        state_dir: Path,
        home_dir: Path,
        logs_dir: Path,
        gateway_host_port: int,
        system_mounts: list[tuple[Path, str]] | None = None,
    ) -> dict[str, Any]:
        env_entries = [
            "HOME=/home/node",
            "TERM=xterm-256color",
            "OPENCLAW_AGENT_DIR=/home/node/.openclaw",
            profile.provider.api_key_env,
        ]
        if profile.gateway.token_env == "OPENCLAW_GATEWAY_TOKEN":
            env_entries.append("OPENCLAW_GATEWAY_TOKEN")
        else:
            env_entries.append(f"OPENCLAW_GATEWAY_TOKEN=${{{profile.gateway.token_env}:-}}")
        if profile.provider.base_url_env:
            env_entries.append(str(profile.provider.base_url_env))

        volumes = [
            f"{home_dir.resolve().as_posix()}:/home/node",
            f"{state_dir.resolve().as_posix()}:/home/node/.openclaw",
            f"{workspace_dir.resolve().as_posix()}:/home/node/.openclaw/workspace",
            f"{logs_dir.resolve().as_posix()}:/home/node/.openclaw/logs",
        ]
        for host_path, container_path in system_mounts or []:
            volumes.append(f"{host_path.resolve().as_posix()}:{container_path}")

        service = {
            "image": profile.runtime.gateway_image,
            "container_name": container_name,
            # Each benchmark case runs a single gateway container accessed through
            # a published localhost port, so a per-project compose network adds no
            # value and can exhaust Docker's default subnet pool during full runs.
            "network_mode": "bridge",
            "command": [
                "node",
                "dist/index.js",
                "gateway",
                "--bind",
                profile.runtime.gateway_bind,
                "--port",
                str(profile.runtime.gateway_internal_port),
            ],
            "ports": [
                f"127.0.0.1:{gateway_host_port}:{profile.runtime.gateway_internal_port}",
            ],
            "environment": env_entries,
            "volumes": volumes,
        }
        user_spec = _container_user_spec()
        if user_spec:
            service["user"] = user_spec
        if profile.runtime.resources.cpus is not None:
            service["cpus"] = profile.runtime.resources.cpus
        if profile.runtime.resources.memory:
            service["mem_limit"] = profile.runtime.resources.memory
        if profile.runtime.resources.pids_limit is not None:
            service["pids_limit"] = profile.runtime.resources.pids_limit

        return {
            "services": {
                profile.runtime.service_name: service,
            }
        }

    def _prepare_system_mounts(
        self,
        case: CaseDefinition | None,
        *,
        workspace_dir: Path,
        state_dir: Path,
        home_dir: Path,
        system_dir: Path,
    ) -> list[tuple[Path, str]]:
        if case is None:
            return []

        mounts: list[tuple[Path, str]] = []
        seen: set[str] = set()
        for env in case.procedure.environment:
            if env.kind in {"file", "document"}:
                self._append_system_mount_if_needed(
                    mounts,
                    seen,
                    target=env.payload.get("target"),
                    workspace_dir=workspace_dir,
                    state_dir=state_dir,
                    home_dir=home_dir,
                    system_dir=system_dir,
                )
                continue
            if env.kind != "skill" or str(env.payload.get("mode", "")).strip() != "inline":
                continue
            for file_item in env.payload.get("files", []):
                if not isinstance(file_item, dict):
                    continue
                self._append_system_mount_if_needed(
                    mounts,
                    seen,
                    target=file_item.get("target"),
                    workspace_dir=workspace_dir,
                    state_dir=state_dir,
                    home_dir=home_dir,
                    system_dir=system_dir,
                )
        return mounts

    def _append_system_mount_if_needed(
        self,
        mounts: list[tuple[Path, str]],
        seen: set[str],
        *,
        target: Any,
        workspace_dir: Path,
        state_dir: Path,
        home_dir: Path,
        system_dir: Path,
    ) -> None:
        target_text = str(target).strip() if target is not None else ""
        if not target_text:
            return
        logical_target = logical_path_key(target_text)
        if not logical_target.startswith(f"{SYSTEM_TOKEN}/"):
            return

        container_path = "/" + logical_target[len(SYSTEM_TOKEN) :].lstrip("/")
        if container_path in seen:
            return
        seen.add(container_path)

        host_path = resolve_runtime_path(
            case_workspace=workspace_dir,
            state_dir=state_dir,
            home_dir=home_dir,
            system_dir=system_dir,
            value=target_text,
        )
        host_path.parent.mkdir(parents=True, exist_ok=True)
        if not host_path.exists():
            host_path.write_text("", encoding="utf-8")
        mounts.append((host_path, container_path))

    def _wait_for_gateway_health(self, handle: RuntimeHandle, timeout_sec: int = 120) -> None:
        # Cold starts can spend tens of seconds installing bundled plugin
        # runtime deps before the gateway's readiness endpoint stabilizes.
        deadline = time.time() + timeout_sec
        health_urls = [
            f"{handle.gateway_url}/readyz",
            f"{handle.gateway_url}/healthz",
        ]
        last_progress = 0.0

        while time.time() < deadline:
            for url in health_urls:
                try:
                    with urlopen(Request(url, method="GET"), timeout=3) as response:
                        if response.status < 500:
                            return
                except (HTTPError, URLError, TimeoutError, OSError, http.client.HTTPException):
                    pass
            now = time.time()
            if now - last_progress >= 5:
                remaining = max(0, int(deadline - now))
                self.logger.info(f"gateway not ready yet; retrying ({remaining}s remaining)")
                last_progress = now
            time.sleep(1)

        raise RuntimeProvisionerError("gateway health check timed out")

    def _compose(
        self,
        handle: RuntimeHandle,
        args: list[str],
        *,
        ignore_error: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if not handle.compose_path or not handle.compose_project_name:
            raise RuntimeProvisionerError("runtime handle does not have compose metadata")
        return self._run(
            [
                self.docker_bin,
                "compose",
                "-f",
                handle.compose_path.as_posix(),
                "-p",
                handle.compose_project_name,
                *args,
            ],
            ignore_error=ignore_error,
        )

    def _run(self, args: list[str], *, ignore_error: bool = False) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, check=False, capture_output=True, text=True)
        if result.returncode != 0 and not ignore_error:
            raise RuntimeProvisionerError(
                f"command failed: {' '.join(args)}\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        return result

    def _compose_diagnostics(self, handle: RuntimeHandle) -> str:
        sections = [
            "runtime diagnostics:",
            f"- compose_path: {handle.compose_path}",
            f"- openclaw_config_path: {handle.openclaw_config_path}",
            f"- gateway_url: {handle.gateway_url}",
        ]

        ps = self._compose(handle, ["ps"], ignore_error=True)
        sections.extend(["", "docker compose ps:", _format_completed_process(ps)])

        logs = self._compose(handle, ["logs", "--no-color", "--tail", "120"], ignore_error=True)
        sections.extend(["", "docker compose logs --tail 120:", _format_completed_process(logs)])

        return "\n".join(sections)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-_.")
    return safe.lower() or "autobench"


def _container_user_spec() -> str | None:
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if not callable(getuid) or not callable(getgid):
        return None
    return f"{getuid()}:{getgid()}"


def _format_completed_process(result: subprocess.CompletedProcess[str]) -> str:
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    parts = [f"returncode={result.returncode}"]
    if stdout:
        parts.extend(["stdout:", stdout])
    if stderr:
        parts.extend(["stderr:", stderr])
    return "\n".join(parts)
