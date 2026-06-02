"""Base agent class for all coding assistant agents."""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from code_assistant.band_integration.communication import (
    CommunicationLayer,
    AgentMessage,
    MessageType,
    Priority,
)
from code_assistant.band_integration.state_manager import StateManager, PipelineState

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all agents in the coding assistant."""

    def __init__(
        self,
        name: str,
        role: str,
        description: str,
        system_prompt: str,
        llm_client: Any,
        model: Optional[str] = None,
        state_manager: Optional[StateManager] = None,
        communication: Optional[CommunicationLayer] = None,
    ):
        self.name = name
        self.role = role
        self.description = description
        self.system_prompt = system_prompt
        self.llm_client = llm_client
        self.model = model
        self.state_manager = state_manager or StateManager()
        self.communication = communication or CommunicationLayer(self.name)
        self._running = False
        self._current_pipeline: Optional[PipelineState] = None

        # Message Hook Registration:
        # Every cooperative agent listens to the BAND communication bus.
        # We register a single default handler `self.process_message` for all MessageTypes
        # (TASK, REVIEW, CODE_CHANGE, CHAT) so that incoming peer messages trigger local processing.
        for m_type in MessageType:
            self.communication.register_handler(m_type, self.process_message)

        logger.info(f"Initialized agent: {self.name} (role: {self.role})")

    @abstractmethod
    async def process_message(self, message: AgentMessage) -> dict:
        """Process an incoming message and return a response."""
        pass

    @abstractmethod
    async def execute_task(self, task_data: dict) -> dict:
        """Execute a task assigned to this agent."""
        pass

    # Ordered fallback model list for OpenRouter free tier.
    # When the primary configured model is rate-limited or unavailable, the agent will
    # automatically cycle through this list until one succeeds. This prevents the entire
    # pipeline from crashing due to a single model's quota being exhausted.
    # NOTE: Verified working June 2026. Update if models go offline (404) or stay rate-limited.
    OPENROUTER_FALLBACK_MODELS = [
        "google/gemma-4-31b-it:free",                     # Confirmed working - good coder
        "nvidia/nemotron-3-super-120b-a12b:free",         # Confirmed working - large reasoning
        "nousresearch/hermes-3-llama-3.1-405b:free",      # 405B fallback
        "openai/gpt-oss-120b:free",                       # OpenAI OSS large
        "openai/gpt-oss-20b:free",                        # OpenAI OSS small
        "qwen/qwen3-coder:free",                          # Good coder (rate-limited at peak)
        "meta-llama/llama-3.3-70b-instruct:free",         # Llama 70B (rate-limited at peak)
        "meta-llama/llama-3.2-3b-instruct:free",          # Small/fast last resort
    ]

    async def call_llm(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Call the LLM with the given messages.

        Uses a multi-model fallback strategy:
        1. Validate that a real API key is configured — raise immediately if not.
        2. Try the configured model up to 5 times with exponential backoff on rate limits.
        3. On repeated rate limits, cycle through OPENROUTER_FALLBACK_MODELS.
        4. If ALL models fail, re-raise the last exception so the error surfaces to the user.
        """
        import os

        # API Key Validation:
        # Require a real key. If missing or placeholder, raise immediately so the user
        # sees a clear error instead of getting silently wrong output.
        api_key = (
            os.getenv("ANTHROPIC_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
            or os.getenv("OVERALL_API_KEY", "")
        )
        is_placeholder = not api_key or "your" in api_key.lower() or api_key in ("test-key", "test")

        if is_placeholder:
            raise RuntimeError(
                f"[{self.name}] No valid API key found. "
                "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OVERALL_API_KEY in your .env file."
            )

        # LLM Call Retry Strategy:
        # Try the primary model up to 5 times with exponential backoff.
        # After the first rate-limit, cycle through OPENROUTER_FALLBACK_MODELS.
        model = self.model
        max_retries = 5
        base_delay = 10  # seconds

        client_class = type(self.llm_client).__name__
        is_anthropic = "Anthropic" in client_class
        is_openai_compat = "OpenAI" in client_class

        last_exception: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                if is_anthropic:
                    if not model:
                        model = "claude-sonnet-4-5"
                    response = await self.llm_client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=self.system_prompt,
                        messages=messages,
                    )
                    result = response.content[0].text if response.content else None
                    if result is None:
                        raise ValueError("LLM returned empty content")
                    return result
                elif is_openai_compat:
                    if not model:
                        model = "gpt-4o-mini"
                    all_messages = [{"role": "system", "content": self.system_prompt}]
                    all_messages.extend(messages)
                    response = await self.llm_client.chat.completions.create(
                        model=model,
                        messages=all_messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    result = response.choices[0].message.content if response.choices else None
                    if result is None:
                        raise ValueError("LLM returned empty content")
                    return result
                else:
                    raise ValueError(f"Unknown LLM client type: {client_class}")

            except Exception as e:
                last_exception = e
                err_msg = str(e).lower()
                is_rate_limit = (
                    "429" in err_msg
                    or "rate limit" in err_msg
                    or "too many requests" in err_msg
                    or "rate_limited" in err_msg
                    or "ratelimit" in err_msg
                )

                if is_rate_limit and attempt < max_retries - 1:
                    import re as _re
                    delay = base_delay * (2 ** attempt)
                    match = _re.search(r"retry_after_seconds':\s*([0-9.]+)", err_msg)
                    if match:
                        delay = float(match.group(1)) + 2
                    else:
                        match2 = _re.search(r"retry-after':\s*'([0-9.]+)'", err_msg)
                        if match2:
                            delay = float(match2.group(1)) + 2

                    logger.warning(
                        f"[{self.name}] Rate limit (429) on model '{model}'. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})…"
                    )

                    if attempt >= 1 and is_openai_compat:
                        fallback_idx = attempt - 1
                        if fallback_idx < len(self.OPENROUTER_FALLBACK_MODELS):
                            new_model = self.OPENROUTER_FALLBACK_MODELS[fallback_idx]
                            if new_model != model:
                                model = new_model
                                logger.info(f"[{self.name}] Switching to fallback model: {model}")

                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[{self.name}] LLM call failed on attempt {attempt + 1}: {e}")
                    if not is_rate_limit:
                        raise
                    break

        # All retries exhausted — surface the real error to the user.
        raise RuntimeError(
            f"[{self.name}] All LLM attempts exhausted after {max_retries} retries. "
            f"Last error: {last_exception}"
        ) from last_exception

    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        from code_assistant.band_integration.communication import LocalMessageBus
        LocalMessageBus.register_agent(self.name, self)
        
        # Connect to Thenvoi WebSocket platform if credentials exist
        await self.communication.connect()
        logger.info(f"Agent {self.name} started")

    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        from code_assistant.band_integration.communication import LocalMessageBus
        LocalMessageBus.unregister_agent(self.name)
        
        # Disconnect from Thenvoi WebSocket platform
        await self.communication.disconnect()
        logger.info(f"Agent {self.name} stopped")

    async def send_to_agent(
        self,
        agent_name: str,
        message_type: MessageType,
        content: dict,
        subject: str = "",
        priority: Priority = Priority.NORMAL,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Send a message to another agent via BAND."""
        return await self.communication.send_message(
            recipient=agent_name,
            message_type=message_type,
            content=content,
            subject=subject,
            priority=priority,
            correlation_id=correlation_id,
        )

    async def broadcast_to_agents(
        self,
        agent_names: list,
        message_type: MessageType,
        content: dict,
        subject: str = "",
    ) -> list:
        """Broadcast a message to multiple agents."""
        return await self.communication.broadcast(
            recipients=agent_names,
            message_type=message_type,
            content=content,
            subject=subject,
        )

    def set_current_pipeline(self, pipeline: PipelineState) -> None:
        """Set the current pipeline context."""
        self._current_pipeline = pipeline

    async def think(self, prompt: str, context: Optional[dict] = None) -> str:
        """Generate a response using the LLM."""
        messages = []
        if context:
            context_str = "\n\n".join(f"{k}: {v}" for k, v in context.items())
            messages.append({
                "role": "user",
                "content": f"Context:\n{context_str}\n\n{prompt}",
            })
        else:
            messages.append({"role": "user", "content": prompt})

        return await self.call_llm(messages)

    def get_capabilities(self) -> dict:
        """Return agent capabilities."""
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
        }