# Architecture Documentation

## System Overview

Code Assistant implements a multi-agent system for automated software development, powered by BAND for agent coordination. The system follows a pipeline architecture where tasks flow through specialized agents.

## Core Components

### 1. Agent Layer

Each agent is an autonomous unit with:
- **LLM Integration**: Connects to Claude (Anthropic) or GPT-4 (OpenAI)
- **Communication**: Uses BAND for inter-agent messaging
- **State Access**: Reads and writes to shared state

```
┌─────────────────────────────────────────┐
│                Agent                     │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ LLM Client  │  │ Communication   │   │
│  │             │  │ Layer (BAND)    │   │
│  └─────────────┘  └─────────────────┘   │
│  ┌─────────────────────────────────┐    │
│  │      State Access               │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

### 2. Communication Layer

The `CommunicationLayer` class handles:
- **Message Types**: TASK, RESPONSE, STATUS_UPDATE, ERROR, etc.
- **Priority Levels**: LOW, NORMAL, HIGH, CRITICAL
- **Request/Response Pattern**: With correlation IDs for tracking
- **Broadcast**: One-to-many message delivery

### 3. State Manager

Centralized state management:
- **Pipeline States**: User task context
- **Tasks**: Individual work items
- **Code Changes**: Files modified
- **Reviews**: Feedback and approvals

### 4. Workflow Pipeline

Sequential phases:
1. **Planning** → Planner creates implementation plan
2. **Plan Review** → Plan Reviewer validates
3. **Coding** → Coder implements changes
4. **Code Review** → Code Reviewer checks quality
5. **Testing** → Test Engineer creates tests
6. **Debugging** → Debugger fixes issues (if needed)
7. **Merging** → Mergemaster creates PR

## Data Flow

```
User Task
    │
    ▼
┌─────────────┐
│  Conductor  │ ◄── Receives task
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Planner   │ ──► │Plan Reviewer│
└──────┬──────┘     └──────┬──────┘
       │                   │
       │ (if approved)    │
       ▼                   │
┌─────────────┐            │
│    Coder    │ ◄──────────┘
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│Code Reviewer│ ──► │  Debugger   │ (if needed)
└──────┬──────┘     └──────┬──────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│Test Engineer│     │ All agents  │
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 ▼
          ┌─────────────┐
          │ Mergemaster │
          └──────┬──────┘
                 │
                 ▼
          ┌─────────────┐
          │   GitHub    │
          │     PR      │
          └─────────────┘
```

## BAND Integration Details

### Agent Registration

Each agent is registered on the BAND platform:
1. Create agent via BAND dashboard
2. Get Agent UUID and API Key
3. Configure in `agent_config.yaml`

### Message Flow

```
Agent A                           Agent B
   │                                 │
   │──── Message ──────────────────► │
   │     (via BAND WebSocket)        │
   │                                 │
   │◄─── Response ───────────────── │
   │     (correlation_id matches)   │
```

### State Synchronization

All agents read/write to the shared `StateManager`:
- Pipeline context is shared
- Tasks are tracked across agents
- Reviews accumulate feedback

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `BAND_API_KEY` | BAND platform API key |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `OPENAI_API_KEY` | OpenAI API key for GPT-4 |
| `GITHUB_TOKEN` | GitHub personal access token |
| `THENVOI_REST_URL` | BAND REST API URL |
| `THENVOI_WS_URL` | BAND WebSocket URL |

### Agent Configuration

```yaml
agents:
  conductor:
    agent_id: "${CONDUCTOR_AGENT_ID}"
    api_key: "${BAND_API_KEY}"
    role: "orchestrator"
```

## Extension Points

### Adding New Agents

1. Create agent class inheriting from `BaseAgent`
2. Implement `process_message` and `execute_task`
3. Add to `AgentFactory.create_all_agents()`
4. Update `CodingPipeline.initialize()`

### Adding New Message Types

1. Add to `MessageType` enum
2. Register handlers in agent initialization
3. Implement processing logic

### Custom Workflows

Modify `CodingPipeline.execute()` to:
- Add/remove phases
- Change agent routing
- Implement conditional logic

## Security Considerations

- Store API keys in `.env` (not in code)
- Add `.env` to `.gitignore`
- Use environment variable substitution in configs
- Validate all external inputs

## Performance

- Agents run asynchronously
- Parallel task execution where possible
- State updates are non-blocking
- WebSocket for real-time communication

## Monitoring

- Structured logging with `rich`
- Pipeline state exportable as JSON
- Status endpoints for health checks
- Activity logs in web UI