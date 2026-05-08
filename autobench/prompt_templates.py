from __future__ import annotations

import re
from pathlib import Path

from .models import CaseDefinition, EnvironmentItem
from .path_utils import runtime_visible_path


PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\}\}")
FIXTURE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class PromptTemplateError(RuntimeError):
    pass


def validate_prompt_templates(case: CaseDefinition) -> list[str]:
    errors: list[str] = []
    references: dict[str, dict[str, str]] = {}
    seen_ids: set[str] = set()

    for env in case.procedure.environment:
        fixture_id = str(env.payload.get("id", "")).strip()
        if not fixture_id:
            continue
        if not FIXTURE_ID_RE.match(fixture_id):
            errors.append(f"environment id {fixture_id!r} must match {FIXTURE_ID_RE.pattern}")
            continue
        if fixture_id in seen_ids:
            errors.append(f"duplicate environment id: {fixture_id}")
            continue
        seen_ids.add(fixture_id)
        references[fixture_id] = placeholder_fields_for_item(env)

    for index, turn in enumerate(case.procedure.turns, start=1):
        malformed = strip_valid_placeholders(turn.content)
        if "{{" in malformed or "}}" in malformed:
            errors.append(f"turn {index} contains malformed fixture placeholder syntax")

        for fixture_id, field_name in iter_placeholders(turn.content):
            values = references.get(fixture_id)
            if values is None:
                errors.append(f"turn {index} references unknown environment id: {fixture_id}")
                continue
            if field_name not in values:
                supported = ", ".join(sorted(values))
                errors.append(
                    f"turn {index} references unsupported placeholder field {fixture_id}.{field_name}; "
                    f"supported fields: {supported}"
                )

    return errors


def resolve_prompt_template(
    template: str,
    environment: list[EnvironmentItem],
    *,
    overrides: dict[str, dict[str, str]] | None = None,
) -> str:
    references = build_placeholder_references(environment)
    if overrides:
        for fixture_id, values in overrides.items():
            references.setdefault(fixture_id, {}).update(values)

    def replace(match: re.Match[str]) -> str:
        fixture_id, field_name = match.groups()
        try:
            values = references[fixture_id]
        except KeyError as exc:
            raise PromptTemplateError(f"unknown environment id in prompt template: {fixture_id}") from exc
        try:
            return values[field_name]
        except KeyError as exc:
            supported = ", ".join(sorted(values))
            raise PromptTemplateError(
                f"unsupported prompt template field {fixture_id}.{field_name}; supported fields: {supported}"
            ) from exc

    resolved = PLACEHOLDER_RE.sub(replace, template)
    malformed = strip_valid_placeholders(resolved)
    if "{{" in malformed or "}}" in malformed:
        raise PromptTemplateError("malformed fixture placeholder syntax")
    return resolved


def iter_placeholders(text: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(2)) for match in PLACEHOLDER_RE.finditer(text)]


def strip_valid_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub("", text)


def build_placeholder_references(environment: list[EnvironmentItem]) -> dict[str, dict[str, str]]:
    references: dict[str, dict[str, str]] = {}
    for env in environment:
        fixture_id = str(env.payload.get("id", "")).strip()
        if not fixture_id:
            continue
        if not FIXTURE_ID_RE.match(fixture_id):
            raise PromptTemplateError(f"environment id {fixture_id!r} must match {FIXTURE_ID_RE.pattern}")
        if fixture_id in references:
            raise PromptTemplateError(f"duplicate environment id: {fixture_id}")
        references[fixture_id] = placeholder_fields_for_item(env)
    return references


def build_runtime_path_overrides(
    environment: list[EnvironmentItem],
    *,
    case_workspace: Path,
) -> dict[str, dict[str, str]]:
    overrides: dict[str, dict[str, str]] = {}
    for env in environment:
        fixture_id = str(env.payload.get("id", "")).strip()
        if not fixture_id:
            continue
        if env.kind in {"file", "document"}:
            target = str(env.payload.get("target", "")).strip()
            if not target:
                continue
            runtime_target = runtime_visible_path(
                case_workspace=case_workspace,
                value=target,
            )
            overrides.setdefault(fixture_id, {})["target"] = runtime_target
            continue
    return overrides


def placeholder_fields_for_item(item: EnvironmentItem) -> dict[str, str]:
    payload = item.payload
    values: dict[str, str] = {}

    name = str(payload.get("name", "")).strip()
    if name:
        values["name"] = name

    if item.kind in {"file", "document"}:
        target = str(payload.get("target", "")).strip()
        if target:
            values["target"] = target
            values["basename"] = Path(target.replace("\\", "/")).name or target
        return values

    if item.kind == "web":
        url = str(payload.get("url", "")).strip()
        if url:
            values["url"] = url
        return values

    if item.kind == "skill":
        reference = str(payload.get("reference", "")).strip()
        if reference:
            values["reference"] = reference
        return values

    return values
