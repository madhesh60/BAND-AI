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

    async def call_llm(
        self,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Call the LLM with the given messages, falling back to mock generator on failure."""
        import os
        
        # API Key Validation & Dry-Run Fallback Check:
        # Check if a valid API key is present in environment variables.
        # If the key is absent or contains placeholder text, fall back to the Mock response generator.
        api_key = (
            os.getenv("ANTHROPIC_API_KEY", "") 
            or os.getenv("OPENAI_API_KEY", "") 
            or os.getenv("OVERALL_API_KEY", "")
        )
        is_placeholder = not api_key or "your" in api_key.lower() or api_key in ("test-key", "test")
        
        if is_placeholder:
            logger.info(f"[{self.name}] Using Mock LLM fallback because no valid API key is present")
            return self._generate_mock_response(messages[-1]["content"])

        # LLM Call Retry Strategy:
        # We try calling the provider up to 5 times. We use exponential backoff as a base delay
        # but dynamically override it if the provider API (such as Venice/OpenRouter)
        # provides a precise 'retry_after_seconds' or 'retry-after' in the error metadata.
        model = self.model
        max_retries = 5
        base_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                # LLM Client Router:
                # 1. Anthropic: Supports the new messages API with a top-level 'system' prompt argument.
                # 2. OpenAI / OpenRouter: Uses standard chat.completions API with a 'system' role message prepended.
                if hasattr(self.llm_client, "messages"):
                    # Anthropic client
                    if not model:
                        model = "claude-sonnet-4-20250514"
                    response = await self.llm_client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=self.system_prompt,
                        messages=messages,
                    )
                    return response.content[0].text
                elif hasattr(self.llm_client, "chat"):
                    # OpenAI or OpenRouter client
                    if not model:
                        model = "gpt-4o"
                    all_messages = [{"role": "system", "content": self.system_prompt}]
                    all_messages.extend(messages)
                    response = await self.llm_client.chat.completions.create(
                        model=model,
                        messages=all_messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return response.choices[0].message.content
                else:
                    raise ValueError("Unknown LLM client type")
            except Exception as e:
                err_msg = str(e).lower()
                is_rate_limit = "429" in err_msg or "rate limit" in err_msg or "too many requests" in err_msg or "rate_limited" in err_msg
                
                if is_rate_limit and attempt < max_retries - 1:
                    import re
                    # Base delay calculation: exponential backoff (5s, 10s, 20s, 40s)
                    delay = base_delay * (2 ** attempt)
                    
                    # Parse Venice/OpenRouter-specific rate limit header patterns
                    match = re.search(r"retry_after_seconds':\s*([0-9.]+)", err_msg)
                    if match:
                        delay = float(match.group(1)) + 1
                    else:
                        match2 = re.search(r"retry-after':\s*'([0-9.]+)'", err_msg)
                        if match2:
                            delay = float(match2.group(1)) + 1
                            
                    logger.warning(f"[{self.name}] Rate limit (429) encountered. Retrying in {delay:.1f}s (Attempt {attempt+1}/{max_retries})...")
                    await asyncio.sleep(delay)
                else:
                    # Log failure and raise the exception, preventing silent failure and aiding user debugging.
                    logger.error(f"[{self.name}] LLM call failed permanently on attempt {attempt+1}: {e}", exc_info=True)
                    raise e

    def _generate_mock_response(self, prompt: str) -> str:
        """Generate structured mock response based on the agent's role and prompt."""
        import json
        
        # Determine based on agent name/role
        if self.name == "planner":
            # Extract task from prompt if possible
            task_match = re.search(r'Task:\s*(.*)', prompt, re.IGNORECASE)
            task = task_match.group(1).strip() if task_match else "coding task"
            
            # Find any .py file names in the task description
            file_matches = re.findall(r'\b[a-zA-Z0-9_-]+\.py\b', task)
            file_path = file_matches[0] if file_matches else "app.py"
            
            return json.dumps({
                "steps": [
                    {
                        "order": 1,
                        "description": f"Initialize the repository and basic files for {task}",
                        "files_affected": [file_path],
                        "action": "create"
                    },
                    {
                        "order": 2,
                        "description": "Implement the core logic and main function",
                        "files_affected": [file_path],
                        "action": "modify"
                    }
                ],
                "files": [
                    {
                        "path": file_path,
                        "action": "create",
                        "description": "Main application file"
                    }
                ],
                "dependencies": [],
                "risks": [],
                "complexity": "low",
                "estimated_steps": 2
            }, indent=2)
            
        elif self.name == "plan_reviewer":
            return json.dumps({
                "status": "approved",
                "issues": [],
                "suggestions": ["Add more specific unit tests in the implementation phase"],
                "missing_steps": [],
                "final_complexity": "low",
                "summary": "The plan looks complete, covers main requirements, and is highly feasible."
            }, indent=2)
            
        elif self.name == "coder":
            # Determine files affected or task
            step_match = re.search(r'Step:\s*(.*)', prompt, re.IGNORECASE)
            step_desc = step_match.group(1).strip() if step_match else "coding step"
            
            files_match = re.search(r'Files affected:\s*(.*)', prompt, re.IGNORECASE)
            files_affected_str = files_match.group(1).strip() if files_match else "app.py"
            
            # Extract first .py file name or fallback
            file_matches = re.findall(r'\b[a-zA-Z0-9_-]+\.py\b', files_affected_str)
            file_path = file_matches[0] if file_matches else "app.py"
            
            # Fetch user task for broader keyword context
            user_task = ""
            if self.state_manager and self.state_manager._states:
                try:
                    active_pipeline = max(
                        self.state_manager._states.values(),
                        key=lambda s: s.updated_at
                    )
                    if active_pipeline:
                        user_task = active_pipeline.user_task
                except Exception:
                    pass
                    
            combined_desc = (step_desc + " " + user_task).lower()
            
            # Generate code based on task keywords
            if "fibonacci" in combined_desc or "fibo" in combined_desc:
                code_content = """# Fibonacci calculation script
def fibonacci(n):
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    sequence = [0, 1]
    while len(sequence) < n:
        sequence.append(sequence[-1] + sequence[-2])
    return sequence

def main():
    n = 10
    print(f"First {n} Fibonacci numbers: {fibonacci(n)}")
    return True

if __name__ == "__main__":
    main()
"""
            elif "hello" in combined_desc or "world" in combined_desc:
                code_content = """# Hello World application
def main():
    print("Hello, World!")
    return True

if __name__ == "__main__":
    main()
"""
            elif "date" in combined_desc or "time" in combined_desc:
                code_content = """# Date and time printing script
from datetime import datetime

def main():
    print(f"Current Date and Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return True

if __name__ == "__main__":
    main()
"""
            else:
                code_content = f"""# Script generated for: {step_desc}
def main():
    print("Executing step: {step_desc}")
    return True

if __name__ == "__main__":
    main()
"""
            return json.dumps({
                "implementations": [
                    {
                        "file_path": file_path,
                        "action": "create",
                        "content": code_content,
                        "explanation": f"Implemented core functionality: {step_desc}"
                    }
                ]
            }, indent=2)
            
        elif self.name == "code_reviewer":
            file_match = re.search(r'File:\s*(.*)', prompt, re.IGNORECASE)
            file_path = file_match.group(1).strip() if file_match else "app.py"
            return json.dumps({
                "file": file_path,
                "issues": [],
                "overall": "approved",
                "summary": "Code is clean, well-formatted, and conforms to standard PEP-8 style guidelines."
            }, indent=2)
            
        elif self.name == "test_engineer":
            file_match = re.search(r'Original file:\s*(.*)', prompt, re.IGNORECASE)
            file_path = file_match.group(1).strip() if file_match else "app.py"
            test_path = file_path.replace(".py", "_test.py") if file_path.endswith(".py") else f"test_{file_path}"
            
            import_name = file_path.replace(".py", "") if file_path.endswith(".py") else "app"
            
            test_content = f"""import pytest
from {import_name} import main

def test_main():
    assert main() is True
"""
            return json.dumps({
                "test_file": test_path,
                "content": test_content,
                "test_count": 1,
                "coverage_estimate": "100%"
            }, indent=2)
            
        elif self.name == "debugger":
            file_match = re.search(r'File:\s*(.*)', prompt, re.IGNORECASE)
            file_path = file_match.group(1).strip() if file_match else "app.py"
            return json.dumps({
                "file": file_path,
                "original_issue": "None",
                "fix_applied": "No changes needed",
                "fixed_content": "",
                "success": True
            }, indent=2)
            
        else:
            return "Mock response"

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