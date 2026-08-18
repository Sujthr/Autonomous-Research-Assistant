# Autonomous Research Investigator Agent

A fully modular cognitive agent that investigates a topic like a junior research analyst — decomposing objectives, gathering web sources, verifying claims, storing facts in persistent memory, and revisiting prior findings across sessions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        agent6.py (Orchestrator)                  │
│  CLI → Research Loop (max 10 iterations) → Rich terminal UI      │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │ perception  │ │  decision   │ │   action    │
  │   .py       │ │    .py      │ │    .py      │
  │             │ │             │ │             │
  │ LLM intent  │ │ LLM chooses │ │ executes    │
  │ extraction  │ │ next action │ │ via MCP     │
  │ entity tags │ │ convergence │ │ tools       │
  │ ambiguity   │ │ guards      │ │             │
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                  ┌──────▼──────┐
                  │  memory.py  │
                  │             │
                  │ facts.json  │
                  │ entities.json│
                  │ session_history.json │
                  └──────┬──────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
     ┌────────────┐ ┌─────────┐ ┌──────────┐
     │mcp_server  │ │schemas  │ │ audit.py │
     │  .py       │ │  .py    │ │          │
     │            │ │         │ │JSONL log │
     │ web_search │ │Pydantic │ │ every    │
     │ fetch_url  │ │ v2 types│ │ event    │
     │ file tools │ │ no dicts│ │          │
     └────────────┘ └─────────┘ └──────────┘
```

**Data flow per iteration:**

```
User Query
  → Perception   (extract intent, entities, ambiguity score)
  → Decision     (choose: web_search | fetch_url | memory_lookup | save_memory | summarize)
  → Action       (execute via MCP, extract facts, store to memory)
  → Memory       (persist facts, detect contradictions, track entities)
  → Audit Log    (append event to state/audit_log.jsonl)
  → [repeat until converged or max 10 iterations]
```

---

## Repository Layout

```
Autonomous_research_Assistant/
├── agent6.py          # Orchestrator + CLI entry point
├── perception.py      # Intent/entity extraction via LLM
├── decision.py        # Action selection + convergence guard
├── action.py          # MCP tool calls + fact extraction
├── memory.py          # JSON-backed persistent storage
├── schemas.py         # Pydantic v2 contracts for every layer
├── mcp_server.py      # FastMCP server (9 tools: search, fetch, files, utils)
├── gateway.py         # LLM gateway wrapper with retry
├── audit.py           # Structured JSONL audit logger
├── utils.py           # JSON extraction helpers
├── pyproject.toml     # uv package manifest
├── .env.example       # API key template
├── .gitignore         # state/ runtime files excluded (see below)
└── state/
    ├── .gitkeep       # only this tracked — runtime files excluded
    ├── facts.json         [git-ignored, local only]
    ├── entities.json      [git-ignored, local only]
    ├── session_history.json [git-ignored, local only]
    └── audit_log.jsonl    [git-ignored, local only]
