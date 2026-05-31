# Code Assistant - Multi-Agent Coding Workflow

A multi-agent coding assistant powered by BAND orchestration, designed for the BAND of Agents Hackathon (Track 2: Multi-Agent Software Development).

## Overview

Code Assistant is a sophisticated multi-agent system where 8 specialized AI agents collaborate to:
- Understand and plan coding tasks
- Implement high-quality code
- Review and validate changes
- Create comprehensive tests
- Debug and fix issues
- Manage Git operations and pull requests

## Architecture

```
User Task
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                      Conductor                            │
│                 (Main Orchestrator)                      │
└─────────────────────────────────────────────────────────┘
    │
    ├──► Planner ───► Plan Reviewer
    │
    ├──► Coder ───► Code Reviewer ───► Debugger (if needed)
    │
    ├──► Test Engineer
    │
    └──► Mergemaster (Git/PR)
```

### Agent Roles

| Agent | Role | Description |
|-------|------|-------------|
| Conductor | Orchestrator | Coordinates the entire workflow |
| Planner | Planning | Breaks down tasks into implementation steps |
| Plan Reviewer | Review | Validates and improves plans |
| Coder | Implementation | Writes code based on plans |
| Code Reviewer | Quality | Reviews code for bugs and best practices |
| Test Engineer | Testing | Creates and runs automated tests |
| Debugger | Fixes | Identifies and fixes code issues |
| Mergemaster | Git | Handles branches, commits, and PRs |

## Features

- **8 Specialized Agents**: Each agent has a specific role in the workflow
- **BAND Integration**: Agents communicate and coordinate via BAND platform
- **Cross-Model Review**: Claude and GPT models work together
- **Automated Testing**: Comprehensive test creation and execution
- **Git Integration**: Automatic branch creation, commits, and PRs
- **Real-time Progress**: Track pipeline execution via CLI or Web UI

## Installation

### Prerequisites

- Python 3.10+
- uv package manager
- BAND account and API key
- Anthropic API key (for Claude)
- OpenAI API key (for GPT-4)
- GitHub token (for PR operations)
- gh CLI (optional, for PR management)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/code-assistant.git
cd code-assistant
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Create environment file:
```bash
cp .env.example .env
```

4. Configure your API keys in `.env`:
```bash
# BAND Platform
BAND_API_KEY=band_u_your_api_key

# LLM Providers
ANTHROPIC_API_KEY=sk-ant-your-key
OPENAI_API_KEY=sk-your-key

# GitHub Integration
GITHUB_TOKEN=ghp_your_token
```

5. Create agents on BAND platform:
   - Go to https://app.band.ai/agents
   - Create 8 agents with names matching `agent_config.yaml`
   - Copy the Agent UUIDs to your `.env` file

6. Register agents and verify setup:
```bash
uv run python -m code_assistant agents
```

## Usage

### CLI Interface

Submit a coding task:
```bash
uv run code-assistant run "Add JWT authentication to the API"
```

List available agents:
```bash
uv run code-assistant agents
```

Check status:
```bash
uv run code-assistant status
```

### Web Interface

Start the web server:
```bash
uv run code-assistant-web
```

Open http://localhost:8000 in your browser.

## How BAND is Used

### Agent Communication

All agents communicate through BAND's platform using the `CommunicationLayer`:

```python
from code_assistant.band_integration import CommunicationLayer

# Send a task to another agent
await agent.send_to_agent(
    "planner",
    MessageType.TASK,
    {"pipeline_id": "123", "task": "Implement feature X"},
    subject="New task assignment"
)
```

### Shared State

Agents share state through `StateManager`:

```python
from code_assistant.band_integration import StateManager

state_manager = StateManager()
pipeline = state_manager.create_pipeline("Add login feature")
state_manager.add_task(pipeline_id=pipeline.pipeline_id, title="Create auth module")
```

### Agent Factory

Create configured agents using `AgentFactory`:

```python
from code_assistant.band_integration import AgentFactory

agents = AgentFactory.create_all_agents()
# Returns dict with all 8 agents configured
```

## Project Structure

```
code-assistant/
├── src/code_assistant/
│   ├── __init__.py           # Package init
│   ├── main.py               # Entry point
│   ├── agents/                # Agent implementations
│   │   ├── __init__.py
│   │   ├── base.py           # BaseAgent class
│   │   ├── conductor.py      # Orchestrator
│   │   ├── planner.py        # Task planner
│   │   ├── plan_reviewer.py # Plan validator
│   │   ├── coder.py          # Code implementation
│   │   ├── code_reviewer.py # Code quality check
│   │   ├── test_engineer.py  # Test creation
│   │   ├── debugger.py       # Issue fixer
│   │   └── mergemaster.py    # Git operations
│   ├── band_integration/      # BAND SDK integration
│   │   ├── __init__.py
│   │   ├── communication.py  # Message passing
│   │   ├── state_manager.py # Shared state
│   │   └── agent_factory.py # Agent creation
│   ├── interfaces/            # User interfaces
│   │   ├── __init__.py
│   │   ├── cli.py            # Command-line
│   │   └── web.py            # Web UI
│   ├── workflows/             # Pipeline orchestration
│   │   ├── __init__.py
│   │   └── coding_pipeline.py
│   └── utils/                 # Utilities
│       ├── __init__.py
│       ├── config.py         # Configuration
│       └── logging.py         # Logging setup
├── tests/                     # Test suite
├── pyproject.toml            # Project config
├── .env.example              # Env template
├── agent_config.yaml         # Agent config
├── README.md                  # This file
└── ARCHITECTURE.md            # Architecture docs
```

## Hackathon Requirements

This project meets all hackathon requirements:

- ✅ Minimum 3 agents collaborating through BAND (we have 8)
- ✅ Meaningful BAND usage as the coordination layer
- ✅ Clear task handoffs between agents
- ✅ Shared context and state management
- ✅ Real business workflow (software development)

### Judging Criteria Addressed

1. **Application of Technology (25%)**
   - 8 agents collaborating through BAND
   - Clear task handoffs and role specialization
   - Shared state management

2. **Presentation (25%)**
   - Clean CLI interface
   - Web UI for demos
   - Well-documented architecture

3. **Business Value (25%)**
   - Solves real software development workflow
   - Reduces manual coordination
   - Accelerates code implementation

4. **Originality (25%)**
   - Multi-model review (Claude + GPT)
   - End-to-end pipeline automation
   - Git/PR automation

## Development

### Run Tests
```bash
pytest tests/
```

### Lint Code
```bash
ruff check src/
```

### Install in Development Mode
```bash
uv pip install -e ".[dev]"
```

## License

MIT License - See LICENSE file for details.

## References

- [BAND SDK Documentation](https://docs.band.ai/integrations/sdks/tutorials/setup)
- [CodeBand Reference](https://github.com/thenvoi/codeband)
- [BAND of Agents Hackathon](https://lablab.ai/ai-hackathons/band-of-agents-hackathon)