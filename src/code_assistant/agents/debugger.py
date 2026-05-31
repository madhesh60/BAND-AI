"""Debugger agent - identifies and fixes code issues."""

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


class DebuggerAgent(BaseAgent):
    """Debugger identifies and fixes code issues."""

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Fix issues identified in reviews or testing."""
        pipeline_id = task_data.get("pipeline_id", "")
        issues = task_data.get("issues", [])

        logger.info(f"Debugging phase - {len(issues)} issues to fix")

        fixed_issues = []
        remaining_issues = []

        for issue in issues:
            issue_type = issue.get("type", "unknown")
            description = issue.get("description", "")
            file_path = issue.get("file_path", "")
            suggestion = issue.get("suggestion", "")

            logger.info(f"Fixing issue in {file_path}: {description}")

            prompt = f"""Fix the following code issue:

File: {file_path}
Issue type: {issue_type}
Description: {description}
Suggested fix: {suggestion}
"""
            if task_data.get("user_feedback"):
                prompt += f"\nHuman Feedback context:\n{task_data.get('user_feedback')}\n"

            prompt += f"""
Provide the fixed version of the code. Return as JSON:
{{
  "file": "{file_path}",
  "original_issue": "{description}",
  "fix_applied": "description of fix",
  "fixed_content": "complete fixed file content",
  "success": true or false
}}"""

            try:
                fix_text = await self.think(prompt)

                json_match = re.search(r'\{[\s\S]*\}', fix_text)
                if json_match:
                    fix_data = json.loads(json_match.group())
                else:
                    fix_data = {
                        "file": file_path,
                        "fix_applied": "No specific fix",
                        "fixed_content": "",
                        "success": False
                    }

                if fix_data.get("success", False):
                    # Record the fix
                    if pipeline_id and fix_data.get("fixed_content"):
                        self.state_manager.add_code_change(
                            pipeline_id=pipeline_id,
                            file_path=file_path,
                            change_type="fix",
                            content=fix_data.get("fixed_content", ""),
                            agent="debugger",
                        )

                    fixed_issues.append({
                        "file": file_path,
                        "issue": description,
                        "fix": fix_data.get("fix_applied"),
                    })
                else:
                    remaining_issues.append({
                        "file": file_path,
                        "issue": description,
                        "reason": "Could not auto-fix",
                    })

            except Exception as e:
                logger.error(f"Failed to fix issue: {e}")
                remaining_issues.append({
                    "file": file_path,
                    "issue": description,
                    "reason": str(e),
                })

        # Notify conductor
        await self.send_to_agent(
            "conductor",
            MessageType.RESPONSE,
            {
                "pipeline_id": pipeline_id,
                "phase": "debugging",
                "status": "completed",
                "fixed": len(fixed_issues),
                "remaining": len(remaining_issues),
            },
            subject="Debugging phase completed",
            priority=Priority.HIGH if remaining_issues else Priority.NORMAL,
        )

        return {
            "status": "debugging_completed",
            "fixed": fixed_issues,
            "remaining": remaining_issues,
        }