
"""Coder agent - implements code based on plans."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from code_assistant.agents.base import BaseAgent
from code_assistant.band_integration.communication import (
    AgentMessage,
    MessageType,
    Priority,
)
from code_assistant.band_integration.state_manager import TaskStatus

logger = logging.getLogger(__name__)


def _detect_language(files_affected: list, task_desc: str, original_task: str) -> tuple:
    """Detect the target programming language from file extensions or task keywords.

    Returns (language_name, default_extension).
    """
    ext_map = {
        ".rs": "Rust",
        ".go": "Go",
        ".ts": "TypeScript",
        ".js": "JavaScript",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".cs": "C#",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".py": "Python",
        ".sh": "Bash",
        ".html": "HTML",
        ".css": "CSS",
    }
    # Check file extensions first — most reliable signal
    for f in files_affected:
        for ext, lang in ext_map.items():
            if f.endswith(ext):
                return lang, ext

    # Fall back to keyword scanning in task text
    combined = (task_desc + " " + original_task).lower()
    keyword_map = [
        (["rust", " .rs ", "cargo"],                         "Rust",       ".rs"),
        (["golang", "go lang", " go ", "go file"],           "Go",         ".go"),
        (["typescript", " .ts "],                            "TypeScript", ".ts"),
        (["javascript", "node.js", "nodejs", " .js "],       "JavaScript", ".js"),
        (["java ", " .java"],                                "Java",       ".java"),
        (["c++", "cpp", "c plus plus"],                      "C++",        ".cpp"),
        (["c#", "csharp", "dotnet", ".net"],                 "C#",         ".cs"),
        (["ruby", " .rb "],                                  "Ruby",       ".rb"),
        (["swift"],                                          "Swift",      ".swift"),
        (["kotlin", " .kt "],                                "Kotlin",     ".kt"),
        (["bash", "shell script", " .sh "],                  "Bash",       ".sh"),
    ]
    for keywords, lang, ext in keyword_map:
        if any(kw in combined for kw in keywords):
            return lang, ext

    return "Python", ".py"  # safe default


def _extract_json(text: str) -> dict | None:
    """Robustly extract a JSON object from LLM response text."""
    # Try 1: parse whole text directly
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try 2: strip markdown code fences
    fenced = re.sub(r'```(?:json)?\s*', '', text)
    fenced = re.sub(r'```', '', fenced).strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass
    # Try 3: find outermost {...} using brace counting
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return None
    return None



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
        logger.info(f"Plan received: {len(plan)} step(s)")
        if plan:
            logger.info(f"First step sample: {str(plan[0])[:200]}")
        else:
            logger.warning("Plan is empty — will use pipeline task description as fallback context")

        # If plan is empty, synthesize a single-step fallback from the pipeline task
        if not plan:
            pipeline = self.state_manager.get_pipeline(pipeline_id)
            user_task = pipeline.user_task if pipeline else "complete the coding task"
            plan = [{
                "order": 1,
                "description": user_task,
                "files_affected": [],
                "action": "create",
            }]
            logger.info(f"Using fallback single-step plan: {user_task}")

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

            # Build a rich prompt with the user's original task as extra context
            pipeline_obj = self.state_manager.get_pipeline(pipeline_id)
            original_task = pipeline_obj.user_task if pipeline_obj else step_desc
            # Detect language from files or task text
            lang_name, lang_ext = _detect_language(files_affected, step_desc, original_task)
            files_hint = ', '.join(files_affected) if files_affected else f'as needed (suggest a sensible filename with {lang_ext} extension)'

            prompt = f"""Implement the following coding step. Write complete, working {lang_name} code.

Original user task: {original_task}
Current step: {step_desc}
Target language: {lang_name}
Files to create/modify: {files_hint}

Requirements:
- Write complete, runnable {lang_name} code with no placeholders or TODOs
- Include a main entry point appropriate for {lang_name}
- Add comments and handle errors gracefully
- The code MUST be in {lang_name}, not any other language

Respond ONLY with a valid JSON object (no markdown, no extra text):
{{
  "implementations": [
    {{
      "file_path": "example{lang_ext}",
      "action": "create",
      "content": "# complete file content here",
      "explanation": "brief explanation"
    }}
  ]
}}"""

            try:
                implementation_text = await self.think(prompt)
                logger.debug(f"Coder LLM raw response (first 300 chars): {implementation_text[:300]}")

                implementation = _extract_json(implementation_text)
                if not implementation:
                    raw_preview = implementation_text[:300].replace('\n', ' ')
                    raise ValueError(
                        f"Coder LLM response for step {step_order} could not be parsed as JSON.\n"
                        f"Raw response preview: {raw_preview}\n"
                        "Check that your LLM model is returning valid JSON as instructed."
                    )

                implementations = implementation.get("implementations", [])
                logger.info(f"Step {step_order}: parsed {len(implementations)} file implementation(s)")

                # Record code changes and write files to disk
                for impl in implementations:
                    file_path = impl.get("file_path", "")
                    content = impl.get("content", "")
                    action = impl.get("action", "create")

                    if not file_path or not content:
                        logger.warning(f"Skipping implementation with empty file_path or content")
                        continue

                    if pipeline_id:
                        self.state_manager.add_code_change(
                            pipeline_id=pipeline_id,
                            file_path=file_path,
                            change_type=action,
                            content=content,
                            agent="coder",
                        )

                    # Write the file to disk so it actually exists
                    try:
                        target = Path(file_path)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(content, encoding="utf-8")
                        logger.info(f"Written file to disk: {file_path}")
                    except Exception as write_err:
                        logger.warning(f"Could not write {file_path} to disk: {write_err}")

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

        logger.info(f"Coding complete: {len(implemented_steps)} file(s) implemented")

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