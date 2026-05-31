"""Main coding pipeline workflow powered by LangGraph."""

import asyncio
import json
import logging
import os
import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from code_assistant.agents.conductor import ConductorAgent
from code_assistant.agents.planner import PlannerAgent
from code_assistant.agents.plan_reviewer import PlanReviewerAgent
from code_assistant.agents.coder import CoderAgent
from code_assistant.agents.code_reviewer import CodeReviewerAgent
from code_assistant.agents.test_engineer import TestEngineerAgent
from code_assistant.agents.debugger import DebuggerAgent
from code_assistant.agents.mergemaster import MergemasterAgent
from code_assistant.band_integration.agent_factory import AgentFactory
from code_assistant.band_integration.state_manager import StateManager, TaskStatus

logger = logging.getLogger(__name__)


class PersistentMemorySaver(MemorySaver):
    """A persistent version of MemorySaver that saves state to a local pickle file.
    
    This custom checkpointer ensures that when the LangGraph workflow halts at human-in-the-loop
    interrupt gates, its full execution state (variables, history, tasks, results) is persisted
    to a local pickle file (`.code_assistant_memory.pkl`). This enables resuming the execution
    across distinct CLI commands and CLI shell runs.
    """

    def __init__(self, filepath: str = ".code_assistant_memory.pkl", **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath
        self._load()

    def _save(self):
        # Recursively convert defaultdict to dict for clean pickle serialization
        def to_dict_recursive(d):
            if isinstance(d, defaultdict):
                return {k: to_dict_recursive(v) for k, v in d.items()}
            return d

        data = {
            "storage": to_dict_recursive(self.storage),
            "writes": dict(self.writes),
            "blobs": dict(self.blobs),
        }
        try:
            with open(self.filepath, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.error(f"Failed to persist memory saver state to {self.filepath}: {e}")

    def _load(self):
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, "rb") as f:
                data = pickle.load(f)
            
            self.storage = defaultdict(lambda: defaultdict(dict))
            for thread_id, ns_dict in data.get("storage", {}).items():
                for ns, cp_dict in ns_dict.items():
                    for cp_id, cp_val in cp_dict.items():
                        self.storage[thread_id][ns][cp_id] = cp_val
            
            self.writes = defaultdict(dict)
            for k, v in data.get("writes", {}).items():
                self.writes[k] = v
                
            self.blobs = defaultdict()
            for k, v in data.get("blobs", {}).items():
                self.blobs[k] = v
        except Exception as e:
            logger.error(f"Failed to load memory saver state from {self.filepath}: {e}")

    def put(self, config, checkpoint, metadata, new_versions):
        res = super().put(config, checkpoint, metadata, new_versions)
        self._save()
        return res

    def put_writes(self, config, writes, task_id, task_path=""):
        res = super().put_writes(config, writes, task_id, task_path)
        self._save()
        return res

    async def aput(self, config, checkpoint, metadata, new_versions):
        res = await super().aput(config, checkpoint, metadata, new_versions)
        self._save()
        return res

    async def aput_writes(self, config, writes, task_id, task_path=""):
        res = await super().aput_writes(config, writes, task_id, task_path)
        self._save()
        return res



class AgentState(TypedDict):
    """State schema for the LangGraph workflow."""
    pipeline_id: str
    user_task: str
    current_phase: str
    plan: List[Dict[str, Any]]
    code_changes: List[Dict[str, Any]]
    reviews: List[Dict[str, Any]]
    tasks: Dict[str, Any]
    error: Optional[str]
    review_status: str  # approved, needs_changes, rejected, pending
    user_feedback: Optional[str]
    retry_count: int


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""

    pipeline_id: str
    status: str
    start_time: str
    end_time: Optional[str] = None
    user_task: str = ""
    phases_completed: list = field(default_factory=list)
    total_tasks: int = 0
    completed_tasks: int = 0
    issues_found: int = 0
    issues_fixed: int = 0
    pr_url: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pipeline_id": self.pipeline_id,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "user_task": self.user_task,
            "phases_completed": self.phases_completed,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "issues_found": self.issues_found,
            "issues_fixed": self.issues_fixed,
            "pr_url": self.pr_url,
            "error": self.error,
            "metadata": self.metadata,
        }


