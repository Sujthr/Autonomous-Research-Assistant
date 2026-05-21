"""Persistent memory layer — facts, entities, session history stored under state/."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from schemas import Entity, Fact, ResearchSession

log = logging.getLogger(__name__)

STATE_DIR = Path(__file__).parent / "state"
FACTS_PATH = STATE_DIR / "facts.json"
ENTITIES_PATH = STATE_DIR / "entities.json"
SESSIONS_PATH = STATE_DIR / "session_history.json"


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _ensure():
    STATE_DIR.mkdir(exist_ok=True)
    for p in (FACTS_PATH, ENTITIES_PATH, SESSIONS_PATH):
        if not p.exists():
            p.write_text("[]", encoding="utf-8")


def _read(path: Path) -> list:
    _ensure()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(path: Path, data: list) -> None:
    _ensure()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── Facts ───────────────────────────────────────────────────────────────────

def load_facts() -> list[Fact]:
    return [Fact(**d) for d in _read(FACTS_PATH)]


def save_fact(fact: Fact) -> None:
    rows = _read(FACTS_PATH)
    rows.append(fact.model_dump())
    _write(FACTS_PATH, rows)
    log.debug("Saved fact %s: %s", fact.id, fact.content[:60])


def search_facts(query: str, entities: Optional[list[str]] = None) -> list[Fact]:
    """Keyword search over stored facts."""
    q = query.lower()
    results = []
    for f in load_facts():
        text = f.content.lower()
        if q in text:
            results.append(f)
            continue
        if entities and any(e.lower() in text for e in entities):
            results.append(f)
    return results


def detect_contradictions(new_fact: Fact, existing: list[Fact]) -> list[str]:
    """
    Lightweight contradiction detection: flags facts sharing entities but
    using antonym pairs. Returns IDs of likely-contradicting existing facts.
    """
    antonyms = [
        ("increases", "decreases"), ("improves", "worsens"),
        ("safe", "dangerous"), ("effective", "ineffective"),
        ("supports", "contradicts"), ("higher", "lower"),
        ("faster", "slower"), ("better", "worse"),
        ("yes", "no"), ("true", "false"),
    ]
    nc = new_fact.content.lower()
    contradicting = []
    for ef in existing:
        if not (set(new_fact.entities) & set(ef.entities)):
            continue
        ec = ef.content.lower()
        for pos, neg in antonyms:
            if (pos in nc and neg in ec) or (neg in nc and pos in ec):
                contradicting.append(ef.id)
                break
    return list(set(contradicting))


# ─── Entities ────────────────────────────────────────────────────────────────

def load_entities() -> dict[str, Entity]:
    rows = _read(ENTITIES_PATH)
    if isinstance(rows, list):
        return {e["name"]: Entity(**e) for e in rows}
    return {}


def save_entities(entities: dict[str, Entity]) -> None:
    _write(ENTITIES_PATH, [e.model_dump() for e in entities.values()])


def upsert_entity(name: str, entity_type: str = "other", fact_id: Optional[str] = None) -> None:
    entities = load_entities()
    if name not in entities:
        entities[name] = Entity(name=name, type=entity_type)
    entities[name].mentions += 1
    if fact_id and fact_id not in entities[name].fact_ids:
        entities[name].fact_ids.append(fact_id)
    save_entities(entities)


# ─── Sessions ────────────────────────────────────────────────────────────────

def load_sessions() -> list[ResearchSession]:
    return [ResearchSession(**d) for d in _read(SESSIONS_PATH)]


def save_session(session: ResearchSession) -> None:
    rows = _read(SESSIONS_PATH)
    for i, s in enumerate(rows):
        if s.get("session_id") == session.session_id:
            rows[i] = session.model_dump()
            _write(SESSIONS_PATH, rows)
            return
    rows.append(session.model_dump())
    _write(SESSIONS_PATH, rows)


# ─── Snapshots (for memory-query responses) ───────────────────────────────────

def get_memory_snapshot(topic: str, entities: Optional[list[str]] = None) -> dict:
    """Return stored knowledge relevant to a topic for 'what did we learn' queries."""
    facts = search_facts(topic, entities)
    all_entities = load_entities()
    topic_lower = topic.lower()
    relevant_entities = {
        k: v for k, v in all_entities.items()
        if topic_lower in k.lower()
        or any(topic_lower in fid for fid in v.fact_ids)
    }
    sessions = load_sessions()
    prior = [s for s in sessions if topic_lower in s.query.lower() and s.status == "completed"]

    return {
        "topic": topic,
        "facts": [f.model_dump() for f in facts[:15]],
        "entities": {k: v.model_dump() for k, v in list(relevant_entities.items())[:10]},
        "prior_sessions": [{"query": s.query, "conclusion": s.conclusion, "facts": s.facts_found}
                           for s in prior[-5:]],
        "total_facts": len(facts),
    }
