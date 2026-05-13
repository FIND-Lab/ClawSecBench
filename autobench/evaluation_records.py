from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import EvaluationResult, SampleType


def load_evaluation_record(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def evaluation_result_from_record(raw: Mapping[str, Any]) -> EvaluationResult | None:
    try:
        quality_flags = raw.get("quality_flags", [])
        if not isinstance(quality_flags, list):
            return None
        check_details = raw.get("check_details", [])
        if not isinstance(check_details, list):
            return None
        skip_reasons = raw.get("skip_reasons", [])
        if not isinstance(skip_reasons, list):
            return None
        return EvaluationResult(
            case_id=str(raw["case_id"]),
            sample_type=SampleType(str(raw["sample_type"])),
            A=raw.get("A"),
            B=raw.get("B"),
            R=raw.get("R"),
            outcome=str(raw["outcome"]),
            quality_flags=[str(item) for item in quality_flags],
            check_details=[item for item in check_details if isinstance(item, dict)],
            skip_reasons=[str(item) for item in skip_reasons],
        )
    except (KeyError, TypeError, ValueError):
        return None


def is_failed_record(raw: Mapping[str, Any]) -> bool:
    return str(raw.get("outcome")) == "runtime_error"


def is_skipped_record(raw: Mapping[str, Any]) -> bool:
    skip_reasons = raw.get("skip_reasons")
    if isinstance(skip_reasons, list) and len(skip_reasons) > 0:
        return True
    return str(raw.get("outcome")) in {"skipped_unsupported", "dry_run"}


def is_resume_reusable_record(raw: Mapping[str, Any]) -> bool:
    return (not is_failed_record(raw)) and (not is_skipped_record(raw))
