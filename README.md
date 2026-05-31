# 🤖 Code Assistant — Multi-Agent Coding Workflow via BAND

> **BAND of Agents Hackathon — Track 2: Multi-Agent Software Development**
> 8 specialized AI agents that collaborate through **BAND as the real communication layer** to plan, write, review, test, debug, and ship code end-to-end.

---

## 🚀 How BAND Powers This System

BAND is **not** a simulation layer here. When `BAND_API_KEY` is set, every agent:

1. **Connects to BAND's WebSocket gateway** on startup via `ThenvoiLink.connect()` and subscribes to its dedicated chatroom.
2. **Sends every peer message to the BAND platform** (REST `POST /chats/{room}/messages`) with proper `@mention` routing to the target agent.
3. **Listens for incoming messages** via an async WebSocket event loop (`async for event in band_client:`) and dispatches them to local handlers.
4. **Stores long-term memory on BAND** via `POST /memories` so agents remember context across restarts.
5. **Provisions a dedicated chatroom per pipeline** so every task run is observable from the BAND web dashboard.

| BAND Feature | Where Used |
|---|---|
| WebSocket real-time events | `CommunicationLayer.connect()` → `_listen_to_events()` |
| REST chat message POST | `CommunicationLayer.send_message()` |
| Agent @mentions | `ChatMessageRequestMentionsItem` per recipient |
| Room provisioning | `_get_or_create_room()` per pipeline |
| Long-term memory | `store_platform_memory()` / `list_platform_memories()` |

**Without** `BAND_API_KEY` the system falls back to a local in-process bus so it still works offline.

---

## 🏗️ Architecture

```
User Task
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│              LangGraph StateGraph Workflow               │
│                                                          │
│  planning → plan_review → [HITL gate] → coding          │
│      → code_review → [HITL gate] → testing → merging   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
BAND Platform (real WebSocket + REST API)
    │  ┌──────────────┐    ┌──────────────┐
    ├─►│  Conductor   │◄──►│   Planner    │
    │  └──────────────┘    └──────────────┘
    │  ┌──────────────┐    ┌──────────────┐
    ├─►│    Coder     │◄──►│ Code Review  │
    │  └──────────────┘    └──────────────┘
    │  ┌──────────────┐    ┌──────────────┐
    └─►│Test Engineer │    │ Mergemaster  │
       └──────────────┘    └──────────────┘
```

### Agent Roles

| Agent | Role | Description |
|-------|------|-------------|
| Conductor | Orchestrator | Coordinates the entire LangGraph workflow |
| Planner | Planning | Breaks user tasks into actionable implementation steps |
| Plan Reviewer | Review | Validates plans before coding starts |
| Coder | Implementation | Writes code based on approved plans |
| Code Reviewer | Quality | Reviews code for bugs and best practices |
| Test Engineer | Testing | Creates and runs automated tests |
| Debugger | Fixes | Identifies and fixes code issues |
| Mergemaster | Git | Handles branches, commits, and PRs |

---

## ✨ Key Features

