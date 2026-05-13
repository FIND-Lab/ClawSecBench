from __future__ import annotations

from pathlib import Path

OPENCLAW_HOME = "/home/node/.openclaw"
HOME_ROOT = "/home/node"
WORKSPACE_HOME = f"{OPENCLAW_HOME}/workspace"
OPENCLAW_STATE_TOKEN = "$OPENCLAW_STATE"
WORKSPACE_TOKEN = "$WORKSPACE"
HOME_TOKEN = "$HOME"
SYSTEM_TOKEN = "$SYSTEM"
OPENCLAW_HOME_ALIAS = "~/.openclaw"
HOME_ALIAS = "~"


def _normalized_nonempty_path(value: str | None) -> str:
    if value is None:
        raise ValueError("path must be a non-empty string")

    raw = value.strip().replace("\\", "/")
    raw = raw.lstrip("/")
    if not raw:
        raise ValueError("path must be a non-empty string")

    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts:
        raise ValueError("path must be a non-empty string")
    if any(part == ".." for part in parts):
        raise ValueError(f"path traversal is not allowed: {value!r}")

    return "/".join(parts)


def normalize_case_path(value: str | None) -> str:
    """Convert a case-declared path into a safe workspace-relative POSIX path."""
    return _normalized_nonempty_path(value)


def case_workspace_path(workspace: Path, value: str | None) -> Path:
    return workspace / normalize_case_path(value)


def is_openclaw_home_path(value: str | None) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    return (
        raw == OPENCLAW_STATE_TOKEN
        or raw.startswith(f"{OPENCLAW_STATE_TOKEN}/")
        or raw == OPENCLAW_HOME_ALIAS
        or raw.startswith(f"{OPENCLAW_HOME_ALIAS}/")
        or raw == OPENCLAW_HOME
        or raw.startswith(f"{OPENCLAW_HOME}/")
    )


def is_workspace_path(value: str | None) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    return (
        raw == WORKSPACE_TOKEN
        or raw.startswith(f"{WORKSPACE_TOKEN}/")
        or raw == WORKSPACE_HOME
        or raw.startswith(f"{WORKSPACE_HOME}/")
    )


def is_home_path(value: str | None) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    return (
        raw == HOME_TOKEN
        or raw.startswith(f"{HOME_TOKEN}/")
        or raw == HOME_ALIAS
        or raw.startswith(f"{HOME_ALIAS}/")
        or raw == HOME_ROOT
        or raw.startswith(f"{HOME_ROOT}/")
    )


def is_system_path(value: str | None) -> bool:
    raw = str(value or "").strip().replace("\\", "/")
    return raw == SYSTEM_TOKEN or raw.startswith(f"{SYSTEM_TOKEN}/") or (
        raw.startswith("/")
        and not is_openclaw_home_path(raw)
        and not is_workspace_path(raw)
        and not is_home_path(raw)
    )


def normalize_openclaw_home_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if raw == OPENCLAW_STATE_TOKEN:
        suffix = ""
    elif raw.startswith(f"{OPENCLAW_STATE_TOKEN}/"):
        suffix = raw[len(OPENCLAW_STATE_TOKEN) + 1 :]
    elif raw == OPENCLAW_HOME_ALIAS:
        suffix = ""
    elif raw.startswith(f"{OPENCLAW_HOME_ALIAS}/"):
        suffix = raw[len(OPENCLAW_HOME_ALIAS) + 1 :]
    elif raw == OPENCLAW_HOME:
        suffix = ""
    elif raw.startswith(f"{OPENCLAW_HOME}/"):
        suffix = raw[len(OPENCLAW_HOME) + 1 :]
    else:
        suffix = raw

    normalized = normalize_case_path(suffix)
    return f"{OPENCLAW_STATE_TOKEN}/{normalized}"


def normalize_workspace_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if raw == WORKSPACE_TOKEN:
        suffix = ""
    elif raw.startswith(f"{WORKSPACE_TOKEN}/"):
        suffix = raw[len(WORKSPACE_TOKEN) + 1 :]
    elif raw == WORKSPACE_HOME:
        suffix = ""
    elif raw.startswith(f"{WORKSPACE_HOME}/"):
        suffix = raw[len(WORKSPACE_HOME) + 1 :]
    else:
        suffix = raw

    normalized = normalize_case_path(suffix)
    return f"{WORKSPACE_TOKEN}/{normalized}"


