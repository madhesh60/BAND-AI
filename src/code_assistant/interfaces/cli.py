"""Command-line interface for the coding assistant."""

import asyncio
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.prompt import Confirm, Prompt
from rich.columns import Columns
from rich import box

from code_assistant.workflows.coding_pipeline import CodingPipeline
from code_assistant.utils.logging import setup_logging, console as rich_console

console = Console()


# ─────────────────────────────────────────────
#  Shared helpers
# ─────────────────────────────────────────────

def _find_pending_pipeline(state_manager):
    """Return the most-recent pipeline that is waiting for a human approval, or None."""
    pending = [
        p for p in state_manager._states.values()
        if p.current_phase in ("plan_approval", "code_approval")
    ]
    if not pending:
        return None
    return max(pending, key=lambda p: p.updated_at)


def _phase_label(phase: str) -> str:
    """Return a human-friendly label for an approval phase."""
    return {
        "plan_approval": "Implementation Plan",
        "code_approval": "Generated Code",
    }.get(phase, phase.replace("_", " ").title())


def _show_pipeline_context(pipeline_state):
    """Print the relevant content (plan or code) so the user can review before deciding."""
    phase = pipeline_state.current_phase

    console.print()
    console.print(Rule(f"[bold yellow]Review Required — {_phase_label(phase)}[/bold yellow]", style="yellow"))

    if phase == "plan_approval":
        # Show the implementation plan stored in metadata, if available
        plan = pipeline_state.metadata.get("implementation_plan") or pipeline_state.metadata.get("plan")
        if plan:
            console.print(Panel(
                str(plan),
                title="[bold cyan]Implementation Plan[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            ))
        else:
            console.print(Panel(
                f"[dim]Task:[/dim] {pipeline_state.user_task}\n\n"
                "[dim]No detailed plan text stored. Check /history for task breakdown.[/dim]",
                title="[bold cyan]Plan Summary[/bold cyan]",
                border_style="cyan",
            ))

    elif phase == "code_approval":
        from rich.syntax import Syntax

        if pipeline_state.code_changes:
            console.print(Panel(
                f"[dim]Task:[/dim] {pipeline_state.user_task}\n"
                f"[dim]Files changed:[/dim] {len(pipeline_state.code_changes)}",
                title="[bold cyan]Code Change Summary[/bold cyan]",
                border_style="cyan",
            ))
            for change in pipeline_state.code_changes:
                file_path = change.get("file_path", "unknown")
                change_type = change.get("change_type", "modify").upper()
                agent = change.get("agent", "unknown")
                content = change.get("content", "")

                color = (
                    "green" if change_type in ("CREATE", "ADD")
                    else "yellow" if change_type == "FIX"
                    else "blue"
                )
                console.print(f"\n[bold {color}]▶  {file_path}  [{change_type} by {agent}][/bold {color}]")
                console.print("─" * min(80, len(f"   {file_path}  [{change_type} by {agent}]") + 4))
                if content:
                    lang = (
                        "python" if file_path.endswith(".py")
                        else "javascript" if file_path.endswith(".js")
                        else "text"
                    )
                    console.print(Syntax(content, lang, theme="monokai", line_numbers=True))
                else:
                    console.print("[dim]  (empty content)[/dim]")
        else:
            console.print(Panel(
                "[dim]No code changes recorded yet.[/dim]",
                title="[bold cyan]Code Review[/bold cyan]",
                border_style="cyan",
            ))

    console.print(Rule(style="yellow"))
    console.print()


def _interactive_approve_flow(pipeline_state, state_manager):
    """
    Show context, ask Y/N, then run approve or collect feedback for reject.
    Returns True if the user approved, False if rejected, None if skipped.
    """
    _show_pipeline_context(pipeline_state)

    pipeline_id = pipeline_state.pipeline_id
    phase_label = _phase_label(pipeline_state.current_phase)

    console.print(Panel(
        f"[bold]Pipeline:[/bold] [cyan]{pipeline_id}[/cyan]\n"
        f"[bold]Task:[/bold] {pipeline_state.user_task}\n"
        f"[bold]Awaiting:[/bold] [yellow]{phase_label} approval[/yellow]",
        title="[bold yellow]⏸  Action Required[/bold yellow]",
        border_style="yellow",
        padding=(0, 2),
    ))
    console.print()

    # Yes/No prompt
    try:
        approved = Confirm.ask(
            f"  [bold green]✔  Approve[/bold green] this {phase_label}?",
            default=True,
        )
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Approval cancelled.[/yellow]")
        return None

    if approved:
        console.print()
        console.print(f"[bold green]✔  Approving {phase_label}…[/bold green]")
        _run_resume(pipeline_id, "approved", None, state_manager)
        return True
    else:
        console.print()
        try:
            feedback = Prompt.ask(
                "  [bold red]✘  Feedback[/bold red] (explain what needs to change)",
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Rejection cancelled.[/yellow]")
            return None

        if not feedback:
            console.print("[red]Feedback is required to reject. Cancelling.[/red]")
            return None

        console.print()
        console.print(f"[bold red]✘  Rejecting with feedback…[/bold red]")
        _run_resume(pipeline_id, "rejected", feedback, state_manager)
        return False


def _run_resume(pipeline_id: str, decision: str, feedback: Optional[str], state_manager):
    """Async helper to resume a pipeline."""
    async def _do():
        pipeline = CodingPipeline()
        await pipeline.initialize()
        pipeline.state_manager = state_manager
        try:
            result = await pipeline.resume(pipeline_id, decision, feedback)
            if decision == "approved":
                console.print(Panel(
                    f"[green]Pipeline resumed successfully.[/green]\n"
                    f"[dim]Status:[/dim] {result.status.upper()}",
                    title="[bold green]✔  Approved[/bold green]",
                    border_style="green",
                ))
            else:
                console.print(Panel(
                    f"[yellow]Pipeline re-queued with your feedback.[/yellow]\n"
                    f"[dim]Status:[/dim] {result.status.upper()}",
                    title="[bold red]✘  Rejected[/bold red]",
                    border_style="red",
                ))
        finally:
            await pipeline.shutdown()

    asyncio.run(_do())


def _display_result(result):
    """Display pipeline execution result."""
    status_color = {
        "completed": "green",
        "running": "yellow",
        "error": "red",
    }.get(result.status, "white")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Value")

    table.add_row("Pipeline ID", f"[dim]{result.pipeline_id}[/dim]")
    table.add_row("Status", f"[{status_color} bold]{result.status.upper()}[/{status_color} bold]")
    table.add_row("Start Time", result.start_time[:19].replace("T", " ") if result.start_time else "N/A")
    table.add_row(
        "End Time",
        (result.end_time[:19].replace("T", " ") if result.end_time and result.end_time != "N/A" else "N/A"),
    )
    table.add_row("Tasks", f"{result.completed_tasks}/{result.total_tasks}")
    table.add_row("Issues Found", str(result.issues_found))
    table.add_row("Issues Fixed", str(result.issues_fixed))

    if result.pr_url:
        table.add_row("PR URL", f"[link={result.pr_url}]{result.pr_url}[/link]")
    if result.error:
        table.add_row("Error", f"[red]{result.error}[/red]")

    console.print(Panel.fit(
        table,
        title="[bold]Pipeline Result[/bold]",
        border_style=status_color,
    ))


# ─────────────────────────────────────────────
#  Interactive shell
# ─────────────────────────────────────────────

def run_interactive_shell():
    """Run an interactive Click REPL command shell for the Code Assistant."""
    from code_assistant.band_integration.state_manager import StateManager

    # ── Welcome banner ──────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        "[bold cyan]  ╔══════════════════════════════════╗[/bold cyan]\n"
        "[bold cyan]  ║   🤖  Code Assistant  v1.0       ║[/bold cyan]\n"
        "[bold cyan]  ╚══════════════════════════════════╝[/bold cyan]\n\n"
        "  Multi-agent coding workflow powered by [bold]BAND[/bold]\n\n"
        "  [dim]Quick start:[/dim]\n"
        "  [bold green]/task Implement a math utility[/bold green]   — start a new task\n"
        "  [bold green]/pending[/bold green]                          — see what needs your approval\n"
        "  [bold green]/approve[/bold green]                          — approve the latest pending step\n"
        "  [bold green]/help[/bold green]                             — all commands",
        title="[bold cyan]Interactive Shell[/bold cyan]",
        border_style="cyan",
        padding=(1, 3),
    ))
    console.print()

    state_manager = StateManager()
    current_pipeline_id = None

    # ── Hint if there's already something waiting ──────────────────────────
    pending = _find_pending_pipeline(state_manager)
    if pending:
        console.print(Panel(
            f"[yellow]A pipeline is waiting for your approval![/yellow]\n"
            f"[dim]Task:[/dim] {pending.user_task}\n"
            f"[dim]Phase:[/dim] {_phase_label(pending.current_phase)}\n\n"
            "Type [bold green]/approve[/bold green] to review and decide.",
            title="[bold yellow]⏸  Pending Approval[/bold yellow]",
            border_style="yellow",
        ))
        console.print()

    while True:
        try:
            line = console.input("[bold cyan]❯ [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting interactive shell.[/yellow]")
            break

        if not line:
            continue

        if line in ("/exit", "/quit"):
            console.print("[yellow]Goodbye! 👋[/yellow]")
            break

        # Reload state manager so it picks up all updates (including external/background agents)
        state_manager.load_state()

        # ── /task ──────────────────────────────────────────────────────────
        if line.startswith("/task"):
            task_desc = line[len("/task"):].strip()
            if not task_desc:
                console.print("[red]Usage: /task <description>[/red]")
                continue

            console.print(Panel.fit(
                f"[bold cyan]Task:[/bold cyan] {task_desc}",
                title="[bold]🚀 Starting Pipeline[/bold]",
                border_style="cyan",
            ))

            async def execute(td=task_desc):
                pipeline = CodingPipeline()
                await pipeline.initialize()
                try:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        progress.add_task("Running agents…", total=None)
                        result = await pipeline.execute(td)
                    _display_result(result)
                    # Hint if pipeline paused for approval
                    if result.status == "running":
                        sm2 = StateManager()
                        ps = sm2.get_pipeline(result.pipeline_id)
                        if ps and ps.current_phase in ("plan_approval", "code_approval"):
                            console.print(Panel(
                                f"[yellow]Pipeline paused for your review.[/yellow]\n\n"
                                f"Type [bold green]/approve[/bold green] to review and approve, or\n"
                                f"     [bold red]/reject[/bold red] to reject with feedback.",
                                title="[bold yellow]⏸  Action Required[/bold yellow]",
                                border_style="yellow",
                            ))
                    return result.pipeline_id
                finally:
                    await pipeline.shutdown()

            current_pipeline_id = asyncio.run(execute())

        # ── /pending ───────────────────────────────────────────────────────
        elif line == "/pending":
            pending_list = [
                p for p in state_manager._states.values()
                if p.current_phase in ("plan_approval", "code_approval")
            ]
            if not pending_list:
                console.print("[green]✔  No pipelines are waiting for approval.[/green]")
                continue

            table = Table(
                show_header=True,
                header_style="bold magenta",
                box=box.ROUNDED,
                border_style="yellow",
            )
            table.add_column("#", style="dim", width=3)
            table.add_column("Task")
            table.add_column("Awaiting", style="yellow")
            table.add_column("Since")

            for i, p in enumerate(
                sorted(pending_list, key=lambda x: x.updated_at, reverse=True), 1
            ):
                table.add_row(
                    str(i),
                    p.user_task[:55] + "…" if len(p.user_task) > 55 else p.user_task,
                    _phase_label(p.current_phase),
                    p.updated_at[:19].replace("T", " "),
                )

            console.print(Panel(
                table,
                title="[bold yellow]⏸  Pipelines Awaiting Approval[/bold yellow]",
                border_style="yellow",
            ))
            console.print("[dim]Type [bold]/approve[/bold] to review the latest one.[/dim]")

        # ── /approve ───────────────────────────────────────────────────────
        elif line.startswith("/approve"):
            parts = line.split()
            explicit_id = parts[1] if len(parts) > 1 else None

            if explicit_id:
                ps = state_manager.get_pipeline(explicit_id)
                if not ps:
                    console.print(f"[red]Pipeline '{explicit_id}' not found.[/red]")
                    continue
            else:
                # Try the current session's pipeline first if it's pending
                ps = None
                if current_pipeline_id:
                    p = state_manager.get_pipeline(current_pipeline_id)
                    if p and p.current_phase in ("plan_approval", "code_approval"):
                        ps = p
                
                # Fall back to finding the most recent pending pipeline
                if not ps:
                    ps = _find_pending_pipeline(state_manager)
                
                if not ps:
                    console.print("[green]✔  No pipelines are currently waiting for approval.[/green]")
                    continue

            if ps.current_phase not in ("plan_approval", "code_approval"):
                console.print(
                    f"[yellow]Pipeline is not waiting for approval. "
                    f"Current phase: [bold]{ps.current_phase}[/bold][/yellow]"
                )
                continue

            _interactive_approve_flow(ps, state_manager)

        # ── /reject ────────────────────────────────────────────────────────
        elif line.startswith("/reject"):
            parts = line.split(maxsplit=2)
            explicit_id = None
            inline_feedback = ""

            # Detect if second token is a known pipeline ID
            if len(parts) >= 2 and parts[1] in state_manager._states:
                explicit_id = parts[1]
                inline_feedback = parts[2] if len(parts) == 3 else ""
            elif len(parts) >= 2:
                inline_feedback = line[len("/reject"):].strip()

            ps = None
            if explicit_id:
                ps = state_manager.get_pipeline(explicit_id)
            else:
                # Try the current session's pipeline first if it's pending
                if current_pipeline_id:
                    p = state_manager.get_pipeline(current_pipeline_id)
                    if p and p.current_phase in ("plan_approval", "code_approval"):
                        ps = p
                
                if not ps:
                    ps = _find_pending_pipeline(state_manager)

            if not ps:
                console.print("[green]✔  No pipelines are currently waiting for approval.[/green]")
                continue

            if ps.current_phase not in ("plan_approval", "code_approval"):
                console.print(
                    f"[yellow]Pipeline is not waiting for approval. "
                    f"Current phase: [bold]{ps.current_phase}[/bold][/yellow]"
                )
                continue

            _show_pipeline_context(ps)

            feedback = inline_feedback
            if not feedback:
                try:
                    feedback = Prompt.ask(
                        "  [bold red]✘  Feedback[/bold red] (explain what needs to change)"
                    ).strip()
                except (KeyboardInterrupt, EOFError):
                    console.print("\n[yellow]Rejection cancelled.[/yellow]")
                    continue

            if not feedback:
                console.print("[red]Feedback is required to reject. Cancelling.[/red]")
                continue

            console.print(f"\n[bold red]✘  Rejecting with feedback…[/bold red]")
            _run_resume(ps.pipeline_id, "rejected", feedback, state_manager)

        # ── /status ────────────────────────────────────────────────────────
        elif line == "/status":
            if not state_manager._states:
                console.print("[yellow]No pipelines have been created yet.[/yellow]")
                continue
            
            p = None
            if current_pipeline_id:
                p = state_manager.get_pipeline(current_pipeline_id)
            if not p:
                latest_id = max(
                    state_manager._states.keys(),
                    key=lambda k: state_manager._states[k].updated_at,
                )
                p = state_manager.get_pipeline(latest_id)

            class _R:
                def __init__(self, p):
                    self.pipeline_id = p.pipeline_id
                    self.status = p.current_phase
                    self.start_time = p.created_at
                    self.end_time = p.updated_at if p.current_phase in ("completed", "error") else "N/A"
                    self.completed_tasks = len([t for t in p.tasks.values() if t.status.value == "completed"])
                    self.total_tasks = len(p.tasks)
                    self.issues_found = len([r for r in p.reviews if r.get("status") in ("rejected", "needs_changes")])
                    self.issues_fixed = len([t for t in p.tasks.values() if t.status.value == "completed" and "failed" in t.description.lower()])
                    self.pr_url = p.metadata.get("pr_url")
                    self.error = p.metadata.get("error")

            _display_result(_R(p))

            # Nudge if approval pending
            if p.current_phase in ("plan_approval", "code_approval"):
                console.print(
                    f"\n[bold yellow]⏸  This pipeline is waiting for your approval "
                    f"({_phase_label(p.current_phase)}).[/bold yellow]\n"
                    "   Type [bold green]/approve[/bold green] to review and decide."
                )

        # ── /history ───────────────────────────────────────────────────────
        elif line.startswith("/history"):
            parts = line.split()
            pipeline_id = parts[1] if len(parts) > 1 else None

            if not state_manager._states:
                console.print("[yellow]No pipeline execution history found.[/yellow]")
                continue

            if pipeline_id:
                pipeline = state_manager.get_pipeline(pipeline_id)
                if not pipeline:
                    console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
                    continue
                _show_history_detail(pipeline)
            else:
                _show_history_list(state_manager)

        # ── /show ──────────────────────────────────────────────────────────
        elif line.startswith("/show"):
            parts = line.split()
            pipeline_id = parts[1] if len(parts) > 1 else None

            if not state_manager._states:
                console.print("[yellow]No pipelines have been created yet.[/yellow]")
                continue

            if not pipeline_id:
                if current_pipeline_id:
                    pipeline_id = current_pipeline_id
                else:
                    pipeline_id = max(
                        state_manager._states.keys(),
                        key=lambda k: state_manager._states[k].updated_at,
                    )

            pipeline = state_manager.get_pipeline(pipeline_id)
            if not pipeline:
                console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
                continue

            _show_code_changes(pipeline)

        # ── /help ──────────────────────────────────────────────────────────
        elif line == "/help":
            _print_help()

        else:
            console.print(
                f"[red]Unknown command:[/red] [bold]{line}[/bold]  "
                "— type [bold green]/help[/bold green] for a list of commands."
            )


# ─────────────────────────────────────────────
#  Reusable display helpers
# ─────────────────────────────────────────────

def _print_help():
    """Print the help table."""
    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=box.ROUNDED,
        border_style="cyan",
        padding=(0, 1),
    )
    table.add_column("Command", style="bold green", no_wrap=True)
    table.add_column("Description")

    rows = [
        ("/task <description>",    "Start a new coding pipeline task"),
        ("/pending",               "List all pipelines waiting for your approval"),
        ("/approve [id]",          "Review and approve the latest (or specific) pending step"),
        ("/reject [id] [msg]",     "Reject the latest (or specific) pending step with feedback"),
        ("/status",                "Show status of the most recent pipeline"),
        ("/history [id]",          "Browse execution history; pass an ID for details"),
        ("/show [id]",             "View code changes for the latest (or specific) pipeline"),
        ("/help",                  "Show this help"),
        ("/exit  or  /quit",       "Exit the interactive shell"),
    ]
    for cmd, desc in rows:
        table.add_row(cmd, desc)

    console.print(Panel(table, title="[bold cyan]Available Commands[/bold cyan]", border_style="cyan"))


