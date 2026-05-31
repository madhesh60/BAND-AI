import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from code_assistant.workflows.coding_pipeline import CodingPipeline, PipelineResult
from code_assistant.band_integration.state_manager import StateManager


class TestLangGraphPipeline:
    """Test suite for the new LangGraph-based CodingPipeline."""

    @pytest.mark.asyncio
    async def test_graph_initialization(self):
        """Test that the LangGraph StateGraph initializes and compiles correctly."""
        pipeline = CodingPipeline()
        await pipeline.initialize()

        assert pipeline._initialized is True
        assert pipeline.graph is not None
        assert pipeline.memory is not None
        assert "planner" in pipeline.agents
        assert "plan_reviewer" in pipeline.agents
        assert "coder" in pipeline.agents

        await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_pipeline_interruption_and_resume(self):
        """Test that the pipeline correctly interrupts at the plan_gate and resumes on approval."""
        pipeline = CodingPipeline()
        await pipeline.initialize()

        pipeline_id = "test-langgraph-thread"

        # Mock the agent executions so we don't call real LLMs
        for name, agent in pipeline.agents.items():
            agent.execute_task = AsyncMock(return_value={"status": "completed"})

        # Manually seed state manager pipeline state if needed
        # Kickoff graph execution
        result = await pipeline.execute("Implement hello world in hello.py", pipeline_id=pipeline_id)

        assert result.pipeline_id == pipeline_id
        
        # Verify the pipeline has paused at the plan_approval phase
        state = pipeline.state_manager.get_pipeline(pipeline_id)
        assert state is not None
        assert state.current_phase == "plan_approval"

        # Check LangGraph next execution checkpoint
        config = {"configurable": {"thread_id": pipeline_id}}
        state_info = await pipeline.graph.aget_state(config)
        assert "plan_gate" in state_info.next

        # Now resume the pipeline with approval
        resume_result = await pipeline.resume(pipeline_id, decision="approved")

        # Verify state manager moved forward
        state = pipeline.state_manager.get_pipeline(pipeline_id)
        assert state is not None
        # It resumes from plan_gate and runs all the way to code_gate (which is the next interrupt!)
        assert state.current_phase == "code_approval"
        
        # Resume the code review with approval to run it to completion
        final_result = await pipeline.resume(pipeline_id, decision="approved")
        
        state = pipeline.state_manager.get_pipeline(pipeline_id)
        assert state is not None
        assert state.current_phase == "completed"

        await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_pipeline_rejection_feedback_loop(self):
        """Test that the pipeline loops back from the plan_gate to planning if rejected."""
        pipeline = CodingPipeline()
        await pipeline.initialize()

        pipeline_id = "test-langgraph-reject-thread"

        # Mock the agent executions
        for name, agent in pipeline.agents.items():
            agent.execute_task = AsyncMock(return_value={"status": "completed"})

        # Kickoff graph execution
        await pipeline.execute("Implement math utility", pipeline_id=pipeline_id)

        # Resume the pipeline with rejection and feedback
        feedback_str = "Please focus on vector operations"
        await pipeline.resume(pipeline_id, decision="rejected", feedback=feedback_str)

        # Check that the pipeline has looped back and is now back in plan_approval (paused again)
        state = pipeline.state_manager.get_pipeline(pipeline_id)
        assert state is not None
        assert state.current_phase == "plan_approval"

        # Check LangGraph next execution checkpoint is plan_gate again
        config = {"configurable": {"thread_id": pipeline_id}}
        state_info = await pipeline.graph.aget_state(config)
        assert "plan_gate" in state_info.next
        assert state_info.values.get("user_feedback") == feedback_str

        await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_persistent_memory_saver(self):
        """Test that the PersistentMemorySaver correctly saves state to disk and can be loaded in a new pipeline instance."""
        import os
        test_pkl = ".test_pipeline_memory.pkl"
        if os.path.exists(test_pkl):
            os.remove(test_pkl)

        try:
            # 1. Start a pipeline using the custom file path
            pipeline1 = CodingPipeline()
            await pipeline1.initialize()
            # Inject a custom file path to avoid overwriting production file
            pipeline1.memory.filepath = test_pkl
            
            pipeline_id = "test-persistent-memory-thread"
            for name, agent in pipeline1.agents.items():
                agent.execute_task = AsyncMock(return_value={"status": "completed"})

            # Kickoff graph execution - it will pause at plan_approval
            await pipeline1.execute("Write persistent file check", pipeline_id=pipeline_id)

            assert os.path.exists(test_pkl) is True

            # 2. Shutdown first pipeline
            await pipeline1.shutdown()

            # 3. Create a second pipeline, which should load the serialized checkpoint automatically
            pipeline2 = CodingPipeline()
            await pipeline2.initialize()
            pipeline2.memory.filepath = test_pkl
            pipeline2.memory._load() # reload it with the custom test path

            config = {"configurable": {"thread_id": pipeline_id}}
            state_info = await pipeline2.graph.aget_state(config)
            
            # Verify the loaded next node matches where we left off
            assert "plan_gate" in state_info.next
            assert state_info.values.get("user_task") == "Write persistent file check"

            await pipeline2.shutdown()

        finally:
            if os.path.exists(test_pkl):
                os.remove(test_pkl)
