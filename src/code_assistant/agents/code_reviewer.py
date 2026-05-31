"""Code reviewer agent - reviews code quality."""

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


class CodeReviewerAgent(BaseAgent):
    """Code Reviewer reviews code for quality and issues."""

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Review code changes."""
        pipeline_id = task_data.get("pipeline_id", "")
        code_changes = task_data.get("code_changes", [])

        logger.info(f"Reviewing {len(code_changes)} code changes")

        all_issues = []
        all_suggestions = []

        for change in code_changes:
            file_path = change.get("file_path", "")
            content = change.get("content", "")
            change_type = change.get("change_type", "unknown")

            prompt = f"""Review the following code change:

File: {file_path}
Action: {change_type}

Code:
```{content}
```

Review this code for:
1. Correctness - Does it do what it's supposed to?
2. Security - Any security vulnerabilities?
3. Performance - Any obvious performance issues?
4. Style - Does it follow Python/JS best practices?
5. Error handling - Are errors handled properly?
6. Testing - Is it testable?

Format your response as JSON:
{{
  "file": "{file_path}",
  "issues": [
    {{
      "severity": "critical" or "warning" or "info",
      "type": "security" or "performance" or "style" or "correctness",
      "description": "issue description",
      "line": "specific line or null",
      "suggestion": "how to fix"
    }}
  ],
  "overall": "approved" or "needs_changes",
  "summary": "brief summary"
}}"""

            try:
                review_text = await self.think(prompt)

                json_match = re.search(r'\{[\s\S]*\}', review_text)
                if json_match:
                    review = json.loads(json_match.group())
                else:
                    review = {
                        "file": file_path,
                        "issues": [],
                        "overall": "approved",
                        "summary": "No issues found"
                    }

                # Record issues
                critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
                if critical_issues:
                    all_issues.extend(critical_issues)

                all_suggestions.extend([
                    f"[{file_path}] {s}" for s in review.get("issues", [])
                ])

                # Add review to pipeline
                if pipeline_id:
                    self.state_manager.add_review(
                        pipeline_id=pipeline_id,
                        reviewer="code_reviewer",
                        status=review.get("overall", "approved"),
                        comments=all_suggestions,
                        file_path=file_path,
                    )

            except Exception as e:
                logger.error(f"Failed to review {file_path}: {e}")

        # Determine overall status
        overall_status = "approved" if not all_issues else "needs_changes"

        # Add overall review
        if pipeline_id:
            self.state_manager.add_review(
                pipeline_id=pipeline_id,
                reviewer="code_reviewer",
                status=overall_status,
                comments=[
                    f"Total issues found: {len(all_issues)} critical, {len(all_suggestions) - len(all_issues)} suggestions"
                ],
            )

        # Notify conductor
        await self.send_to_agent(
            "conductor",
            MessageType.RESPONSE,
            {
                "pipeline_id": pipeline_id,
                "phase": "review",
                "status": overall_status,
                "issues_found": len(all_issues),
                "suggestions": len(all_suggestions) - len(all_issues),
            },
            subject="Code review completed",
            priority=Priority.HIGH if all_issues else Priority.NORMAL,
        )

        return {
            "status": "review_completed",
            "overall_status": overall_status,
            "issues": all_issues,
            "suggestions": all_suggestions,
        }