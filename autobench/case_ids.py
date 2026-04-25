from __future__ import annotations

import re
from typing import Any, Iterable


CASE_ID_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def parse_case_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("metadata.id must be a non-empty string")
    return _normalize_case_id_text(value)


def coerce_case_id(value: Any) -> str:
    if value is None or isinstance(value, bool):
        raise ValueError("case id must be a non-empty string")
    return _normalize_case_id_text(str(value))


def case_id_matches(actual: Any, expected: Any) -> bool:
    actual_text = coerce_case_id(actual)
    expected_text = coerce_case_id(expected)
    if actual_text == expected_text:
        return True

    actual_number = _numeric_case_id(actual_text)
    expected_number = _numeric_case_id(expected_text)
    return actual_number is not None and actual_number == expected_number


def matches_case_id_filter(case_id: Any, selected_case_ids: Iterable[Any]) -> bool:
    return any(case_id_matches(case_id, selected_id) for selected_id in selected_case_ids)


def case_label(case_id: Any) -> str:
    return f"case {coerce_case_id(case_id)}"


def case_dirname(case_id: Any) -> str:
    return f"case-{case_id_path_token(case_id)}"


def case_artifact_stem(case_id: Any) -> str:
    return case_dirname(case_id)


def case_artifact_name(case_id: Any, suffix: str, *, extension: str = "json") -> str:
    stem = case_artifact_stem(case_id)
    return f"{stem}-{suffix}.{extension}"


def case_id_path_token(case_id: Any) -> str:
    text = coerce_case_id(case_id)
    if not CASE_ID_PATH_RE.fullmatch(text):
        raise ValueError(
            "metadata.id must match ^[A-Za-z0-9][A-Za-z0-9_-]*$ so it can be used in runtime artifact paths"
        )
    return text


def _normalize_case_id_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("case id must be a non-empty string")
    return text


def _numeric_case_id(value: str) -> int | None:
    if not value.isdigit():
        return None
    return int(value)
