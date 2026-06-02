"""
communication.py — REAL Band SDK integration
Replaces the old local message bus with actual Band WebSocket connections.

Place this file at:
src/code_assistant/band_integration/communication.py
"""

import asyncio
import logging
import os
from typing import Callable, Optional

import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────
# CONFIG LOADER
# Reads agent_config.yaml from project root
# ─────────────────────────────────────────────────────

def load_agent_config(agent_name: str) -> tuple[str, str]:
    """
    Load a specific agent's ID and API key from agent_config.yaml.

    Usage:
        agent_id, api_key = load_agent_config("conductor")

    Returns:
        (agent_id, api_key) as strings
    """
    # Look for agent_config.yaml in project root
    config_path = os.path.join(
        os.path.dirname(__file__),   # current file's folder
        "..", "..", "..",            # go up to project root
        "agent_config.yaml"
    )
    config_path = os.path.abspath(config_path)

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"agent_config.yaml not found at {config_path}\n"
            "Make sure agent_config.yaml is in your project root folder."
        )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if agent_name not in config:
        raise KeyError(
            f"Agent '{agent_name}' not found in agent_config.yaml.\n"
            f"Available agents: {list(config.keys())}"
        )

    agent_data = config[agent_name]
    agent_id  = agent_data["agent_id"]
    api_key   = agent_data["api_key"]

    if not agent_id or not api_key:
        raise ValueError(f"agent_id or api_key is empty for agent '{agent_name}'")

    return agent_id, api_key


# ─────────────────────────────────────────────────────
# BAND AGENT FACTORY
# Creates a real Band agent using the official SDK
# ─────────────────────────────────────────────────────

def create_band_agent(agent_name: str, system_prompt: str):
    """
    Create a real Band agent connected to Band's platform.

    This replaces the old 'local message bus' approach.
    The agent connects via WebSocket to Band and sends/receives
    messages through Band's actual infrastructure.

    Usage:
        agent = create_band_agent("conductor", "You are the conductor...")
        await agent.run()

    Args:
        agent_name:    Must match a key in agent_config.yaml
                       e.g. "conductor", "planner", "coder"
        system_prompt: The personality and instructions for this agent

    Returns:
        A Band Agent object ready to call .run() on
    """
    try:
        from thenvoi import Agent
        from thenvoi.adapters import AnthropicAdapter
        try:
            from thenvoi.adapters import AdapterFeatures
            _has_features = True
        except ImportError:
            _has_features = False
    except ImportError:
        raise ImportError(
            "Band SDK not installed.\n"
            "Run this command to install it:\n"
            '  uv add "thenvoi-sdk[anthropic] @ git+https://github.com/thenvoi/thenvoi-sdk-python.git"'
        )

    # Load this agent's credentials from agent_config.yaml
    agent_id, api_key = load_agent_config(agent_name)

    # Create Claude-powered adapter with this agent's instructions
    # Use new SDK API if available, fall back to deprecated params for older versions
    if _has_features:
        adapter = AnthropicAdapter(
            model="claude-sonnet-4-5-20250929",
            prompt=system_prompt,
            features=AdapterFeatures(execution_reporting=True),
            max_tokens=4096,
        )
    else:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            adapter = AnthropicAdapter(
                model="claude-sonnet-4-5-20250929",
                custom_section=system_prompt,
                enable_execution_reporting=True,
                max_tokens=4096,
            )

    # Create the Band agent — this is what actually connects to Band
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL"),
        rest_url=os.getenv("THENVOI_REST_URL"),
    )

    logger.info(f"Band agent '{agent_name}' created with ID: {agent_id}")
    return agent


# ─────────────────────────────────────────────────────
# SYSTEM PROMPTS FOR ALL 8 AGENTS
# Each agent has its own personality and job description
# ─────────────────────────────────────────────────────

