"""Decision layer — chooses the next action and detects research convergence."""
from __future__ import annotations

import logging

from gateway import LLM
from schemas import AgentState, DecisionResult, PerceptionResult
from utils import extract_json

log = logging.getLogger(__name__)

_llm = LLM()

MAX_ITERATIONS = 10
MIN_FACTS_TO_CONCLUDE = 3
STUCK_WINDOW = 3          # same action this many times → force convergence

_SYSTEM = (
    "You are the Decision Layer of an autonomous research agent. "
    "Given the current research state, pick the single best next action. "
    "Reply with a valid JSON object — no markdown, no prose."
)

_PROMPT = """\
Research state:

Goal        : {goal}
Topic       : {topic}
Iteration   : {iteration} / {max_iter}
Facts found : {fact_count}  (need {min_facts} to conclude)
Queries used: {queries}
URLs visited: {urls}
Last actions: {history}
Pending URLs: {pending_urls}

Available actions:
  web_search   – search the web (requires: query)
  fetch_url    – deep-read a URL (requires: url)
  memory_lookup – recall stored facts on this topic (no params)
  save_memory  – extract & store facts from last fetched page (no params)
  summarize    – synthesise conclusion from gathered facts
  done         – research complete, conclusion already stored

Rules:
1. If iteration==1 and is_memory_query={is_memory_query}, start with memory_lookup.
2. If iteration==1 and not memory_query, start with web_search.
3. After web_search, prefer fetch_url on the best pending URL.
4. After fetch_url, always do save_memory next.
5. Alternate between web_search and fetch_url to cover multiple sources.
6. When fact_count >= {min_facts} OR iteration >= {max_iter}-1, do summarize.
7. Never repeat a query or URL already used.

Reply with exactly:
{{
  "action": "<action_name>",
  "reason": "<why this action now, 1 sentence>",
  "query": "<search query if action=web_search, else null>",
  "url": "<url if action=fetch_url, else null>",
  "confidence": <0.0-1.0>,
  "converged": <true if you believe research is sufficiently complete>
}}"""


def _is_stuck(history: list[str]) -> bool:
    if len(history) < STUCK_WINDOW:
        return False
    tail = history[-STUCK_WINDOW:]
    return len(set(tail)) == 1 and tail[0] in ("web_search", "fetch_url")


def decide(
    state: AgentState,
    perception: PerceptionResult,
) -> DecisionResult:
    # Hard guards — no LLM needed
    if state.iteration >= MAX_ITERATIONS:
        log.info("[decision] max iterations → summarize")
        return DecisionResult(
            action="summarize",
            reason="max iterations reached",
            converged=True,
            confidence=1.0,
        )

    if _is_stuck(state.action_history):
        log.warning("[decision] stuck in %s loop → summarize", state.action_history[-1])
        return DecisionResult(
            action="summarize",
            reason="convergence guard: repeated action detected",
            converged=True,
            confidence=0.85,
        )

    prompt = _PROMPT.format(
        goal=perception.intent.primary_goal,
        topic=perception.intent.topic,
        iteration=state.iteration,
        max_iter=MAX_ITERATIONS,
        fact_count=state.session.facts_found,
        min_facts=MIN_FACTS_TO_CONCLUDE,
        queries=state.search_queries_used[-5:] or "none",
        urls=state.urls_visited[-5:] or "none",
        history=state.action_history[-5:] or "none",
        pending_urls=state.pending_urls[:3] or "none",
        is_memory_query=perception.intent.is_memory_query,
    )

    try:
        resp = _llm.chat(
            prompt=prompt,
            system=_SYSTEM,
            auto_route="decision",
            max_tokens=512,
            temperature=0.1,
        )
        data = extract_json(resp.get("text", ""))

        decision = DecisionResult(
            action=data.get("action", "web_search"),
            reason=data.get("reason", ""),
            query=data.get("query"),
            url=data.get("url"),
            confidence=float(data.get("confidence", 0.7)),
            converged=bool(data.get("converged", False)),
        )
        log.info(
            "[decision] action=%s  reason=%r  confidence=%.2f  converged=%s",
            decision.action,
            decision.reason[:80],
            decision.confidence,
            decision.converged,
        )
        return decision

    except Exception as exc:
        log.warning("[decision] LLM failed (%s) — fallback heuristic", exc)
        # Fallback heuristic
        if state.session.facts_found >= MIN_FACTS_TO_CONCLUDE:
            return DecisionResult(
                action="summarize",
                reason="fallback: enough facts gathered",
                converged=True,
                confidence=0.7,
            )
        if state.pending_urls:
            return DecisionResult(
                action="fetch_url",
                reason="fallback: pending URL from last search",
                url=state.pending_urls[0],
                confidence=0.6,
            )
        return DecisionResult(
            action="web_search",
            reason="fallback: initial exploration",
            query=perception.intent.primary_goal,
            confidence=0.5,
        )
