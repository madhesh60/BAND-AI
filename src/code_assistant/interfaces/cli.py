"""Command-line interface for the coding assistant."""

import asyncio
import sys
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from code_assistant.workflows.coding_pipeline import CodingPipeline
from code_assistant.utils.logging import setup_logging, console as rich_console

console = Console()


def run_interactive_shell():
    """Run an interactive Click REPL command shell for the Code Assistant.
    
    The shell supports standard slash commands (/task, /status, /history, /show, /approve, /reject, /help, /exit)
    which query and update the StateManager and drive the LangGraph agent state machine.
    """
    import json
    from code_assistant.band_integration.state_manager import StateManager
    
    console.print(Panel(
        "[bold cyan]Code Assistant Interactive Shell[/bold cyan]\n\n"
        "Type [bold green]/help[/bold green] to list commands, [bold green]/exit[/bold green] to quit.\n"
        "To start a task: [bold green]/task Implement math utility[/bold green]",
        title="Interactive Shell",
        border_style="cyan"
    ))
    
    state_manager = StateManager()
    
    while True:
        try:
            line = console.input("[bold cyan]> [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting interactive shell.[/yellow]")
            break
            
        if not line:
            continue
            
        if line == "/exit" or line == "/quit":
            console.print("[yellow]Goodbye![/yellow]")
            break
            
        # Command Routing Logic:
        # We parse commands starting with a slash '/' and route them to their respective functions.
        if line.startswith("/task"):
            task_desc = line[len("/task"):].strip()
            if not task_desc:
                console.print("[red]Error: Task description cannot be empty.[/red]")
                continue
            
            console.print(Panel.fit(
                f"[bold cyan]Code Assistant[/bold cyan]\n"
                f"Task: {task_desc}",
                title="Starting Pipeline",
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
                        progress.add_task("Executing pipeline...", total=None)
                        result = await pipeline.execute(task_desc)
                    _display_result(result)
                finally:
                    await pipeline.shutdown()

            asyncio.run(execute())
            
        elif line == "/status":
            if not state_manager._states:
                console.print("[yellow]No pipelines have been created yet.[/yellow]")
                continue
            latest_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
            pipeline = state_manager.get_pipeline(latest_id)
            
            class DummyResult:
                def __init__(self, p):
                    self.pipeline_id = p.pipeline_id
                    self.status = p.current_phase
                    self.start_time = p.created_at
                    self.end_time = p.updated_at if p.current_phase in ["completed", "error"] else "N/A"
                    self.completed_tasks = len([t for t in p.tasks.values() if t.status.value == "completed"])
                    self.total_tasks = len(p.tasks)
                    self.issues_found = len([r for r in p.reviews if r.get("status") in ["rejected", "needs_changes"]])
                    self.issues_fixed = len([t for t in p.tasks.values() if t.status.value == "completed" and "failed" in t.description.lower()])
                    self.pr_url = p.metadata.get("pr_url")
                    self.error = p.metadata.get("error")

            _display_result(DummyResult(pipeline))
            
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
                
                console.print(Panel.fit(
                    f"[bold cyan]Pipeline Details[/bold cyan]\n"
                    f"ID: {pipeline.pipeline_id}\n"
                    f"Task: {pipeline.user_task}\n"
                    f"Phase: {pipeline.current_phase.upper()}",
                    title="Pipeline Info",
                    border_style="cyan"
                ))
                
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Task ID", style="dim")
                table.add_column("Title")
                table.add_column("Assigned Agent")
                table.add_column("Status")

                for task in pipeline.tasks.values():
                    status_style = {
                        "completed": "green",
                        "pending": "dim",
                        "in_progress": "yellow",
                        "failed": "red"
                    }.get(task.status.value, "white")
                    table.add_row(
                        task.id[:8],
                        task.title,
                        task.assigned_agent or "N/A",
                        f"[{status_style}]{task.status.value.upper()}[/{status_style}]"
                    )
                console.print(table)
            else:
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Pipeline ID")
                table.add_column("Task")
                table.add_column("Phase/Status")
                table.add_column("Tasks Completed")
                table.add_column("Created At")

                sorted_pipelines = sorted(
                    state_manager._states.values(),
                    key=lambda p: p.created_at,
                    reverse=True
                )

                for p in sorted_pipelines:
                    comp_tasks = len([t for t in p.tasks.values() if t.status.value == "completed"])
                    tot_tasks = len(p.tasks)
                    status_style = "green" if p.current_phase == "completed" else "yellow"
                    table.add_row(
                        p.pipeline_id,
                        p.user_task[:50] + "..." if len(p.user_task) > 50 else p.user_task,
                        f"[{status_style}]{p.current_phase.upper()}[/{status_style}]",
                        f"{comp_tasks}/{tot_tasks}",
                        p.created_at[:19].replace("T", " ")
                    )
                console.print(table)
                
        elif line.startswith("/show"):
            parts = line.split()
            pipeline_id = parts[1] if len(parts) > 1 else None
            
            if not state_manager._states:
                console.print("[yellow]No pipelines have been created yet.[/yellow]")
                continue
                
            if not pipeline_id:
                pipeline_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
                
            pipeline = state_manager.get_pipeline(pipeline_id)
            if not pipeline:
                console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
                continue
                
            if not pipeline.code_changes:
                console.print("[yellow]No code changes recorded for this pipeline.[/yellow]")
                continue
                
            console.print(Panel.fit(
                f"[bold cyan]Code Changes for Pipeline {pipeline.pipeline_id}[/bold cyan]\n"
                f"Task: {pipeline.user_task}",
                title="Pipeline Code Artifacts",
                border_style="cyan"
            ))
            
            from rich.syntax import Syntax
            for change in pipeline.code_changes:
                file_path = change.get("file_path")
                change_type = change.get("change_type", "modify").upper()
                agent = change.get("agent", "unknown")
                content = change.get("content", "")
                
                color = "green" if change_type in ["CREATE", "ADD"] else "yellow" if change_type == "FIX" else "blue"
                
                console.print(f"\n[bold {color}]File: {file_path} ({change_type} by {agent})[/bold {color}]")
                if content:
                    lang = "python" if file_path.endswith(".py") else "javascript" if file_path.endswith(".js") else "text"
                    syntax = Syntax(content, lang, theme="monokai", line_numbers=True)
                    console.print(syntax)
                else:
                    console.print("[dim]Empty content[/dim]")
                    
        elif line.startswith("/approve"):
            parts = line.split()
            pipeline_id = parts[1] if len(parts) > 1 else None
            
            if not state_manager._states:
                console.print("[yellow]No active pipelines found.[/yellow]")
                continue
                
            if not pipeline_id:
                pipeline_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
                
            pipeline_state = state_manager.get_pipeline(pipeline_id)
            if not pipeline_state:
                console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
                continue
                
            if pipeline_state.current_phase not in ["plan_approval", "code_approval"]:
                console.print(f"[yellow]Pipeline {pipeline_id} is not waiting for approval. Current phase: {pipeline_state.current_phase}[/yellow]")
                continue
                
            console.print(f"[green]Approving pipeline {pipeline_id}...[/green]")
            
            async def run_approve():
                pipeline = CodingPipeline()
                await pipeline.initialize()
                pipeline.state_manager = state_manager
                try:
                    result = await pipeline.resume(pipeline_id, "approved")
                    console.print(f"[green]Resumed successfully! Status: {result.status}[/green]")
                finally:
                    await pipeline.shutdown()
                    
            asyncio.run(run_approve())
            
        elif line.startswith("/reject"):
            parts = line.split(maxsplit=2)
            pipeline_id = None
            feedback = ""
            
            if len(parts) == 3 and parts[1] in state_manager._states:
                pipeline_id = parts[1]
                feedback = parts[2]
            elif len(parts) >= 2:
                feedback = line[len("/reject"):].strip()
                if parts[1] in state_manager._states:
                    pipeline_id = parts[1]
                    feedback = ""
                    if len(parts) == 3:
                        feedback = parts[2]
            
            if not state_manager._states:
                console.print("[yellow]No active pipelines found.[/yellow]")
                continue
                
            if not pipeline_id:
                pipeline_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
                
            pipeline_state = state_manager.get_pipeline(pipeline_id)
            if not pipeline_state:
                console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
                continue
                
            if pipeline_state.current_phase not in ["plan_approval", "code_approval"]:
                console.print(f"[yellow]Pipeline {pipeline_id} is not waiting for approval. Current phase: {pipeline_state.current_phase}[/yellow]")
                continue
                
            if not feedback:
                feedback = console.input("[yellow]Enter feedback details (required): [/yellow]").strip()
                if not feedback:
                    console.print("[red]Error: Rejection requires feedback.[/red]")
                    continue
                    
            console.print(f"[red]Rejecting pipeline {pipeline_id} with feedback: {feedback}[/red]")
            
            async def run_resume():
                pipeline = CodingPipeline()
                await pipeline.initialize()
                pipeline.state_manager = state_manager
                try:
                    result = await pipeline.resume(pipeline_id, "rejected", feedback)
                    console.print(f"[green]Resumed successfully with feedback! Status: {result.status}[/green]")
                finally:
                    await pipeline.shutdown()
                    
            asyncio.run(run_resume())
            
        elif line == "/help":
            console.print("[bold]Available Commands:[/bold]")
            console.print("  [bold cyan]/task <description>[/bold cyan] - Start a new coding pipeline task")
            console.print("  [bold cyan]/status[/bold cyan]            - Show status of the latest pipeline")
            console.print("  [bold cyan]/history [id][/bold cyan]     - Show execution history")
            console.print("  [bold cyan]/show [id][/bold cyan]        - Show code changes of a pipeline")
            console.print("  [bold cyan]/approve [id][/bold cyan]      - Approve a paused implementation or code review step")
            console.print("  [bold cyan]/reject [id] <msg>[/bold cyan]   - Reject a paused step with feedback comments")
            console.print("  [bold cyan]/help[/bold cyan]              - Show this help message")
            console.print("  [bold cyan]/exit[/bold cyan] or [bold cyan]/quit[/bold cyan]     - Exit the interactive shell")
        else:
            console.print(f"[red]Unknown command: {line}. Type /help for assistance.[/red]")


@click.group(invoke_without_command=True)
@click.option("--log-level", default="INFO", help="Logging level")
@click.pass_context
def cli(ctx, log_level):
    """Code Assistant - Multi-agent coding workflow powered by BAND."""
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level
    setup_logging(level=log_level)
    
    if ctx.invoked_subcommand is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            run_interactive_shell()
        else:
            click.echo(ctx.get_help())


@cli.command()
@click.argument("task")
@click.option("--watch", is_flag=True, help="Watch pipeline progress")
@click.pass_context
def run(ctx, task, watch):
    """Execute a coding task through the agent pipeline."""
    console.print(Panel.fit(
        f"[bold cyan]Code Assistant[/bold cyan]\n"
        f"Task: {task}",
        title="Starting Pipeline",
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
                progress.add_task("Executing pipeline...", total=None)

                result = await pipeline.execute(task)

            # Display results
            _display_result(result)

        finally:
            await pipeline.shutdown()

    asyncio.run(execute())


@cli.command()
@click.pass_context
def agents(ctx):
    """List all available agents."""
    console.print(Panel.fit(
        "[bold cyan]Available Agents[/bold cyan]",
        title="Agent Registry",
        border_style="cyan",
    ))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Role")
    table.add_column("Description")

    agents_list = [
        ("conductor", "orchestrator", "Main workflow orchestrator"),
        ("planner", "planner", "Creates implementation plans"),
        ("plan_reviewer", "reviewer", "Validates and refines plans"),
        ("coder", "coder", "Implements code changes"),
        ("code_reviewer", "reviewer", "Reviews code quality"),
        ("test_engineer", "tester", "Creates and runs tests"),
        ("debugger", "debugger", "Fixes code issues"),
        ("mergemaster", "merger", "Handles Git operations"),
    ]

    for name, role, desc in agents_list:
        table.add_row(name, role, desc)

    console.print(table)


@cli.command()
@click.pass_context
def status(ctx):
    """Show current/latest pipeline status."""
    from code_assistant.band_integration.state_manager import StateManager
    
    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No pipelines have been created yet.[/yellow]")
        return

    # Get the latest pipeline by sorting by updated_at
    latest_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
    pipeline = state_manager.get_pipeline(latest_id)
    
    class DummyResult:
        def __init__(self, p):
            self.pipeline_id = p.pipeline_id
            self.status = p.current_phase
            self.start_time = p.created_at
            self.end_time = p.updated_at if p.current_phase in ["completed", "error"] else "N/A"
            self.completed_tasks = len([t for t in p.tasks.values() if t.status.value == "completed"])
            self.total_tasks = len(p.tasks)
            self.issues_found = len([r for r in p.reviews if r.get("status") in ["rejected", "needs_changes"]])
            self.issues_fixed = len([t for t in p.tasks.values() if t.status.value == "completed" and "failed" in t.description.lower()])
            self.pr_url = p.metadata.get("pr_url")
            self.error = p.metadata.get("error")

    _display_result(DummyResult(pipeline))


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
            console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
            return
        
        console.print(Panel.fit(
            f"[bold cyan]Pipeline Details[/bold cyan]\n"
            f"ID: {pipeline.pipeline_id}\n"
            f"Task: {pipeline.user_task}\n"
            f"Phase: {pipeline.current_phase.upper()}",
            title="Pipeline Info",
            border_style="cyan"
        ))
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Task ID", style="dim")
        table.add_column("Title")
        table.add_column("Assigned Agent")
        table.add_column("Status")

        for task in pipeline.tasks.values():
            status_style = {
                "completed": "green",
                "pending": "dim",
                "in_progress": "yellow",
                "failed": "red"
            }.get(task.status.value, "white")
            table.add_row(
                task.id[:8],
                task.title,
                task.assigned_agent or "N/A",
                f"[{status_style}]{task.status.value.upper()}[/{status_style}]"
            )
        console.print(table)
        
        if pipeline.reviews:
            console.print("\n[bold cyan]Reviews & Feedback[/bold cyan]")
            review_table = Table(show_header=True, header_style="bold magenta")
            review_table.add_column("Reviewer")
            review_table.add_column("Status")
            review_table.add_column("Comments")
            
            for rev in pipeline.reviews:
                status_style = "green" if rev.get("status") == "approved" else "red"
                review_table.add_row(
                    rev.get("reviewer", "N/A"),
                    f"[{status_style}]{rev.get('status', 'N/A').upper()}[/{status_style}]",
                    ", ".join(rev.get("comments", []))[:80]
                )
            console.print(review_table)
            
        if pipeline.code_changes:
            console.print("\n[bold cyan]Code Changes Summary[/bold cyan]")
            changes_table = Table(show_header=True, header_style="bold magenta")
            changes_table.add_column("File Path")
            changes_table.add_column("Change Type")
            changes_table.add_column("Authoring Agent")
            
            for change in pipeline.code_changes:
                changes_table.add_row(
                    change.get("file_path", "N/A"),
                    change.get("change_type", "N/A").upper(),
                    change.get("agent", "N/A")
                )
            console.print(changes_table)
            console.print(f"\n[dim]To view the full code, run: [bold cyan]uv run code-assistant show --pipeline-id {pipeline.pipeline_id}[/bold cyan][/dim]")
            
    else:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Pipeline ID")
        table.add_column("Task")
        table.add_column("Phase/Status")
        table.add_column("Tasks Completed")
        table.add_column("Created At")

        sorted_pipelines = sorted(
            state_manager._states.values(),
            key=lambda p: p.created_at,
            reverse=True
        )

        for p in sorted_pipelines:
            comp_tasks = len([t for t in p.tasks.values() if t.status.value == "completed"])
            tot_tasks = len(p.tasks)
            status_style = "green" if p.current_phase == "completed" else "yellow"
            table.add_row(
                p.pipeline_id,
                p.user_task[:50] + "..." if len(p.user_task) > 50 else p.user_task,
                f"[{status_style}]{p.current_phase.upper()}[/{status_style}]",
                f"{comp_tasks}/{tot_tasks}",
                p.created_at[:19].replace("T", " ")
            )
        console.print(table)


def _display_result(result):
    """Display pipeline execution result."""
    status_color = {
        "completed": "green",
        "running": "yellow",
        "error": "red",
    }.get(result.status, "white")

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")

    table.add_row("Pipeline ID", result.pipeline_id)
    table.add_row("Status", f"[{status_color}]{result.status.upper()}[/{status_color}]")
    table.add_row("Start Time", result.start_time)
    table.add_row("End Time", result.end_time or "N/A")
    table.add_row("Tasks", f"{result.completed_tasks}/{result.total_tasks}")
    table.add_row("Issues Found", str(result.issues_found))
    table.add_row("Issues Fixed", str(result.issues_fixed))

    if result.pr_url:
        table.add_row("PR URL", result.pr_url)

    if result.error:
        table.add_row("Error", f"[red]{result.error}[/red]")

    console.print(Panel.fit(
        table,
        title="[bold]Pipeline Result[/bold]",
        border_style="green",
    ))


@cli.command()
@click.option("--pipeline-id", help="Specific pipeline ID (defaults to latest)")
@click.option("--file", "file_filter", help="Specific file to view")
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
        console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
        return
        
    if not pipeline.code_changes:
        console.print("[yellow]No code changes recorded for this pipeline.[/yellow]")
        return
        
    console.print(Panel.fit(
        f"[bold cyan]Code Changes for Pipeline {pipeline.pipeline_id}[/bold cyan]\n"
        f"Task: {pipeline.user_task}",
        title="Pipeline Code Artifacts",
        border_style="cyan"
    ))
    
    for change in pipeline.code_changes:
        file_path = change.get("file_path")
        if file_filter and file_filter not in file_path:
            continue
            
        change_type = change.get("change_type", "modify").upper()
        agent = change.get("agent", "unknown")
        content = change.get("content", "")
        
        color = "green" if change_type in ["CREATE", "ADD"] else "yellow" if change_type == "FIX" else "blue"
        
        console.print(f"\n[bold {color}]File: {file_path} ({change_type} by {agent})[/bold {color}]")
        console.print("─" * len(f"File: {file_path} ({change_type} by {agent})"))
        
        if content:
            lang = "python" if file_path.endswith(".py") else "javascript" if file_path.endswith(".js") else "text"
            syntax = Syntax(content, lang, theme="monokai", line_numbers=True)
            console.print(syntax)
        else:
            console.print("[dim]Empty content[/dim]")


@cli.command()
@click.argument("pipeline-id", required=False)
@click.pass_context
def approve(ctx, pipeline_id):
    """Approve a paused step in the coding pipeline."""
    from code_assistant.band_integration.state_manager import StateManager
    
    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No active pipelines found.[/yellow]")
        return
        
    if not pipeline_id:
        pipeline_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
        
    pipeline_state = state_manager.get_pipeline(pipeline_id)
    if not pipeline_state:
        console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
        return
        
    if pipeline_state.current_phase not in ["plan_approval", "code_approval"]:
        console.print(f"[yellow]Pipeline {pipeline_id} is not waiting for approval. Current phase: {pipeline_state.current_phase}[/yellow]")
        return
        
    console.print(f"[green]Approving pipeline {pipeline_id}...[/green]")
    
    async def run_resume():
        pipeline = CodingPipeline()
        await pipeline.initialize()
        pipeline.state_manager = state_manager
        
        try:
            result = await pipeline.resume(pipeline_id, "approved")
            console.print(f"[green]Resumed successfully! Status: {result.status}[/green]")
        finally:
            await pipeline.shutdown()
            
    asyncio.run(run_resume())


@cli.command()
@click.argument("feedback")
@click.option("--pipeline-id", help="Specific pipeline ID (defaults to latest)")
@click.pass_context
def reject(ctx, feedback, pipeline_id):
    """Reject a paused step in the coding pipeline with feedback."""
    from code_assistant.band_integration.state_manager import StateManager
    
    state_manager = StateManager()
    if not state_manager._states:
        console.print("[yellow]No active pipelines found.[/yellow]")
        return
        
    if not pipeline_id:
        pipeline_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
        
    pipeline_state = state_manager.get_pipeline(pipeline_id)
    if not pipeline_state:
        console.print(f"[red]Pipeline ID {pipeline_id} not found.[/red]")
        return
        
    if pipeline_state.current_phase not in ["plan_approval", "code_approval"]:
        console.print(f"[yellow]Pipeline {pipeline_id} is not waiting for approval. Current phase: {pipeline_state.current_phase}[/yellow]")
        return
        
    console.print(f"[red]Rejecting pipeline {pipeline_id} with feedback: {feedback}[/red]")
    
    async def run_resume():
        pipeline = CodingPipeline()
        await pipeline.initialize()
        pipeline.state_manager = state_manager
        
        try:
            result = await pipeline.resume(pipeline_id, "rejected", feedback)
            console.print(f"[green]Resumed successfully with feedback! Status: {result.status}[/green]")
        finally:
            await pipeline.shutdown()
            
    asyncio.run(run_resume())


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()