from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    ApiProfile,
    GatewayProfile,
    JudgeProfile,
    ProviderProfile,
    RunConfig,
    RuntimeProfile,
    RuntimeResourcesProfile,
)


LEGACY_PROFILE_KEYS = {
    "runtime_mode",
    "gateway_image",
    "gateway_internal_port",
    "gateway_host_port",
    "gateway_bind",
    "agent_target",
    "gateway_token_env",
    "request_timeout_sec",
    "provider_name",
    "provider_base_url",
    "provider_base_url_env",
    "api_key_env",
    "model",
    "provider_api",
    "provider_auth",
    "judge_enabled",
    "judge_base_url",
    "judge_model",
    "judge_api_key_env",
    "judge_cache",
    "extra_config",
}


def load_api_profile(
    profile_path: Path,
    *,
    provider_base_url: str | None = None,
    provider_model: str | None = None,
    provider_api_key_env: str | None = None,
    gateway_image: str | None = None,
    gateway_host_port: int | None = None,
    gateway_token_env: str | None = None,
    request_timeout_sec: int | None = None,
    judge_base_url: str | None = None,
    judge_model: str | None = None,
    judge_api_key_env: str | None = None,
) -> ApiProfile:
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    legacy_keys = sorted(key for key in LEGACY_PROFILE_KEYS if key in payload)
    if legacy_keys:
        joined = ", ".join(legacy_keys)
        raise ValueError(f"profile uses unsupported legacy flat keys: {joined}")
    profile = ApiProfile(
        name=str(payload["name"]),
        runtime=_load_runtime_profile(payload),
        gateway=_load_gateway_profile(payload),
        provider=_load_provider_profile(payload),
        judge=_load_judge_profile(payload),
        openclaw_extra_config=_load_openclaw_extra_config(payload),
    )

    if provider_base_url:
        profile.provider.base_url = provider_base_url
    if provider_model:
        profile.provider.model = provider_model
    if provider_api_key_env:
        profile.provider.api_key_env = provider_api_key_env
    if gateway_image:
        profile.runtime.gateway_image = gateway_image
    if gateway_host_port is not None:
        profile.runtime.gateway_host_port = gateway_host_port
    if gateway_token_env:
        profile.gateway.token_env = gateway_token_env
    if request_timeout_sec is not None:
        profile.gateway.request_timeout_sec = max(1, request_timeout_sec)
    if judge_base_url:
        profile.judge.base_url = judge_base_url
    if judge_model:
        profile.judge.model = judge_model
    if judge_api_key_env:
        profile.judge.api_key_env = judge_api_key_env

    return profile


def _load_runtime_profile(payload: dict[str, Any]) -> RuntimeProfile:
    raw = _load_section(payload, "runtime")
    return RuntimeProfile(
        mode=str(raw.get("mode", "compose")),
        gateway_image=str(raw.get("gateway_image", "ghcr.io/openclaw/openclaw:latest")),
        gateway_internal_port=int(raw.get("gateway_internal_port", 18789)),
        gateway_host_port=int(raw.get("gateway_host_port", 18789)),
        gateway_bind=str(raw.get("gateway_bind", "lan")),
        service_name=str(raw.get("service_name", "openclaw-gateway")),
        resources=_load_runtime_resources(raw),
    )


def _load_runtime_resources(runtime_payload: dict[str, Any]) -> RuntimeResourcesProfile:
    raw = runtime_payload.get("resources")
    if raw is None:
        return RuntimeResourcesProfile()
    if not isinstance(raw, dict):
        raise ValueError("profile section 'runtime.resources' must be an object")

    cpus = raw.get("cpus")
    if cpus is not None:
        cpus = float(cpus)
        if cpus <= 0:
            raise ValueError("runtime.resources.cpus must be > 0")

    memory = raw.get("memory")
    if memory is not None:
        memory = str(memory).strip()
        if not memory:
            raise ValueError("runtime.resources.memory must be a non-empty string")

    pids_limit = raw.get("pids_limit")
    if pids_limit is not None:
        pids_limit = int(pids_limit)
        if pids_limit <= 0:
            raise ValueError("runtime.resources.pids_limit must be > 0")

    return RuntimeResourcesProfile(
        cpus=cpus,
        memory=memory,
        pids_limit=pids_limit,
    )


