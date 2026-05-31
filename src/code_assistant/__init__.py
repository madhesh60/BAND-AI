"""Multi-agent coding assistant powered by BAND orchestration."""

__version__ = "0.1.0"
__author__ = "MiniMax Agent"

from code_assistant.agents import (
    ConductorAgent,
    PlannerAgent,
    PlanReviewerAgent,
    CoderAgent,
    CodeReviewerAgent,
    TestEngineerAgent,
    DebuggerAgent,
    MergemasterAgent,
)
from code_assistant.band_integration import AgentFactory, CommunicationLayer, StateManager
from code_assistant.workflows import CodingPipeline

__all__ = [
    "ConductorAgent",
    "PlannerAgent",
    "PlanReviewerAgent",
    "CoderAgent",
    "CodeReviewerAgent",
    "TestEngineerAgent",
    "DebuggerAgent",
    "MergemasterAgent",
    "AgentFactory",
    "CommunicationLayer",
    "StateManager",
    "CodingPipeline",
]