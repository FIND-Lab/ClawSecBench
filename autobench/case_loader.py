from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from jsonschema.validators import validator_for

from .case_ids import case_label, matches_case_id_filter
from .models import CaseDefinition, SampleType
from .path_utils import logical_path_key
from .prompt_templates import validate_prompt_templates
from .skill_registry import bundled_skill_names


class CaseLoaderError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parents[1]
CASE_SCHEMA_PATH = ROOT / "schema" / "case.schema.json"


def load_cases(
    cases_dir: Path,
    *,
    case_ids: Iterable[str] | None = None,
    sample_types: Iterable[SampleType] | None = None,
) -> list[CaseDefinition]:
    if not cases_dir.exists():
        raise CaseLoaderError(f"cases directory not found: {cases_dir}")

    selected_case_ids = list(case_ids or [])
    type_set = set(sample_types or [])
    type_text_set = {value.value if isinstance(value, SampleType) else str(value) for value in type_set}

    cases: list[CaseDefinition] = []
    validation_errors: list[str] = []
    for path in sorted(cases_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            validation_errors.append(
                f"case file {path.name} is not valid JSON: line {exc.lineno}, column {exc.colno}: {exc.msg}"
            )
            continue
        raw_metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
        raw_id = raw_metadata.get("id")
        raw_sample_type = raw_metadata.get("sample_type")

        if selected_case_ids and not matches_case_id_filter(raw_id, selected_case_ids):
            continue
        if type_set and str(raw_sample_type) not in type_text_set:
            continue

        schema_errors = validate_case_schema(raw)
        if schema_errors:
            joined = "\n- ".join(schema_errors)
            validation_errors.append(f"{_case_label(path, raw)} is invalid against schema:\n- {joined}")
            continue

        case = CaseDefinition.from_dict(raw)
        case_errors = [
            *validate_prompt_templates(case),
            *validate_inline_skill_names(case),
        ]
        if case_errors:
            joined = "\n- ".join(case_errors)
            validation_errors.append(f"{case_label(case.metadata.id)} is invalid:\n- {joined}")
            continue

        cases.append(case)

    if validation_errors:
        raise CaseLoaderError("\n\n".join(validation_errors))
    if not cases:
        raise CaseLoaderError("no cases matched current filters")

    return cases


@lru_cache(maxsize=1)
def _case_schema_validator() -> Any:
    schema = json.loads(CASE_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


def validate_case_schema(raw: dict[str, Any]) -> list[str]:
    validator = _case_schema_validator()
    errors: list[str] = []
    for error in sorted(validator.iter_errors(raw), key=_validation_error_sort_key):
        location = _format_validation_path(error.absolute_path)
        if location == "$":
            errors.append(error.message)
        else:
            errors.append(f"{location}: {error.message}")
    return errors


def _case_label(path: Path, raw: dict[str, Any]) -> str:
    metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
    case_id = metadata.get("id")
    if case_id is None:
        return f"case file {path.name}"
    try:
        return case_label(case_id)
    except ValueError:
        return f"case {case_id!r}"


def _validation_error_sort_key(error: Any) -> tuple[str, ...]:
    return tuple(str(segment) for segment in error.absolute_path)


def _format_validation_path(path: Any) -> str:
    location = "$"
    for segment in path:
        if isinstance(segment, int):
            location += f"[{segment}]"
        else:
            location += f".{segment}"
    return location


def detect_mixed_overlap(case: CaseDefinition) -> bool:
    if case.metadata.sample_type != SampleType.ATTACK_MIXED:
        return False
    if not case.attack or not case.benign_task:
        return False

    attack_keys = {(c.type, c.path, c.value, c.pattern) for c in case.attack.success_checks}
    benign_keys = {(c.type, c.path, c.value, c.pattern) for c in case.benign_task.success_checks}
    return bool(attack_keys.intersection(benign_keys))


def validate_inline_skill_names(case: CaseDefinition) -> list[str]:
    bundled_lookup = {name.casefold(): name for name in bundled_skill_names()}
    errors: list[str] = []
    for index, env in enumerate(case.procedure.environment):
        if env.kind != "skill" or str(env.payload.get("mode", "")).strip() != "inline":
            continue

        declared_name = str(env.payload.get("name", "")).strip()
        if declared_name:
            bundled_name = bundled_lookup.get(declared_name.casefold())
            if bundled_name is not None:
                errors.append(
                    f"procedure.environment[{index}]: inline skill name collides with bundled skill snapshot: "
                    f"{declared_name}"
                )

        collided_dirs = {
            bundled_name
            for file_item in env.payload.get("files", [])
            if isinstance(file_item, dict)
            for bundled_name in [_bundled_skill_name_for_target(file_item.get("target"), bundled_lookup)]
            if bundled_name is not None
        }
        for bundled_name in sorted(collided_dirs):
            errors.append(
                f"procedure.environment[{index}]: inline skill targets bundled skill directory: {bundled_name}"
            )
    return errors


def _bundled_skill_name_for_target(target: Any, bundled_lookup: dict[str, str]) -> str | None:
    skill_dir = _inline_skill_dir_from_target(target)
    if skill_dir is None:
        return None
    return bundled_lookup.get(skill_dir.casefold())


def _inline_skill_dir_from_target(target: Any) -> str | None:
    target_text = str(target).strip() if target is not None else ""
    if not target_text:
        return None
    try:
        logical_target = logical_path_key(target_text)
    except ValueError:
        return None

    parts = logical_target.split("/")
    for index, part in enumerate(parts):
        if part != "skills":
            continue
        if index + 2 >= len(parts):
            continue
        return parts[index + 1]
    return None
