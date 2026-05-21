Concept
An agent that investigates a topic like a junior research analyst.
Why it stands out
Instead of simple Q&A, it:
•	decomposes objectives 
•	gathers sources 
•	verifies claims 
•	stores facts in memory 
•	revisits past findings 
Architecture Strength
Excellent for:
•	Perception layer 
•	Decision layer 
•	Memory persistence 
•	Tool orchestration 
Sample Queries
•	“Find the top causes of EV battery degradation” 
•	“Remember that Tesla uses 4680 cells” 
•	“What did we learn earlier about Tesla batteries?” 
Impressive Features
•	contradiction detection 
•	confidence scoring 
•	citation graph 
•	memory snapshots 


# Project: Autonomous Research Investigator Agent

Build a fully modular cognitive agent architecture in Python using:

- memory.py
- perception.py
- decision.py
- action.py
- schemas.py
- agent6.py
- mcp_server.py

Requirements:
- Pydantic v2 contracts on every layer
- No dict passing between layers
- Use llm_gatewayV3 for ALL LLM calls
- Use MCP stdio transport
- Persistent memory under state/
- uv package management only
- No LangChain/LangGraph/CrewAI

Agent Objective:
The agent acts like a professional research investigator.

Capabilities:
- Understand complex research goals
- Break problems into sub-goals
- Search web using Tavily
- Crawl pages using crawl4ai
- Store facts in durable memory
- Recall prior findings across runs
- Detect contradictions
- Generate evidence-backed conclusions

Memory:
- facts.json
- session_history.json
- entities.json

Perception Layer:
- intent extraction
- entity extraction
- ambiguity detection
- risk assessment

Decision Layer:
- decide next action
- decide whether memory lookup required
- decide whether web research required
- convergence detection

Action Layer:
- Tavily search
- crawl4ai extraction
- save memory
- summarize findings

Need:
- structured logging
- retry handling
- iteration counter
- convergence guard
- CLI interface

Provide:
- full codebase
- README
- .env.example
- sample runs
- test queries
- architecture diagram