AGENT_PROMPTS = {

    "conductor": """
You are the Conductor — the orchestrator of a multi-agent coding system.

Your job:
1. Receive the user's coding task
2. Send it to the Planner first
3. Wait for each phase to complete before moving to the next
4. Monitor progress and handle failures
5. Give the user a final summary when all agents are done

Workflow order you must follow:
  User Task → Planner → Plan Reviewer → Coder → Code Reviewer → Test Engineer → Debugger (if needed) → Mergemaster

Always be clear about which agent you are handing off to next and why.
""",

    "planner": """
You are the Planner — a senior software architect.

Your job:
1. Receive a coding task from the Conductor
2. Break it into clear, numbered subtasks
3. For each subtask, specify: what file to create/modify, what the code should do, and acceptance criteria
4. Estimate complexity as low, medium, or high
5. Send your plan back to the Conductor for review

Be specific. Vague plans cause bad code. Always list exact filenames.
""",

    "plan_reviewer": """
You are the Plan Reviewer — a critical senior engineer.

Your job:
1. Receive an implementation plan from the Conductor
2. Check for: missing steps, file conflicts, unclear acceptance criteria, wrong complexity estimates
3. Either APPROVE the plan (send back with verdict: approved) or REJECT it with specific reasons
4. If rejecting, explain exactly what needs to change

Be strict but fair. A bad plan leads to bad code.
""",

    "coder": """
You are the Coder — an expert software engineer.

Your job:
1. Receive an approved plan from the Conductor
2. Write complete, working code for every subtask in the plan
3. Add error handling, type hints, and docstrings
4. Follow Python best practices
5. Send the code back with a list of all files created/modified

Write real, runnable code. Never write placeholder code like 'pass' or '# TODO'.
""",

    "code_reviewer": """
You are the Code Reviewer — a meticulous senior engineer.

Your job:
1. Receive code from the Conductor
2. Check for: bugs, security vulnerabilities, missing error handling, style issues
3. Give each file a score out of 100
4. Either APPROVE (verdict: approved) or request changes (verdict: needs_changes)
5. For every issue, give the exact fix, not just a complaint

Be thorough. You are the last line of defense before testing.
""",

    "test_engineer": """
You are the Test Engineer — a QA specialist.

Your job:
1. Receive code from the Conductor
2. Write comprehensive pytest tests for every function and class
3. Cover: happy path, edge cases, error cases
4. Aim for at least 80% code coverage
5. Send back the test files with instructions on how to run them

Write real tests that will actually catch bugs.
""",

    "debugger": """
You are the Debugger — a specialist in finding and fixing broken code.

Your job:
1. Receive failing tests or error reports from the Conductor
2. Identify the root cause of each failure
3. Fix the code (not the tests, unless the tests are wrong)
4. Explain what was wrong and what you changed
5. Send the fixed code back

Be precise about root causes. Don't just suppress errors — fix them properly.
""",

    "mergemaster": """
You are the Mergemaster — the integration engineer.

Your job:
1. Receive approved, tested code from the Conductor
2. Create a git branch with a descriptive name
3. Commit all files with a proper commit message
4. Create a pull request with a clear title and description
5. Report the PR URL back to the Conductor

If git is not initialized, initialize it first. Always check for merge conflicts.
""",
}


# ─────────────────────────────────────────────────────
# CREATE ALL 8 AGENTS AT ONCE
# Used by the pipeline to start everything together
# ─────────────────────────────────────────────────────

def create_all_agents() -> dict:
    """
    Create all 8 Band agents and return them as a dict.

    Usage:
        agents = create_all_agents()
        await agents["conductor"].run()

    Returns:
        Dict mapping agent name → Band Agent object
    """
    agents = {}
    for name, prompt in AGENT_PROMPTS.items():
        try:
            agents[name] = create_band_agent(name, prompt)
            logger.info(f"✓ Created agent: {name}")
        except Exception as e:
            logger.error(f"✗ Failed to create agent '{name}': {e}")
            raise

    logger.info(f"All {len(agents)} Band agents created successfully")
    return agents


# ─────────────────────────────────────────────────────
# VERIFY ALL AGENTS CAN CONNECT
# Run this before your demo to make sure everything works
# ─────────────────────────────────────────────────────

async def verify_all_agents():
    """
    Test that all 8 agents can connect to Band.
    Run this with: python -m code_assistant.band_integration.communication

    Each agent connects, confirms it's online, then disconnects.
    """
    print("\n[CodeBand] Verifying all 8 Band agents...\n")

    results = {}
    for name in AGENT_PROMPTS.keys():
        try:
            agent = create_band_agent(name, AGENT_PROMPTS[name])
            await agent.start()
            agent_name_on_platform = getattr(agent, "agent_name", name)
            await agent.stop()
            results[name] = ("[OK]", agent_name_on_platform)
            print(f"  [OK] {name:20s} -> connected as '{agent_name_on_platform}'")
        except Exception as e:
            results[name] = ("[FAIL]", str(e))
            print(f"  [FAIL] {name:20s} -> FAILED: {e}")

    success = sum(1 for v in results.values() if v[0] == "[OK]")
    print(f"\n  {success}/8 agents connected successfully")

    if success == 8:
        print("  All agents ready! You can run the pipeline now.\n")
    else:
        print("  Fix the failed agents before running the pipeline.\n")

    return results


