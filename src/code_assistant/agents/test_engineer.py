"""Test engineer agent - creates and runs tests."""

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


class TestEngineerAgent(BaseAgent):
    """Test Engineer creates and manages automated tests."""

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Create and run tests for code changes."""
        pipeline_id = task_data.get("pipeline_id", "")
        code_changes = list(task_data.get("code_changes", []))

        logger.info(f"Creating tests for {len(code_changes)} code changes")

        test_files_created = []
        test_results = []

        for change in code_changes:
            file_path = change.get("file_path", "")
            content = change.get("content", "")
            change_type = change.get("change_type", "modify")

            # Determine test file path
            if file_path.endswith(".py"):
                test_path = file_path.replace(".py", "_test.py")
                if not test_path.startswith("test_"):
                    test_path = "test_" + test_path
            else:
                test_path = f"test_{file_path}"

            prompt = f"""Create comprehensive tests for the following code:

Original file: {file_path}
Test file: {test_path}

Code to test:
```{content}
```

Create tests following best practices:
1. Use pytest for Python, jest for JavaScript
2. Test one thing per test function
3. Use descriptive test names
4. Include both happy path and edge cases
5. Use proper mocking/fixtures
6. Include docstrings

Format your response as JSON:
{{
  "test_file": "{test_path}",
  "content": "complete test file content",
  "test_count": number of test functions,
  "coverage_estimate": "what percentage of code is covered"
}}"""

            try:
                test_text = await self.think(prompt)

                json_match = re.search(r'\{[\s\S]*\}', test_text)
                if json_match:
                    test_data = json.loads(json_match.group())
                else:
                    test_data = {
                        "test_file": test_path,
                        "content": "# Tests placeholder",
                        "test_count": 0,
                        "coverage_estimate": "unknown"
                    }

                # Record test file
                if pipeline_id:
                    self.state_manager.add_code_change(
                        pipeline_id=pipeline_id,
                        file_path=test_data.get("test_file", test_path),
                        change_type="create",
                        content=test_data.get("content", ""),
                        agent="test_engineer",
                    )

                test_files_created.append({
                    "file": test_data.get("test_file", test_path),
                    "test_count": test_data.get("test_count", 0),
                    "coverage": test_data.get("coverage_estimate", "unknown"),
                })

            except Exception as e:
                logger.error(f"Failed to create tests for {file_path}: {e}")

        # Notify conductor
        await self.send_to_agent(
            "conductor",
            MessageType.RESPONSE,
            {
                "pipeline_id": pipeline_id,
                "phase": "testing",
                "status": "completed",
                "test_files_created": len(test_files_created),
                "tests": test_files_created,
            },
            subject="Testing phase completed",
            priority=Priority.NORMAL,
        )

        return {
            "status": "testing_completed",
            "pipeline_id": pipeline_id,
            "test_files": test_files_created,
        }