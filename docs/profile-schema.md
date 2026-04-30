# ClawSecBench Profile Schema

This document specifies the grouped runtime profile format used by benchmark configs such as `configs/baseline.json`. The formal schema is defined in `schema/profile.schema.json`.

## Purpose

The profile schema describes benchmark runner configuration that is shared across cases:

- which OpenClaw gateway image to start
- which provider/model to call through the gateway
- which token env vars to read
- which resource limits and logging knobs to apply
- which optional judge configuration to use

Unlike case JSON, profile JSON is operational configuration rather than benchmark data.

## Validation Model

Profile JSON is validated against `schema/profile.schema.json` before typed loading.

The schema is intentionally strict:

- top-level `additionalProperties` is `false`
- each grouped section also sets `additionalProperties: false`
- invalid types and out-of-range numeric values fail validation before runtime provisioning starts

This means unknown fields such as historical flat keys or ad hoc local flags are rejected instead of being silently ignored.

## Top-Level Structure

Each profile is a JSON object with these top-level fields:

```json
{
  "name": "baseline",
  "runtime": {},
  "gateway": {},
  "provider": {},
  "judge": {},
  "openclaw": {}
}
```

Only `name` is required by schema. All grouped sections are optional and inherit loader defaults when omitted.

## Sections

### `name`

`name` is a non-empty string used for human identification of the profile.

### `runtime`

`runtime` controls how the benchmark starts OpenClaw.

Supported fields:

| Field | Type | Notes |
|---|---|---|
| `mode` | enum | currently only `compose` |
| `gateway_image` | string | Docker image tag or digest reference |
| `gateway_internal_port` | integer | `1..65535` |
| `gateway_host_port` | integer | `1..65535` |
| `gateway_bind` | string | gateway bind target such as `lan` |
| `service_name` | string | compose service name |
| `gateway_log_level` | string | non-blank log level, e.g. `debug` |
| `gateway_verbose` | boolean | toggles verbose gateway startup logs |
| `resources.cpus` | number | must be `> 0` |
| `resources.memory` | string | non-blank Docker memory limit |
| `resources.pids_limit` | integer | must be `>= 1` |

### `gateway`

`gateway` controls request routing into the started OpenClaw gateway.

Supported fields:

| Field | Type | Notes |
|---|---|---|
| `agent_target` | string | target passed to OpenClaw chat requests |
| `token_env` | env-var string | bearer token env var name |
| `request_timeout_sec` | integer | must be `>= 1` |

### `provider`

`provider` defines the upstream model endpoint exposed through OpenClaw.

Supported fields:

| Field | Type | Notes |
|---|---|---|
| `name` | string | provider key written into generated `openclaw.json` |
| `base_url` | string | OpenAI-compatible upstream base URL |
| `api_key_env` | env-var string | env var name exported into the gateway container |
| `model` | string | provider model id, typically `provider/model-name` |
| `api` | string | OpenClaw provider API mode |
| `auth` | string | OpenClaw provider auth mode |

### `judge`

`judge` holds optional LLM-judge overrides.

Supported fields:

| Field | Type | Notes |
|---|---|---|
| `base_url` | string or `null` | optional judge endpoint |
| `api_key_env` | env-var string or `null` | optional judge API key env |
| `model` | string or `null` | optional judge model |
| `cache` | boolean | whether judge cache is enabled |

### `openclaw`

`openclaw.extra_config` is a free-form JSON object merged into the generated baseline `openclaw.json`.

This is the one intentionally open-ended part of the profile schema, because the shape depends on OpenClaw configuration rather than the benchmark runner itself.

## Defaults

When a grouped section or field is omitted, the loader falls back to benchmark defaults in `autobench/settings.py`.

Important defaults today:

- `runtime.mode = "compose"`
- `runtime.gateway_image = "ghcr.io/openclaw/openclaw:2026.4.24"`
- `runtime.gateway_host_port = 18789`
- `gateway.agent_target = "openclaw/default"`
- `gateway.token_env = "OPENCLAW_GATEWAY_TOKEN"`
- `gateway.request_timeout_sec = 300`
- `provider.name = "dashscope"`
- `provider.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"`
- `provider.api_key_env = "DASHSCOPE_API_KEY"`
- `provider.model = "dashscope/qwen3.6-plus"`
- `judge.cache = true`

Use `configs/baseline.json` as the canonical working example.

## Relationship to CLI Overrides

The profile schema validates only the JSON file content itself.

CLI flags such as:

- `--provider-base-url`
- `--provider-model`
- `--provider-api-key-env`
- `--gateway-image`
- `--gateway-host-port`
- `--gateway-token-env`
- `--request-timeout-sec`

are applied after the profile file is loaded and validated.

In other words:

- schema validation governs the on-disk config file
- CLI overrides remain a separate runtime override layer

## Example

```json
{
  "name": "baseline",
  "runtime": {
    "mode": "compose",
    "gateway_image": "ghcr.io/openclaw/openclaw:2026.4.24",
    "gateway_internal_port": 18789,
    "gateway_host_port": 18789,
    "gateway_bind": "lan",
    "resources": {
      "cpus": 4.0,
      "memory": "8g",
      "pids_limit": 512
    }
  },
  "gateway": {
    "agent_target": "openclaw/default",
    "token_env": "OPENCLAW_GATEWAY_TOKEN",
    "request_timeout_sec": 300
  },
  "provider": {
    "name": "dashscope",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key_env": "DASHSCOPE_API_KEY",
    "model": "dashscope/qwen3.6-plus",
    "api": "openai-completions",
    "auth": "api-key"
  },
  "judge": {
    "cache": true
  },
  "openclaw": {
    "extra_config": {}
  }
}
```
