"""Tests for the message bus."""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from src.message_bus import Message, MessageBus, MessageType


class TestMessageBus:
    """Test suite for the MessageBus."""

    def test_create_bus(self) -> None:
        """Test creating a message bus."""
        bus = MessageBus()
        assert len(bus) == 0
        assert bus.queue_size == 0
        assert bus.metrics["published"] == 0

    def test_start_stop(self) -> None:
        """Test starting and stopping the bus."""
        bus = MessageBus()
        bus.start()
        assert bus._running is True
        bus.stop()
        assert bus._running is False

    def test_subscribe(self) -> None:
        """Test subscribing to messages."""
        bus = MessageBus()
        received: List[Message] = []

        def handler(msg: Message) -> None:
            received.append(msg)

        sub_id = bus.subscribe("sub_1", handler)
        assert len(bus) == 1
        assert sub_id == "sub_1"

    def test_unsubscribe(self) -> None:
        """Test unsubscribing."""
        bus = MessageBus()

        def handler(msg: Message) -> None:
            pass

        bus.subscribe("sub_1", handler)
        result = bus.unsubscribe("sub_1")
        assert result is True
        assert len(bus) == 0

    def test_publish(self) -> None:
        """Test publishing a message."""
        bus = MessageBus()
        msg = Message(
            sender_id="agent_1",
            message_type=MessageType.DIRECT,
            payload={"data": "test"},
            recipient_id="agent_2",
        )
        result = bus.publish(msg)
        assert result is True
        assert bus.metrics["published"] == 1

    def test_send_direct(self) -> None:
        """Test sending a direct message."""
        bus = MessageBus()
        result = bus.send_direct(
            sender_id="agent_1",
            recipient_id="agent_2",
            payload={"content": "hello"},
        )
        assert result is True
        assert bus.metrics["direct"] == 1

    def test_broadcast(self) -> None:
        """Test broadcasting a message."""
        bus = MessageBus()
        result = bus.broadcast(
            sender_id="agent_1",
            payload={"content": "hello all"},
        )
        assert result is True
        assert bus.metrics["broadcasts"] == 1

    def test_message_delivery(self) -> None:
        """Test that messages are delivered to subscribers."""
        bus = MessageBus()
        received: List[Message] = []

        def handler(msg: Message) -> None:
            received.append(msg)

        bus.subscribe("sub_1", handler, message_types=[MessageType.DIRECT])
        bus.start()

        bus.send_direct(
            sender_id="agent_1",
            recipient_id="sub_1",
            payload={"content": "test"},
        )

        time.sleep(0.3)  # Allow delivery
        assert len(received) == 1
        assert received[0].payload["content"] == "test"

        bus.stop()

    def test_message_filtering(self) -> None:
        """Test that messages are filtered by type."""
        bus = MessageBus()
        direct_received: List[Message] = []
        broadcast_received: List[Message] = []

        bus.subscribe(
            "sub_1",
            lambda m: direct_received.append(m),
            message_types=[MessageType.DIRECT],
        )
        bus.subscribe(
            "sub_2",
            lambda m: broadcast_received.append(m),
            message_types=[MessageType.BROADCAST],
        )
        bus.start()

        bus.send_direct("a1", "sub_1", {"t": "d"})
        bus.broadcast("a1", {"t": "b"})

        time.sleep(0.3)
        assert len(direct_received) == 1
        assert len(broadcast_received) == 1

        bus.stop()

    def test_sender_filter(self) -> None:
        """Test filtering by sender."""
        bus = MessageBus()
        received: List[Message] = []

        bus.subscribe(
            "sub_1",
            lambda m: received.append(m),
            sender_filter="agent_1",
        )
        bus.start()

        bus.send_direct("agent_1", "sub_1", {"t": "from1"})
        bus.send_direct("agent_2", "sub_1", {"t": "from2"})

        time.sleep(0.3)
        assert len(received) == 1
        assert received[0].payload["t"] == "from1"

        bus.stop()

    def test_message_to_dict(self) -> None:
        """Test message serialization."""
        msg = Message(
            sender_id="a1",
            message_type=MessageType.DIRECT,
            payload={"key": "value"},
            recipient_id="a2",
        )
        d = msg.to_dict()
        assert d["sender_id"] == "a1"
        assert d["message_type"] == "direct"
        assert d["payload"]["key"] == "value"

    def test_history(self) -> None:
        """Test message history retrieval."""
        bus = MessageBus()
        bus.publish(Message("a1", MessageType.DIRECT, {"n": 1}))
        bus.publish(Message("a1", MessageType.BROADCAST, {"n": 2}))
        bus.publish(Message("a2", MessageType.DIRECT, {"n": 3}))

        history = bus.get_history()
        assert len(history) == 3

        filtered = bus.get_history(message_type=MessageType.BROADCAST)
        assert len(filtered) == 1

        filtered = bus.get_history(sender_id="a1")
        assert len(filtered) == 2

    def test_clear_history(self) -> None:
        """Test clearing message history."""
        bus = MessageBus()
        bus.publish(Message("a1", MessageType.DIRECT, {}))
        bus.clear_history()
        history = bus.get_history()
        assert len(history) == 0

    def test_metrics(self) -> None:
        """Test metrics tracking."""
        bus = MessageBus()
        bus.publish(Message("a1", MessageType.DIRECT, {}))
        bus.publish(Message("a1", MessageType.BROADCAST, {}))

        metrics = bus.metrics
        assert metrics["published"] == 2
        assert metrics["broadcasts"] == 1

    def test_ttl_expired(self) -> None:
        """Test that expired messages are dropped."""
        bus = MessageBus()
        msg = Message(
            sender_id="a1",
            message_type=MessageType.DIRECT,
            payload={},
            ttl_seconds=0,
        )
        result = bus.publish(msg)
        assert result is False
        assert bus.metrics["dropped"] == 1
