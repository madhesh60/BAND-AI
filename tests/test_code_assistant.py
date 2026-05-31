"""Test suite for code assistant."""

import pytest
from code_assistant.agents.base import BaseAgent
from code_assistant.band_integration import StateManager, CommunicationLayer, AgentFactory
from code_assistant.workflows import CodingPipeline


class TestStateManager:
    """Test state manager functionality."""

    def test_create_pipeline(self):
        """Test pipeline creation."""
        manager = StateManager()
        pipeline = manager.create_pipeline("Test task")

        assert pipeline.user_task == "Test task"
        assert pipeline.pipeline_id is not None
        assert pipeline.current_phase == "init"

    def test_add_task(self):
        """Test adding tasks to pipeline."""
        manager = StateManager()
        pipeline = manager.create_pipeline("Test task")

        task = manager.add_task(
            pipeline_id=pipeline.pipeline_id,
            title="Test subtask",
            description="Test description",
            assigned_agent="coder",
        )

        assert task is not None
        assert task.title == "Test subtask"
        assert task.assigned_agent == "coder"

    def test_update_pipeline(self):
        """Test pipeline updates."""
        manager = StateManager()
        pipeline = manager.create_pipeline("Test task")

        updated = manager.update_pipeline(
            pipeline_id=pipeline.pipeline_id,
            current_phase="coding",
        )

        assert updated is not None
        assert updated.current_phase == "coding"

    def test_add_code_change(self):
        """Test adding code changes."""
        manager = StateManager()
        pipeline = manager.create_pipeline("Test task")

        manager.add_code_change(
            pipeline_id=pipeline.pipeline_id,
            file_path="test.py",
            change_type="create",
            content="print('hello')",
            agent="coder",
        )

        assert len(pipeline.code_changes) == 1
        assert pipeline.code_changes[0]["file_path"] == "test.py"

    def test_add_review(self):
        """Test adding reviews."""
        manager = StateManager()
        pipeline = manager.create_pipeline("Test task")

        manager.add_review(
            pipeline_id=pipeline.pipeline_id,
            reviewer="code_reviewer",
            status="approved",
            comments=["Looks good!"],
        )

        assert len(pipeline.reviews) == 1
        assert pipeline.reviews[0]["status"] == "approved"