- **Real BAND WebSocket integration** — live bidirectional events between all agents
- **LangGraph state machine** — formal graph with interrupt-before gates for human approval
- **Persistent memory** — `PersistentMemorySaver` + BAND long-term memory API
- **Human-in-the-loop** — pause at plan and code review stages for user `/approve` or `/reject`
- **Multi-model fallback** — cycles through 5 free OpenRouter models on rate limits (never crashes)
- **Auto git init** — Mergemaster creates git repo if missing (no more `fatal: not a git repository`)
- **Null-safe LLM calls** — explicit None guards on every LLM response (no NoneType crashes)
- **Docker ready** — `docker/Dockerfile` + `docker/docker-compose.yml`
- **CI/CD** — GitHub Actions on every push

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) package manager
- BAND account and API key — [app.band.ai](https://app.band.ai)
- OpenRouter key (recommended free models) or Anthropic/OpenAI key

### Quick Start

```bash
# 1. Clone
git clone https://github.com/madhesh60/BAND-AI.git
cd BAND-AI

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.example .env
# Edit .env: add BAND_API_KEY and OVERALL_API_KEY (OpenRouter)

# 4. Configure agent IDs
cp agent_config.yaml.example agent_config.yaml
# Edit agent_config.yaml: add BAND agent IDs from app.band.ai

# 5. Run
uv run code-assistant
```

---

## 🖥️ CLI Usage

### Interactive Shell (default)

```bash
uv run code-assistant
```

| Command | Description |
|---------|-------------|
| `/task <description>` | Start a new coding pipeline |
| `/status` | Show latest pipeline status |
| `/history` | List all pipeline runs |
| `/show [id]` | View generated code changes |
| `/approve [id]` | Approve paused plan or code review |
| `/reject [id] <feedback>` | Reject with feedback (triggers re-plan) |
| `/help` | Show all commands |
| `/exit` | Quit |

### One-Shot Commands

```bash
# Run a task directly
uv run code-assistant run "Implement a Fibonacci calculator"

# Check status
uv run code-assistant status

# Show generated code
uv run code-assistant show

# View history
uv run code-assistant history

# List all agents
uv run code-assistant agents
```

---

## 🐳 Docker

```bash
# Build and start the interactive CLI
docker compose -f docker/docker-compose.yml run code-assistant

# Run a specific task
docker compose -f docker/docker-compose.yml run code-assistant run "Build a REST API"
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env`:

```env
# BAND Platform (required for real platform mode)
BAND_API_KEY=band_a_your_key_here
THENVOI_REST_URL=https://app.band.ai/
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket

# LLM — OpenRouter (recommended — many free models)
OVERALL_API_KEY=sk-or-v1-your_key_here
LLM_MODEL=google/gemma-2-9b-it:free

# Per-agent model overrides
CODER_MODEL=qwen/qwen-2.5-coder-32b-instruct:free
PLANNER_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

If `BAND_API_KEY` is not set or contains placeholder text, all agents fall back to the local in-process message bus. This is useful for local testing without BAND credentials.

---

## 🗂️ Project Structure

```
code-assistant/
├── src/code_assistant/
│   ├── agents/                 # 8 specialized agents
│   │   ├── base.py             # BaseAgent: LLM retry + BAND lifecycle
│   │   ├── conductor.py        # Orchestrator
│   │   ├── planner.py
│   │   ├── plan_reviewer.py
│   │   ├── coder.py
│   │   ├── code_reviewer.py    # Null-safe LLM response handling
│   │   ├── test_engineer.py
│   │   ├── debugger.py
│   │   └── mergemaster.py      # Auto git-init, PR creation
│   ├── band_integration/
│   │   ├── communication.py    # ThenvoiLink WebSocket + REST + memories
│   │   ├── state_manager.py    # Shared pipeline state
│   │   └── agent_factory.py    # Agent configuration factory
│   ├── interfaces/
│   │   └── cli.py              # Click CLI + interactive shell
│   ├── workflows/
│   │   └── coding_pipeline.py  # LangGraph StateGraph + PersistentMemorySaver
│   └── utils/
│       ├── config.py           # Config + API key routing
│       └── logging.py
├── tests/                      # 22 passing tests
├── docker/                     # Dockerfile + docker-compose.yml
├── docs/                       # ARCHITECTURE, CLI_USAGE, CONFIGURATION
├── experiments/                # Exploratory scripts
├── .github/workflows/ci.yml    # GitHub Actions CI
├── agent_config.yaml.example   # Template — copy to agent_config.yaml
├── .env.example                # Template — copy to .env
└── pyproject.toml
```

---

## 🧪 Tests

```bash
uv run pytest
# 22 passed — covers WebSocket event routing, BAND platform mirroring, LangGraph interrupts
```

---

## 🏆 Hackathon Requirements

| Requirement | Status |
|-------------|--------|
| ≥ 3 agents via BAND | ✅ 8 agents, all registered on BAND |
| BAND as real coordination layer | ✅ WebSocket events + REST messages + memories |
| Clear task handoffs | ✅ LangGraph graph with conditional edges |
| Shared state | ✅ `StateManager` + BAND memory API |
| Real business workflow | ✅ Full software dev pipeline |
| Human-in-the-loop | ✅ LangGraph interrupt gates |

---

## 📚 References

- [BAND SDK Documentation](https://docs.band.ai/integrations/sdks/tutorials/setup)
- [Thenvoi SDK](https://pypi.org/project/thenvoi/)
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/)
- [BAND of Agents Hackathon](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)

---

## License

MIT — see [LICENSE](LICENSE).