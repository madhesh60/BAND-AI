# 🎬 Live Demo Guide

This guide walks through a complete end-to-end run of Code Assistant so you can reproduce the demo in under 5 minutes.

---

## Prerequisites

```bash
git clone https://github.com/madhesh60/BAND-AI.git
cd BAND-AI
uv sync
cp .env.example .env          # add your BAND_API_KEY + OVERALL_API_KEY
cp agent_config.yaml.example agent_config.yaml   # add BAND agent IDs
```

---

## Demo 1: Interactive Shell (Recommended)

```bash
uv run code-assistant
```

You'll see:

```
╭─ Interactive Shell ──────────────────────────╮
│ Code Assistant Interactive Shell              │
│                                               │
│ Type /help to list commands, /exit to quit.  │
│ To start a task: /task Implement math utility │
╰───────────────────────────────────────────────╯
>
```

### Step 1 — Submit a Task

```
> /task Create a Python script that calculates prime numbers up to N
```

Watch the agents collaborate in sequence:
1. **Planner** creates an implementation plan
2. **Plan Reviewer** validates it
3. Pipeline pauses ← **BAND WebSocket delivers the pause notification**

### Step 2 — Check the Plan

```
> /status
```

You'll see the pipeline is at `PLAN_APPROVAL` phase.

### Step 3 — Approve the Plan

```
> /approve
```

Agents continue:
4. **Coder** implements the code
5. **Code Reviewer** reviews it
6. Pipeline pauses again at `CODE_APPROVAL`

### Step 4 — Approve the Code

```
> /approve
```

7. **Test Engineer** writes tests
8. **Mergemaster** creates a branch, commits, and opens a PR

### Step 5 — See the Output

```
> /show
```

Displays the generated code with syntax highlighting.

---

## Demo 2: One-Shot CLI

```bash
uv run code-assistant run "Write a Fibonacci number generator"
```

Runs the full pipeline non-interactively. Useful for showing fast end-to-end execution.

---

## Demo 3: BAND Platform Visibility

While the pipeline runs, open **[app.band.ai](https://app.band.ai)** in your browser.

You'll see:
- A dedicated chatroom created for the pipeline run
- Each agent sending messages with `@mentions` to route tasks
- Long-term memories being stored after each phase

This proves BAND is the **actual coordination layer**, not a local queue.

---

## Demo 4: Pipeline History

```bash
uv run code-assistant history
```

Shows all previous runs. Pick a pipeline ID and view its details:

```bash
uv run code-assistant history --pipeline-id <id>
```

---

## Verification

```bash
uv run pytest  # Should show: 22 passed
```

---

## What Judges Are Looking For

| Criterion | Evidence |
|-----------|----------|
| BAND as real coordination | Open app.band.ai during run — see live messages |
| Agent collaboration | Watch logs show each agent handing off work |
| Human-in-the-loop | Use `/approve` and `/reject` commands mid-pipeline |
| Memory persistence | Kill and restart — pipeline resumes from checkpoint |
| Code quality | `uv run pytest` — 22 tests pass |
