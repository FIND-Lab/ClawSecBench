from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .case_ids import parse_case_id


class SampleType(str, Enum):
    ATTACK_PURE = "attack_pure"
    ATTACK_MIXED = "attack_mixed"
    BENIGN = "benign"


class SuccessPolicy(str, Enum):
    ALL = "all"
    ANY = "any"


class SuccessMode(str, Enum):
    JUDGE = "judge"
    CHECKS = "checks"


@dataclass
class CheckDefinition:
    type: str
    value: Any | None = None
    pattern: str | None = None
    path: str | None = None
    scope: str | None = None
    criteria: str | None = None
    rubric: str | None = None
    json_path: str | None = None
    operator: str | None = None
    command: str | None = None
    args_contains: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CheckDefinition":
        return cls(
            type=str(raw["type"]).strip(),
            value=raw.get("value"),
            pattern=raw.get("pattern"),
            path=raw.get("path"),
            scope=raw.get("scope"),
            criteria=raw.get("criteria"),
            rubric=raw.get("rubric"),
            json_path=raw.get("json_path"),
            operator=raw.get("operator"),
            command=raw.get("command"),
            args_contains=_string_list(raw.get("args_contains")),
        )


@dataclass
class RefusalCheckDefinition:
    accepted_reasons: list[str]
    scope: str = "final_reply"
    rubric: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RefusalCheckDefinition":
        return cls(
            accepted_reasons=_string_list(raw["accepted_reasons"]),
            scope=str(raw["scope"]),
            rubric=raw.get("rubric"),
        )


@dataclass
class SuccessJudgeDefinition:
    rubric: str
    focus_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SuccessJudgeDefinition":
        return cls(
            rubric=str(raw["rubric"]).strip(),
            focus_paths=_string_list(raw.get("focus_paths")),
        )


@dataclass
class TaskBlock:
    goal: str
    success_mode: SuccessMode
    success_judge: SuccessJudgeDefinition | None
    success_policy: SuccessPolicy
    success_checks: list[CheckDefinition]
    refusal_check: RefusalCheckDefinition | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskBlock":
        policy = SuccessPolicy(str(raw["success_policy"]))
        success_mode = SuccessMode(str(raw["success_mode"]))
        if not isinstance(raw.get("success_judge"), dict):
            raise ValueError("task block is missing required success_judge object")
        success_judge = SuccessJudgeDefinition.from_dict(raw["success_judge"])
        refusal_check = None
        if isinstance(raw.get("refusal_check"), dict):
            refusal_check = RefusalCheckDefinition.from_dict(raw["refusal_check"])
        return cls(
            goal=str(raw["goal"]).strip(),
            success_mode=success_mode,
            success_judge=success_judge,
            success_policy=policy,
            success_checks=[CheckDefinition.from_dict(x) for x in raw["success_checks"]],
            refusal_check=refusal_check,
        )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError(f"expected list of strings, got {type(value).__name__}")


@dataclass
class CaseMetadata:
    id: str
    sample_type: SampleType
    threat_layer: str
    attack_category: str
    name: str
    description: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CaseMetadata":
        return cls(
            id=parse_case_id(raw["id"]),
            sample_type=SampleType(str(raw["sample_type"])),
            threat_layer=str(raw["threat_layer"]),
            attack_category=str(raw["attack_category"]),
            name=str(raw.get("name", "")),
            description=str(raw.get("description", "")),
        )


@dataclass
class ProcedureTurn:
    role: str
    content: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProcedureTurn":
        return cls(role=str(raw["role"]), content=str(raw["content"]))


@dataclass
class EnvironmentItem:
    kind: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EnvironmentItem":
        kind = str(raw["kind"]).strip()
        payload = {k: v for k, v in raw.items() if k != "kind"}
        return cls(kind=kind, payload=payload)


@dataclass
class ProcedureDefinition:
    session_mode: str
    request_timeout_sec: int | None
    turns: list[ProcedureTurn]
    environment: list[EnvironmentItem]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProcedureDefinition":
        return cls(
            session_mode=str(raw["session_mode"]),
            request_timeout_sec=int(raw["request_timeout_sec"]) if raw.get("request_timeout_sec") is not None else None,
            turns=[ProcedureTurn.from_dict(x) for x in raw["turns"]],
            environment=[EnvironmentItem.from_dict(x) for x in raw["environment"]],
        )


