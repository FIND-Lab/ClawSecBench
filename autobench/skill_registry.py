from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_SNAPSHOT_PATH = ROOT / "metadata" / "openclaw-skill-snapshots" / "latest-2026-04-25.json"


@lru_cache(maxsize=4)
def load_skill_snapshot(snapshot_path: str | None = None) -> dict[str, Any]:
    path = Path(snapshot_path) if snapshot_path else DEFAULT_SKILL_SNAPSHOT_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def bundled_skill_names(snapshot_path: Path | None = None) -> set[str]:
    payload = load_skill_snapshot(str(snapshot_path) if snapshot_path else None)
    return {
        str(item.get("name", "")).strip()
        for item in payload.get("skills", [])
        if str(item.get("name", "")).strip()
    }


def allowed_skill_references(snapshot_path: Path | None = None) -> set[str]:
    return bundled_skill_names(snapshot_path)
