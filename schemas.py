"""Pydantic v2 contracts for every layer of the research agent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, Field


def _uid(n: int = 8) -> str:
    return str(uuid.uuid4()).replace("-", "")[:n]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Perception layer ─────────────────────────────────────────────────────────

class SubGoal(BaseModel):
    id: str = Field(default_factory=_uid)
    description: str
    completed: bool = False


class Intent(BaseModel):
    primary_goal: str
    topic: str = "research"
    sub_goals: list[SubGoal] = Field(default_factory=list)
    is_memory_query: bool = False


class PerceptionResult(BaseModel):
    intent: Intent
    entities: list[str] = Field(default_factory=list)
    ambiguity_score: float = Field(ge=0.0, le=1.0, default=0.3)
    risk_level: Literal["low", "medium", "high"] = "low"
    clarification_needed: bool = False
    clarification_question: Optional[str] = None


# ─── Decision layer ───────────────────────────────────────────────────────────

class DecisionResult(BaseModel):
    action: Literal["web_search", "fetch_url", "memory_lookup", "save_memory", "summarize", "done"]
    reason: str
    query: Optional[str] = None
    url: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    converged: bool = False


# ─── Memory layer ─────────────────────────────────────────────────────────────

class Fact(BaseModel):
    id: str = Field(default_factory=lambda: _uid(12))
    content: str
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    timestamp: str = Field(default_factory=_now_iso)
    entities: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)  # IDs of contradicted facts
    session_id: str = ""


class Entity(BaseModel):
    name: str
    type: Literal["person", "organization", "concept", "place", "technology", "other"] = "other"
    mentions: int = 0
    fact_ids: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class ResearchSession(BaseModel):
    session_id: str = Field(default_factory=_uid)
    query: str
    started_at: str = Field(default_factory=_now_iso)
    ended_at: Optional[str] = None
    iterations: int = 0
    facts_found: int = 0
    conclusion: Optional[str] = None
    status: Literal["active", "completed", "failed"] = "active"


# ─── Agent state ──────────────────────────────────────────────────────────────

class AgentState(BaseModel):
    session: ResearchSession
    perception: Optional[PerceptionResult] = None
    iteration: int = 0
    search_queries_used: list[str] = Field(default_factory=list)
    urls_visited: list[str] = Field(default_factory=list)
    action_history: list[str] = Field(default_factory=list)
    pending_urls: list[str] = Field(default_factory=list)
    scraped_texts: list[dict[str, str]] = Field(default_factory=list)


# ─── Action layer ─────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class ActionResult(BaseModel):
    action: str
    success: bool
    data: Any = None
    error: Optional[str] = None