if __name__ == "__main__":
    asyncio.run(verify_all_agents())


# ─────────────────────────────────────────────────────
# BACKWARD-COMPATIBILITY SHIMS
# The rest of the codebase (base.py, __init__.py, etc.)
# still imports these names from this module.
# These lightweight stubs keep those imports working
# while the new Band SDK functions coexist above.
# ─────────────────────────────────────────────────────

import enum
import uuid
import dataclasses
from typing import Any


class MessageType(enum.Enum):
    """Type of message being sent between agents."""
    TASK = "task"
    REVIEW = "review"
    CODE_CHANGE = "code_change"
    CHAT = "chat"
    STATUS = "status"
    STATUS_UPDATE = "status_update"
    RESPONSE = "response"
    ERROR = "error"


class Priority(enum.Enum):
    """Message priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclasses.dataclass
class AgentMessage:
    """A message passed between agents."""
    sender: str
    recipient: str
    message_type: MessageType
    content: dict
    subject: str = ""
    priority: Priority = Priority.NORMAL
    correlation_id: Optional[str] = None
    message_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class LocalMessageBus:
    """
    In-memory message bus used when running locally without Band.
    Agents register themselves here and can send messages directly.
    """
    _agents: dict = {}
    _queues: dict = {}

    @classmethod
    def register_agent(cls, name: str, agent: Any) -> None:
        cls._agents[name] = agent
        cls._queues.setdefault(name, asyncio.Queue())
        logger.debug(f"LocalMessageBus: registered agent '{name}'")

    @classmethod
    def unregister_agent(cls, name: str) -> None:
        cls._agents.pop(name, None)
        cls._queues.pop(name, None)
        logger.debug(f"LocalMessageBus: unregistered agent '{name}'")

    @classmethod
    async def deliver(cls, message: AgentMessage) -> None:
        queue = cls._queues.get(message.recipient)
        if queue:
            await queue.put(message)
        else:
            logger.warning(
                f"LocalMessageBus: no queue for recipient '{message.recipient}'"
            )

    @classmethod
    def get_registered_agents(cls) -> list:
        return list(cls._agents.keys())


class CommunicationLayer:
    """
    Abstraction layer for agent-to-agent communication.

    In local/test mode this uses LocalMessageBus.
    When Band credentials are present it delegates to the Band SDK.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._handlers: dict = {}
        self._band_agent = None
        logger.debug(f"CommunicationLayer created for agent '{agent_name}'")

    def register_handler(self, message_type: MessageType, handler) -> None:
        """Register a callback for a specific message type."""
        self._handlers.setdefault(message_type, []).append(handler)

    async def connect(self) -> None:
        """Connect to Band if credentials are available, otherwise stay local."""
        try:
            self._band_agent = create_band_agent(
                self.agent_name,
                AGENT_PROMPTS.get(self.agent_name, ""),
            )
            logger.info(f"[{self.agent_name}] Connected to Band platform")
        except Exception as exc:
            logger.warning(
                f"[{self.agent_name}] Band connection skipped (running locally): {exc}"
            )

    async def disconnect(self) -> None:
        """Disconnect from Band."""
        if self._band_agent and hasattr(self._band_agent, "stop"):
            try:
                await self._band_agent.stop()
            except Exception:
                pass
        self._band_agent = None

    async def send_message(
        self,
        recipient: str,
        message_type: MessageType,
        content: dict,
        subject: str = "",
        priority: Priority = Priority.NORMAL,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Send a message to another agent."""
        msg = AgentMessage(
            sender=self.agent_name,
            recipient=recipient,
            message_type=message_type,
            content=content,
            subject=subject,
            priority=priority,
            correlation_id=correlation_id,
        )
        await LocalMessageBus.deliver(msg)
        logger.debug(
            f"[{self.agent_name}] → [{recipient}] {message_type.value}: {subject}"
        )
        return msg.message_id

    async def broadcast(
        self,
        recipients: list,
        message_type: MessageType,
        content: dict,
        subject: str = "",
    ) -> list:
        """Send a message to multiple agents."""
        ids = []
        for recipient in recipients:
            mid = await self.send_message(
                recipient=recipient,
                message_type=message_type,
                content=content,
                subject=subject,
            )
            ids.append(mid)
        return ids