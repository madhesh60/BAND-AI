"""BAND communication layer for agent coordination."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

# Thenvoi SDK imports
try:
    from thenvoi import ThenvoiLink
    from thenvoi.client.rest import (
        ChatMessageRequest,
        ChatMessageRequestMentionsItem,
        MemoryCreateRequest,
    )
except ImportError:
    ThenvoiLink = None
    ChatMessageRequest = None
    ChatMessageRequestMentionsItem = None
    MemoryCreateRequest = None


class MessageType(str, Enum):
    """Types of messages between agents."""

    TASK = "task"
    RESPONSE = "response"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    APPROVAL = "approval"
    REJECTION = "rejection"
    HANDOVER = "handover"
    HEARTBEAT = "heartbeat"


class Priority(str, Enum):
    """Message priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentMessage:
    """Message structure for agent communication."""

    id: str = field(default_factory=lambda: str(uuid4()))
    sender: str = ""
    recipient: str = ""
    message_type: MessageType = MessageType.TASK
    priority: Priority = Priority.NORMAL
    subject: str = ""
    content: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_id: Optional[str] = None
    references: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "subject": self.subject,
            "content": self.content,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "references": self.references,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        """Create message from dictionary."""
        return cls(
            id=data.get("id", str(uuid4())),
            sender=data.get("sender", ""),
            recipient=data.get("recipient", ""),
            message_type=MessageType(data.get("message_type", "task")),
            priority=Priority(data.get("priority", "normal")),
            subject=data.get("subject", ""),
            content=data.get("content", {}),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            correlation_id=data.get("correlation_id"),
            references=data.get("references", []),
        )


class LocalMessageBus:
    """Thread-safe asynchronous local message router for agents."""

    _agents: dict = {}
    _lock = asyncio.Lock()

    @classmethod
    def register_agent(cls, name: str, agent: Any) -> None:
        cls._agents[name] = agent
        logger.info(f"Registered agent '{name}' on local message bus")

    @classmethod
    def unregister_agent(cls, name: str) -> None:
        cls._agents.pop(name, None)
        logger.info(f"Unregistered agent '{name}' from local message bus")

    @classmethod
    async def post_message(cls, message: AgentMessage) -> None:
        recipient = message.recipient
        if recipient in cls._agents:
            agent = cls._agents[recipient]
            # Deliver in a non-blocking background task
            asyncio.create_task(cls._deliver(agent, message))
        else:
            logger.warning(
                f"LocalMessageBus: Recipient '{recipient}' not registered (message: {message.subject})"
            )

    @classmethod
    async def _deliver(cls, agent: Any, message: AgentMessage) -> None:
        try:
            if hasattr(agent, "communication"):
                agent.communication.receive_message(message)
            else:
                agent.receive_message(message)
        except Exception as e:
            logger.error(f"Failed to deliver message to agent '{agent.name}': {e}")