def _show_history_detail(pipeline):
    """Show detailed history for a single pipeline."""
    console.print(Panel.fit(
        f"[bold]ID:[/bold]    [dim]{pipeline.pipeline_id}[/dim]\n"
        f"[bold]Task:[/bold]  {pipeline.user_task}\n"
        f"[bold]Phase:[/bold] [cyan]{pipeline.current_phase.upper()}[/cyan]",
        title="[bold cyan]Pipeline Details[/bold cyan]",
        border_style="cyan",
    ))

    table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE_HEAVY)
    table.add_column("Task ID", style="dim")
    table.add_column("Title")
    table.add_column("Agent")
    table.add_column("Status")

    for task in pipeline.tasks.values():
        s = task.status.value
        style = {"completed": "green", "pending": "dim", "in_progress": "yellow", "failed": "red"}.get(s, "white")
        table.add_row(task.id[:8], task.title, task.assigned_agent or "N/A", f"[{style}]{s.upper()}[/{style}]")

    console.print(table)

    if pipeline.reviews:
        rt = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE_HEAVY)
        rt.add_column("Reviewer")
        rt.add_column("Status")
        rt.add_column("Comments")
        for rev in pipeline.reviews:
            st = rev.get("status", "N/A")
            col = "green" if st == "approved" else "red"
            rt.add_row(
                rev.get("reviewer", "N/A"),
                f"[{col}]{st.upper()}[/{col}]",
                ", ".join(rev.get("comments", []))[:80],
            )
        console.print("\n[bold cyan]Reviews & Feedback[/bold cyan]")
        console.print(rt)

    if pipeline.code_changes:
        console.print("\n[bold cyan]Code Changes Summary[/bold cyan]")
        ct = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE_HEAVY)
        ct.add_column("File Path")
        ct.add_column("Change Type")
        ct.add_column("Agent")
        for change in pipeline.code_changes:
            ct.add_row(change.get("file_path", "N/A"), change.get("change_type", "N/A").upper(), change.get("agent", "N/A"))
        console.print(ct)
        console.print(f"\n[dim]Run [bold cyan]/show {pipeline.pipeline_id}[/bold cyan] to view full code.[/dim]")


