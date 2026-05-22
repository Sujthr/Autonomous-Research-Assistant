"""
Autonomous Research Investigator Agent -- main orchestrator.

Usage:
    python agent6.py "Find the top causes of EV battery degradation"
    python agent6.py --remember "Tesla uses 4680 cells"
    python agent6.py "What did we learn earlier about Tesla batteries?"
    python agent6.py --session          # list past sessions
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.rule import Rule
from rich.table import Table

load_dotenv(Path(__file__).parent / ".env")

import action as A
import decision as D
import perception as P
from audit import AuditLogger
from memory import get_memory_snapshot, load_sessions, save_session
from schemas import AgentState, ResearchSession

log = logging.getLogger(__name__)
console = Console()

MCP_SERVER = Path(__file__).parent / "mcp_server.py"

# ─── Logging setup ────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s"
    logging.basicConfig(level=level, format=fmt,
                        handlers=[
                            logging.StreamHandler(),
                            logging.FileHandler("agent.log", encoding="utf-8"),
                        ])
    # Quiet noisy libs
    for lib in ("httpx", "httpcore", "asyncio", "mcp"):
        logging.getLogger(lib).setLevel(logging.WARNING)


# ─── Display helpers ──────────────────────────────────────────────────────────

def _banner(query: str) -> None:
    console.print(Panel.fit(
        f"[bold cyan]Autonomous Research Agent[/bold cyan]\n"
        f"[white]{query}[/white]",
        border_style="cyan",
    ))


def _step(iteration: int, action: str, reason: str) -> None:
    console.print(
        f"\n[bold yellow]>> Iter {iteration:02d}[/bold yellow]  "
        f"[green]{action}[/green]  [dim]{reason[:80]}[/dim]"
    )


def _result_ok(msg: str) -> None:
    console.print(f"  [green]OK[/green] {msg}")


def _result_warn(msg: str) -> None:
    console.print(f"  [yellow]!![/yellow] {msg}")


def _show_conclusion(conclusion: str) -> None:
    console.print(Rule("[bold green]Research Conclusion[/bold green]"))
    console.print(conclusion)
    console.print(Rule())


def _show_sessions() -> None:
    sessions = load_sessions()
    if not sessions:
        console.print("[dim]No past sessions found.[/dim]")
        return
    t = Table(title="Past Research Sessions", show_lines=True)
    t.add_column("ID", style="cyan", width=10)
    t.add_column("Query", style="white")
    t.add_column("Status", style="green")
    t.add_column("Facts", justify="right")
    t.add_column("Iterations", justify="right")
    for s in sessions[-20:]:
        t.add_row(s.session_id, s.query[:60], s.status, str(s.facts_found), str(s.iterations))
    console.print(t)


# ─── Quick remember ───────────────────────────────────────────────────────────

def _store_manual_fact(statement: str) -> None:
    """Store a fact the user dictates directly, skipping the research loop."""
    from memory import save_fact, upsert_entity
    from schemas import Fact
    fact = Fact(
        content=statement,
        confidence=1.0,
        session_id="manual",
        entities=[w for w in statement.split() if w[0].isupper() and len(w) > 2],
    )
    save_fact(fact)
    for ent in fact.entities:
        upsert_entity(ent, fact_id=fact.id)
    console.print(f"[green]Stored:[/green] {statement}")


# ─── Core research loop ───────────────────────────────────────────────────────

async def _research_loop(
    query: str,
    mcp: ClientSession,
    verbose: bool = False,
) -> str:
    import time as _time

    session = ResearchSession(query=query)
    state = AgentState(session=session)
    save_session(session)

    audit = AuditLogger(session.session_id, query)
    audit.session_start(query)

    # ── Perception ────────────────────────────────────────────────────────────
    t0 = _time.monotonic()
    with Progress(SpinnerColumn(), TextColumn("[cyan]Perceiving query..."), transient=True, console=console):
        perc = P.perceive(query)
    perc_ms = int((_time.monotonic() - t0) * 1000)

    # Detect whether LLM was used: fallback sets topic="research", ambiguity=0.5
    perc_llm_ok = not (perc.intent.topic == "research" and perc.ambiguity_score == 0.5)
    audit.perception(
        topic=perc.intent.topic,
        entities=perc.entities,
        ambiguity=perc.ambiguity_score,
        llm_ok=perc_llm_ok,
        duration_ms=perc_ms,
    )

    state.perception = perc
    console.print(
        f"  [dim]Topic:[/dim] [cyan]{perc.intent.topic}[/cyan]  "
        f"[dim]Entities:[/dim] {perc.entities[:5]}  "
        f"[dim]Ambiguity:[/dim] {perc.ambiguity_score:.2f}"
    )

    if perc.clarification_needed:
        console.print(f"\n[yellow]Clarification needed:[/yellow] {perc.clarification_question}")
        audit.session_end("clarification_needed", 0, 0)
        return "Query too ambiguous to research -- please clarify."

    # ── Memory query short-circuit ────────────────────────────────────────────
    if perc.intent.is_memory_query:
        console.print("[cyan]-> Memory query detected -- consulting stored knowledge[/cyan]")
        snapshot = get_memory_snapshot(perc.intent.topic, perc.entities)
        if snapshot["total_facts"] == 0:
            audit.session_end("no_memory", 0, 0)
            return "No stored knowledge found on this topic. Run a fresh research query first."
        ar = A.run_summarize(state, perc)
        conclusion = ar.data or "No conclusion could be generated."
        session.conclusion = conclusion
        session.status = "completed"
        save_session(session)
        audit.session_end("memory_query", snapshot["total_facts"], 0)
        return conclusion

    last_fetched_text: str = ""
    last_fetched_url: str = ""

    for iteration in range(1, D.MAX_ITERATIONS + 1):
        state.iteration = iteration
        session.iterations = iteration

        # ── Decision ──────────────────────────────────────────────────────────
        t0 = _time.monotonic()
        dec = D.decide(state, perc)
        dec_ms = int((_time.monotonic() - t0) * 1000)

        # Fallback decisions have no reason text or have "fallback:" prefix
        dec_llm_ok = bool(dec.reason and not dec.reason.startswith("fallback"))
        audit.decision(
            iteration=iteration,
            action=dec.action,
            reason=dec.reason,
            confidence=dec.confidence,
            llm_ok=dec_llm_ok,
            converged=dec.converged,
            duration_ms=dec_ms,
        )

        _step(iteration, dec.action, dec.reason)
        state.action_history.append(dec.action)

        # ── web_search ────────────────────────────────────────────────────────
        if dec.action == "web_search":
            query_str = dec.query or perc.intent.primary_goal
            if query_str in state.search_queries_used:
                query_str += f" {perc.intent.topic} latest"
            state.search_queries_used.append(query_str)

            audit.action_start(iteration, "web_search", {"query": query_str})
            ar = await A.run_web_search(mcp, query_str)
            if ar.success and ar.data:
                results = ar.data
                new_urls = [r.url for r in results if r.url and r.url not in state.urls_visited]
                state.pending_urls = new_urls[:5]
                audit.action_end(iteration, "web_search", True, {
                    "result_count": len(results),
                    "new_urls": len(new_urls),
                    "urls": [r.url for r in results],
                })
                _result_ok(f"Got {len(results)} results")
                if verbose:
                    for r in results:
                        console.print(f"    [dim]{r.title[:60]}[/dim]  {r.url}")
            else:
                audit.action_end(iteration, "web_search", False, error=ar.error)
                _result_warn(f"Search failed: {ar.error}")

        # ── fetch_url ─────────────────────────────────────────────────────────
        elif dec.action == "fetch_url":
            url = dec.url or (state.pending_urls[0] if state.pending_urls else "")
            if not url:
                audit.action_end(iteration, "fetch_url", False, error="no URL available")
                _result_warn("No URL to fetch -- switching to web_search next")
                state.action_history[-1] = "web_search"
                continue
            if url in state.urls_visited:
                if state.pending_urls:
                    state.pending_urls.pop(0)
                continue

            state.urls_visited.append(url)
            if url in state.pending_urls:
                state.pending_urls.remove(url)

            audit.action_start(iteration, "fetch_url", {"url": url})
            ar = await A.run_fetch_url(mcp, url)
            if ar.success and ar.data:
                content = ar.data.get("text", "") if isinstance(ar.data, dict) else str(ar.data)
                http_status = ar.data.get("status", 0) if isinstance(ar.data, dict) else 0
                last_fetched_text = content
                last_fetched_url = url
                audit.action_end(iteration, "fetch_url", True, {
                    "url": url,
                    "http_status": http_status,
                    "chars": len(content),
                })
                _result_ok(f"Fetched {len(content):,} chars from {url}")
            else:
                audit.action_end(iteration, "fetch_url", False, {"url": url}, error=ar.error)
                _result_warn(f"Fetch failed: {ar.error}")

        # ── memory_lookup ─────────────────────────────────────────────────────
        elif dec.action == "memory_lookup":
            audit.action_start(iteration, "memory_lookup", {
                "topic": perc.intent.topic, "entities": perc.entities,
            })
            ar = A.run_memory_lookup(perc.intent.topic, perc.entities)
            snap = ar.data or {}
            n = snap.get("total_facts", 0)
            audit.action_end(iteration, "memory_lookup", True, {
                "facts_found": n,
                "prior_sessions": len(snap.get("prior_sessions", [])),
            })
            _result_ok(f"Memory: {n} relevant facts, {len(snap.get('prior_sessions', []))} prior sessions")
            if verbose and snap.get("facts"):
                for f in snap["facts"][:3]:
                    console.print(f"    [dim]{f['content'][:80]}[/dim]")

        # ── save_memory ───────────────────────────────────────────────────────
        elif dec.action == "save_memory":
            if not last_fetched_text:
                audit.action_end(iteration, "save_memory", False, error="no fetched content")
                _result_warn("No fetched content to save -- skipping")
                continue
            audit.action_start(iteration, "save_memory", {
                "url": last_fetched_url, "content_chars": len(last_fetched_text),
            })
            ar = await A.run_save_memory(state, perc, last_fetched_text, last_fetched_url)
            if ar.success and ar.data:
                n = len(ar.data)
                session.facts_found += n
                contradictions = [f for f in ar.data if f.contradicts]
                audit.action_end(iteration, "save_memory", True, {
                    "facts_saved": n,
                    "total_facts": session.facts_found,
                    "contradictions": len(contradictions),
                    "llm_used": all(f.confidence >= 0.7 for f in ar.data),
                })
                _result_ok(f"Saved {n} facts  (total: {session.facts_found})")
                if contradictions:
                    _result_warn(f"{len(contradictions)} fact(s) contradict prior knowledge!")
            else:
                audit.action_end(iteration, "save_memory", False, error=ar.error)
                _result_warn(f"Save failed: {ar.error}")
            last_fetched_text = ""

        # ── summarize ─────────────────────────────────────────────────────────
        elif dec.action in ("summarize", "done"):
            audit.action_start(iteration, "summarize", {"facts_available": session.facts_found})
            ar = A.run_summarize(state, perc)
            conclusion = ar.data if ar.success else f"(summarize failed: {ar.error})"
            audit.action_end(iteration, "summarize", ar.success, {
                "conclusion_chars": len(conclusion),
            }, error=ar.error if not ar.success else None)
            session.conclusion = conclusion
            session.status = "completed"
            session.ended_at = datetime.now(timezone.utc).isoformat()
            save_session(session)
            audit.session_end("completed", session.facts_found, iteration)
            _result_ok("Conclusion generated")
            return conclusion

        save_session(session)

        if dec.converged and dec.action not in ("summarize", "done"):
            console.print("  [green]✓ Converged -- generating conclusion[/green]")
            audit.action_start(iteration, "summarize", {"facts_available": session.facts_found})
            ar = A.run_summarize(state, perc)
            conclusion = ar.data if ar.success else "(summarize failed)"
            audit.action_end(iteration, "summarize", ar.success, {
                "conclusion_chars": len(conclusion),
            })
            session.conclusion = conclusion
            session.status = "completed"
            session.ended_at = datetime.now(timezone.utc).isoformat()
            save_session(session)
            audit.session_end("converged", session.facts_found, iteration)
            return conclusion

    # Exhausted iterations
    audit.action_start(D.MAX_ITERATIONS, "summarize", {"facts_available": session.facts_found})
    ar = A.run_summarize(state, perc)
    conclusion = ar.data if ar.success else "Research reached iteration limit without a clear conclusion."
    audit.action_end(D.MAX_ITERATIONS, "summarize", ar.success, {"conclusion_chars": len(conclusion)})
    session.conclusion = conclusion
    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc).isoformat()
    save_session(session)
    audit.session_end("max_iterations", session.facts_found, D.MAX_ITERATIONS)
    return conclusion


async def _run(query: str, verbose: bool) -> None:
    _banner(query)
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER)],
    )
    with Progress(SpinnerColumn(), TextColumn("[cyan]Connecting to MCP server..."),
                  transient=True, console=console):
        pass  # progress shown while context managers start

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            console.print("[green]✓ MCP server connected[/green]")
            conclusion = await _research_loop(query, mcp, verbose=verbose)

    _show_conclusion(conclusion)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonomous Research Investigator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", nargs="?", help="Research question")
    parser.add_argument("--remember", metavar="FACT",
                        help="Store a fact directly without research")
    parser.add_argument("--session", action="store_true",
                        help="List past research sessions")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show debug output")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    if args.session:
        _show_sessions()
        return

    if args.remember:
        _store_manual_fact(args.remember)
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    asyncio.run(_run(args.query, verbose=args.verbose))


if __name__ == "__main__":
    main()