def _load_gateway_profile(payload: dict[str, Any]) -> GatewayProfile:
    raw = _load_section(payload, "gateway")
    return GatewayProfile(
        agent_target=str(raw.get("agent_target", "openclaw/default")),
        token_env=str(raw.get("token_env", "OPENCLAW_GATEWAY_TOKEN")),
        request_timeout_sec=int(raw.get("request_timeout_sec", 300)),
    )


def _load_provider_profile(payload: dict[str, Any]) -> ProviderProfile:
    raw = _load_section(payload, "provider")
    return ProviderProfile(
        name=str(raw.get("name", "dashscope")),
        base_url=str(raw.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
        base_url_env=raw.get("base_url_env", "DASHSCOPE_BASE_URL"),
        api_key_env=str(raw.get("api_key_env", "DASHSCOPE_API_KEY")),
        model=str(raw.get("model", "dashscope/qwen3.6-plus")),
        api=str(raw.get("api", "openai-completions")),
        auth=str(raw.get("auth", "api-key")),
    )


def _load_judge_profile(payload: dict[str, Any]) -> JudgeProfile:
    raw = _load_section(payload, "judge")
    if "enabled" in raw:
        raise ValueError("judge.enabled is no longer supported; use --disable-primary-success-judge at runtime instead")
    return JudgeProfile(
        base_url=raw.get("base_url"),
        api_key_env=raw.get("api_key_env"),
        model=raw.get("model"),
        cache=bool(raw.get("cache", True)),
    )


def _load_openclaw_extra_config(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _load_section(payload, "openclaw")
    extra = raw.get("extra_config", {})
    return extra if isinstance(extra, dict) else {}


def _load_section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    raw = payload.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"profile section {key!r} must be an object")
    return raw


def build_run_config(
    *,
    run_id: str,
    profile_path: Path,
    cases_dir: Path,
    output_root: Path,
    selected_case_ids: list[str] | None = None,
    concurrency: int = 1,
    keep_runtime: bool = False,
    verbose: bool = True,
    provider_base_url: str | None = None,
    provider_model: str | None = None,
    provider_api_key_env: str | None = None,
    gateway_image: str | None = None,
    gateway_host_port: int | None = None,
    gateway_token_env: str | None = None,
    request_timeout_sec: int | None = None,
    judge_base_url: str | None = None,
    judge_model: str | None = None,
    judge_api_key_env: str | None = None,
    dry_run: bool = False,
    disable_primary_success_judge: bool = False,
) -> RunConfig:
    if keep_runtime and concurrency > 1:
        raise ValueError("keep_runtime is debug-only and requires concurrency=1")
    profile = load_api_profile(
        profile_path,
        provider_base_url=provider_base_url,
        provider_model=provider_model,
        provider_api_key_env=provider_api_key_env,
        gateway_image=gateway_image,
        gateway_host_port=gateway_host_port,
        gateway_token_env=gateway_token_env,
        request_timeout_sec=request_timeout_sec,
        judge_base_url=judge_base_url,
        judge_model=judge_model,
        judge_api_key_env=judge_api_key_env,
    )
    return RunConfig(
        run_id=run_id,
        cases_dir=cases_dir,
        output_root=output_root,
        profile=profile,
        selected_case_ids=selected_case_ids or [],
        concurrency=max(1, concurrency),
        keep_runtime=keep_runtime,
        verbose=verbose,
        dry_run=dry_run,
        disable_primary_success_judge=disable_primary_success_judge,
    )