def _show_history_list(state_manager):
    """Show a summary list of all pipelines."""
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED, border_style="cyan")
    table.add_column("Task", max_width=50)
    table.add_column("Phase/Status")
    table.add_column("Tasks")
    table.add_column("Created At")
    table.add_column("Needs Action?", style="yellow")

    sorted_pipelines = sorted(state_manager._states.values(), key=lambda p: p.created_at, reverse=True)

    for p in sorted_pipelines:
        comp = len([t for t in p.tasks.values() if t.status.value == "completed"])
        tot = len(p.tasks)
        st_col = "green" if p.current_phase == "completed" else "red" if p.current_phase == "error" else "yellow"
        needs = (
            f"[bold yellow]⏸  {_phase_label(p.current_phase)}[/bold yellow]"
            if p.current_phase in ("plan_approval", "code_approval")
            else "[dim]—[/dim]"
        )
        table.add_row(
            p.user_task[:50] + "…" if len(p.user_task) > 50 else p.user_task,
            f"[{st_col}]{p.current_phase.upper()}[/{st_col}]",
            f"{comp}/{tot}",
            p.created_at[:19].replace("T", " "),
            needs,
        )
    console.print(table)


def _show_code_changes(pipeline):
    """Show all code changes for a pipeline."""
    from rich.syntax import Syntax

    if not pipeline.code_changes:
        console.print("[yellow]No code changes recorded for this pipeline.[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold cyan]Code Changes — Pipeline {pipeline.pipeline_id}[/bold cyan]\n"
        f"Task: {pipeline.user_task}",
        title="Pipeline Code Artifacts",
        border_style="cyan",
    ))

    for change in pipeline.code_changes:
        file_path = change.get("file_path", "unknown")
        change_type = change.get("change_type", "modify").upper()
        agent = change.get("agent", "unknown")
        content = change.get("content", "")

        color = "green" if change_type in ("CREATE", "ADD") else "yellow" if change_type == "FIX" else "blue"
        console.print(f"\n[bold {color}]▶  {file_path}  [{change_type} by {agent}][/bold {color}]")
        console.print("─" * 60)
        if content:
            lang = "python" if file_path.endswith(".py") else "javascript" if file_path.endswith(".js") else "text"
            console.print(Syntax(content, lang, theme="monokai", line_numbers=True))
        else:
            console.print("[dim]  (empty content)[/dim]")


