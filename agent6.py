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
    session = ResearchSession(query=query)
    state = AgentState(session=session)
    save_session(session)

    # Perception
    with Progress(SpinnerColumn(), TextColumn("[cyan]Perceiving query..."), transient=True, console=console):
        perc = P.perceive(query)

    state.perception = perc
    console.print(
        f"  [dim]Topic:[/dim] [cyan]{perc.intent.topic}[/cyan]  "
        f"[dim]Entities:[/dim] {perc.entities[:5]}  "
        f"[dim]Ambiguity:[/dim] {perc.ambiguity_score:.2f}"
    )

    if perc.clarification_needed:
        console.print(f"\n[yellow]Clarification needed:[/yellow] {perc.clarification_question}")
        return "Query too ambiguous to research -- please clarify."

    # Memory query short-circuit
    if perc.intent.is_memory_query:
        console.print("[cyan]-> Memory query detected -- consulting stored knowledge[/cyan]")
        snapshot = get_memory_snapshot(perc.intent.topic, perc.entities)
        if snapshot["total_facts"] == 0:
            return "No stored knowledge found on this topic. Run a fresh research query first."
        ar = A.run_summarize(state, perc)
        conclusion = ar.data or "No conclusion could be generated."
        session.conclusion = conclusion
        session.status = "completed"
        save_session(session)
        return conclusion

    last_fetched_text: str = ""
    last_fetched_url: str = ""

    for iteration in range(1, D.MAX_ITERATIONS + 1):
        state.iteration = iteration
        session.iterations = iteration

        # Decision
        dec = D.decide(state, perc)
        _step(iteration, dec.action, dec.reason)
        state.action_history.append(dec.action)

        # ── web_search ────────────────────────────────────────────────────────
        if dec.action == "web_search":
            query_str = dec.query or perc.intent.primary_goal
            if query_str in state.search_queries_used:
                # Modify query to avoid repetition
                query_str += f" {perc.intent.topic} latest"
            state.search_queries_used.append(query_str)

            ar = await A.run_web_search(mcp, query_str)
            if ar.success and ar.data:
                results = ar.data
                _result_ok(f"Got {len(results)} results")
                new_urls = [r.url for r in results if r.url and r.url not in state.urls_visited]
                state.pending_urls = new_urls[:5]
                if verbose:
                    for r in results:
                        console.print(f"    [dim]{r.title[:60]}[/dim]  {r.url}")
            else:
                _result_warn(f"Search failed: {ar.error}")

        # ── fetch_url ─────────────────────────────────────────────────────────
        elif dec.action == "fetch_url":
            url = dec.url or (state.pending_urls[0] if state.pending_urls else "")
            if not url:
                _result_warn("No URL to fetch -- switching to web_search next")
                state.action_history[-1] = "web_search"  # correct history
                continue
            if url in state.urls_visited:
                if state.pending_urls:
                    state.pending_urls.pop(0)
                continue

            state.urls_visited.append(url)
            if url in state.pending_urls:
                state.pending_urls.remove(url)

            ar = await A.run_fetch_url(mcp, url)
            if ar.success and ar.data:
                content = ar.data.get("text", "") if isinstance(ar.data, dict) else str(ar.data)
                last_fetched_text = content
                last_fetched_url = url
                _result_ok(f"Fetched {len(content):,} chars from {url}")
            else:
                _result_warn(f"Fetch failed: {ar.error}")

        # ── memory_lookup ─────────────────────────────────────────────────────
        elif dec.action == "memory_lookup":
            ar = A.run_memory_lookup(perc.intent.topic, perc.entities)
            snap = ar.data or {}
            n = snap.get("total_facts", 0)
            _result_ok(f"Memory: {n} relevant facts, {len(snap.get('prior_sessions', []))} prior sessions")
            if verbose and snap.get("facts"):
                for f in snap["facts"][:3]:
                    console.print(f"    [dim]{f['content'][:80]}[/dim]")

        # ── save_memory ───────────────────────────────────────────────────────
        elif dec.action == "save_memory":
            if not last_fetched_text:
                _result_warn("No fetched content to save -- skipping")
                continue
            ar = await A.run_save_memory(state, perc, last_fetched_text, last_fetched_url)
            if ar.success and ar.data:
                n = len(ar.data)
                session.facts_found += n
                _result_ok(f"Saved {n} facts  (total: {session.facts_found})")
                contradictions = [f for f in ar.data if f.contradicts]
                if contradictions:
                    _result_warn(f"{len(contradictions)} fact(s) contradict prior knowledge!")
            else:
                _result_warn(f"Save failed: {ar.error}")
            last_fetched_text = ""  # consumed

        # ── summarize ─────────────────────────────────────────────────────────
        elif dec.action in ("summarize", "done"):
            ar = A.run_summarize(state, perc)
            conclusion = ar.data if ar.success else f"(summarize failed: {ar.error})"
            session.conclusion = conclusion
            session.status = "completed"
            session.ended_at = datetime.now(timezone.utc).isoformat()
            save_session(session)
            _result_ok("Conclusion generated")
            return conclusion

        # Save progress after every iteration
        save_session(session)

        if dec.converged and dec.action not in ("summarize", "done"):
            console.print("  [green]✓ Converged -- generating conclusion[/green]")
            ar = A.run_summarize(state, perc)
            conclusion = ar.data if ar.success else "(summarize failed)"
            session.conclusion = conclusion
            session.status = "completed"
            session.ended_at = datetime.now(timezone.utc).isoformat()
            save_session(session)
            return conclusion

    # Exhausted all iterations without explicit done
    ar = A.run_summarize(state, perc)
    conclusion = ar.data if ar.success else "Research reached iteration limit without a clear conclusion."
    session.conclusion = conclusion
    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc).isoformat()
    save_session(session)
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
