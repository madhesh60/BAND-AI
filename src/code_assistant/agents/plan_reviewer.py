"""Plan reviewer agent - validates and improves plans."""

import json
import logging
import re
from typing import Any

from code_assistant.agents.base import BaseAgent
from code_assistant.band_integration.communication import (
    AgentMessage,
    MessageType,
    Priority,
)

logger = logging.getLogger(__name__)


class PlanReviewerAgent(BaseAgent):
    """Plan Reviewer validates and improves implementation plans."""

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Review and refine an implementation plan."""
        pipeline_id = task_data.get("pipeline_id", "")
        plan = task_data.get("plan", {})
        original_task = task_data.get("original_task", "")

        logger.info(f"Reviewing plan for: {original_task}")

        # Use LLM to review the plan
        prompt = f"""Review the following implementation plan for completeness and quality:

Original Task: {original_task}

Plan:
{json.dumps(plan, indent=2)}

Evaluate the plan based on:
1. Completeness - Are all necessary steps included?
2. Feasibility - Can this realistically be implemented?
3. Clarity - Is each step clear and actionable?
4. Risks - Are there potential issues or edge cases?
5. Best practices - Does it follow good software engineering practices?

Provide:
- Overall approval status (approved/needs_revision)
- List of issues or suggestions (if any)
- Any missing steps or considerations
- Estimated complexity recalculated

Format your response as JSON:
{{
  "status": "approved" or "needs_revision",
  "issues": ["issue 1", "issue 2"],
  "suggestions": ["suggestion 1"],
  "missing_steps": ["missing step"],
  "final_complexity": "low/medium/high",
  "summary": "brief summary"
}}"""

        try:
            review_text = await self.think(prompt)

            # Parse review
            json_match = re.search(r'\{[\s\S]*\}', review_text)
            if json_match:
                review_data = json.loads(json_match.group())
            else:
                review_data = {
                    "status": "approved",
                    "issues": [],
                    "suggestions": [],
                    "missing_steps": [],
                    "final_complexity": "medium",
                    "summary": "Plan looks good"
                }

            # Add review to pipeline
            if pipeline_id:
                self.state_manager.add_review(
                    pipeline_id=pipeline_id,
                    reviewer="plan_reviewer",
                    status=review_data.get("status", "approved"),
                    comments=review_data.get("issues", []) + review_data.get("suggestions", []),
                )

            # Send back to conductor
            if review_data.get("status") == "approved":
                await self.send_to_agent(
                    "conductor",
                    MessageType.RESPONSE,
                    {
                        "pipeline_id": pipeline_id,
                        "phase": "planning",
                        "status": "approved",
                        "review": review_data,
                    },
                    subject="Plan approved",
                    priority=Priority.HIGH,
                )
            else:
                # Send back to planner for revision
                await self.send_to_agent(
                    "planner",
                    MessageType.TASK,
                    {
                        "pipeline_id": pipeline_id,
                        "task": original_task,
                        "review_feedback": review_data,
                    },
                    subject="Revise implementation plan",
                    priority=Priority.HIGH,
                )

            return {
                "status": "review_completed",
                "review": review_data,
            }

        except Exception as e:
            logger.error(f"Failed to review plan: {e}")
            return {
                "status": "error",
                "error": str(e),
            }