# ─────────────────────────────────────────────
#  Click command group
# ─────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def cli(ctx, log_level):
    """Code Assistant — Multi-agent coding workflow powered by BAND."""
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level
    setup_logging(level=log_level)

    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            run_interactive_shell()
        else:
            click.echo(ctx.get_help())


# ─────────────────────────────────────────────
#  run
# ─────────────────────────────────────────────

@cli.command()
@click.argument("task")
@click.option("--watch", is_flag=True, help="Watch pipeline progress")
@click.pass_context
def run(ctx, task, watch):
    """Execute a coding task through the agent pipeline."""
    console.print(Panel.fit(
        f"[bold cyan]Task:[/bold cyan] {task}",
        title="[bold]🚀 Starting Pipeline[/bold]",
        border_style="cyan",
    ))

    async def execute():
        pipeline = CodingPipeline()
        await pipeline.initialize()

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("Running agents…", total=None)
                result = await pipeline.execute(task)

            _display_result(result)

            # Nudge the user if the pipeline paused for approval
            if result.status == "running":
                from code_assistant.band_integration.state_manager import StateManager
                sm = StateManager()
                ps = sm.get_pipeline(result.pipeline_id)
                phase = ps.current_phase if ps else "unknown"

                if phase in ("plan_approval", "code_approval"):
                    console.print(Panel(
                        f"[yellow]The pipeline is waiting for you to review "
                        f"the [bold]{_phase_label(phase)}[/bold].[/yellow]\n\n"
                        "Run [bold green]uv run code-assistant approve[/bold green] to review and approve, or\n"
                        "    [bold red]uv run code-assistant reject \"your feedback\"[/bold red] to send it back.",
                        title="[bold yellow]⏸  Action Required[/bold yellow]",
                        border_style="yellow",
                    ))
        finally:
            await pipeline.shutdown()

    asyncio.run(execute())


