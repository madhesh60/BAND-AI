"""Planner agent - creates implementation plans."""

import json
import logging
import re
from typing import Any

from code_assistant.agents.base import BaseAgent
from code_assistant.band_integration.communication import (
    AgentMessage,
    MessageType,
)

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """Planner creates detailed implementation plans from user tasks."""

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Create an implementation plan."""
        pipeline_id = task_data.get("pipeline_id", "")
        user_task = task_data.get("task", "")

        logger.info(f"Creating plan for task: {user_task}")

        # Use LLM to create a structured plan
        prompt = f"""Create a detailed implementation plan for the following task:

Task: {user_task}

Break this down into:
1. Required files to create or modify
2. Step-by-step implementation steps
3. Dependencies and prerequisites
4. Potential challenges and considerations
5. Estimated complexity (low/medium/high)

Format your response as a JSON structure with the following fields:
- steps: array of step objects with (order, description, files_affected, action)
- files: array of file objects with (path, action: create/modify/delete, description)
- dependencies: array of strings
- risks: array of risk descriptions
- complexity: string (low/medium/high)
- estimated_steps: integer

Return ONLY the JSON, no additional text."""

        try:
            plan_text = await self.think(prompt)

            # Parse the plan
            json_match = re.search(r'\{[\s\S]*\}', plan_text)
            if json_match:
                plan_data = json.loads(json_match.group())
            else:
                plan_data = {
                    "steps": [{"order": 1, "description": user_task, "files_affected": [], "action": "implement"}],
                    "files": [],
                    "dependencies": [],
                    "risks": [],
                    "complexity": "medium",
                    "estimated_steps": 1
                }

            # Update pipeline with plan
            if pipeline_id:
                self.state_manager.update_pipeline(pipeline_id, plan=plan_data.get("steps", []))

                # Add tasks to pipeline
                for step in plan_data.get("steps", []):
                    self.state_manager.add_task(
                        pipeline_id=pipeline_id,
                        title=step.get("description", ""),
                        description=f"Step {step.get('order')}: {step.get('description', '')}",
                        assigned_agent="coder",
                    )

            # Send plan to plan reviewer
            await self.send_to_agent(
                "plan_reviewer",
                MessageType.TASK,
                {
                    "pipeline_id": pipeline_id,
                    "plan": plan_data,
                    "original_task": user_task,
                },
                subject="Review implementation plan",
            )

            return {
                "status": "plan_created",
                "pipeline_id": pipeline_id,
                "plan": plan_data,
            }

        except Exception as e:
            logger.error(f"Failed to create plan: {e}")
            return {
                "status": "error",
                "error": str(e),
                "pipeline_id": pipeline_id,
            }