class CodingPipeline:
    """Main coding pipeline that orchestrates all agents using LangGraph."""

    def __init__(self):
        self.state_manager = StateManager()
        self.agents: dict = {}
        self._initialized = False
        self.graph = None
        self.memory = None

    async def initialize(self) -> None:
        """Initialize all agents and compile the LangGraph workflow."""
        if self._initialized:
            return

        logger.info("Initializing coding pipeline and agents...")

        # Create agents using factory
        agent_configs = AgentFactory.create_all_agents()

        # Create agent instances
        self.agents["conductor"] = ConductorAgent(
            name="conductor",
            role="orchestrator",
            description="Main orchestrator",
            system_prompt=agent_configs["conductor"]["system_prompt"],
            llm_client=agent_configs["conductor"]["llm"],
            model=agent_configs["conductor"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["planner"] = PlannerAgent(
            name="planner",
            role="planner",
            description="Task planner",
            system_prompt=agent_configs["planner"]["system_prompt"],
            llm_client=agent_configs["planner"]["llm"],
            model=agent_configs["planner"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["plan_reviewer"] = PlanReviewerAgent(
            name="plan_reviewer",
            role="reviewer",
            description="Plan reviewer",
            system_prompt=agent_configs["plan_reviewer"]["system_prompt"],
            llm_client=agent_configs["plan_reviewer"]["llm"],
            model=agent_configs["plan_reviewer"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["coder"] = CoderAgent(
            name="coder",
            role="coder",
            description="Code implementer",
            system_prompt=agent_configs["coder"]["system_prompt"],
            llm_client=agent_configs["coder"]["llm"],
            model=agent_configs["coder"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["code_reviewer"] = CodeReviewerAgent(
            name="code_reviewer",
            role="reviewer",
            description="Code reviewer",
            system_prompt=agent_configs["code_reviewer"]["system_prompt"],
            llm_client=agent_configs["code_reviewer"]["llm"],
            model=agent_configs["code_reviewer"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["test_engineer"] = TestEngineerAgent(
            name="test_engineer",
            role="tester",
            description="Test engineer",
            system_prompt=agent_configs["test_engineer"]["system_prompt"],
            llm_client=agent_configs["test_engineer"]["llm"],
            model=agent_configs["test_engineer"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["debugger"] = DebuggerAgent(
            name="debugger",
            role="debugger",
            description="Debugger",
            system_prompt=agent_configs["debugger"]["system_prompt"],
            llm_client=agent_configs["debugger"]["llm"],
            model=agent_configs["debugger"].get("model"),
            state_manager=self.state_manager,
        )

        self.agents["mergemaster"] = MergemasterAgent(
            name="mergemaster",
            role="merger",
            description="Git operations",
            system_prompt=agent_configs["mergemaster"]["system_prompt"],
            llm_client=agent_configs["mergemaster"]["llm"],
            model=agent_configs["mergemaster"].get("model"),
            state_manager=self.state_manager,
        )

        # Start all agents
        for agent in self.agents.values():
            await agent.start()

        # Build LangGraph workflow
        self._build_graph()

        self._initialized = True
        logger.info(f"Pipeline initialized with LangGraph and {len(self.agents)} agents")

    def _build_graph(self):
        """Construct and compile the LangGraph StateGraph workflow.
        
        The graph models our cooperative multi-agent workflow:
        1. Planning: The `planner` agent creates an implementation plan.
        2. Plan Review: The `plan_reviewer` agent verifies security, complexity, and sanity.
        3. Plan Approval (HITL Gate): The execution is halted before `plan_gate` to wait for 
           user confirmation (via CLI `/approve` or `/reject`). If rejected, we route back 
           to Planning (incorporating feedback). If approved, we route to Coding.
        4. Coding: The `coder` agent performs changes on files.
        5. Code Review: The `code_reviewer` reviews code quality and conformity.
        6. Code Approval (HITL Gate): The execution is halted before `code_gate` to wait for
           user confirmation. If rejected, we route to Debugging (which forwards feedback to coder).
           If approved, we route to Testing.
        7. Testing: The `test_engineer` creates/runs tests.
        8. Merging: The `mergemaster` commits/pushes files.
        """
        workflow = StateGraph(AgentState)

        # Add Nodes corresponding to agent tasks
        workflow.add_node("planning", self._planning_node)
        workflow.add_node("plan_review", self._plan_review_node)
        workflow.add_node("plan_gate", self._plan_gate_node)
        workflow.add_node("coding", self._coding_node)
        workflow.add_node("code_review", self._code_review_node)
        workflow.add_node("code_gate", self._code_gate_node)
        workflow.add_node("debugging", self._debugging_node)
        workflow.add_node("testing", self._testing_node)
        workflow.add_node("merging", self._merging_node)

        # Add linear progress edges
        workflow.add_edge(START, "planning")
        workflow.add_edge("planning", "plan_review")
        workflow.add_edge("plan_review", "plan_gate")

        # Routing logic from plan_gate:
        # Route to 'coding' if the plan is approved, or loop back to 'planning' if rejected.
        workflow.add_conditional_edges(
            "plan_gate",
            self._decide_after_plan_gate,
            {
                "coding": "coding",
                "planning": "planning"
            }
        )

        workflow.add_edge("coding", "code_review")
        workflow.add_edge("code_review", "code_gate")

        # Routing logic from code_gate:
        # Route to 'testing' if code review is approved, or 'debugging' if revisions are needed.
        workflow.add_conditional_edges(
            "code_gate",
            self._decide_after_code_gate,
            {
                "testing": "testing",
                "debugging": "debugging"
            }
        )

        workflow.add_edge("debugging", "coding")
        workflow.add_edge("testing", "merging")
        workflow.add_edge("merging", END)

        # Initialize checkpointer for Human-In-The-Loop interrupts.
        # This saves state to the persistent `.code_assistant_memory.pkl` pickle file.
        self.memory = PersistentMemorySaver()
        
        # Compile with interrupts. The execution will pause right before entering plan_gate
        # and code_gate nodes, allowing the user to review the state via CLI and approve/reject.
        self.graph = workflow.compile(
            checkpointer=self.memory,
            interrupt_before=["plan_gate", "code_gate"]
        )

    # --- Node Implementations ---

    async def _planning_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: planning] Starting planning for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="planning")

        task_desc = state["user_task"]
        pipeline = self.state_manager.get_pipeline(pipeline_id)
        prev_plan = pipeline.plan if pipeline else []
        prev_reviews = pipeline.reviews if pipeline else []

        rejection_details = []
        if prev_reviews:
            for r in prev_reviews:
                if r.get("reviewer") == "plan_reviewer" and r.get("status") in ["rejected", "needs_revision"]:
                    comments = r.get("comments", [])
                    comments_str = ", ".join(comments) if isinstance(comments, list) else str(comments)
                    rejection_details.append(f"- Plan Reviewer Feedback: {comments_str}")

        if state.get("user_feedback") and state.get("review_status") == "rejected":
            rejection_details.append(f"- Human Feedback: {state['user_feedback']}")
            logger.info(f"Re-planning with user feedback: {state['user_feedback']}")

        if rejection_details:
            rejection_str = "\n".join(rejection_details)
            prev_plan_str = json.dumps(prev_plan, indent=2)
            task_desc += (
                f"\n\n[REVISION REQUESTED]\n"
                f"We are revising the implementation plan. Here is the feedback on why the previous plan was rejected:\n"
                f"{rejection_str}\n\n"
                f"Here was the previous plan:\n"
                f"{prev_plan_str}\n\n"
                f"Please revise the plan to address all comments and feedback above."
            )

        planner = self.agents["planner"]
        await planner.execute_task({
            "pipeline_id": pipeline_id,
            "task": task_desc,
        })

        pipeline = self.state_manager.get_pipeline(pipeline_id)
        plan = pipeline.plan if pipeline else []

        return {
            "plan": plan,
            "current_phase": "planning",
            "review_status": "pending",
        }

    async def _plan_review_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: plan_review] Reviewing plan for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="plan_review")

        reviewer = self.agents["plan_reviewer"]
        await reviewer.execute_task({
            "pipeline_id": pipeline_id,
            "plan": state["plan"],
        })

        pipeline = self.state_manager.get_pipeline(pipeline_id)
        reviews = pipeline.reviews if pipeline else []

        # Default fallback approval
        review_status = "approved"
        for r in reversed(reviews):
            if r.get("reviewer") == "plan_reviewer":
                if r.get("status") in ["rejected", "needs_revision", "needs_changes"]:
                    review_status = "rejected"
                break

        # Set phase to plan_approval for Human-in-the-Loop interruption UI/CLI
        self.state_manager.update_pipeline(pipeline_id, current_phase="plan_approval")

        return {
            "reviews": reviews,
            "review_status": review_status,
            "current_phase": "plan_approval",
        }

    async def _plan_gate_node(self, state: AgentState) -> dict:
        # Resumes here after Plan Approval HITL interrupt
        logger.info(f"[LangGraph Node: plan_gate] Evaluation. review_status={state['review_status']}")
        return {}

    async def _coding_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: coding] Implementing code for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="coding")

        coder = self.agents["coder"]
        await coder.execute_task({
            "pipeline_id": pipeline_id,
            "plan": state["plan"],
        })

        pipeline = self.state_manager.get_pipeline(pipeline_id)
        code_changes = pipeline.code_changes if pipeline else []

        return {
            "code_changes": code_changes,
            "current_phase": "coding",
            "review_status": "pending",
        }

    async def _code_review_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: code_review] Reviewing code changes for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="code_review")

        reviewer = self.agents["code_reviewer"]
        await reviewer.execute_task({
            "pipeline_id": pipeline_id,
            "code_changes": state["code_changes"],
        })

        pipeline = self.state_manager.get_pipeline(pipeline_id)
        reviews = pipeline.reviews if pipeline else []

        review_status = "approved"
        for r in reversed(reviews):
            if r.get("reviewer") == "code_reviewer":
                if r.get("status") == "rejected":
                    review_status = "needs_changes"
                break

        # Set phase to code_approval for Human-in-the-Loop interruption UI/CLI
        self.state_manager.update_pipeline(pipeline_id, current_phase="code_approval")

        return {
            "reviews": reviews,
            "review_status": review_status,
            "current_phase": "code_approval",
        }

    async def _code_gate_node(self, state: AgentState) -> dict:
        # Resumes here after Code Approval HITL interrupt
        logger.info(f"[LangGraph Node: code_gate] Evaluation. review_status={state['review_status']}")
        return {}

    async def _debugging_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: debugging] Fixing issues for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="debugging")

        pipeline = self.state_manager.get_pipeline(pipeline_id)
        
        # Fetch rejected code reviews and map to the format expected by debugger
        raw_reviews = [r for r in pipeline.reviews if r.get("status") in ["rejected", "needs_changes"]] if pipeline else []
        debugger_issues = []
        for r in raw_reviews:
            comments = r.get("comments", [])
            file_path = r.get("file_path", "")
            comments_str = "\n".join(comments) if isinstance(comments, list) else str(comments)
            debugger_issues.append({
                "type": "code_review_rejection",
                "description": comments_str,
                "file_path": file_path,
                "suggestion": "Fix issues found in the code review.",
            })

        # Append human feedback if present
        if state.get("user_feedback"):
            affected_files = list(set([c.get("file_path") for c in pipeline.code_changes if c.get("file_path")])) if pipeline else []
            if not affected_files and pipeline:
                affected_files = list(set([f.get("path") for f in pipeline.plan if f.get("path")]))
            
            for file_path in affected_files:
                debugger_issues.append({
                    "type": "human_feedback",
                    "description": state["user_feedback"],
                    "file_path": file_path,
                    "suggestion": "Revise the code based on human feedback.",
                })
            if not affected_files:
                debugger_issues.append({
                    "type": "human_feedback",
                    "description": state["user_feedback"],
                    "file_path": "",
                    "suggestion": "Revise the code based on human feedback.",
                })

        debugger = self.agents["debugger"]
        await debugger.execute_task({
            "pipeline_id": pipeline_id,
            "issues": debugger_issues,
            "user_feedback": state.get("user_feedback"),
        })

        return {
            "retry_count": state["retry_count"] + 1,
            "current_phase": "debugging",
        }

    async def _testing_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: testing] Running test suite for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="testing")

        tester = self.agents["test_engineer"]
        await tester.execute_task({
            "pipeline_id": pipeline_id,
            "code_changes": state["code_changes"],
        })

        return {
            "current_phase": "testing",
        }

    async def _merging_node(self, state: AgentState) -> dict:
        pipeline_id = state["pipeline_id"]
        logger.info(f"[LangGraph Node: merging] Merging code changes for pipeline {pipeline_id}")
        self.state_manager.update_pipeline(pipeline_id, current_phase="merging")

        merger = self.agents["mergemaster"]
        await merger.execute_task({
            "pipeline_id": pipeline_id,
            "code_changes": state["code_changes"],
        })

        # Finalize status to completed
        self.state_manager.update_pipeline(pipeline_id, current_phase="completed")

        return {
            "current_phase": "completed",
        }

    # --- Routing Decisions ---

    def _decide_after_plan_gate(self, state: AgentState) -> str:
        if state.get("review_status") == "approved":
            return "coding"
        return "planning"

    def _decide_after_code_gate(self, state: AgentState) -> str:
        if state.get("review_status") == "approved":
            return "testing"
        return "debugging"

    # --- API execution methods ---

    async def execute(self, user_task: str, pipeline_id: Optional[str] = None) -> PipelineResult:
        """Kickoff graph execution for a user task."""
        if not self._initialized:
            await self.initialize()

        pipeline_id = pipeline_id or str(uuid4())
        start_time = datetime.utcnow().isoformat()

        logger.info(f"Kicking off LangGraph workflow {pipeline_id} for task: {user_task}")

        result = PipelineResult(
            pipeline_id=pipeline_id,
            status="running",
            start_time=start_time,
            user_task=user_task,
        )

        # Register state in state manager
        pipeline = self.state_manager.get_pipeline(pipeline_id)
        if not pipeline:
            pipeline = self.state_manager.create_pipeline(user_task, pipeline_id=pipeline_id)

        config = {"configurable": {"thread_id": pipeline_id}}

        initial_state: AgentState = {
            "pipeline_id": pipeline_id,
            "user_task": user_task,
            "current_phase": "planning",
            "plan": [],
            "code_changes": [],
            "reviews": [],
            "tasks": {},
            "error": None,
            "review_status": "pending",
            "user_feedback": None,
            "retry_count": 0,
        }

        try:
            # Execute graph. It will pause automatically before plan_gate or code_gate
            await self.graph.ainvoke(initial_state, config)
            
            # Fetch latest state after execution paused or finished
            self._update_result_from_state(result, pipeline_id)

        except Exception as e:
            logger.error(f"LangGraph execution error: {e}", exc_info=True)
            result.status = "error"
            result.error = str(e)
            result.end_time = datetime.utcnow().isoformat()
            self.state_manager.update_pipeline(pipeline_id, current_phase="error", metadata={"error": str(e)})

        return result

    async def resume(self, pipeline_id: str, decision: str, feedback: Optional[str] = None) -> PipelineResult:
        """Resume a paused graph execution with approval/rejection and optional feedback."""
        if not self._initialized:
            await self.initialize()

        logger.info(f"Resuming LangGraph workflow {pipeline_id} with decision: {decision}")
        config = {"configurable": {"thread_id": pipeline_id}}

        pipeline = self.state_manager.get_pipeline(pipeline_id)
        if not pipeline:
            raise ValueError(f"Pipeline {pipeline_id} not found in state manager")

        # Determine which review stage we are resuming from
        current_phase = pipeline.current_phase
        as_node = "plan_review"
        if "code" in current_phase:
            as_node = "code_review"

        # Update the state values in LangGraph storage
        await self.graph.aupdate_state(
            config,
            {
                "review_status": decision,
                "user_feedback": feedback,
            },
            as_node=as_node
        )

        # Notify StateManager of resume phase transition
        resuming_phase = "planning" if decision != "approved" and as_node == "plan_review" else "coding" if decision != "approved" and as_node == "code_review" else "coding" if as_node == "plan_review" else "testing"
        self.state_manager.update_pipeline(pipeline_id, current_phase=resuming_phase)

        result = PipelineResult(
            pipeline_id=pipeline_id,
            status="running",
            start_time=pipeline.created_at,
            user_task=pipeline.user_task,
        )

        try:
            # Continue graph execution from interrupt
            await self.graph.ainvoke(None, config)
            self._update_result_from_state(result, pipeline_id)
        except Exception as e:
            logger.error(f"LangGraph resume error: {e}", exc_info=True)
            result.status = "error"
            result.error = str(e)
            result.end_time = datetime.utcnow().isoformat()
            self.state_manager.update_pipeline(pipeline_id, current_phase="error", metadata={"error": str(e)})

        return result

    def _update_result_from_state(self, result: PipelineResult, pipeline_id: str):
        """Update result fields from StateManager state."""
        pipeline_state = self.state_manager.get_pipeline(pipeline_id)
        if pipeline_state:
            result.phases_completed = [pipeline_state.current_phase]
            result.total_tasks = len(pipeline_state.tasks)
            result.completed_tasks = len([
                t for t in pipeline_state.tasks.values()
                if t.status.value == "completed"
            ])
            result.issues_found = len([
                r for r in pipeline_state.reviews
                if r.get("status") == "rejected"
            ])
            result.status = "completed" if pipeline_state.current_phase == "completed" else "running"
            if pipeline_state.current_phase == "completed":
                result.end_time = datetime.utcnow().isoformat()

    async def shutdown(self) -> None:
        """Shutdown all agents."""
        logger.info("Shutting down coding pipeline...")
        for agent in self.agents.values():
            await agent.stop()
        self._initialized = False