from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .case_ids import coerce_case_id
from .evaluation_records import is_failed_record, is_skipped_record, load_evaluation_record
from .models import CaseRunResult, RunSummary

if TYPE_CHECKING:
    from .models import CaseDefinition
    from .runtime_support import UnsupportedRuntimeFeature


class Reporter:
    def build_summary(self, run_id: str, results: list[CaseRunResult], output_dir: Path) -> RunSummary:
        by_sample_type = Counter(item.case.metadata.sample_type.value for item in results)
        outcome_counts = Counter(item.evaluation.outcome for item in results)
        skip_reason_counts = Counter(
            reason for item in results if not item.executed for reason in item.evaluation.skip_reasons
        )
        records = [asdict(item.evaluation) for item in results]
        skipped_cases = sum(1 for record in records if is_skipped_record(record))
        failed_cases = sum(1 for record in records if is_failed_record(record))

        summary = RunSummary(
            run_id=run_id,
            total_cases=len(results),
            finished_cases=len(results) - skipped_cases - failed_cases,
            failed_cases=failed_cases,
            skipped_cases=skipped_cases,
            by_sample_type=dict(by_sample_type),
            outcome_counts=dict(outcome_counts),
            skip_reason_counts=dict(skip_reason_counts),
            result_paths=[str(item.evaluation_path) for item in results],
        )

        summary_path = output_dir / "summary.json"
        summary_path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")

        report_path = output_dir / "report.md"
        report_path.write_text(self._render_markdown(summary), encoding="utf-8")
        return summary

    def rebuild_summary_from_run_dir(self, run_id: str, output_dir: Path) -> RunSummary:
        evaluation_paths = sorted(output_dir.glob("cases/case-*/artifacts/case-*-evaluation.json"))
        if not evaluation_paths:
            raise FileNotFoundError(f"no evaluation artifacts found under {output_dir}")
        records: list[dict] = []
        for path in evaluation_paths:
            record = load_evaluation_record(path)
            if record is not None:
                records.append(record)

        by_sample_type = Counter(str(record["sample_type"]) for record in records)
        outcome_counts = Counter(str(record["outcome"]) for record in records)
        skip_reason_counts = Counter(
            reason
            for record in records
            for reason in record.get("skip_reasons", [])
        )

        summary = RunSummary(
            run_id=run_id,
            total_cases=len(records),
            finished_cases=sum(
                1 for record in records if not is_skipped_record(record) and not is_failed_record(record)
            ),
            failed_cases=sum(1 for record in records if is_failed_record(record)),
            skipped_cases=sum(1 for record in records if is_skipped_record(record)),
            by_sample_type=dict(by_sample_type),
            outcome_counts=dict(outcome_counts),
            skip_reason_counts=dict(skip_reason_counts),
            result_paths=[str(path) for path in evaluation_paths],
        )

        summary_path = output_dir / "summary.json"
        summary_path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")

        report_path = output_dir / "report.md"
        report_path.write_text(self._render_markdown(summary), encoding="utf-8")
        return summary

    def update_run_manifest(self, run_id: str, output_dir: Path, summary: RunSummary) -> dict:
        manifest_path = output_dir / "run_manifest.json"
        manifest: dict[str, object]
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {"run_id": run_id}
        manifest["case_count"] = summary.total_cases
        manifest["summary"] = asdict(summary)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def build_sample_distribution_report(
        self,
        run_id: str,
        case_support: list[tuple["CaseDefinition", list["UnsupportedRuntimeFeature"]]],
        output_dir: Path,
    ) -> Path:
        report_path = output_dir / "case.md"
        report_path.write_text(self._render_sample_distribution_markdown(run_id, case_support), encoding="utf-8")
        return report_path

    def _render_markdown(self, summary: RunSummary) -> str:
        lines = [
            "# AutoBench Run Report",
            "",
            f"- run_id: {summary.run_id}",
            f"- total_cases: {summary.total_cases}",
            f"- finished_cases: {summary.finished_cases}",
            f"- failed_cases: {summary.failed_cases}",
            f"- skipped_cases: {summary.skipped_cases}",
            "",
            "## By Sample Type",
            "",
        ]
        for key, value in sorted(summary.by_sample_type.items()):
            lines.append(f"- {key}: {value}")

        lines.extend(["", "## Outcomes", ""])
        for key, value in sorted(summary.outcome_counts.items()):
            lines.append(f"- {key}: {value}")

        if summary.skip_reason_counts:
            lines.extend(["", "## Skip Reasons", ""])
            for key, value in sorted(summary.skip_reason_counts.items()):
                lines.append(f"- {key}: {value}")

        failed_rows = []
        for record in self._load_report_records(summary):
            if not is_failed_record(record):
                continue
            failed_rows.append(self._failure_row(record))
        if failed_rows:
            lines.extend(["", "## Failed Cases", ""])
            lines.extend(
                self._render_markdown_table(
                    ["case_id", "sample_type", "outcome", "stage", "error"],
                    failed_rows,
                )
            )

        return "\n".join(lines)

    def _render_sample_distribution_markdown(
        self,
        run_id: str,
        case_support: list[tuple["CaseDefinition", list["UnsupportedRuntimeFeature"]]],
    ) -> str:
        reason_counts = Counter(feature.code for _, features in case_support for feature in features)
        supported_count = sum(1 for _, features in case_support if not features)
        unsupported_count = len(case_support) - supported_count
        by_sample_type = Counter(case.metadata.sample_type.value for case, _ in case_support)
        by_threat_layer = Counter(case.metadata.threat_layer for case, _ in case_support)
        by_attack_category = Counter(case.metadata.attack_category for case, _ in case_support)
        by_environment_signature = Counter(self._case_environment_signature(case) for case, _ in case_support)

        lines = [
            "# 样本分布报告",
            "",
            "## 运行概览",
            "",
            f"- 运行 ID：{run_id}",
            f"- Case 总数：{len(case_support)}",
            f"- 可运行：{supported_count}",
            f"- 暂不支持：{unsupported_count}",
            "",
        ]

        lines.extend(["## 分类汇总", ""])
        lines.extend(
            self._render_markdown_table(
                ["维度", "项", "数量"],
                [
                    ("样本类型", key, str(value))
                    for key, value in self._sorted_counter_items(by_sample_type)
                ]
                + [
                    ("威胁层", key, str(value))
                    for key, value in self._sorted_counter_items(by_threat_layer)
                ]
                + [
                    ("攻击类别", key, str(value))
                    for key, value in self._sorted_counter_items(by_attack_category)
                ]
                + [
                    ("环境组合", key, str(value))
                    for key, value in self._sorted_counter_items(by_environment_signature)
                ],
            )
        )

        if reason_counts:
            lines.extend(["", "## 暂不支持原因", ""])
            lines.extend(
                self._render_markdown_table(
                    ["原因", "数量"],
                    [
                        (self._unsupported_reason_label(key), str(value))
                        for key, value in self._sorted_counter_items(reason_counts)
                    ],
                )
            )

        unsupported_rows = [
            (
                case.metadata.id,
                case.metadata.threat_layer,
                case.metadata.attack_category,
                self._case_environment_summary(case),
                "；".join(self._format_unsupported_feature(feature) for feature in features),
            )
            for case, features in case_support
            if features
        ]
        if unsupported_rows:
            lines.extend(["", "## 暂不支持 Case", ""])
            lines.extend(
                self._render_markdown_table(
                    ["Case", "威胁层", "攻击类别", "环境", "原因"],
                    unsupported_rows,
                )
            )

        lines.extend(["", "## Case 概览", ""])
        lines.extend(
            self._render_markdown_table(
                ["Case", "样本类型", "威胁层", "攻击类别", "会话模式", "轮数", "环境", "状态", "备注"],
                [
                    (
                        case.metadata.id,
                        case.metadata.sample_type.value,
                        case.metadata.threat_layer,
                        case.metadata.attack_category,
                        case.procedure.session_mode,
                        str(len(case.procedure.turns)),
                        self._case_environment_summary(case),
                        "可运行" if not features else "暂不支持",
                        "；".join(self._format_unsupported_feature(feature) for feature in features) if features else "-",
                    )
                    for case, features in case_support
                ],
            )
        )

        return "\n".join(lines)

    def _case_environment_summary(self, case: "CaseDefinition") -> str:
        if not case.procedure.environment:
            return "无"

        counts: Counter[str] = Counter()
        for env in case.procedure.environment:
            label = env.kind
            if env.kind == "web":
                access = str(env.payload.get("access", "")).strip()
                if access:
                    label = f"{label}:{access}"
            counts[label] += 1
        items = [
            f"{label}×{count}" if count > 1 else label
            for label, count in self._sorted_counter_items(counts)
        ]
        return ", ".join(items)

    def _case_environment_signature(self, case: "CaseDefinition") -> str:
        if not case.procedure.environment:
            return "none"
        labels = set()
        for env in case.procedure.environment:
            label = env.kind
            if env.kind == "web":
                access = str(env.payload.get("access", "")).strip()
                if access:
                    label = f"{label}:{access}"
            labels.add(label)
        return "+".join(sorted(labels))

    def _unsupported_reason_label(self, value: str) -> str:
        return {
            "email": "邮件环境未实现",
            "private_web": "私有网页未实现",
            "reset_each_turn": "逐轮重置会话未实现",
            "skill_reference": "技能引用已禁用",
        }.get(value, value)

    def _format_unsupported_feature(self, feature: "UnsupportedRuntimeFeature") -> str:
        if feature.code == "skill_reference":
            prefix = "skill reference fixtures are disabled by benchmark policy; use inline/manual skill files instead: "
            refs = feature.message[len(prefix) :] if feature.message.startswith(prefix) else feature.message
            return f"技能引用已禁用：{refs}"
        return self._unsupported_reason_label(feature.code)

    def _sorted_counter_items(self, counter: Counter[str]) -> list[tuple[str, int]]:
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))

    def _render_markdown_table(self, headers: list[str], rows: list[tuple[str, ...]]) -> list[str]:
        if not rows:
            return ["- 无"]
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for row in rows:
            sanitized = [str(cell).replace("\n", " ").replace("|", "\\|").strip() for cell in row]
            lines.append("| " + " | ".join(sanitized) + " |")
        return lines

    def _load_report_records(self, summary: RunSummary) -> list[dict]:
        records: list[dict] = []
        for path_text in summary.result_paths:
            path = Path(path_text)
            if not path.exists():
                continue
            record = load_evaluation_record(path)
            if record is None:
                continue
            records.append(record)
        return records

    def _failure_row(self, record: dict) -> tuple[str, str, str, str, str]:
        stage = "-"
        message = "-"
        for detail in record.get("check_details", []):
            if not isinstance(detail, dict) or detail.get("block") != "runtime.error":
                continue
            stage = str(detail.get("stage", "-"))
            message = str(detail.get("message", "-"))
            break
        return (
            self._format_case_id(record.get("case_id")),
            str(record.get("sample_type", "-")),
            str(record.get("outcome", "-")),
            stage,
            message,
        )

    def _format_case_id(self, value: object) -> str:
        try:
            return coerce_case_id(value)
        except ValueError:
            return str(value if value is not None else "-")
