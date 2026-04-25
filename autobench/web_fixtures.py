from __future__ import annotations

from typing import Any


def web_access(payload: dict[str, Any]) -> str:
    return str(payload.get("access", "")).strip()


def is_private_web_fixture(payload: dict[str, Any]) -> bool:
    return web_access(payload) == "private"


def is_public_web_fixture(payload: dict[str, Any]) -> bool:
    return web_access(payload) == "public"