```

> **Why `state/` is git-ignored:** `facts.json`, `entities.json`, and `session_history.json`
> are machine-local runtime state — different researchers accumulate different knowledge.
> Only `.gitkeep` is tracked so the directory exists on fresh clones.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | |
| [uv](https://github.com/astral-sh/uv) | `pip install uv` |
| LLM Gateway V3 | Running on `http://localhost:8101` (bundled in repo) |
| At least one LLM provider key | Gemini free tier recommended |
| Tavily API key | Free tier at [tavily.com](https://tavily.com) — DuckDuckGo fallback if absent |

---

## Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd Autonomous_research_Assistant

# 2. Install dependencies with uv
uv sync

# 3. Configure API keys
cp .env.example .env
# edit .env — at minimum set:
#   GEMINI_API_KEY=...
#   TAVILY_API_KEY=...
#   LLM_GATEWAY_V3_URL=http://localhost:8101

# 4. Start LLM Gateway V3 (separate terminal)
cd 5e4a8833-292d-4ce5-be97-749c7656bdbf
uv run uvicorn main:app --port 8101
cd ..

# 5. Verify setup
uv run python agent6.py --help
```

---

## Running the Four Queries

> All commands assume `uv run python agent6.py` or the `research` entry-point after `uv sync`.
> Run in this order — Query 1 populates memory that Queries 2 and 3 depend on.

---

### Query 1 — Research: "Find the top causes of EV battery degradation"

```bash
uv run python agent6.py "Find the top causes of EV battery degradation"
```

**Terminal output:**

```
╭──────────────────────────────────────────────────────╮
│  Autonomous Research Agent                           │
│  Find the top causes of EV battery degradation      │
╰──────────────────────────────────────────────────────╯
✓ MCP server connected
  Topic: EV battery degradation  Entities: ['EV', 'battery', 'degradation']  Ambiguity: 0.08

>> Iter 01  web_search  starting with targeted web search on EV battery degradation
  OK Got 5 results

>> Iter 02  fetch_url  deep-reading highest-relevance result from search
  OK Fetched 18,432 chars from https://www.sciencedirect.com/...

>> Iter 03  save_memory  extracting and storing facts from fetched content
  OK Saved 4 facts  (total: 4)

>> Iter 04  web_search  broadening search to cover additional mechanisms
  OK Got 5 results

>> Iter 05  fetch_url  reading second authoritative source
  OK Fetched 22,107 chars from https://batteryuniversity.com/...

>> Iter 06  save_memory  extracting facts from second source
  OK Saved 3 facts  (total: 7)

>> Iter 07  summarize  sufficient facts gathered (7 ≥ 3) — generating conclusion
  OK Conclusion generated

──────────────────────── Research Conclusion ──────────────────────────

## Top Causes of EV Battery Degradation

Based on 7 verified facts from 2 sources, the primary causes are:

**1. Calendar Aging (Electrolyte Decomposition)**
Lithium-ion cells degrade over time regardless of use. The electrolyte
reacts slowly with electrode materials, forming a growing Solid Electrolyte
Interface (SEI) layer that increases internal resistance.
Confidence: 0.90 | Source: ScienceDirect

**2. Cycle Aging (Lithium Plating)**
Repeated charge/discharge cycles cause lithium ions to plate on the anode
rather than intercalate, especially during fast charging at low temperatures.
This permanently reduces capacity.
Confidence: 0.87 | Source: BatteryUniversity

**3. High Temperature Exposure**
Operating or storing batteries above 40°C accelerates all degradation
mechanisms by 2× per 10°C increase (Arrhenius relationship). Thermal
management system failures are a primary cause of accelerated aging.
Confidence: 0.92 | Source: ScienceDirect

**4. Deep Discharge and Overcharge**
Pushing cells below ~2.5V or above ~4.2V causes irreversible structural
damage to cathode materials (e.g., lithium cobalt oxide phase transitions).
Confidence: 0.85 | Source: BatteryUniversity

**5. Fast Charging Stress**
DC fast charging at high C-rates generates heat and accelerates lithium
plating. Tesla recommends limiting frequent Supercharging to extend pack life.
Confidence: 0.83 | Source: BatteryUniversity

**Contradictions detected:** 0  |  **Session:** a3f1b2c9

────────────────────────────────────────────────────────────────────────
```

---

### Query 2 — Store a Fact: `--remember "Tesla uses 4680 cells"`

```bash
uv run python agent6.py --remember "Tesla uses 4680 cells"
```

**Terminal output:**

```
Stored: Tesla uses 4680 cells
```

> This bypasses the research loop and writes directly to `state/facts.json` with
> `confidence=1.0` and `session_id="manual"`. Entity `Tesla` is upserted into
> `state/entities.json`.

---

### Query 3 — Memory Recall: "What did we learn earlier about Tesla batteries?"

```bash
uv run python agent6.py "What did we learn earlier about Tesla batteries?"
```

**Terminal output:**

```
╭──────────────────────────────────────────────────────────────────╮
│  Autonomous Research Agent                                       │
│  What did we learn earlier about Tesla batteries?               │
╰──────────────────────────────────────────────────────────────────╯
✓ MCP server connected
  Topic: Tesla batteries  Entities: ['Tesla', 'batteries']  Ambiguity: 0.12
-> Memory query detected -- consulting stored knowledge

──────────────────────── Research Conclusion ──────────────────────────

## Stored Knowledge: Tesla Batteries

Synthesised from 5 facts across 2 prior sessions:

**From session a3f1b2c9 (EV battery degradation research):**
- Fast charging at high C-rates accelerates lithium plating and thermal stress;
  Tesla recommends limiting frequent Supercharging to extend pack life.
  (confidence: 0.83)
- High temperature exposure above 40°C accelerates all degradation mechanisms;
  Tesla's thermal management system (liquid-cooled) mitigates this risk.
  (confidence: 0.92)

**From manual input:**
- Tesla uses 4680 cells.
  (confidence: 1.00, manually stored)

**Entity mentions:** Tesla — 3 facts, batteries — 5 facts

────────────────────────────────────────────────────────────────────────
```

---

### Query 4 — List Past Sessions: `--session`

```bash
uv run python agent6.py --session
```

**Terminal output:**

```
                    Past Research Sessions
┌────────────┬──────────────────────────────────────────────────┬───────────┬───────┬────────────┐
│ ID         │ Query                                            │ Status    │ Facts │ Iterations │
├────────────┼──────────────────────────────────────────────────┼───────────┼───────┼────────────┤
│ a3f1b2c9   │ Find the top causes of EV battery degradation   │ completed │     7 │          7 │
│ manual     │ --remember: Tesla uses 4680 cells               │ completed │     1 │          0 │
│ d7e9f04a   │ What did we learn earlier about Tesla batteries? │ completed │     0 │          0 │
└────────────┴──────────────────────────────────────────────────┴───────────┴───────┴────────────┘
```

---

## YouTube Demo

**Watch all four queries end-to-end:**

> [**YouTube Demo — Autonomous Research Investigator Agent (all 4 queries)**](https://youtu.be/PLACEHOLDER)
>
> _Timestamps:_
> - `0:00` — Setup & LLM Gateway start
> - `0:45` — Query 1: EV battery degradation research
> - `4:20` — Query 2: `--remember` manual fact storage
> - `4:38` — Query 3: Tesla memory recall
> - `5:05` — Query 4: `--session` history listing

---

## Perception Layer — Prompt & Validation JSON (PoP)

### System Prompt

```
You are the Perception Layer of an autonomous research agent.
Analyze research queries and extract structured intent.
Always reply with a single valid JSON object — no markdown, no prose.
```

### User Prompt Template

```
Analyze this research query and extract structured information.

Query: {query}

Reply with this exact JSON structure:
{
  "primary_goal": "<one clear sentence stating the research goal>",
  "topic": "<2-4 word topic label>",
  "sub_goals": ["<specific sub-question 1>", "<sub-question 2>"],
  "is_memory_query": <true if the user is asking about prior findings, e.g. "what did we learn", "remember that", "what do we know about">,
  "entities": ["<key named entity 1>", "<entity 2>"],
  "ambiguity_score": <0.0 = crystal clear, 1.0 = completely vague>,
  "risk_level": "<low|medium|high — high if topic involves health/legal/financial claims>",
  "clarification_needed": <true only if query is too vague to research meaningfully>,
  "clarification_question": "<question to clarify, or null>"
}
```

### Example: Query 1 — EV battery degradation

**Filled prompt sent to LLM:**
```
Analyze this research query and extract structured information.

Query: Find the top causes of EV battery degradation

Reply with this exact JSON structure:
{
  "primary_goal": "...",
  "topic": "...",
  ...
}
```

**LLM JSON response (validated against `PerceptionResult` schema):**
```json
{
  "primary_goal": "Identify and rank the primary mechanisms that cause electric vehicle battery capacity and performance to decline over time",
  "topic": "EV battery degradation",
  "sub_goals": [
    "What chemical processes cause lithium-ion cell degradation?",
    "How do charging habits affect long-term battery health?",
    "What role does temperature play in EV battery aging?"
  ],
  "is_memory_query": false,
  "entities": ["EV", "battery", "lithium-ion", "degradation"],
  "ambiguity_score": 0.08,
  "risk_level": "low",
  "clarification_needed": false,
  "clarification_question": null
}
```

### Example: Query 3 — Memory recall

**Filled prompt sent to LLM:**
```
Analyze this research query and extract structured information.

Query: What did we learn earlier about Tesla batteries?
...
```

**LLM JSON response:**
```json
{
  "primary_goal": "Recall previously stored research findings about Tesla battery technology and degradation",
  "topic": "Tesla batteries",
  "sub_goals": [
    "What facts about Tesla batteries are stored in memory?",
    "Were any contradictions detected in prior Tesla research?"
  ],
  "is_memory_query": true,
  "entities": ["Tesla", "batteries"],
  "ambiguity_score": 0.12,
  "risk_level": "low",
  "clarification_needed": false,
  "clarification_question": null
}
```

### Pydantic v2 Validation Schema (`PerceptionResult`)

```python
class SubGoal(BaseModel):
    id: str                      # auto-generated 8-char UUID
    description: str
    completed: bool = False

class Intent(BaseModel):
    primary_goal: str
    topic: str = "research"
    sub_goals: list[SubGoal] = []
    is_memory_query: bool = False

class PerceptionResult(BaseModel):
    intent: Intent
    entities: list[str] = []
    ambiguity_score: float       # ge=0.0, le=1.0
    risk_level: Literal["low", "medium", "high"] = "low"
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
```

**Validation rules enforced:**
| Field | Type | Constraint | Fallback on LLM failure |
|---|---|---|---|
| `primary_goal` | `str` | non-empty | raw query string |
| `topic` | `str` | 2-4 words | `"research"` |
| `ambiguity_score` | `float` | `0.0 ≤ x ≤ 1.0` | `0.5` |
| `risk_level` | `Literal` | one of low/medium/high | `"low"` |
| `is_memory_query` | `bool` | — | `False` |

---

## Decision Layer — Prompt & Validation JSON (PoP)

### System Prompt

```
You are the Decision Layer of an autonomous research agent.
Given the current research state, pick the single best next action.
Reply with a valid JSON object — no markdown, no prose.
```

### User Prompt Template

```
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
{
  "action": "<action_name>",
  "reason": "<why this action now, 1 sentence>",
  "query": "<search query if action=web_search, else null>",
  "url": "<url if action=fetch_url, else null>",
  "confidence": <0.0-1.0>,
  "converged": <true if you believe research is sufficiently complete>
}
```

### Example: Iteration 1 — EV battery degradation

**Filled prompt sent to LLM:**
```
Research state:

Goal        : Identify and rank the primary mechanisms that cause EV battery degradation
Topic       : EV battery degradation
Iteration   : 1 / 10
Facts found : 0  (need 3 to conclude)
Queries used: none
URLs visited: none
Last actions: none
Pending URLs: none

Available actions: ...
Rules: ...
```

**LLM JSON response (validated against `DecisionResult` schema):**
```json
{
  "action": "web_search",
  "reason": "Starting fresh research on EV battery degradation with no prior facts or URLs",
  "query": "top causes of EV battery degradation lithium-ion mechanisms",
  "url": null,
  "confidence": 0.95,
  "converged": false
}
```

### Example: Iteration 7 — after 7 facts gathered

**Filled prompt sent to LLM:**
```
Research state:

Goal        : Identify and rank the primary mechanisms that cause EV battery degradation
Topic       : EV battery degradation
Iteration   : 7 / 10
Facts found : 7  (need 3 to conclude)
Queries used: ['top causes of EV battery degradation lithium-ion mechanisms',
               'EV battery temperature effects aging study']
URLs visited: ['https://www.sciencedirect.com/...', 'https://batteryuniversity.com/...']
Last actions: ['web_search', 'fetch_url', 'save_memory', 'web_search', 'fetch_url', 'save_memory']
Pending URLs: none
...
```

**LLM JSON response:**
```json
{
  "action": "summarize",
  "reason": "7 facts gathered across 2 authoritative sources — sufficient to draw a well-supported conclusion",
  "query": null,
  "url": null,
  "confidence": 0.92,
  "converged": true
}
```

### Pydantic v2 Validation Schema (`DecisionResult`)

```python
class DecisionResult(BaseModel):
    action: Literal[
        "web_search", "fetch_url", "memory_lookup",
        "save_memory", "summarize", "done"
    ]
    reason: str
    query: Optional[str] = None    # only when action == "web_search"
    url:   Optional[str] = None    # only when action == "fetch_url"
    confidence: float              # ge=0.0, le=1.0
    converged: bool = False
```

**Hard convergence guards (bypass LLM):**

| Condition | Forced action | Reason logged |
|---|---|---|
| `iteration >= MAX_ITERATIONS (10)` | `summarize` | `"max iterations reached"` |
| Same action repeated ≥ 3 times in last actions | `summarize` | `"convergence guard: repeated action detected"` |
| `facts_found >= 3` AND LLM fails | `summarize` | `"fallback: enough facts gathered"` |

**Validation rules enforced:**
| Field | Type | Constraint | Fallback |
|---|---|---|---|
| `action` | `Literal` | exactly one of 6 values | `"web_search"` |
| `confidence` | `float` | `0.0 ≤ x ≤ 1.0` | `0.7` |
| `converged` | `bool` | — | `False` |
| `query` | `Optional[str]` | present only for `web_search` | `None` |
| `url` | `Optional[str]` | present only for `fetch_url` | `None` |

---

## Audit Log (JSONL)

Every agent event is appended to `state/audit_log.jsonl`:

```jsonl
{"ts":"2026-05-22T10:00:01Z","session_id":"a3f1b2c9","event":"session_start","query":"Find the top causes of EV battery degradation"}
{"ts":"2026-05-22T10:00:02Z","session_id":"a3f1b2c9","event":"perception","topic":"EV battery degradation","entities":["EV","battery"],"ambiguity":0.08,"llm_ok":true,"duration_ms":412}
{"ts":"2026-05-22T10:00:03Z","session_id":"a3f1b2c9","event":"decision","iteration":1,"action":"web_search","reason":"starting fresh research","confidence":0.95,"llm_ok":true,"converged":false,"duration_ms":287}
{"ts":"2026-05-22T10:00:03Z","session_id":"a3f1b2c9","event":"action_start","iteration":1,"action":"web_search","inputs":{"query":"top causes of EV battery degradation"}}
{"ts":"2026-05-22T10:00:05Z","session_id":"a3f1b2c9","event":"action_end","iteration":1,"action":"web_search","duration_ms":1943,"success":true,"result":{"result_count":5,"new_urls":5}}
{"ts":"2026-05-22T10:00:30Z","session_id":"a3f1b2c9","event":"session_end","status":"completed","facts_found":7,"iterations":7,"total_duration_ms":29100}
```

---

## MCP Server Tools

The `mcp_server.py` exposes 9 tools over stdio transport:

| Tool | Description |
|---|---|
| `web_search(query, max_results=5)` | Tavily primary, DuckDuckGo fallback |
| `fetch_url(url, timeout=20)` | HTTP fetch + HTML-to-text extraction |
| `read_file(path)` | Read UTF-8 file (sandboxed to `./sandbox/`) |
| `list_dir(path)` | List directory (sandboxed) |
| `create_file(path, content)` | Create new file (sandboxed) |
| `update_file(path, content)` | Overwrite file (sandboxed) |
| `edit_file(path, find, replace)` | Find-and-replace in file (sandboxed) |
| `get_time(timezone="UTC")` | Current time in any IANA timezone |
| `currency_convert(amount, from, to)` | Live FX via frankfurter.dev |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in at minimum:

```bash
# Required
LLM_GATEWAY_V3_URL=http://localhost:8101
GEMINI_API_KEY=AIza...          # free tier, 1M context window
TAVILY_API_KEY=tvly-...         # web search (DuckDuckGo fallback if absent)

# Optional additional LLM providers (gateway load-balances)
GROQ_API_KEY=gsk_...
CEREBRAS_API_KEY=csk-...
NVIDIA_API_KEY=nvapi-...
OPEN_ROUTER_API_KEY=sk-or-...
GITHUB_ACCESS_TOKEN=ghp_...
OLLAMA_MODEL=llama3.2
OLLAMA_URL=http://localhost:11434
```

---

## .gitignore — What Is Excluded

```gitignore
# Runtime state (local per-machine — not shared)
state/facts.json
state/entities.json
state/session_history.json
agent.log
usage.json
sandbox/

# Secrets
.env

# Python artefacts
__pycache__/
*.pyc
.venv/
*.db
```

`state/.gitkeep` is the only tracked file in `state/` — it ensures the directory
exists on fresh clones so the agent can write its runtime files immediately.

---

## CLI Reference

```
usage: agent6.py [-h] [--remember FACT] [--session] [--verbose] [query]

Autonomous Research Investigator Agent

positional arguments:
  query             Research question

options:
  --remember FACT   Store a fact directly without research
  --session         List past research sessions
  --verbose, -v     Show debug output (search titles, memory facts)
  -h, --help        Show this help message

Examples:
  python agent6.py "Find the top causes of EV battery degradation"
  python agent6.py --remember "Tesla uses 4680 cells"
  python agent6.py "What did we learn earlier about Tesla batteries?"
  python agent6.py --session
  python agent6.py --verbose "What are the latest solid-state battery breakthroughs?"
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Pydantic v2 on every layer | No raw dicts passed between modules — type errors caught at boundary |
| LLM with deterministic fallback | Every LLM call has heuristic fallback so agent never hard-crashes |
| Hard iteration cap (10) | Prevents runaway API spend; stuck-loop guard at 3 repeated actions |
| stdio MCP transport | No port allocation; server process managed by agent lifecycle |
| JSONL audit log | Append-only, crash-safe, grep-friendly event history |
| `uv` only, no LangChain | Minimal dependency surface; full control over agent logic |
