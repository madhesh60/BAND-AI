"""Coder agent - implements code based on plans."""

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
from code_assistant.band_integration.state_manager import TaskStatus

logger = logging.getLogger(__name__)


class CoderAgent(BaseAgent):
    """Coder implements code based on approved plans."""

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Implement code based on plan."""
        pipeline_id = task_data.get("pipeline_id", "")
        plan = task_data.get("plan", [])

        logger.info(f"Coding phase started for pipeline: {pipeline_id}")

        implemented_steps = []

        for step in plan:
            step_order = step.get("order", 0)
            step_desc = step.get("description", "")
            files_affected = step.get("files_affected", [])

            logger.info(f"Implementing step {step_order}: {step_desc}")

            # Find corresponding task and set IN_PROGRESS
            task_id = None
            if pipeline_id:
                pipeline = self.state_manager.get_pipeline(pipeline_id)
                if pipeline:
                    for t_id, task in pipeline.tasks.items():
                        if task.title == step_desc:
                            task_id = t_id
                            self.state_manager.update_task(
                                pipeline_id=pipeline_id,
                                task_id=task_id,
                                status=TaskStatus.IN_PROGRESS,
                            )
                            break

            # Create implementation details
            prompt = f"""Implement the following step in the coding workflow:

Step: {step_desc}
Files affected: {', '.join(files_affected) if files_affected else 'None specified'}

For each file that needs to be created or modified:
1. Provide the complete file path
2. Provide the complete file content
3. Explain what changes were made

Format your response as JSON:
{{
  "implementations": [
    {{
      "file_path": "path/to/file.py",
      "action": "create" or "modify",
      "content": "complete file content",
      "explanation": "what was done"
    }}
  ]
}}"""

            try:
                implementation_text = await self.think(prompt)

                # Parse implementation
                json_match = re.search(r'\{[\s\S]*\}', implementation_text)
                if json_match:
                    implementation = json.loads(json_match.group())
                else:
                    implementation = {"implementations": []}

                # Record code changes
                for impl in implementation.get("implementations", []):
                    if pipeline_id:
                        self.state_manager.add_code_change(
                            pipeline_id=pipeline_id,
                            file_path=impl.get("file_path", ""),
                            change_type=impl.get("action", "modify"),
                            content=impl.get("content", ""),
                            agent="coder",
                        )

                    implemented_steps.append({
                        "step": step_order,
                        "description": step_desc,
                        "implementation": impl,
                    })

                # Update task status to COMPLETED
                if pipeline_id and task_id:
                    self.state_manager.update_task(
                        pipeline_id=pipeline_id,
                        task_id=task_id,
                        status=TaskStatus.COMPLETED,
                    )

            except Exception as e:
                logger.error(f"Failed to implement step {step_order}: {e}")
                if pipeline_id:
                    if task_id:
                        self.state_manager.update_task(
                            pipeline_id=pipeline_id,
                            task_id=task_id,
                            status=TaskStatus.FAILED,
                            errors=[str(e)],
                        )
                    else:
                        self.state_manager.add_task(
                            pipeline_id=pipeline_id,
                            title=f"Step {step_order} failed",
                            description=str(e),
                        )

        # Notify conductor of completion
        await self.send_to_agent(
            "conductor",
            MessageType.RESPONSE,
            {
                "pipeline_id": pipeline_id,
                "phase": "coding",
                "status": "completed",
                "steps_implemented": len(implemented_steps),
            },
            subject="Coding phase completed",
            priority=Priority.HIGH,
        )

        return {
            "status": "coding_completed",
            "pipeline_id": pipeline_id,
            "implemented_steps": implemented_steps,
        }