class CommunicationLayer:
    """Handles communication between agents via BAND.
    
    If credentials (BAND_API_KEY) are set in the environment, it dynamically 
    initializes a connection via the thenvoi SDK (ThenvoiLink) to mirror 
    messages and manage chat rooms/memories directly on the Band.ai platform.
    If credentials are not found, it gracefully falls back to LocalMessageBus.
    """

    def __init__(self, agent_name: str, band_client: Optional[Any] = None):
        import os
        self.agent_name = agent_name
        self.band_client = band_client
        self._message_handlers: dict = {}
        self._pending_messages: list = []
        self._awaiting_response: dict = {}
        self._listener_task: Optional[asyncio.Task] = None
        
        # Dynamic SDK Client Initialization:
        # If no client is passed explicitly but we have real BAND credentials in the env,
        # we dynamically spin up a ThenvoiLink for this specific agent.
        if not self.band_client and ThenvoiLink is not None:
            api_key = os.getenv("BAND_API_KEY", "")
            is_placeholder = not api_key or "your" in api_key.lower() or api_key == "test-key"
            
            if not is_placeholder:
                from code_assistant.utils.config import config
                agent_cfg = config.get_agent_config(agent_name)
                if agent_cfg and agent_cfg.agent_id:
                    agent_id = agent_cfg.agent_id
                    is_real_id = agent_id and "{" not in agent_id
                    
                    if is_real_id:
                        band_cfg = config.config.band
                        try:
                            logger.info(f"[{self.agent_name}] Dynamically initializing ThenvoiLink client (agent_id={agent_id})")
                            self.band_client = ThenvoiLink(
                                agent_id=agent_id,
                                api_key=api_key,
                                ws_url=band_cfg.ws_url,
                                rest_url=band_cfg.rest_url,
                            )
                        except Exception as e:
                            logger.error(f"[{self.agent_name}] Failed to initialize ThenvoiLink: {e}")
                            
        logger.info(f"Communication layer initialized for agent: {agent_name}")

    def register_handler(
        self,
        message_type: MessageType,
        handler: Callable,
    ) -> None:
        """Register a handler for a specific message type."""
        if message_type not in self._message_handlers:
            self._message_handlers[message_type] = []
        self._message_handlers[message_type].append(handler)
        logger.debug(f"Registered handler for {message_type.value} on {self.agent_name}")

    async def _get_or_create_room(self) -> Optional[str]:
        """Retrieve the current pipeline's platform chatroom ID, creating it if missing."""
        if not self.band_client:
            return None
            
        from code_assistant.band_integration.state_manager import StateManager
        state_manager = StateManager()
        if not state_manager._states:
            return None
            
        # Get the latest active pipeline
        latest_id = max(state_manager._states.keys(), key=lambda k: state_manager._states[k].updated_at)
        pipeline = state_manager.get_pipeline(latest_id)
        if not pipeline:
            return None
            
        room_id = pipeline.metadata.get("band_room_id")
        if room_id:
            return room_id
            
        # Dynamically create room on the platform
        try:
            from thenvoi.client.rest import ChatRoomRequest
            logger.info(f"[{self.agent_name}] Dynamic Chatroom creation on Thenvoi for pipeline {pipeline.pipeline_id}")
            response = await self.band_client.rest.agent_api_chats.create_agent_chat(
                chat=ChatRoomRequest(task_id=pipeline.pipeline_id)
            )
            if response and response.data:
                room_id = response.data.id
                pipeline.metadata["band_room_id"] = room_id
                state_manager.save_state()
                logger.info(f"[{self.agent_name}] Created platform chatroom ID: {room_id}")
                return room_id
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to create platform chatroom: {e}")
            
        return None

    async def send_message(
        self,
        recipient: str,
        message_type: MessageType,
        content: dict,
        subject: str = "",
        priority: Priority = Priority.NORMAL,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Send a message to another agent.
        
        Posts the message to the local in-process LocalMessageBus (for pipeline execution)
        and mirrors it to the shared Thenvoi room if credentials are valid.
        """
        message = AgentMessage(
            sender=self.agent_name,
            recipient=recipient,
            message_type=message_type,
            priority=priority,
            subject=subject,
            content=content,
            correlation_id=correlation_id,
        )

        logger.info(
            f"[{self.agent_name}] Sending {message_type.value} to {recipient}: {subject}"
        )

        # 1. Asynchronously post to Thenvoi Platform (Mirroring Mode)
        if self.band_client and ChatMessageRequest is not None:
            # Run room lookup and dispatch in a safe task so connection errors don't disrupt local pipeline
            async def mirror_task():
                try:
                    room_id = await self._get_or_create_room()
                    if room_id:
                        # Construct mentioning structure
                        from code_assistant.utils.config import config
                        recipient_cfg = config.get_agent_config(recipient)
                        mentions = []
                        if recipient_cfg and recipient_cfg.agent_id:
                            # Mentions are required by the Thenvoi message API
                            handle = recipient_cfg.role or recipient
                            mentions.append(ChatMessageRequestMentionsItem(
                                id=recipient_cfg.agent_id,
                                handle=handle
                            ))
                        
                        # Serialize content dict nicely to display in the chatroom
                        formatted_content = f"[{message_type.value.upper()}] {subject}\n\n"
                        if isinstance(content, dict):
                            formatted_content += json.dumps(content, indent=2)
                        else:
                            formatted_content += str(content)
                            
                        await self.band_client.rest.agent_api_messages.create_agent_chat_message(
                            chat_id=room_id,
                            message=ChatMessageRequest(
                                content=formatted_content,
                                mentions=mentions
                            )
                        )
                        logger.info(f"[{self.agent_name}] Message mirrored to Thenvoi room {room_id}")
                except Exception as e:
                    logger.warning(f"[{self.agent_name}] Failed to mirror message to Thenvoi: {e}")
            
            asyncio.create_task(mirror_task())

        # 2. Local fallback routing (always run to ensure pipeline runs fast and offline-ready)
        self._pending_messages.append(message)
        await LocalMessageBus.post_message(message)

        return message.id

    async def request_response(
        self,
        recipient: str,
        message_type: MessageType,
        content: dict,
        timeout: float = 30.0,
    ) -> Optional[AgentMessage]:
        """Send a message and wait for a response."""
        correlation_id = str(uuid4())
        message_id = await self.send_message(
            recipient=recipient,
            message_type=message_type,
            content=content,
            correlation_id=correlation_id,
        )

        future = asyncio.Future()
        self._awaiting_response[correlation_id] = future

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response to {message_id}")
            self._awaiting_response.pop(correlation_id, None)
            return None

    def receive_message(self, message: AgentMessage) -> None:
        """Process an incoming message."""
        logger.info(
            f"[{self.agent_name}] Received {message.message_type.value} from {message.sender}"
        )

        # Handle correlation responses
        if message.correlation_id and message.correlation_id in self._awaiting_response:
            future = self._awaiting_response.pop(message.correlation_id)
            if not future.done():
                future.set_result(message)
            return

        # Dispatch to registered handlers
        handlers = self._message_handlers.get(message.message_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(message))
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"Handler error: {e}")

    async def broadcast(
        self,
        message_type: MessageType,
        content: dict,
        recipients: list,
        subject: str = "",
    ) -> list:
        """Broadcast a message to multiple recipients."""
        message_ids = []
        for recipient in recipients:
            msg_id = await self.send_message(
                recipient=recipient,
                message_type=message_type,
                content=content,
                subject=subject,
            )
            message_ids.append(msg_id)
        return message_ids

    def get_pending_messages(self) -> list:
        """Get all pending messages."""
        return self._pending_messages.copy()

    def clear_pending(self) -> None:
        """Clear pending messages."""
        self._pending_messages.clear()

    async def store_platform_memory(
        self,
        content: str,
        thought: str,
        system: str = "long_term",
        type: str = "episodic",
        segment: str = "agent",
    ) -> Optional[Any]:
        """Store long-term memory on the Thenvoi/BAND platform."""
        if not self.band_client or MemoryCreateRequest is None:
            logger.debug(f"[{self.agent_name}] Skipping store_platform_memory (local/fallback mode)")
            return None
            
        try:
            logger.info(f"[{self.agent_name}] Storing platform memory: type={type}, thought={thought}")
            response = await self.band_client.rest.agent_api_memories.create_agent_memory(
                memory=MemoryCreateRequest(
                    content=content,
                    system=system,
                    type=type,
                    segment=segment,
                    thought=thought,
                    scope="subject",
                    subject_id=self.band_client.runtime.agent_id,
                )
            )
            if response and response.data:
                return response.data
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to store platform memory: {e}")
        return None

    async def list_platform_memories(
        self,
        content_query: Optional[str] = None,
        system: Optional[str] = None,
        type: Optional[str] = None,
    ) -> list:
        """List long-term memories retrieved from the Thenvoi/BAND platform."""
        if not self.band_client:
            logger.debug(f"[{self.agent_name}] Skipping list_platform_memories (local/fallback mode)")
            return []
            
        try:
            logger.info(f"[{self.agent_name}] Listing platform memories for content_query='{content_query}'")
            response = await self.band_client.rest.agent_api_memories.list_agent_memories(
                content_query=content_query,
                system=system,
                type=type,
                page_size=50,
            )
            if response and response.data:
                return response.data
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to list platform memories: {e}")
        return []

    async def connect(self) -> None:
        """Connect to the Thenvoi platform and start listening for events in the background."""
        if not self.band_client:
            return
            
        try:
            logger.info(f"[{self.agent_name}] Connecting to Thenvoi WebSocket gateway...")
            await self.band_client.connect()
            # Subscribe to agent's rooms/topics so we receive messages
            await self.band_client.subscribe_agent_rooms()
            
            # Start background asyncio task to consume WebSocket events
            self._listener_task = asyncio.create_task(self._listen_to_events())
            logger.info(f"[{self.agent_name}] WebSocket connection established. Listening for events.")
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to connect to Thenvoi WebSocket: {e}")

    async def disconnect(self) -> None:
        """Disconnect from the Thenvoi platform and clean up listeners."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
            
        if self.band_client:
            try:
                await self.band_client.disconnect()
                logger.info(f"[{self.agent_name}] Disconnected from Thenvoi platform")
            except Exception as e:
                logger.error(f"[{self.agent_name}] Error during Thenvoi disconnect: {e}")

    async def _listen_to_events(self) -> None:
        """Asynchronous loop consuming events from the Thenvoi link event queue."""
        try:
            # ThenvoiLink implements async iterator yielding PlatformEvent models
            async for event in self.band_client:
                if event.type == "message_created" and event.payload:
                    payload = event.payload
                    # Ignore messages that this agent sent
                    if payload.sender_id == self.band_client.runtime.agent_id:
                        continue
                        
                    logger.info(f"[{self.agent_name}] WebSocket received platform message from {payload.sender_name or payload.sender_id}: {payload.content[:50]}...")
                    
                    try:
                        # Extract the original payload content dict if it is serialized as JSON
                        content_dict = {}
                        msg_body = payload.content
                        if "\n\n" in msg_body:
                            parts = msg_body.split("\n\n", 1)
                            msg_body = parts[1]
                        try:
                            content_dict = json.loads(msg_body)
                        except Exception:
                            content_dict = {"text": payload.content}
                            
                        # Reconstruct the AgentMessage and route to the local handlers
                        msg = AgentMessage(
                            id=payload.id,
                            sender=payload.sender_name or "platform",
                            recipient=self.agent_name,
                            message_type=MessageType.TASK,
                            content=content_dict,
                            correlation_id=payload.thread_id,
                        )
                        self.receive_message(msg)
                    except Exception as e:
                        logger.error(f"[{self.agent_name}] Error routing platform message: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.agent_name}] WebSocket event listener loop encountered an error: {e}")