# ─────────────────────────────────────────────
#  agents
# ─────────────────────────────────────────────

@cli.command()
@click.pass_context
def agents(ctx):
    """List all available agents."""
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED, border_style="cyan")
    table.add_column("Name", style="bold green")
    table.add_column("Role", style="cyan")
    table.add_column("Description")

    agents_list = [
        ("conductor",      "orchestrator", "Main workflow orchestrator"),
        ("planner",        "planner",      "Creates implementation plans"),
        ("plan_reviewer",  "reviewer",     "Validates and refines plans"),
        ("coder",          "coder",        "Implements code changes"),
        ("code_reviewer",  "reviewer",     "Reviews code quality"),
        ("test_engineer",  "tester",       "Creates and runs tests"),
        ("debugger",       "debugger",     "Fixes code issues"),
        ("mergemaster",    "merger",       "Handles Git operations"),
    ]

    for name, role, desc in agents_list:
        table.add_row(name, role, desc)

    console.print(Panel(table, title="[bold cyan]🤖 Agent Registry[/bold cyan]", border_style="cyan"))


# ─────────────────────────────────────────────
#  status
# ─────────────────────────────────────────────

@cli.command()
@click.pass_context
def status(ctx):
    """Show current/latest pipeline status."""
    from code_assistant.band_integration.state_manager import StateManager

    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No pipelines have been created yet.[/yellow]")
        return

    latest_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
    p = state_manager.get_pipeline(latest_id)

    class _R:
        def __init__(self, p):
            self.pipeline_id = p.pipeline_id
            self.status = p.current_phase
            self.start_time = p.created_at
            self.end_time = p.updated_at if p.current_phase in ("completed", "error") else "N/A"
            self.completed_tasks = len([t for t in p.tasks.values() if t.status.value == "completed"])
            self.total_tasks = len(p.tasks)
            self.issues_found = len([r for r in p.reviews if r.get("status") in ("rejected", "needs_changes")])
            self.issues_fixed = len([t for t in p.tasks.values() if t.status.value == "completed" and "failed" in t.description.lower()])
            self.pr_url = p.metadata.get("pr_url")
            self.error = p.metadata.get("error")

    _display_result(_R(p))

    if p.current_phase in ("plan_approval", "code_approval"):
        console.print(Panel(
            f"[yellow]This pipeline is waiting for your review of the "
            f"[bold]{_phase_label(p.current_phase)}[/bold].[/yellow]\n\n"
            "Run [bold green]uv run code-assistant approve[/bold green] to review and approve, or\n"
            "    [bold red]uv run code-assistant reject \"your feedback\"[/bold red] to send it back.",
            title="[bold yellow]⏸  Action Required[/bold yellow]",
            border_style="yellow",
        ))


