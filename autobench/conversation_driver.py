from __future__ import annotations

import http.client
import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .case_ids import case_artifact_name, case_label
from .logging_utils import ProgressLogger
from .models import CaseDefinition, ConversationTrace, RuntimeHandle, TurnRecord
from .prompt_templates import build_runtime_path_overrides, resolve_prompt_template


class ConversationDriverError(RuntimeError):
    pass


class ConversationDriver:
    def __init__(self, logger: ProgressLogger | None = None) -> None:
        self.logger = logger or ProgressLogger()

    def run_case(
        self,
        case: CaseDefinition,
        runtime: RuntimeHandle,
        fixture_manifest: dict[str, Any],
        *,
        agent_target: str,
        backend_model: str,
        gateway_token: str | None = None,
        request_timeout_sec: int = 300,
    ) -> ConversationTrace:
        if case.procedure.session_mode != "single_session":
            raise ConversationDriverError(
                f"unsupported session_mode for current runner: "
                f"{case.procedure.session_mode}; only single_session is supported"
            )

        session_key = f"case-{case.metadata.id}-{uuid.uuid4().hex[:8]}"
        turns: list[TurnRecord] = []
        placeholder_overrides = build_runtime_path_overrides(
            case.procedure.environment,
            case_workspace=Path(fixture_manifest["case_workspace"]),
        )

        user_turns = [turn for turn in case.procedure.turns if turn.role == "user"]
        for index, turn in enumerate(user_turns, start=1):
            if turn.role != "user":
                continue

            resolved_prompt = resolve_prompt_template(
                turn.content,
                case.procedure.environment,
                overrides=placeholder_overrides,
            )
            self.logger.info(f"{case_label(case.metadata.id)}: sending turn {index}/{len(user_turns)}")
            started_at = time.monotonic()
            response_json = self._send_chat_completion(
                base_url=runtime.gateway_url,
                agent_target=agent_target,
                backend_model=backend_model,
                prompt=resolved_prompt,
                session_key=session_key,
                gateway_token=gateway_token,
                request_timeout_sec=request_timeout_sec,
            )
            text = extract_text_from_openai_response(response_json)
            elapsed = time.monotonic() - started_at
            self.logger.info(
                f"{case_label(case.metadata.id)}: received turn {index}/{len(user_turns)} "
                f"response_chars={len(text)} elapsed={elapsed:.1f}s"
            )
            turns.append(
                TurnRecord(
                    role=turn.role,
                    prompt=resolved_prompt,
                    response_text=text,
                    prompt_template=turn.content if resolved_prompt != turn.content else None,
                    raw_response=response_json,
                )
            )

        trace = ConversationTrace(case_id=case.metadata.id, session_key=session_key, turns=turns)
        trace_path = runtime.artifacts_dir / case_artifact_name(case.metadata.id, "trace")
        trace_path.write_text(json.dumps(asdict(trace), ensure_ascii=False, indent=2), encoding="utf-8")
        return trace

    def _send_chat_completion(
        self,
        *,
        base_url: str,
        agent_target: str,
        backend_model: str,
        prompt: str,
        session_key: str,
        gateway_token: str | None,
        request_timeout_sec: int,
    ) -> dict[str, Any]:
        payload = {
            "model": agent_target,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"{base_url}/v1/chat/completions"

        headers = {
            "content-type": "application/json",
            "x-openclaw-session-key": session_key,
            "x-openclaw-model": backend_model,
        }
        if gateway_token:
            headers["authorization"] = f"Bearer {gateway_token}"

        return _post_json(url, body=body, headers=headers, timeout_sec=request_timeout_sec)


def extract_text_from_openai_response(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = item.get("text") if isinstance(item, dict) else None
                if isinstance(text, str):
                    parts.append(text)
            if parts:
                return "\n".join(parts)

    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    return json.dumps(payload, ensure_ascii=False)


def _post_json(url: str, *, body: bytes, headers: dict[str, str], timeout_sec: int) -> dict[str, Any]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise ConversationDriverError(f"unsupported chat URL scheme: {parts.scheme or '<empty>'}")
    if not parts.hostname:
        raise ConversationDriverError("chat URL is missing hostname")

    port = parts.port or (443 if parts.scheme == "https" else 80)
    target = parts.path or "/"
    if parts.query:
        target = f"{target}?{parts.query}"

    connection_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    connection = connection_cls(parts.hostname, port, timeout=timeout_sec)
    try:
        connection.request("POST", target, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if response.status >= 400:
            content = raw.decode("utf-8", errors="replace")
            raise ConversationDriverError(f"chat call failed: status={response.status}, body={content}")
        return json.loads(raw.decode("utf-8"))
    finally:
        connection.close()
