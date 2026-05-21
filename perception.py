"""Perception layer — intent extraction, entity recognition, ambiguity and risk scoring."""
from __future__ import annotations

import logging

from gateway import LLM
from schemas import Intent, PerceptionResult, SubGoal
from utils import extract_json

log = logging.getLogger(__name__)

_llm = LLM()

_SYSTEM = (
    "You are the Perception Layer of an autonomous research agent. "
    "Analyze research queries and extract structured intent. "
    "Always reply with a single valid JSON object — no markdown, no prose."
)

_PROMPT = """\
Analyze this research query and extract structured information.

Query: {query}

Reply with this exact JSON structure:
{{
  "primary_goal": "<one clear sentence stating the research goal>",
  "topic": "<2-4 word topic label>",
  "sub_goals": ["<specific sub-question 1>", "<sub-question 2>"],
  "is_memory_query": <true if the user is asking about prior findings, e.g. "what did we learn", "remember that", "what do we know about">,
  "entities": ["<key named entity 1>", "<entity 2>"],
  "ambiguity_score": <0.0 = crystal clear, 1.0 = completely vague>,
  "risk_level": "<low|medium|high — high if topic involves health/legal/financial claims>",
  "clarification_needed": <true only if query is too vague to research meaningfully>,
  "clarification_question": "<question to clarify, or null>"
}}"""


def perceive(query: str) -> PerceptionResult:
    log.info("[perception] query=%r", query[:100])
    try:
        resp = _llm.chat(
            prompt=_PROMPT.format(query=query),
            system=_SYSTEM,
            auto_route="perception",
            max_tokens=1024,
            temperature=0.15,
        )
        data = extract_json(resp.get("text", ""))

        intent = Intent(
            primary_goal=data.get("primary_goal", query),
            topic=data.get("topic", "research"),
            sub_goals=[SubGoal(description=sg) for sg in data.get("sub_goals", [])],
            is_memory_query=bool(data.get("is_memory_query", False)),
        )
        result = PerceptionResult(
            intent=intent,
            entities=data.get("entities", []),
            ambiguity_score=float(data.get("ambiguity_score", 0.3)),
            risk_level=data.get("risk_level", "low"),
            clarification_needed=bool(data.get("clarification_needed", False)),
            clarification_question=data.get("clarification_question"),
        )
        log.info(
            "[perception] topic=%r  entities=%s  ambiguity=%.2f  memory_query=%s",
            result.intent.topic,
            result.entities[:4],
            result.ambiguity_score,
            result.intent.is_memory_query,
        )
        return result

    except Exception as exc:
        log.warning("[perception] LLM failed (%s) — using safe defaults", exc)
        return PerceptionResult(
            intent=Intent(primary_goal=query, topic="research"),
            ambiguity_score=0.5,
            risk_level="low",
        )
