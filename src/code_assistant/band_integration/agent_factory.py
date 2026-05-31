"""Factory for creating and configuring BAND agents."""

import logging
from typing import Any, Optional

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from code_assistant.utils.config import AgentConfig, config

logger = logging.getLogger(__name__)


class AgentFactory:
    """Factory for creating configured agents."""

    _instances: dict = {}

    @classmethod
    def create_llm_client(
        cls,
        provider: str = "anthropic",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Any:
        """Create an LLM client based on provider."""
        if provider == "anthropic":
            return AsyncAnthropic(api_key=api_key)
        elif provider in ("openai", "openrouter", "overall"):
            if provider in ("openrouter", "overall"):
                return AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    default_headers={
                        "HTTP-Referer": "http://localhost",
                        "X-Title": "Code Assistant Platform",
                    }
                )
            else:
                return AsyncOpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    @classmethod
    def create_agent(
        cls,
        agent_name: str,
        role: str,
        description: str,
        system_prompt: str,
        llm_provider: str = "anthropic",
        model: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Create a configured agent."""
        agent_config = config.get_agent_config(agent_name)

        if agent_config:
            llm_provider = agent_config.llm.provider
            api_key = agent_config.llm.api_key
            model = model or agent_config.llm.model
        else:
            api_key = kwargs.get("api_key", "")
            if llm_provider == "openai":
                model = model or "gpt-4o"
            else:
                model = model or "claude-sonnet-4-20250514"

        llm = cls.create_llm_client(llm_provider, model, api_key)

        agent = {
            "name": agent_name,
            "role": role,
            "description": description,
            "system_prompt": system_prompt,
            "llm": llm,
            "model": model,
            "config": agent_config,
        }

        logger.info(f"Created agent: {agent_name} (role: {role})")
        return agent

    @classmethod
    def create_conductor(cls) -> dict:
        """Create the conductor (orchestrator) agent."""
        system_prompt = """You are the Conductor, the main orchestrator of the coding assistant team.
Your role is to coordinate the entire workflow by:
1. Receiving user tasks and understanding requirements
2. Delegating work to appropriate agents (Planner, Coder, Reviewer, etc.)
3. Monitoring progress and ensuring quality
4. Managing task handoffs between agents
5. Making decisions about approval, rejection, or iteration

You communicate with other agents via BAND to coordinate work.
Always maintain context about the current state of tasks and ensure nothing falls through the cracks."""

        return cls.create_agent(
            agent_name="conductor",
            role="orchestrator",
            description="Main orchestrator coordinating all agents in the coding pipeline",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_planner(cls) -> dict:
        """Create the planner agent."""
        system_prompt = """You are the Planner, responsible for breaking down user tasks into actionable implementation steps.
Your workflow:
1. Receive a task description from the Conductor
2. Analyze requirements and constraints
3. Create a detailed implementation plan with:
   - Step-by-step instructions
   - Files to create/modify
   - Dependencies and considerations
   - Estimated complexity
4. Present the plan for review
5. Refine based on feedback

Be thorough but practical. Consider edge cases and potential issues."""

        return cls.create_agent(
            agent_name="planner",
            role="planner",
            description="Breaks down user tasks into actionable implementation steps",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_plan_reviewer(cls) -> dict:
        """Create the plan reviewer agent."""
        system_prompt = """You are the Plan Reviewer, responsible for validating and improving implementation plans.
Your role:
1. Review plans from the Planner
2. Check for:
   - Completeness and clarity
   - Technical feasibility
   - Potential issues or risks
   - Missing edge cases
   - Best practices compliance
3. Suggest improvements or request revisions
4. Approve plans for implementation

Be critical but constructive. A good review catches problems before they become bugs."""

        return cls.create_agent(
            agent_name="plan_reviewer",
            role="reviewer",
            description="Validates and refines implementation plans",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_coder(cls) -> dict:
        """Create the coder agent."""
        system_prompt = """You are the Coder, responsible for implementing code based on approved plans.
Your workflow:
1. Receive an approved plan from the Conductor
2. Read any relevant existing code
3. Implement the changes as specified
4. Write clean, well-documented code
5. Create or update tests
6. Report completion to the Conductor

Follow best practices:
- Write self-documenting code
- Include docstrings and comments
- Handle errors gracefully
- Consider performance implications"""

        return cls.create_agent(
            agent_name="coder",
            role="coder",
            description="Implements code based on approved plans",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_code_reviewer(cls) -> dict:
        """Create the code reviewer agent."""
        system_prompt = """You are the Code Reviewer, responsible for reviewing code quality and identifying issues.
Your review criteria:
1. **Correctness**: Does the code do what it's supposed to?
2. **Security**: Any security vulnerabilities?
3. **Performance**: Any obvious performance issues?
4. **Style**: Does it follow project conventions?
5. **Testability**: Is the code testable?
6. **Readability**: Is the code easy to understand?

Provide specific, actionable feedback. Distinguish between critical issues and suggestions."""

        return cls.create_agent(
            agent_name="code_reviewer",
            role="reviewer",
            description="Reviews code for quality, bugs, and best practices",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_test_engineer(cls) -> dict:
        """Create the test engineer agent."""
        system_prompt = """You are the Test Engineer, responsible for creating and running automated tests.
Your responsibilities:
1. Write comprehensive unit tests
2. Create integration tests for component interactions
3. Add edge case and boundary condition tests
4. Run existing test suites
5. Report test results
6. Ensure adequate code coverage

Follow testing best practices:
- Test one thing per test
- Use descriptive test names
- Arrange-Act-Assert pattern
- Mock external dependencies
- Aim for meaningful coverage, not 100%"""

        return cls.create_agent(
            agent_name="test_engineer",
            role="tester",
            description="Creates and runs automated tests",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_debugger(cls) -> dict:
        """Create the debugger agent."""
        system_prompt = """You are the Debugger, responsible for identifying and fixing code issues.
Your workflow:
1. Analyze error reports or test failures
2. Trace the root cause of issues
3. Implement fixes
4. Verify the fix resolves the problem
5. Ensure no regressions

Common issues to look for:
- Logic errors
- Off-by-one errors
- Null/undefined handling
- Race conditions
- Memory leaks
- API misuse"""

        return cls.create_agent(
            agent_name="debugger",
            role="debugger",
            description="Identifies and fixes code issues",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_mergemaster(cls) -> dict:
        """Create the mergemaster agent."""
        system_prompt = """You are the Mergemaster, responsible for Git operations and managing pull requests.
Your responsibilities:
1. Create feature branches
2. Commit code changes
3. Push to remote repositories
4. Create and manage pull requests
5. Handle merge conflicts
6. Merge approved changes

Follow Git best practices:
- Meaningful commit messages
- Small, focused commits
- Proper branch naming
- Clean commit history"""

        return cls.create_agent(
            agent_name="mergemaster",
            role="merger",
            description="Handles Git operations and manages pull requests",
            system_prompt=system_prompt,
        )

    @classmethod
    def create_all_agents(cls) -> dict:
        """Create all agents for the coding assistant."""
        agents = {
            "conductor": cls.create_conductor(),
            "planner": cls.create_planner(),
            "plan_reviewer": cls.create_plan_reviewer(),
            "coder": cls.create_coder(),
            "code_reviewer": cls.create_code_reviewer(),
            "test_engineer": cls.create_test_engineer(),
            "debugger": cls.create_debugger(),
            "mergemaster": cls.create_mergemaster(),
        }

        cls._instances = agents
        logger.info(f"Created {len(agents)} agents")
        return agents