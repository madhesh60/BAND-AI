"""Mergemaster agent - handles Git operations."""

import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from code_assistant.agents.base import BaseAgent
from code_assistant.band_integration.communication import (
    AgentMessage,
    MessageType,
    Priority,
)
from code_assistant.utils.config import config

logger = logging.getLogger(__name__)


class MergemasterAgent(BaseAgent):
    """Mergemaster handles Git operations and PR management."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.repo_path = Path.cwd()
        self.default_branch = config.config.git.default_branch

    async def process_message(self, message: AgentMessage) -> dict:
        """Process incoming messages."""
        if message.message_type == MessageType.TASK:
            return await self.execute_task(message.content)
        return {"status": "unknown_message"}

    async def execute_task(self, task_data: dict) -> dict:
        """Handle Git operations and merging."""
        pipeline_id = task_data.get("pipeline_id", "")
        code_changes = task_data.get("code_changes", [])

        logger.info(f"Mergemaster processing {len(code_changes)} changes")

        results = {
            "branch_created": None,
            "commits_made": 0,
            "pr_created": False,
            "pr_url": None,
            "merge_status": None,
        }

        try:
            # Get pipeline for context
            pipeline = self.state_manager.get_pipeline(pipeline_id)
            task_description = pipeline.user_task if pipeline else "code changes"

            # --- Git Repository Initialization Guard ---
            # If the working directory is not a git repository, we auto-initialize one.
            # This prevents the 'fatal: not a git repository' crash when running inside
            # a fresh container or a directory that was never initialized.
            git_dir = self.repo_path / ".git"
            if not git_dir.exists():
                logger.warning(f"[mergemaster] No .git directory found at {self.repo_path}. Auto-initializing git repo...")
                await self._run_git("init")
                await self._run_git("config", "user.email", "code-assistant@band.ai")
                await self._run_git("config", "user.name", "Code Assistant")
                # Stage everything present so we have an initial base commit to branch from
                await self._run_git("add", ".")
                code, _, stderr = await self._run_git(
                    "commit", "-m", "chore: initial commit by Code Assistant"
                )
                if code != 0 and "nothing to commit" not in stderr.lower():
                    logger.warning(f"[mergemaster] Initial commit failed: {stderr}")

            # Sanitize for branch name
            branch_name = self._create_branch_name(task_description)

            # Create feature branch
            await self._create_branch(branch_name)
            results["branch_created"] = branch_name

            # Apply code changes
            for change in code_changes:
                file_path = change.get("file_path", "")
                content = change.get("content", "")
                change_type = change.get("change_type", "modify")

                if content:  # Only write if we have content
                    await self._write_file(file_path, content)
                    await self._commit_file(file_path, f"{change_type}: {file_path}")
                    results["commits_made"] += 1

            # Push to remote
            await self._push_branch(branch_name)

            # Create PR
            pr_result = await self._create_pr(
                branch_name=branch_name,
                title=f"feat: {task_description[:50]}",
                body=f"## Summary\n\nImplemented: {task_description}\n\n## Changes\n\n- {results['commits_made']} files modified",
            )

            if pr_result:
                results["pr_created"] = True
                results["pr_url"] = pr_result.get("url")

            # Check auto-merge eligibility
            if self._should_auto_merge():
                await self._auto_merge(branch_name)
                results["merge_status"] = "auto_merged"
            else:
                results["merge_status"] = "pr_created_pending_review"

        except Exception as e:
            logger.error(f"Mergemaster error: {e}")
            results["error"] = str(e)

        # Notify conductor
        await self.send_to_agent(
            "conductor",
            MessageType.RESPONSE,
            {
                "pipeline_id": pipeline_id,
                "phase": "merging",
                "status": "completed",
                **results,
            },
            subject="Merging phase completed",
            priority=Priority.NORMAL,
        )

        return {
            "status": "merging_completed",
            "results": results,
        }

    def _create_branch_name(self, description: str) -> str:
        """Create a valid Git branch name from description."""
        # Lowercase, replace spaces with hyphens, remove special chars
        name = description.lower()
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '-', name)
        name = re.sub(r'[^a-z0-9-]', '', name)

        # Limit length and add prefix
        name = name[:50].strip('-')
        return f"feature/{name}"

    async def _run_git(self, *args) -> tuple:
        """Run a git command."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            logger.error(f"Git command failed: {e}")
            return 1, "", str(e)

    async def _create_branch(self, branch_name: str) -> bool:
        """Create a new Git branch."""
        code, stdout, stderr = await self._run_git("checkout", "-b", branch_name)
        if code == 0:
            logger.info(f"Created branch: {branch_name}")
            return True
        logger.error(f"Failed to create branch: {stderr}")
        return False

    async def _write_file(self, file_path: str, content: str) -> bool:
        """Write content to a file."""
        try:
            full_path = self.repo_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            logger.info(f"Wrote file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False

    async def _commit_file(self, file_path: str, message: str) -> bool:
        """Stage and commit a file."""
        await self._run_git("add", file_path)
        code, stdout, stderr = await self._run_git("commit", "-m", message)
        if code == 0:
            logger.info(f"Committed: {file_path}")
            return True
        logger.warning(f"Commit failed (may be empty): {stderr}")
        return False

    async def _push_branch(self, branch_name: str) -> bool:
        """Push branch to remote."""
        code, stdout, stderr = await self._run_git(
            "push", "-u", "origin", branch_name
        )
        if code == 0:
            logger.info(f"Pushed branch: {branch_name}")
            return True
        logger.error(f"Failed to push branch: {stderr}")
        return False

    async def _create_pr(
        self,
        branch_name: str,
        title: str,
        body: str,
    ) -> Optional[dict]:
        """Create a pull request using gh CLI."""
        try:
            result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", title,
                    "--body", body,
                    "--base", self.default_branch,
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Extract PR URL from output
                pr_url = result.stdout.strip()
                logger.info(f"Created PR: {pr_url}")
                return {"url": pr_url, "status": "created"}

            logger.error(f"PR creation failed: {result.stderr}")
            return None

        except FileNotFoundError:
            logger.warning("gh CLI not installed, skipping PR creation")
            return None
        except Exception as e:
            logger.error(f"PR creation error: {e}")
            return None

    def _should_auto_merge(self) -> bool:
        """Check if changes should be auto-merged."""
        threshold = config.config.git.auto_merge_threshold.lower()
        return threshold == "low"

    async def _auto_merge(self, branch_name: str) -> bool:
        """Automatically merge the PR."""
        try:
            result = subprocess.run(
                ["gh", "pr", "merge", "--squash", "--auto", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.info(f"Auto-merged branch: {branch_name}")
                return True

            logger.warning(f"Auto-merge failed: {result.stderr}")
            return False

        except Exception as e:
            logger.error(f"Auto-merge error: {e}")
            return False