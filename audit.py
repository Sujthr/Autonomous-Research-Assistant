"""
Structured JSONL audit log — one JSON event per line.

Written to state/audit_log.jsonl. Every session appends to the same file
so you can grep across runs. Each line is valid JSON: load with:

    import json
    events = [json.loads(l) for l in open("state/audit_log.jsonl")]

Event types:
    session_start   – new research session begins
    perception      – query understanding result
    decision        – action chosen for an iteration
    action_start    – action about to execute (with inputs)
    action_end      – action completed (with duration + result summary)
    llm_call        – LLM call outcome (success / 503 / parse error)
    session_end     – session complete (status, facts, total duration)
    error           – unexpected exception at any layer
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATE = Path(__file__).parent / "state"
_LOG   = _STATE / "audit_log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(event: dict) -> None:
    _STATE.mkdir(exist_ok=True)
    with _LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


class AuditLogger:
    """Per-session audit logger. Create once at the start of _research_loop."""

    def __init__(self, session_id: str, query: str) -> None:
        self.session_id = session_id
        self._session_t0 = time.monotonic()
        self._action_t0: float = 0.0

    # ── helpers ───────────────────────────────────────────────────────────────

    def _e(self, event: str, **kw: Any) -> dict:
        return {"ts": _now(), "session_id": self.session_id, "event": event, **kw}

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def session_start(self, query: str) -> None:
        _append(self._e("session_start", query=query))

    def session_end(self, status: str, facts_found: int, iterations: int) -> None:
        _append(self._e(
            "session_end",
            status=status,
            facts_found=facts_found,
            iterations=iterations,
            total_duration_ms=int((time.monotonic() - self._session_t0) * 1000),
        ))

    # ── perception ────────────────────────────────────────────────────────────

    def perception(
        self,
        topic: str,
        entities: list[str],
        ambiguity: float,
        llm_ok: bool,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        _append(self._e(
            "perception",
            topic=topic,
            entities=entities,
            ambiguity=ambiguity,
            llm_ok=llm_ok,
            duration_ms=duration_ms,
            error=error,
        ))

    # ── decision ──────────────────────────────────────────────────────────────

    def decision(
        self,
        iteration: int,
        action: str,
        reason: str,
        confidence: float,
        llm_ok: bool,
        duration_ms: int,
        converged: bool = False,
        error: str | None = None,
    ) -> None:
        _append(self._e(
            "decision",
            iteration=iteration,
            action=action,
            reason=reason,
            confidence=confidence,
            llm_ok=llm_ok,
            converged=converged,
            duration_ms=duration_ms,
            error=error,
        ))

    # ── actions ───────────────────────────────────────────────────────────────

    def action_start(self, iteration: int, action: str, inputs: dict[str, Any]) -> None:
        self._action_t0 = time.monotonic()
        _append(self._e("action_start", iteration=iteration, action=action, inputs=inputs))

    def action_end(
        self,
        iteration: int,
        action: str,
        success: bool,
        result_summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        _append(self._e(
            "action_end",
            iteration=iteration,
            action=action,
            duration_ms=int((time.monotonic() - self._action_t0) * 1000),
            success=success,
            result=result_summary or {},
            error=error,
        ))

    # ── LLM tracking (called from action.py) ─────────────────────────────────

    def llm_call(
        self,
        layer: str,
        success: bool,
        model_route: str = "",
        error: str | None = None,
    ) -> None:
        _append(self._e(
            "llm_call",
            layer=layer,
            success=success,
            model_route=model_route,
            error=error,
        ))

    # ── errors ────────────────────────────────────────────────────────────────

    def error(self, layer: str, message: str, exc: str | None = None) -> None:
        _append(self._e("error", layer=layer, message=message, exc=exc))