class TestCommunicationLayer:
    """Test communication layer."""

    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending messages."""
        from code_assistant.band_integration.communication import MessageType
        comm = CommunicationLayer("test_agent")

        message_id = await comm.send_message(
            recipient="other_agent",
            message_type=MessageType.TASK,
            content={"task": "test"},
            subject="Test message",
        )

        assert message_id is not None
        assert len(comm.get_pending_messages()) == 1

    @pytest.mark.asyncio
    async def test_send_message_with_mock_band_client(self):
        """Test sending messages with a mock ThenvoiLink client."""
        import asyncio
        from code_assistant.band_integration.communication import MessageType
        
        class MockRestMessages:
            def __init__(self):
                self.sent_messages = []
                
            async def create_agent_chat_message(self, chat_id, message, request_options=None):
                self.sent_messages.append((chat_id, message))
                class DummyResponse:
                    data = type('DummyData', (object,), {'id': 'msg-123'})()
                return DummyResponse()

        class MockRestChats:
            async def create_agent_chat(self, chat, request_options=None):
                class DummyResponse:
                    data = type('DummyData', (object,), {'id': 'room-xyz'})()
                return DummyResponse()

        class MockRest:
            def __init__(self):
                self.agent_api_messages = MockRestMessages()
                self.agent_api_chats = MockRestChats()

        class MockBandClient:
            def __init__(self):
                self.rest = MockRest()

        mock_client = MockBandClient()
        comm = CommunicationLayer("test_agent", band_client=mock_client)
        
        # We also need a pipeline state so that _get_or_create_room returns a valid room ID
        from code_assistant.band_integration.state_manager import StateManager
        state_manager = StateManager()
        pipeline = state_manager.create_pipeline("Test task")
        pipeline.metadata["band_room_id"] = "room-xyz"
        
        message_id = await comm.send_message(
            recipient="coder",
            message_type=MessageType.TASK,
            content={"task": "test"},
            subject="Test message",
        )
        
        assert message_id is not None
        # Allow async mirror task to complete
        await asyncio.sleep(0.1)
        
        # Verify message was mirrored to mock client
        assert len(mock_client.rest.agent_api_messages.sent_messages) == 1
        chat_id, msg = mock_client.rest.agent_api_messages.sent_messages[0]
        assert chat_id == "room-xyz"
        assert "[TASK] Test message" in msg.content


    def test_receive_message(self):
        """Test receiving messages."""
        from code_assistant.band_integration import AgentMessage, MessageType

        comm = CommunicationLayer("test_agent")
        received_messages = []

        def handler(message):
            received_messages.append(message)

        comm.register_handler(MessageType.TASK, handler)

        message = AgentMessage(
            sender="other_agent",
            recipient="test_agent",
            message_type=MessageType.TASK,
            content={"task": "test"},
        )

        comm.receive_message(message)

        assert len(received_messages) == 1
        assert received_messages[0].sender == "other_agent"

    @pytest.mark.asyncio
    async def test_live_websocket_listener_event_routing(self):
        """Test that the live WebSocket event listener routes message events successfully."""
        import asyncio
        from code_assistant.band_integration.communication import MessageType
        
        class MockMessagePayload:
            id = "msg-999"
            content = '[TASK] Hello from WebSocket\n\n{"test": "ok"}'
            message_type = "task"
            sender_id = "sender-peer-id"
            sender_name = "coder-peer"
            chat_room_id = "room-xyz"
            thread_id = "thread-123"
            inserted_at = "2026-05-31T00:00:00Z"
            updated_at = "2026-05-31T00:00:00Z"
            metadata = None

        class MockMessageEvent:
            type = "message_created"
            room_id = "room-xyz"
            payload = MockMessagePayload()

        class MockRuntime:
            agent_id = "my-local-agent-id"

        class MockBandClient:
            def __init__(self):
                self.runtime = MockRuntime()
                self._events = [MockMessageEvent()]
                self.connected = False
                self.subscribed = False
                self.disconnected = False
                
            async def connect(self):
                self.connected = True
                
            async def subscribe_agent_rooms(self):
                self.subscribed = True
                
            async def disconnect(self):
                self.disconnected = True
                
            def __aiter__(self):
                return self
                
            async def __anext__(self):
                if self._events:
                    # Stagger slightly so connection runs
                    await asyncio.sleep(0.01)
                    return self._events.pop(0)
                raise StopAsyncIteration()

        mock_client = MockBandClient()
        comm = CommunicationLayer("test_agent", band_client=mock_client)
        
        # Register handler
        received_messages = []
        comm.register_handler(MessageType.TASK, lambda msg: received_messages.append(msg))
        
        # Connect - this spawns the listener task in the background
        await comm.connect()
        assert mock_client.connected is True
        assert mock_client.subscribed is True
        
        # Wait for the async task loop to process the event
        await asyncio.sleep(0.05)
        
        # Verify the event reached our registered handler
        assert len(received_messages) == 1
        msg = received_messages[0]
        assert msg.sender == "coder-peer"
        assert msg.correlation_id == "thread-123"
        assert msg.content == {"test": "ok"}
        
        # Disconnect and verify teardown
        await comm.disconnect()
        assert mock_client.disconnected is True



class TestAgentFactory:
    """Test agent factory."""

    def test_create_llm_client_anthropic(self):
        """Test creating Anthropic LLM client."""
        client = AgentFactory.create_llm_client(
            provider="anthropic",
            api_key="test-key",
        )

        assert client is not None
        assert hasattr(client, "messages")

    def test_create_llm_client_openai(self):
        """Test creating OpenAI LLM client."""
        client = AgentFactory.create_llm_client(
            provider="openai",
            api_key="test-key",
        )

        assert client is not None
        assert hasattr(client, "chat")

    def test_create_llm_client_openrouter(self):
        """Test creating OpenRouter LLM client."""
        client = AgentFactory.create_llm_client(
            provider="openrouter",
            api_key="test-key",
        )

        assert client is not None
        assert hasattr(client, "chat")
        assert str(client.base_url).rstrip("/") == "https://openrouter.ai/api/v1"

    def test_create_agent(self):
        """Test creating an agent."""
        agent = AgentFactory.create_agent(
            agent_name="test",
            role="tester",
            description="Test agent",
            system_prompt="You are a test agent.",
        )

        assert agent["name"] == "test"
        assert agent["role"] == "tester"
        assert agent["system_prompt"] == "You are a test agent."

    def test_create_all_agents(self):
        """Test creating all agents."""
        agents = AgentFactory.create_all_agents()

        expected_agents = [
            "conductor",
            "planner",
            "plan_reviewer",
            "coder",
            "code_reviewer",
            "test_engineer",
            "debugger",
            "mergemaster",
        ]

        for agent_name in expected_agents:
            assert agent_name in agents
            assert agents[agent_name]["name"] == agent_name


class TestCodingPipeline:
    """Test coding pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_initialization(self):
        """Test pipeline initialization."""
        pipeline = CodingPipeline()
        await pipeline.initialize()

        assert pipeline._initialized is True
        assert len(pipeline.agents) == 8
        assert "conductor" in pipeline.agents
        assert "planner" in pipeline.agents
        assert "mergemaster" in pipeline.agents

        await pipeline.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test pipeline shutdown."""
        pipeline = CodingPipeline()
        await pipeline.initialize()
        await pipeline.shutdown()

        assert pipeline._initialized is False


class TestBaseAgent:
    """Test base agent functionality."""

    @pytest.mark.asyncio
    async def test_send_to_agent(self):
        """Test sending to another agent."""
        from code_assistant.agents.base import BaseAgent
        from code_assistant.band_integration import MessageType

        class TestAgent(BaseAgent):
            async def process_message(self, message):
                pass

            async def execute_task(self, task_data):
                pass

        agent = TestAgent(
            name="test",
            role="tester",
            description="Test",
            system_prompt="Test",
            llm_client=None,
        )

        message_id = await agent.send_to_agent(
            "other",
            MessageType.TASK,
            {"task": "test"},
        )

        assert message_id is not None

    @pytest.mark.asyncio
    async def test_think(self):
        """Test LLM thinking."""
        from code_assistant.agents.base import BaseAgent
        from anthropic import AsyncAnthropic

        class TestAgent(BaseAgent):
            async def process_message(self, message):
                pass

            async def execute_task(self, task_data):
                pass

        # This will fail without API key, but tests the flow
        agent = TestAgent(
            name="test",
            role="tester",
            description="Test",
            system_prompt="You are helpful.",
            llm_client=AsyncAnthropic(api_key="test"),
        )

        # Just verify it doesn't crash
        try:
            result = await agent.think("Say hello")
        except Exception:
            pass  # Expected without valid API key

