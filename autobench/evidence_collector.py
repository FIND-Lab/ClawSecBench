from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .case_ids import case_artifact_name
from .fixture_builder import snapshot_selected_paths, snapshot_tree
from .models import CaseDefinition, EvidenceBundle, RuntimeHandle


class EvidenceCollector:
    COMMAND_HINT_RE = re.compile(r"\b(curl|bash|sh|python|node|rm|chmod|env|printenv|cat)\b", re.IGNORECASE)
    STRUCTURED_EVENT_SUFFIXES = {".json", ".jsonl", ".ndjson"}
    SESSION_TRAJECTORY_GLOB = "*.trajectory.jsonl"
    COMMAND_KEYS = {
        "argv",
        "cmd",
        "command",
        "command_line",
        "executable",
        "script",
        "shell_command",
    }

    def collect(
        self,
        case: CaseDefinition,
        runtime: RuntimeHandle,
        fixture_manifest: dict[str, Any],
        trace: Any,
    ) -> EvidenceBundle:
        final_reply = trace.turns[-1].response_text if trace.turns else ""
        full_reply = "\n\n".join(turn.response_text for turn in trace.turns)

        command_events = self._collect_command_events(runtime, trace)
        session_diagnostics = self._collect_session_diagnostics(runtime, trace)

        case_workspace = Path(fixture_manifest["case_workspace"])
        tracked_paths = {
            str(key): Path(path)
            for key, path in dict(fixture_manifest.get("tracked_paths", {})).items()
        }
        snapshot_before = dict(fixture_manifest.get("snapshot_before", {}))
        snapshot_after = snapshot_tree(case_workspace)
        snapshot_after.update(snapshot_selected_paths(tracked_paths))

        bundle = EvidenceBundle(
            case_id=case.metadata.id,
            final_reply=final_reply,
            full_reply_text=full_reply,
            command_events=command_events,
            file_snapshot_before=snapshot_before,
            file_snapshot_after=snapshot_after,
            session_diagnostics=session_diagnostics,
            artifacts={
                "trace_file": str(runtime.artifacts_dir / case_artifact_name(case.metadata.id, "trace")),
                "workspace": str(case_workspace),
                "openclaw_state_dir": str(runtime.state_dir),
                "home_dir": str(runtime.home_dir),
                "system_dir": str(runtime.system_dir),
            },
            trace=trace,
        )

        out_path = runtime.artifacts_dir / case_artifact_name(case.metadata.id, "evidence")
        out_path.write_text(json.dumps(asdict(bundle), ensure_ascii=False, indent=2), encoding="utf-8")
        return bundle

    def _collect_command_events(self, runtime: RuntimeHandle, trace: Any | None = None) -> list[str]:
        events: list[str] = []
        events.extend(self._collect_trace_command_events(trace))

        for root in (runtime.logs_dir, runtime.state_dir):
            events.extend(self._collect_structured_command_events(root))
        events.extend(self._collect_log_line_command_events(runtime.logs_dir))

        return _dedupe(events)

    def _collect_session_diagnostics(self, runtime: RuntimeHandle, trace: Any | None = None) -> list[dict[str, Any]]:
        session_key = getattr(trace, "session_key", None)
        if not session_key:
            return []

        sessions_dir = runtime.state_dir / "agents" / "main" / "sessions"
        if not sessions_dir.exists():
            return []

        diagnostics: list[dict[str, Any]] = []
        for path in sorted(sessions_dir.rglob(self.SESSION_TRAJECTORY_GLOB)):
            diagnostic = self._parse_session_trajectory(path, session_key=session_key)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return diagnostics

    def _parse_session_trajectory(self, path: Path, *, session_key: str) -> dict[str, Any] | None:
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return None

        diagnostic: dict[str, Any] = {
            "session_key": session_key,
            "trajectory_file": str(path),
            "session_id": None,
            "final_status": None,
            "session_status": None,
            "timed_out": False,
            "idle_timed_out": False,
            "timed_out_during_compaction": False,
            "external_abort": False,
            "aborted": False,
            "prompt_error": None,
            "prompt_error_source": None,
            "assistant_texts_count": 0,
        }
        matched = False

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("traceSchema") != "openclaw-trajectory":
                continue
            if payload.get("sessionKey") != session_key:
                continue

            matched = True
            diagnostic["session_id"] = payload.get("sessionId") or diagnostic["session_id"]
            data = payload.get("data", {})
            event_type = payload.get("type")

            if event_type == "model.completed":
                diagnostic["aborted"] = bool(data.get("aborted")) or diagnostic["aborted"]
                diagnostic["external_abort"] = bool(data.get("externalAbort")) or diagnostic["external_abort"]
                diagnostic["timed_out"] = bool(data.get("timedOut")) or diagnostic["timed_out"]
                diagnostic["idle_timed_out"] = bool(data.get("idleTimedOut")) or diagnostic["idle_timed_out"]
                diagnostic["timed_out_during_compaction"] = bool(
                    data.get("timedOutDuringCompaction")
                ) or diagnostic["timed_out_during_compaction"]
                diagnostic["prompt_error"] = data.get("promptError") or diagnostic["prompt_error"]
                diagnostic["prompt_error_source"] = data.get("promptErrorSource") or diagnostic["prompt_error_source"]
                assistant_texts = data.get("assistantTexts")
                if isinstance(assistant_texts, list):
                    diagnostic["assistant_texts_count"] = max(
                        diagnostic["assistant_texts_count"],
                        len(assistant_texts),
                    )
            elif event_type == "trace.artifacts":
                diagnostic["final_status"] = data.get("finalStatus") or diagnostic["final_status"]
                diagnostic["aborted"] = bool(data.get("aborted")) or diagnostic["aborted"]
                diagnostic["external_abort"] = bool(data.get("externalAbort")) or diagnostic["external_abort"]
                diagnostic["timed_out"] = bool(data.get("timedOut")) or diagnostic["timed_out"]
                diagnostic["idle_timed_out"] = bool(data.get("idleTimedOut")) or diagnostic["idle_timed_out"]
                diagnostic["timed_out_during_compaction"] = bool(
                    data.get("timedOutDuringCompaction")
                ) or diagnostic["timed_out_during_compaction"]
                diagnostic["prompt_error"] = data.get("promptError") or diagnostic["prompt_error"]
                diagnostic["prompt_error_source"] = data.get("promptErrorSource") or diagnostic["prompt_error_source"]
                assistant_texts = data.get("assistantTexts")
                if isinstance(assistant_texts, list):
                    diagnostic["assistant_texts_count"] = max(
                        diagnostic["assistant_texts_count"],
                        len(assistant_texts),
                    )
            elif event_type == "session.ended":
                diagnostic["session_status"] = data.get("status") or diagnostic["session_status"]
                diagnostic["aborted"] = bool(data.get("aborted")) or diagnostic["aborted"]
                diagnostic["external_abort"] = bool(data.get("externalAbort")) or diagnostic["external_abort"]
                diagnostic["timed_out"] = bool(data.get("timedOut")) or diagnostic["timed_out"]
                diagnostic["idle_timed_out"] = bool(data.get("idleTimedOut")) or diagnostic["idle_timed_out"]
                diagnostic["timed_out_during_compaction"] = bool(
                    data.get("timedOutDuringCompaction")
                ) or diagnostic["timed_out_during_compaction"]
                diagnostic["prompt_error"] = data.get("promptError") or diagnostic["prompt_error"]
                diagnostic["prompt_error_source"] = data.get("promptErrorSource") or diagnostic["prompt_error_source"]

        if not matched:
            return None

        diagnostic["error"] = any(
            (
                diagnostic["final_status"] == "error",
                diagnostic["session_status"] == "error",
                diagnostic["timed_out"],
                diagnostic["idle_timed_out"],
                bool(diagnostic["prompt_error"]),
            )
        )
        return diagnostic

    def _collect_trace_command_events(self, trace: Any | None) -> list[str]:
        events: list[str] = []
        if trace is None:
            return events
        for turn in getattr(trace, "turns", []):
            events.extend(_extract_commands(getattr(turn, "raw_response", None)))
        return events

    def _collect_structured_command_events(self, root: Path) -> list[str]:
        events: list[str] = []
        if not root.exists():
            return events

        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.STRUCTURED_EVENT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if path.suffix.lower() == ".json":
                try:
                    events.extend(_extract_commands(json.loads(text)))
                except json.JSONDecodeError:
                    continue
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    events.extend(_extract_commands(json.loads(line)))
                except json.JSONDecodeError:
                    continue

        return events

    def _collect_log_line_command_events(self, logs_dir: Path) -> list[str]:
        events: list[str] = []
        if not logs_dir.exists():
            return events

        for log in sorted(logs_dir.rglob("*.log")):
            try:
                text = log.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                if self.COMMAND_HINT_RE.search(line):
                    events.append(line.strip())
        return events


def _extract_commands(value: Any) -> list[str]:
    events: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in EvidenceCollector.COMMAND_KEYS:
                command = _command_to_text(item)
                if command:
                    events.append(command)
            events.extend(_extract_commands(item))
        return events

    if isinstance(value, list):
        for item in value:
            events.extend(_extract_commands(item))
    return events


def _command_to_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        parts = [str(part) for part in value]
        return " ".join(parts).strip() or None
    if isinstance(value, dict):
        for key in ("command", "cmd", "shell_command", "argv"):
            if key in value:
                return _command_to_text(value[key])
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
