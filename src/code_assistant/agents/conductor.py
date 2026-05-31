"""Conductor agent - main orchestrator."""

import asyncio
import logging
from typing import Any, Optional

from code_assistant.agents.base import BaseAgent
from code_assistant.band_integration.communication import (
    AgentMessage,
    MessageType,
    Priority,
)

logger = logging.getLogger(__name__)


class ConductorAgent(BaseAgent):
    """Conductor orchestrates the entire coding workflow."""

    def __init__(self, **kwargs):
        # Prevent got multiple values for keyword argument error by popping them from kwargs
        kwargs.pop("name", None)
        kwargs.pop("role", None)
        kwargs.pop("description", None)
        super().__init__(
            name="conductor",
            role="orchestrator",
            description="Main orchestrator coordinating all agents",
            **kwargs,
        )
        self._workflow_handlers = {
            "planning": self._handle_planning_phase,
            "coding": self._handle_coding_phase,
            "review": self._handle_review_phase,
            "testing": self._handle_testing_phase,
            "debugging": self._handle_debugging_phase,
            "merging": self._handle_merging_phase,
        }
        self._phase_events: dict = {}
        self._phase_results: dict = {}

    def complete_phase(self, phase_name: str, status: str):
        if phase_name in self._phase_events:
            self._phase_results[phase_name] = status
            self._phase_events[phase_name].set()

    async def wait_for_phase(self, phase_name: str) -> str:
        self._phase_events[phase_name] = asyncio.Event()
        logger.info(f"Conductor waiting for phase '{phase_name}' to complete...")
        await self._phase_events[phase_name].wait()
        status = self._phase_results.get(phase_name, "completed")
        logger.info(f"Conductor resumed: phase '{phase_name}' finished with status '{status}'")
        return status

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        logger.info(f"Conductor processing: {message.message_type.value}")

        if message.message_type == MessageType.TASK:
            return await self._handle_new_task(message)
        elif message.message_type == MessageType.RESPONSE:
            return await self._handle_response(message)
        elif message.message_type == MessageType.STATUS_UPDATE:
            return await self._handle_status_update(message)
        elif message.message_type == MessageType.ERROR:
            return await self._handle_error(message)
        else:
            logger.warning(f"Unknown message type: {message.message_type}")
            return {"status": "unknown_message_type"}

    async def execute_task(self, task_data: dict) -> dict:
        """Execute the main orchestration workflow."""
        user_task = task_data.get("task", "")
        pipeline_id = task_data.get("pipeline_id", "")

        logger.info(f"Conductor starting workflow for: {user_task}")

        # Create pipeline state if not exists
        if pipeline_id:
            pipeline = self.state_manager.get_pipeline(pipeline_id)
            if not pipeline:
                pipeline = self.state_manager.create_pipeline(user_task, pipeline_id=pipeline_id)
        else:
            pipeline = self.state_manager.create_pipeline(user_task)
            pipeline_id = pipeline.pipeline_id

        self.set_current_pipeline(pipeline)

        # Reset events/results
        self._phase_events.clear()
        self._phase_results.clear()

        # Phase 1: Planning
        await self._handle_planning_phase(pipeline)
        await self.wait_for_phase("planning")

        # Phase 2: Coding
        await self._handle_coding_phase(pipeline)
        await self.wait_for_phase("coding")

        # Phase 3: Review
        await self._handle_review_phase(pipeline)
        review_status = await self.wait_for_phase("review")

        # Iterative Debugging loop: if review needs changes, route to debugging
        max_retries = 3
        retry_count = 0
        while review_status == "needs_changes" and retry_count < max_retries:
            logger.info(f"Code review rejected. Starting debugging iteration {retry_count + 1}...")
            # Retrieve latest state with rejected reviews
            pipeline = self.state_manager.get_pipeline(pipeline_id)
            await self._handle_debugging_phase(pipeline)
            await self.wait_for_phase("debugging")

            # Re-review the fixed changes
            pipeline = self.state_manager.get_pipeline(pipeline_id)
            await self._handle_review_phase(pipeline)
            review_status = await self.wait_for_phase("review")
            retry_count += 1

        # Phase 4: Testing
        pipeline = self.state_manager.get_pipeline(pipeline_id)
        await self._handle_testing_phase(pipeline)
        await self.wait_for_phase("testing")

        # Phase 5: Merging
        pipeline = self.state_manager.get_pipeline(pipeline_id)
        await self._handle_merging_phase(pipeline)
        await self.wait_for_phase("merging")

        # Update final state to completed
        self.state_manager.update_pipeline(pipeline_id, current_phase="completed")

        return {
            "status": "completed",
            "pipeline_id": pipeline_id,
            "summary": {
                "tasks_completed": len([t for t in pipeline.tasks.values() if t.status.value == "completed"]),
                "reviews_passed": len([r for r in pipeline.reviews if r.get("status") == "approved"]),
            },
        }

    async def _handle_new_task(self, message: AgentMessage) -> dict:
        """Handle a new task assignment."""
        task = message.content.get("task", "")
        logger.info(f"New task received: {task}")

        return await self.execute_task({"task": task})

    async def _handle_planning_phase(self, pipeline) -> dict:
        """Coordinate the planning phase."""
        logger.info("Phase 1: Planning")
        self.state_manager.update_pipeline(pipeline.pipeline_id, current_phase="planning")

        # Send task to planner
        await self.send_to_agent(
            "planner",
            MessageType.TASK,
            {
                "pipeline_id": pipeline.pipeline_id,
                "task": pipeline.user_task,
            },
            subject=f"Create plan for: {pipeline.user_task[:50]}...",
        )

        return {"phase": "planning", "status": "delegated"}

    async def _handle_coding_phase(self, pipeline) -> dict:
        """Coordinate the coding phase."""
        logger.info("Phase 2: Coding")
        self.state_manager.update_pipeline(pipeline.pipeline_id, current_phase="coding")

        # Delegate to coder
        await self.send_to_agent(
            "coder",
            MessageType.TASK,
            {
                "pipeline_id": pipeline.pipeline_id,
                "plan": pipeline.plan,
            },
            subject=f"Implement: {pipeline.user_task[:50]}...",
        )

        return {"phase": "coding", "status": "delegated"}

    async def _handle_review_phase(self, pipeline) -> dict:
        """Coordinate the review phase."""
        logger.info("Phase 3: Review")
        self.state_manager.update_pipeline(pipeline.pipeline_id, current_phase="review")

        # Delegate to code reviewer
        await self.send_to_agent(
            "code_reviewer",
            MessageType.TASK,
            {
                "pipeline_id": pipeline.pipeline_id,
                "code_changes": pipeline.code_changes,
            },
            subject=f"Review changes for: {pipeline.user_task[:50]}...",
        )

        return {"phase": "review", "status": "delegated"}

    async def _handle_testing_phase(self, pipeline) -> dict:
        """Coordinate the testing phase."""
        logger.info("Phase 4: Testing")
        self.state_manager.update_pipeline(pipeline.pipeline_id, current_phase="testing")

        # Delegate to test engineer
        await self.send_to_agent(
            "test_engineer",
            MessageType.TASK,
            {
                "pipeline_id": pipeline.pipeline_id,
                "code_changes": pipeline.code_changes,
            },
            subject=f"Create tests for: {pipeline.user_task[:50]}...",
        )

        return {"phase": "testing", "status": "delegated"}

    async def _handle_debugging_phase(self, pipeline) -> dict:
        """Coordinate the debugging phase if needed."""
        logger.info("Phase 4.5: Debugging (if needed)")
        self.state_manager.update_pipeline(pipeline.pipeline_id, current_phase="debugging")

        # Check if there are issues to fix
        issues = [r for r in pipeline.reviews if r.get("status") == "rejected"]
        if issues:
            await self.send_to_agent(
                "debugger",
                MessageType.TASK,
                {
                    "pipeline_id": pipeline.pipeline_id,
                    "issues": issues,
                },
                subject=f"Fix issues in: {pipeline.user_task[:50]}...",
            )

        return {"phase": "debugging", "status": "delegated"}

    async def _handle_merging_phase(self, pipeline) -> dict:
        """Coordinate the merging phase."""
        logger.info("Phase 5: Merging")
        self.state_manager.update_pipeline(pipeline.pipeline_id, current_phase="merging")

        # Delegate to mergemaster
        await self.send_to_agent(
            "mergemaster",
            MessageType.TASK,
            {
                "pipeline_id": pipeline.pipeline_id,
                "code_changes": pipeline.code_changes,
            },
            subject=f"Merge changes for: {pipeline.user_task[:50]}...",
        )

        return {"phase": "merging", "status": "delegated"}

    async def _handle_response(self, message: AgentMessage) -> dict:
        """Handle responses from other agents."""
        sender = message.sender
        content = message.content
        logger.info(f"Response from {sender}: {content.get('status', 'unknown')}")

        # Update pipeline based on response
        pipeline_id = content.get("pipeline_id")
        if pipeline_id:
            updates = {k: v for k, v in content.items() if k != "pipeline_id"}
            self.state_manager.update_pipeline(pipeline_id, **updates)

        # Trigger phase completion
        phase = content.get("phase")
        status = content.get("status")
        if phase:
            self.complete_phase(phase, status)

        return {"status": "response_received", "from": sender}

    async def _handle_status_update(self, message: AgentMessage) -> dict:
        """Handle status updates from agents."""
        status = message.content.get("status", "unknown")
        agent = message.sender
        logger.info(f"Status update from {agent}: {status}")

        return {"status": "status_received"}

    async def _handle_error(self, message: AgentMessage) -> dict:
        """Handle error reports from agents."""
        error = message.content.get("error", "Unknown error")
        agent = message.sender
        logger.error(f"Error from {agent}: {error}")

        # Could implement retry logic or escalation here
        return {"status": "error_received", "from": agent}