# ─────────────────────────────────────────────
#  history
# ─────────────────────────────────────────────

@cli.command()
@click.option("--pipeline-id", help="Specific pipeline ID")
@click.pass_context
def history(ctx, pipeline_id):
    """Show pipeline execution history."""
    from code_assistant.band_integration.state_manager import StateManager

    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No pipeline execution history found.[/yellow]")
        return

    if pipeline_id:
        pipeline = state_manager.get_pipeline(pipeline_id)
        if not pipeline:
            console.print(f"[red]Pipeline ID '{pipeline_id}' not found.[/red]")
            return
        _show_history_detail(pipeline)
    else:
        _show_history_list(state_manager)


# ─────────────────────────────────────────────
#  show
# ─────────────────────────────────────────────

@cli.command()
@click.option("--pipeline-id", help="Specific pipeline ID (defaults to latest)")
@click.option("--file", "file_filter", help="Filter to a specific file path")
@click.pass_context
def show(ctx, pipeline_id, file_filter):
    """Show the code changes and files generated by a pipeline."""
    from code_assistant.band_integration.state_manager import StateManager
    from rich.syntax import Syntax

    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No pipelines have been created yet.[/yellow]")
        return

    if not pipeline_id:
        pipeline_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)

    pipeline = state_manager.get_pipeline(pipeline_id)
    if not pipeline:
        console.print(f"[red]Pipeline ID '{pipeline_id}' not found.[/red]")
        return

    if not pipeline.code_changes:
        console.print("[yellow]No code changes recorded for this pipeline.[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold cyan]Code Changes — Pipeline {pipeline.pipeline_id}[/bold cyan]\n"
        f"Task: {pipeline.user_task}",
        title="Pipeline Code Artifacts",
        border_style="cyan",
    ))

    for change in pipeline.code_changes:
        file_path = change.get("file_path", "unknown")
        if file_filter and file_filter not in file_path:
            continue

        change_type = change.get("change_type", "modify").upper()
        agent = change.get("agent", "unknown")
        content = change.get("content", "")

        color = "green" if change_type in ("CREATE", "ADD") else "yellow" if change_type == "FIX" else "blue"
        console.print(f"\n[bold {color}]▶  {file_path}  [{change_type} by {agent}][/bold {color}]")
        console.print("─" * 60)
        if content:
            lang = "python" if file_path.endswith(".py") else "javascript" if file_path.endswith(".js") else "text"
            console.print(Syntax(content, lang, theme="monokai", line_numbers=True))
        else:
            console.print("[dim]  (empty content)[/dim]")


