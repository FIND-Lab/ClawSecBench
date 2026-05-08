from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CaseDefinition, EnvironmentItem, RuntimeHandle
from .path_utils import logical_path_key, resolve_runtime_path
from .web_fixtures import is_private_web_fixture, is_public_web_fixture


OPENCLAW_CONFIG_LOGICAL_PATH = "$OPENCLAW_STATE/openclaw.json"


class FixtureBuilder:
    def build(self, case: CaseDefinition, runtime: RuntimeHandle) -> dict[str, Any]:
        case_workspace = runtime.workspace_dir
        case_workspace.mkdir(parents=True, exist_ok=True)

        web_root = case_workspace / "web-fixtures"
        skill_root = case_workspace / "skills"

        created_paths: list[str] = []
        tracked_paths: dict[str, str] = {}
        for env in case.procedure.environment:
            created, tracked = self._apply_environment_item(
                env,
                case_workspace,
                runtime.state_dir,
                runtime.home_dir,
                runtime.system_dir,
                web_root,
                skill_root,
            )
            created_paths.extend(created)
            tracked_paths.update(tracked)

        tracked_paths.update(
            self._collect_check_tracked_paths(
                case,
                case_workspace=case_workspace,
                state_dir=runtime.state_dir,
                home_dir=runtime.home_dir,
                system_dir=runtime.system_dir,
            )
        )

        snapshot_before = snapshot_tree(case_workspace)
        snapshot_before.update(snapshot_selected_paths({key: Path(path) for key, path in tracked_paths.items()}))

        return {
            "case_id": case.metadata.id,
            "case_workspace": case_workspace,
            "created_paths": created_paths,
            "tracked_paths": tracked_paths,
            "snapshot_before": snapshot_before,
            "web_root": web_root,
            "skill_root": skill_root,
        }

    def _collect_check_tracked_paths(
        self,
        case: CaseDefinition,
        *,
        case_workspace: Path,
        state_dir: Path,
        home_dir: Path,
        system_dir: Path,
    ) -> dict[str, str]:
        raw_paths: list[str] = []

        for block in (case.benign_task, case.attack):
            if not block:
                continue
            for chk in block.success_checks:
                if chk.path:
                    raw_paths.append(chk.path)
            if block.success_judge and block.success_judge.focus_paths:
                raw_paths.extend(block.success_judge.focus_paths)

        tracked_paths: dict[str, str] = {}
        for raw_path in raw_paths:
            logical_target = logical_path_key(raw_path)
            if logical_target.startswith("$WORKSPACE/"):
                continue
            target_path = resolve_runtime_path(
                case_workspace=case_workspace,
                state_dir=state_dir,
                home_dir=home_dir,
                system_dir=system_dir,
                value=raw_path,
            )
            tracked_paths[logical_target] = target_path.as_posix()
        return tracked_paths

    def _apply_environment_item(
        self,
        item: EnvironmentItem,
        case_workspace: Path,
        state_dir: Path,
        home_dir: Path,
        system_dir: Path,
        web_root: Path,
        skill_root: Path,
    ) -> tuple[list[str], dict[str, str]]:
        kind = item.kind
        payload = item.payload

        if kind in {"file", "document"}:
            return self._materialize_file_like_fixture(
                target=payload.get("target"),
                content=str(payload.get("content", "")),
                mtime=payload.get("mtime"),
                case_workspace=case_workspace,
                state_dir=state_dir,
                home_dir=home_dir,
                system_dir=system_dir,
            )

        if kind == "web":
            access = str(payload.get("access", "")).strip()
            if is_public_web_fixture(payload):
                return [], {}
            if is_private_web_fixture(payload):
                raise ValueError("private web fixtures are declared in schema but runtime support is not implemented yet")
            raise ValueError(f"web fixture has unsupported access mode: {access!r}")

        if kind == "skill":
            mode = str(payload.get("mode", "")).strip()
            if mode == "reference":
                return [], {}
            if mode == "inline":
                created_paths: list[str] = []
                tracked_paths: dict[str, str] = {}
                for file_item in payload.get("files", []):
                    if not isinstance(file_item, dict):
                        continue
                    created, tracked = self._materialize_file_like_fixture(
                        target=file_item.get("target"),
                        content=str(file_item.get("content", "")),
                        mtime=file_item.get("mtime"),
                        case_workspace=case_workspace,
                        state_dir=state_dir,
                        home_dir=home_dir,
                        system_dir=system_dir,
                    )
                    created_paths.extend(created)
                    tracked_paths.update(tracked)
                return created_paths, tracked_paths
            raise ValueError(f"skill fixture has unsupported mode: {mode!r}")

        raise ValueError(f"environment item has unsupported kind: {kind!r}")

    def _materialize_file_like_fixture(
        self,
        *,
        target: Any,
        content: str,
        mtime: Any,
        case_workspace: Path,
        state_dir: Path,
        home_dir: Path,
        system_dir: Path,
    ) -> tuple[list[str], dict[str, str]]:
        target_text = str(target).strip() if target is not None else ""
        if not target_text:
            raise ValueError("file-like fixture is missing required target")

        logical_target = logical_path_key(target_text)
        target_path = resolve_runtime_path(
            case_workspace=case_workspace,
            state_dir=state_dir,
            home_dir=home_dir,
            system_dir=system_dir,
            value=target_text,
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if logical_target == OPENCLAW_CONFIG_LOGICAL_PATH:
            merge_openclaw_config_fixture(target_path, content)
        else:
            target_path.write_text(content, encoding="utf-8")
        if mtime is not None:
            apply_fixture_mtime(target_path, mtime)
        tracked = {logical_target: target_path.as_posix()}
        return [target_path.as_posix()], tracked


def snapshot_tree(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        entry = snapshot_value(path)
        if entry is None:
            continue
        rel = path.relative_to(root).as_posix()
        snapshot[rel] = entry
    return snapshot


def snapshot_selected_paths(paths: dict[str, Path]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for logical_key, path in sorted(paths.items()):
        entry = snapshot_value(path)
        if entry is None:
            continue
        snapshot[logical_key] = entry
    return snapshot


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_value(path: Path) -> str | None:
    if path.is_symlink():
        return f"symlink:{os.readlink(path)}"
    if path.is_file():
        return sha256_file(path)
    return None


def apply_fixture_mtime(path: Path, value: Any) -> None:
    timestamp = parse_fixture_timestamp(value)
    os.utime(path, (timestamp, timestamp))


def merge_openclaw_config_fixture(path: Path, content: str) -> None:
    base_payload: dict[str, Any] = {}
    if path.exists():
        base_payload = parse_json_object_fixture(
            path.read_text(encoding="utf-8"),
            source=f"existing OpenClaw config at {path}",
        )
    overlay_payload = parse_json_object_fixture(
        content,
        source=f"fixture content for {OPENCLAW_CONFIG_LOGICAL_PATH}",
    )
    merged_payload = deep_merge_json_objects(base_payload, overlay_payload)
    path.write_text(json.dumps(merged_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_json_object_fixture(content: str, *, source: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} must be valid JSON object text") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must decode to a JSON object")
    return payload


def deep_merge_json_objects(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_json_objects(merged[key], value)
        else:
            merged[key] = value
    return merged


def parse_fixture_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid fixture mtime: {value!r}")

    text = value.strip()
    normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()
