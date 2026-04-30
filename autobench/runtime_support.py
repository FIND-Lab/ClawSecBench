from __future__ import annotations

from dataclasses import dataclass

from .models import CaseDefinition
from .web_fixtures import is_private_web_fixture


@dataclass(frozen=True)
class UnsupportedRuntimeFeature:
    code: str
    message: str


EMAIL_FEATURE = UnsupportedRuntimeFeature(
    code="email",
    message="email fixtures are declared in schema but runtime support is not implemented yet",
)
PRIVATE_WEB_FEATURE = UnsupportedRuntimeFeature(
    code="private_web",
    message="private web fixtures are declared in schema but runtime support is not implemented yet",
)
RESET_EACH_TURN_FEATURE = UnsupportedRuntimeFeature(
    code="reset_each_turn",
    message="session_mode=reset_each_turn is declared in schema but runtime support is not implemented yet",
)
SKILL_REFERENCE_FEATURE_CODE = "skill_reference"


def detect_unsupported_runtime_features(case: CaseDefinition) -> list[UnsupportedRuntimeFeature]:
    features: list[UnsupportedRuntimeFeature] = []
    seen: set[str] = set()
    if case.procedure.session_mode == "reset_each_turn":
        seen.add(RESET_EACH_TURN_FEATURE.code)
        features.append(RESET_EACH_TURN_FEATURE)

    declared_skill_references: list[str] = []
    for env in case.procedure.environment:
        feature: UnsupportedRuntimeFeature | None = None
        if env.kind == "email":
            feature = EMAIL_FEATURE
        elif env.kind == "web" and is_private_web_fixture(env.payload):
            feature = PRIVATE_WEB_FEATURE
        elif env.kind == "skill" and str(env.payload.get("mode", "")).strip() == "reference":
            reference = str(env.payload.get("reference", "")).strip()
            if reference:
                declared_skill_references.append(reference)
        if feature is None or feature.code in seen:
            continue
        seen.add(feature.code)
        features.append(feature)

    if declared_skill_references and SKILL_REFERENCE_FEATURE_CODE not in seen:
        declared_refs = ", ".join(sorted(set(declared_skill_references)))
        features.append(
            UnsupportedRuntimeFeature(
                code=SKILL_REFERENCE_FEATURE_CODE,
                message=(
                    "skill reference fixtures are disabled by benchmark policy; "
                    f"use inline/manual skill files instead: {declared_refs}"
                ),
            )
        )
    return features