# ─────────────────────────────────────────────
#  pending  (new command)
# ─────────────────────────────────────────────

@cli.command()
@click.pass_context
def pending(ctx):
    """List all pipelines that are waiting for your approval."""
    from code_assistant.band_integration.state_manager import StateManager

    state_manager = StateManager()
    pending_list = [
        p for p in state_manager._states.values()
        if p.current_phase in ("plan_approval", "code_approval")
    ]

    if not pending_list:
        console.print(Panel(
            "[green]✔  No pipelines are currently waiting for approval.[/green]",
            title="Pending Approvals",
            border_style="green",
        ))
        return

    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        border_style="yellow",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Task")
    table.add_column("Awaiting", style="yellow")
    table.add_column("Paused Since")

    for i, p in enumerate(sorted(pending_list, key=lambda x: x.updated_at, reverse=True), 1):
        table.add_row(
            str(i),
            p.user_task[:55] + "…" if len(p.user_task) > 55 else p.user_task,
            _phase_label(p.current_phase),
            p.updated_at[:19].replace("T", " "),
        )

    console.print(Panel(
        table,
        title="[bold yellow]⏸  Pipelines Awaiting Your Approval[/bold yellow]",
        border_style="yellow",
    ))
    console.print(
        "\n[dim]Run [bold green]uv run code-assistant approve[/bold green] "
        "to review and approve the latest one.[/dim]"
    )


