"""Action layer — executes decisions via MCP tools and the LLM gateway."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from mcp import ClientSession

from gateway import LLM
from utils import extract_json
from memory import detect_contradictions, load_facts, save_fact, upsert_entity
from schemas import ActionResult, AgentState, Fact, PerceptionResult, SearchResult

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_llm = LLM()

# ─── MCP helpers ─────────────────────────────────────────────────────────────

async def _tool(session: ClientSession, name: str, args: dict) -> Any:
    """Call an MCP tool and return the parsed payload.

    FastMCP may encode a list return as one TextContent per item (not one big
    JSON array), so we collect ALL content items and reconstruct the list.
    """
    result = await session.call_tool(name, args)
    if not result.content:
        return None

    if len(result.content) == 1:
        try:
            return json.loads(result.content[0].text)
        except Exception:
            return result.content[0].text

    # Multiple TextContent items → each is one element of the original list
    collected = []
    for c in result.content:
        try:
            collected.append(json.loads(c.text))
        except Exception:
            collected.append(c.text)
    return collected


# ─── Web search ──────────────────────────────────────────────────────────────

async def run_web_search(session: ClientSession, query: str) -> ActionResult:
    log.info("[action] web_search query=%r", query)
    try:
        raw = await _tool(session, "web_search", {"query": query, "max_results": 5})
        if not raw:
            return ActionResult(action="web_search", success=False, error="no results")
        results = [SearchResult(**r) if isinstance(r, dict) else r for r in raw]
        return ActionResult(action="web_search", success=True, data=results)
    except Exception as exc:
        log.error("[action] web_search failed: %s", exc)
        return ActionResult(action="web_search", success=False, error=str(exc))


# ─── URL fetching ─────────────────────────────────────────────────────────────

async def run_fetch_url(session: ClientSession, url: str) -> ActionResult:
    log.info("[action] fetch_url url=%s", url)
    try:
        raw = await _tool(session, "fetch_url", {"url": url})
        if not raw:
            return ActionResult(action="fetch_url", success=False, error="empty response")
        return ActionResult(action="fetch_url", success=True, data=raw)
    except Exception as exc:
        log.error("[action] fetch_url failed: %s", exc)
        return ActionResult(action="fetch_url", success=False, error=str(exc))


# ─── Fact extraction & memory save ────────────────────────────────────────────

_EXTRACT_SYSTEM = (
    "You are a precision fact extractor for a research agent. "
    "Extract concrete, verifiable factual claims from the text. "
    "Ignore navigation, ads, and boilerplate. "
    "Reply with a single valid JSON object only."
)

_EXTRACT_PROMPT = """\
Research goal: {goal}
Source URL: {url}

Text (up to 4 000 chars):
{content}

Extract factual claims relevant to the research goal. Reply:
{{
  "facts": [
    {{
      "content": "<precise factual statement, one sentence>",
      "confidence": <0.0-1.0>,
      "entities": ["<named entity>", ...],
      "is_key_finding": <true if directly answers the research goal>
    }}
  ]
}}"""


async def run_save_memory(
    state: AgentState,
    perception: PerceptionResult,
    content: str,
    url: str,
) -> ActionResult:
    log.info("[action] save_memory from %s (%d chars)", url, len(content))
    truncated = content[:4000]

    try:
        resp = _llm.chat(
            prompt=_EXTRACT_PROMPT.format(
                goal=perception.intent.primary_goal,
                url=url,
                content=truncated,
            ),
            system=_EXTRACT_SYSTEM,
            auto_route="memory",
            max_tokens=1024,
            temperature=0.1,
        )
        data = extract_json(resp.get("text", ""))

        existing = load_facts()
        saved: list[Fact] = []

        for item in data.get("facts", []):
            fact = Fact(
                content=item["content"],
                source_url=url,
                confidence=float(item.get("confidence", 0.7)),
                entities=item.get("entities", perception.entities),
                session_id=state.session.session_id,
            )
            contradictions = detect_contradictions(fact, existing)
            if contradictions:
                fact.contradicts = contradictions
                log.warning(
                    "[memory] CONTRADICTION: fact %r contradicts %s",
                    fact.content[:60],
                    contradictions,
                )
            save_fact(fact)
            existing.append(fact)
            for ent in fact.entities:
                upsert_entity(ent, fact_id=fact.id)
            saved.append(fact)

        log.info("[action] save_memory: stored %d facts", len(saved))
        return ActionResult(action="save_memory", success=True, data=saved)

    except Exception as exc:
        log.error("[action] save_memory failed: %s", exc)
        return ActionResult(action="save_memory", success=False, error=str(exc))


# ─── Memory lookup ────────────────────────────────────────────────────────────

def run_memory_lookup(topic: str, entities: list[str]) -> ActionResult:
    from memory import get_memory_snapshot
    log.info("[action] memory_lookup topic=%r", topic)
    snapshot = get_memory_snapshot(topic, entities)
    return ActionResult(action="memory_lookup", success=True, data=snapshot)


# ─── Summarize ────────────────────────────────────────────────────────────────

_SUMMARY_SYSTEM = (
    "You are a senior research analyst writing evidence-backed conclusions. "
    "Be precise, cite sources, and assign confidence scores. "
    "Structure your report clearly."
)

_SUMMARY_PROMPT = """\
Write a comprehensive research report for:

Goal : {goal}
Topic: {topic}

Gathered evidence ({fact_count} facts):
{facts}

Structure your report as:
## Key Findings
(bullet points, each with confidence score X/10)

## Evidence Summary
(paragraph synthesising the sources)

## Contradictions & Uncertainties
(note any conflicting evidence or gaps)

## Overall Confidence: X/10
(explain the rating)"""


def run_summarize(state: AgentState, perception: PerceptionResult) -> ActionResult:
    log.info("[action] summarize session=%s", state.session.session_id)
    all_facts = load_facts()
    session_facts = [f for f in all_facts if f.session_id == state.session.session_id]
    if not session_facts:
        session_facts = all_facts[-20:]

    fact_lines = "\n".join(
        f"[{i+1}] conf={f.confidence:.1f}  {f.content}  | {f.source_url or 'memory'}"
        for i, f in enumerate(session_facts[:20])
    )

    try:
        resp = _llm.chat(
            prompt=_SUMMARY_PROMPT.format(
                goal=perception.intent.primary_goal,
                topic=perception.intent.topic,
                fact_count=len(session_facts),
                facts=fact_lines or "(none gathered yet)",
            ),
            system=_SUMMARY_SYSTEM,
            auto_route="decision",
            max_tokens=1500,
            temperature=0.3,
        )
        conclusion = resp.get("text", "").strip() or "No conclusion could be generated."
        return ActionResult(action="summarize", success=True, data=conclusion)
    except Exception as exc:
        log.error("[action] summarize failed: %s", exc)
        return ActionResult(action="summarize", success=False, error=str(exc))
