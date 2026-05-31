"""Shared state management for agent coordination."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a task in the pipeline."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Represents a task in the workflow."""

    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    result: Optional[dict] = None
    errors: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert task to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_agent": self.assigned_agent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "errors": self.errors,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Create task from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())),
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=TaskStatus(data.get("status", "pending")),
            assigned_agent=data.get("assigned_agent"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            result=data.get("result"),
            errors=data.get("errors", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PipelineState:
    """Represents the state of the entire coding pipeline."""

    pipeline_id: str = field(default_factory=lambda: str(uuid4()))
    user_task: str = ""
    current_phase: str = "init"
    tasks: dict = field(default_factory=dict)
    plan: list = field(default_factory=list)
    code_changes: list = field(default_factory=list)
    reviews: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert state to dictionary."""
        return {
            "pipeline_id": self.pipeline_id,
            "user_task": self.user_task,
            "current_phase": self.current_phase,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "plan": self.plan,
            "code_changes": self.code_changes,
            "reviews": self.reviews,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineState":
        """Create state from dictionary."""
        return cls(
            pipeline_id=data.get("pipeline_id", str(uuid4())),
            user_task=data.get("user_task", ""),
            current_phase=data.get("current_phase", "init"),
            tasks={
                k: Task.from_dict(v) for k, v in data.get("tasks", {}).items()
            },
            plan=data.get("plan", []),
            code_changes=data.get("code_changes", []),
            reviews=data.get("reviews", []),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            metadata=data.get("metadata", {}),
        )


class StateManager:
    """Manages shared state across agents."""

    def __init__(self, state_file: str = ".code_assistant_state.json"):
        self.state_file = state_file
        self._states: dict = {}
        self._listeners: list = []
        self.load_state()
        logger.info("State manager initialized")

    def load_state(self) -> None:
        import os
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self._states[k] = PipelineState.from_dict(v)
                logger.info(f"Loaded {len(self._states)} pipeline states from {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    def save_state(self) -> None:
        try:
            with open(self.state_file, "w") as f:
                json.dump({k: v.to_dict() for k, v in self._states.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def create_pipeline(self, user_task: str, pipeline_id: Optional[str] = None) -> PipelineState:
        """Create a new pipeline state."""
        state = PipelineState(user_task=user_task, pipeline_id=pipeline_id or str(uuid4()))
        self._states[state.pipeline_id] = state
        logger.info(f"Created pipeline: {state.pipeline_id}")
        self._notify_listeners("create", state)
        return state

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineState]:
        """Get a pipeline state by ID."""
        return self._states.get(pipeline_id)

    def update_pipeline(self, pipeline_id: str, **updates) -> Optional[PipelineState]:
        """Update pipeline state."""
        state = self._states.get(pipeline_id)
        if state is None:
            return None

        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)

        state.updated_at = datetime.utcnow().isoformat()
        self._notify_listeners("update", state)
        return state

    def add_task(
        self,
        pipeline_id: str,
        title: str,
        description: str,
        assigned_agent: Optional[str] = None,
    ) -> Optional[Task]:
        """Add a task to a pipeline."""
        state = self._states.get(pipeline_id)
        if state is None:
            return None

        task = Task(
            title=title,
            description=description,
            assigned_agent=assigned_agent,
        )
        state.tasks[task.id] = task
        state.updated_at = datetime.utcnow().isoformat()
        self._notify_listeners("task_added", state, task)
        return task

    def update_task(
        self,
        pipeline_id: str,
        task_id: str,
        **updates,
    ) -> Optional[Task]:
        """Update a task."""
        state = self._states.get(pipeline_id)
        if state is None or task_id not in state.tasks:
            return None

        task = state.tasks[task_id]
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.utcnow().isoformat()
        state.updated_at = datetime.utcnow().isoformat()
        self._notify_listeners("task_updated", state, task)
        return task

    def add_code_change(
        self,
        pipeline_id: str,
        file_path: str,
        change_type: str,
        content: str,
        agent: str,
    ) -> None:
        """Add a code change to the pipeline."""
        state = self._states.get(pipeline_id)
        if state is None:
            return

        change = {
            "id": str(uuid4()),
            "file_path": file_path,
            "change_type": change_type,
            "content": content,
            "agent": agent,
            "timestamp": datetime.utcnow().isoformat(),
        }
        state.code_changes.append(change)
        state.updated_at = datetime.utcnow().isoformat()
        self._notify_listeners("code_change", state, change)

    def add_review(
        self,
        pipeline_id: str,
        reviewer: str,
        status: str,
        comments: list,
        file_path: Optional[str] = None,
    ) -> None:
        """Add a review to the pipeline."""
        state = self._states.get(pipeline_id)
        if state is None:
            return

        review = {
            "id": str(uuid4()),
            "reviewer": reviewer,
            "status": status,
            "comments": comments,
            "file_path": file_path,
            "timestamp": datetime.utcnow().isoformat(),
        }
        state.reviews.append(review)
        state.updated_at = datetime.utcnow().isoformat()
        self._notify_listeners("review", state, review)

    def register_listener(self, listener: callable) -> None:
        """Register a state change listener."""
        self._listeners.append(listener)

    def _notify_listeners(self, event: str, state: PipelineState, data: Any = None) -> None:
        """Notify all listeners of state changes."""
        self.save_state()
        for listener in self._listeners:
            try:
                listener(event, state, data)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    def export_state(self, pipeline_id: str) -> Optional[str]:
        """Export pipeline state as JSON string."""
        state = self._states.get(pipeline_id)
        if state is None:
            return None
        return json.dumps(state.to_dict(), indent=2)

    def import_state(self, json_str: str) -> Optional[PipelineState]:
        """Import pipeline state from JSON string."""
        try:
            data = json.loads(json_str)
            state = PipelineState.from_dict(data)
            self._states[state.pipeline_id] = state
            return state
        except Exception as e:
            logger.error(f"Failed to import state: {e}")
            return None