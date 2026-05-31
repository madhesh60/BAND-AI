# Code Assistant Architecture

This document describes the internal architecture of the Code Assistant. It covers the LangGraph-based agentic workflow, the cooperative multi-agent communication layer built on BAND principles, and the state persistence mechanism.

---

## System Overview

The Code Assistant is built as a single-process application orchestrating a pool of specialized agents. Rather than running a single linear script, the codebase implements an agentic graph state machine using **LangGraph**. Cooperative agent execution is governed by a local blackboard communication layer.

```
                  ┌───────────────────────────────────────────┐
                  │                 User CLI                  │
                  └──────────────┬─────────────▲──────────────┘
                    /task        │             │ /approve or /reject
                                 ▼             │
                  ┌────────────────────────────┴──────────────┐
                  │          LangGraph Orchestration          │
                  └──────────────────────┬────────────────────┘
                                         │
                  ┌──────────────────────▼────────────────────┐
                  │       Local Message Bus (BAND layer)      │
                  └────────┬──────────┬──────────┬──────────┬─┘
                           │          │          │          │
                           ▼          ▼          ▼          ▼
                      [Planner]    [Coder]   [Reviewer]  [Debugger]
```

---

## 1. LangGraph State Machine

The entire development workflow is modeled as a directed graph (`StateGraph`) where each node corresponds to a logical step or agent execution context.

```
       [START]
          │
          ▼
     [planning] ──────────► [plan_review]
                                   │
                                   ▼
                             [plan_gate]  ◄─── (Human-in-the-Loop Interrupt)
                                   │
                    Rejected       ├─────────────────────────┐
             ┌─────────────────────┤                         │ Approved
             │                     │                         │
             ▼                     │                         ▼
     [re-planning]                 │                     [coding]
             ▲                     │                         │
             └─────────────────────┘                         ▼
                                                       [code_review]
                                                             │
                                                             ▼
                                                       [code_gate]  ◄─── (Human-in-the-Loop Interrupt)
                                                             │
                                              Rejected       ├─────────────────────────┐
                                       ┌─────────────────────┤                         │ Approved
                                       │                     │                         │
                                       ▼                     │                         ▼
                                 [debugging]                 │                     [testing]
                                       ▲                     │                         │
                                       └─────────────────────┘                         ▼
                                                                                   [merging]
                                                                                       │
                                                                                       ▼
                                                                                     [END]
```

### Nodes & Responsibilities

- **`planning`**: Invokes the `planner` agent to inspect the workspace and decompose the user prompt into a structured, step-by-step implementation plan.
- **`plan_review`**: Invokes the `plan_reviewer` agent to check the plan's feasibility, compatibility, and safety.
- **`plan_gate`**: An evaluation check. The graph pauses before entering this gate, creating a Human-in-the-loop (HITL) checkpoint. The user must explicitly `/approve` the plan or `/reject` it with feedback.
- **`coding`**: Invokes the `coder` agent to implement the approved plan. The agent writes files to the workspace.
- **`code_review`**: Invokes the `code_reviewer` agent to review the generated code files for quality, styling, and correctness.
- **`code_gate`**: An evaluation check. The graph pauses before entering this gate. The user must `/approve` the code changes or `/reject` them with feedback.
- **`debugging`**: If the code is rejected (by the reviewer or user), the `debugger` agent consumes the feedback logs and applies targeted fixes before routing back to `coding`.
- **`testing`**: Invokes the `test_engineer` agent to generate test suites and run tests.
- **`merging`**: Invokes the `mergemaster` agent to finalize files, run checkups, and update git references.

### Routing Logic

The state machine utilizes **conditional edges** to evaluate the flow:
- `_decide_after_plan_gate`: Routes to `coding` if `review_status == "approved"`, else loops back to `planning`.
- `_decide_after_code_gate`: Routes to `testing` if `review_status == "approved"`, else loops to `debugging`.

---

## 2. Cooperative Agent Communication (BAND)

Agent coordination is decoupled using a localized version of the **BAND collaborative layer**:

- **`LocalMessageBus`**: A central static registry where agents register themselves upon startup (`start()`). It acts as the local message transport.
- **`CommunicationLayer`**: Provides a client-like interface for agents to send point-to-point messages (`send_message`) or distribute information to multiple parties (`broadcast`).
- **`AgentMessage`**: Represents structured messages passed between agents containing fields like `sender`, `recipient`, `message_type`, `content`, `priority`, and `correlation_id`.
- **Message Hooks**: Every agent registers a callback callback for each `MessageType` enum (e.g. `MessageType.TASK`). When an agent receives a message, the bus dispatches it to `process_message` or `execute_task`.

---

## 3. Checkpointing & State Persistence

To support user interaction in a stateless CLI environment, the graph is compiled with a custom **`PersistentMemorySaver`**:

- **Local Storage**: Every state transition (including writes, metadata, and thread variables) is recorded in a pickle-serialized database at `.code_assistant_memory.pkl`.
- **Process Boundaries**: When an interrupt occurs, the Python process exits. The file `.code_assistant_memory.pkl` persists the state.
- **Resuming**: When the user runs `/approve` or `/reject` in the interactive shell or standard CLI command, the loader:
  1. Instantiates a new `CodingPipeline` and retrieves the state from `.code_assistant_memory.pkl` using the target `thread_id`.
  2. Updates the state with the user's decision and optional feedback via `aupdate_state`.
  3. Resumes execution from the interrupt checkpoint using `ainvoke(None, config)`.