# ─────────────────────────────────────────────
#  approve
# ─────────────────────────────────────────────

@cli.command()
@click.argument("pipeline-id", required=False)
@click.pass_context
def approve(ctx, pipeline_id):
    """Review and approve a paused pipeline step.

    If no PIPELINE-ID is given, the most recent pending pipeline is used.
    The command will show you the plan or code and ask for confirmation.
    """
    from code_assistant.band_integration.state_manager import StateManager

    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No active pipelines found.[/yellow]")
        return

    if pipeline_id:
        ps = state_manager.get_pipeline(pipeline_id)
        if not ps:
            console.print(f"[red]Pipeline '{pipeline_id}' not found.[/red]")
            return
    else:
        ps = _find_pending_pipeline(state_manager)
        if not ps:
            console.print(Panel(
                "[green]✔  No pipelines are currently waiting for approval.[/green]\n\n"
                "[dim]Run [bold]uv run code-assistant pending[/bold] to check for pending items.[/dim]",
                title="Nothing to Approve",
                border_style="green",
            ))
            return

    if ps.current_phase not in ("plan_approval", "code_approval"):
        console.print(
            f"[yellow]Pipeline is not waiting for approval.\n"
            f"Current phase: [bold]{ps.current_phase}[/bold][/yellow]"
        )
        return

    _interactive_approve_flow(ps, state_manager)


# ─────────────────────────────────────────────
#  reject
# ─────────────────────────────────────────────

@cli.command()
@click.argument("feedback", required=False)
@click.option("--pipeline-id", help="Specific pipeline ID (defaults to latest pending)")
@click.pass_context
def reject(ctx, feedback, pipeline_id):
    """Reject a paused pipeline step with feedback.

    FEEDBACK can be given inline or you will be prompted for it interactively.
    If no --pipeline-id is given, the most recent pending pipeline is used.
    """
    from code_assistant.band_integration.state_manager import StateManager

    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No active pipelines found.[/yellow]")
        return

    if pipeline_id:
        ps = state_manager.get_pipeline(pipeline_id)
        if not ps:
            console.print(f"[red]Pipeline '{pipeline_id}' not found.[/red]")
            return
    else:
        ps = _find_pending_pipeline(state_manager)
        if not ps:
            console.print(Panel(
                "[green]✔  No pipelines are currently waiting for approval.[/green]",
                title="Nothing to Reject",
                border_style="green",
            ))
            return

    if ps.current_phase not in ("plan_approval", "code_approval"):
        console.print(
            f"[yellow]Pipeline is not waiting for approval.\n"
            f"Current phase: [bold]{ps.current_phase}[/bold][/yellow]"
        )
        return

    # Show context so user knows what they're rejecting
    _show_pipeline_context(ps)

    console.print(Panel(
        f"[bold]Pipeline:[/bold] [cyan]{ps.pipeline_id}[/cyan]\n"
        f"[bold]Task:[/bold] {ps.user_task}\n"
        f"[bold]Awaiting:[/bold] [yellow]{_phase_label(ps.current_phase)} approval[/yellow]",
        title="[bold red]✘  Rejecting Pipeline Step[/bold red]",
        border_style="red",
        padding=(0, 2),
    ))
    console.print()

    if not feedback:
        try:
            feedback = Prompt.ask(
                "  [bold red]Feedback[/bold red] (explain what needs to change)"
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Rejection cancelled.[/yellow]")
            return

    if not feedback:
        console.print("[red]Feedback is required to reject. Cancelling.[/red]")
        return

    console.print(f"\n[bold red]✘  Rejecting with feedback…[/bold red]")
    _run_resume(ps.pipeline_id, "rejected", feedback, state_manager)


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()