@dataclass
class CaseDefinition:
    metadata: CaseMetadata
    procedure: ProcedureDefinition
    attack: TaskBlock | None = None
    benign_task: TaskBlock | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CaseDefinition":
        attack = TaskBlock.from_dict(raw["attack"]) if isinstance(raw.get("attack"), dict) else None
        benign_task = TaskBlock.from_dict(raw["benign_task"]) if isinstance(raw.get("benign_task"), dict) else None
        return cls(
            metadata=CaseMetadata.from_dict(raw["metadata"]),
            procedure=ProcedureDefinition.from_dict(raw["procedure"]),
            attack=attack,
            benign_task=benign_task,
            raw=raw,
        )


@dataclass
class RuntimeResourcesProfile:
    cpus: float | None = None
    memory: str | None = None
    pids_limit: int | None = None


@dataclass
class RuntimeProfile:
    mode: str = "compose"
    gateway_image: str = "ghcr.io/openclaw/openclaw:2026.4.24"
    gateway_internal_port: int = 18789
    gateway_host_port: int = 18789
    gateway_bind: str = "lan"
    service_name: str = "openclaw-gateway"
    gateway_log_level: str | None = None
    gateway_verbose: bool = False
    resources: RuntimeResourcesProfile = field(default_factory=RuntimeResourcesProfile)


@dataclass
class GatewayProfile:
    agent_target: str = "openclaw/default"
    token_env: str = "OPENCLAW_GATEWAY_TOKEN"
    request_timeout_sec: int = 300


@dataclass
class ProviderProfile:
    name: str = "dashscope"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    base_url_env: str | None = "DASHSCOPE_BASE_URL"
    api_key_env: str = "DASHSCOPE_API_KEY"
    model: str = "dashscope/qwen3.6-plus"
    api: str = "openai-completions"
    auth: str = "api-key"


@dataclass
class JudgeProfile:
    base_url: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    cache: bool = True


@dataclass
class ApiProfile:
    name: str
    runtime: RuntimeProfile = field(default_factory=RuntimeProfile)
    gateway: GatewayProfile = field(default_factory=GatewayProfile)
    provider: ProviderProfile = field(default_factory=ProviderProfile)
    judge: JudgeProfile = field(default_factory=JudgeProfile)
    openclaw_extra_config: dict[str, Any] = field(default_factory=dict)

    @property
    def provider_base_url(self) -> str:
        return self.provider.base_url

    @property
    def model(self) -> str:
        return self.provider.model

    @property
    def api_key_env(self) -> str:
        return self.provider.api_key_env

    @property
    def gateway_image(self) -> str:
        return self.runtime.gateway_image

    @property
    def gateway_internal_port(self) -> int:
        return self.runtime.gateway_internal_port

    @property
    def gateway_host_port(self) -> int:
        return self.runtime.gateway_host_port

    @property
    def extra_config(self) -> dict[str, Any]:
        return self.openclaw_extra_config


@dataclass
class RunConfig:
    run_id: str
    cases_dir: Path
    output_root: Path
    profile: ApiProfile
    selected_case_ids: list[str] = field(default_factory=list)
    concurrency: int = 1
    keep_runtime: bool = False
    verbose: bool = True
    dry_run: bool = False
    disable_primary_success_judge: bool = False


@dataclass
class RuntimeHandle:
    run_dir: Path
    runtime_dir: Path
    artifacts_dir: Path
    workspace_dir: Path
    state_dir: Path
    home_dir: Path
    system_dir: Path
    logs_dir: Path
    network_name: str
    container_name: str
    openclaw_config_path: Path
    gateway_url: str
    compose_path: Path | None = None
    compose_project_name: str | None = None


@dataclass
class TurnRecord:
    role: str
    prompt: str
    response_text: str
    prompt_template: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTrace:
    case_id: str
    session_key: str
    turns: list[TurnRecord]


@dataclass
class EvidenceBundle:
    case_id: str
    final_reply: str
    full_reply_text: str
    command_events: list[str] = field(default_factory=list)
    file_snapshot_before: dict[str, str] = field(default_factory=dict)
    file_snapshot_after: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    trace: ConversationTrace | None = None


@dataclass
class EvaluationResult:
    case_id: str
    sample_type: SampleType
    A: bool | None
    B: bool | None
    R: bool | None
    outcome: str
    quality_flags: list[str] = field(default_factory=list)
    check_details: list[dict[str, Any]] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)


@dataclass
class CaseRunResult:
    case: CaseDefinition
    evaluation: EvaluationResult
    evidence_path: Path
    evaluation_path: Path
    executed: bool = True


@dataclass
class RunSummary:
    run_id: str
    total_cases: int
    finished_cases: int
    failed_cases: int
    skipped_cases: int
    by_sample_type: dict[str, int]
    outcome_counts: dict[str, int]
    skip_reason_counts: dict[str, int]
    result_paths: list[str]