def normalize_home_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if raw == HOME_TOKEN:
        suffix = ""
    elif raw.startswith(f"{HOME_TOKEN}/"):
        suffix = raw[len(HOME_TOKEN) + 1 :]
    elif raw == HOME_ALIAS:
        suffix = ""
    elif raw.startswith(f"{HOME_ALIAS}/"):
        suffix = raw[len(HOME_ALIAS) + 1 :]
    elif raw == HOME_ROOT:
        suffix = ""
    elif raw.startswith(f"{HOME_ROOT}/"):
        suffix = raw[len(HOME_ROOT) + 1 :]
    else:
        suffix = raw

    normalized = normalize_case_path(suffix)
    return f"{HOME_TOKEN}/{normalized}"


def normalize_system_path(value: str | None) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    if raw == SYSTEM_TOKEN:
        suffix = ""
    elif raw.startswith(f"{SYSTEM_TOKEN}/"):
        suffix = raw[len(SYSTEM_TOKEN) + 1 :]
    elif raw.startswith("/"):
        suffix = raw.lstrip("/")
    else:
        suffix = raw

    normalized = normalize_case_path(suffix)
    return f"{SYSTEM_TOKEN}/{normalized}"


def logical_path_key(value: str | None) -> str:
    if is_openclaw_home_path(value):
        return normalize_openclaw_home_path(value)
    if is_workspace_path(value):
        return normalize_workspace_path(value)
    if is_home_path(value):
        return normalize_home_path(value)
    if is_system_path(value):
        return normalize_system_path(value)
    return normalize_case_path(value)


def resolve_runtime_path(
    *,
    case_workspace: Path,
    state_dir: Path,
    home_dir: Path | None = None,
    system_dir: Path | None = None,
    value: str | None,
) -> Path:
    if is_openclaw_home_path(value):
        normalized = normalize_openclaw_home_path(value)
        suffix = normalized[len(OPENCLAW_STATE_TOKEN) :].lstrip("/")
        return state_dir / suffix
    if is_workspace_path(value):
        normalized = normalize_workspace_path(value)
        suffix = normalized[len(WORKSPACE_TOKEN) :].lstrip("/")
        return case_workspace / suffix
    if is_home_path(value):
        normalized = normalize_home_path(value)
        suffix = normalized[len(HOME_TOKEN) :].lstrip("/")
        target_root = home_dir or case_workspace
        return target_root / suffix
    if is_system_path(value):
        normalized = normalize_system_path(value)
        suffix = normalized[len(SYSTEM_TOKEN) :].lstrip("/")
        target_root = system_dir or case_workspace
        return target_root / suffix
    return case_workspace / normalize_case_path(value)


def runtime_visible_path(
    *,
    case_workspace: Path,
    value: str | None,
) -> str:
    if is_openclaw_home_path(value):
        normalized = normalize_openclaw_home_path(value)
        suffix = normalized[len(OPENCLAW_STATE_TOKEN) :].lstrip("/")
        return f"{OPENCLAW_HOME}/{suffix}" if suffix else OPENCLAW_HOME
    if is_workspace_path(value):
        normalized = normalize_workspace_path(value)
        suffix = normalized[len(WORKSPACE_TOKEN) :].lstrip("/")
        return f"{WORKSPACE_HOME}/{suffix}" if suffix else WORKSPACE_HOME
    if is_home_path(value):
        normalized = normalize_home_path(value)
        suffix = normalized[len(HOME_TOKEN) :].lstrip("/")
        return f"{HOME_ROOT}/{suffix}" if suffix else HOME_ROOT
    if is_system_path(value):
        normalized = normalize_system_path(value)
        suffix = normalized[len(SYSTEM_TOKEN) :].lstrip("/")
        return f"/{suffix}" if suffix else "/"
    return f"{WORKSPACE_HOME}/{normalize_case_path(value)}"
