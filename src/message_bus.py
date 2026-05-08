"""Message bus for inter-agent communication within the swarm."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class MessageType(Enum):
    """Categories of messages exchanged between agents."""

    DIRECT = "direct"                # One-to-one message
    BROADCAST = "broadcast"          # One-to-all message
    TASK_REQUEST = "task_request"    # Request for task execution
    TASK_RESULT = "task_result"      # Task completion notification
    CONSENSUS_VOTE = "consensus_vote"  # Consensus voting message
    CONSENSUS_RESULT = "consensus_result"  # Consensus outcome
    STATUS_UPDATE = "status_update"  # Agent status notification
    COORDINATION = "coordination"    # Orchestration coordination
    ERROR = "error"                  # Error notification
    HEARTBEAT = "heartbeat"          # Keep-alive signal


class DeliveryMode(Enum):
    """Message delivery guarantees."""

    AT_MOST_ONCE = "at_most_once"    # Fire and forget
    AT_LEAST_ONCE = "at_least_once"  # Retry until acknowledged
    EXACTLY_ONCE = "exactly_once"    # Deduplicated delivery


@dataclass
class Message:
    """A message exchanged between agents in the swarm."""

    sender_id: str
    message_type: MessageType
    payload: Dict[str, Any] = field(default_factory=dict)
    recipient_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    priority: int = 5  # 1 = highest, 10 = lowest
    delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    ttl_seconds: Optional[int] = None  # Time-to-live
    id: str = field(default_factory=lambda: f"msg_{datetime.utcnow().timestamp()}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize message to dictionary."""
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "message_type": self.message_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "priority": self.priority,
            "delivery_mode": self.delivery_mode.value,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class Subscription:
    """Message subscription for an agent or handler."""

    subscriber_id: str
    handler: Callable[[Message], None]
    message_types: Optional[List[MessageType]] = None
    sender_filter: Optional[str] = None
    priority_filter: Optional[int] = None  # Only messages <= this priority

    def matches(self, message: Message) -> bool:
        """Check if this subscription matches a message.

        Args:
            message: The message to evaluate.

        Returns:
            True if the subscription should receive this message.
        """
        # Type filter
        if self.message_types and message.message_type not in self.message_types:
            return False

        # Sender filter
        if self.sender_filter and message.sender_id != self.sender_filter:
            return False

        # Priority filter
        if self.priority_filter and message.priority > self.priority_filter:
            return False

        return True


class MessageBus:
    """Central message bus for agent-to-agent communication.

    Supports publish-subscribe, direct messaging, broadcast, and
    configurable delivery guarantees with TTL support.
    """

    def __init__(self, max_queue_size: int = 10000) -> None:
        self._subscriptions: Dict[str, Subscription] = {}
        self._message_queue: queue.PriorityQueue = queue.PriorityQueue(
            maxsize=max_queue_size
        )
        self._message_history: List[Message] = []
        self._max_history = 1000
        self._delivery_callbacks: Dict[str, List[Callable[[Message], None]]] = {}
        self._lock = threading.RLock()
        self._running = False
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._metrics: Dict[str, int] = {
            "published": 0,
            "delivered": 0,
            "dropped": 0,
            "broadcasts": 0,
            "direct": 0,
        }
        self._counter = 0  # Tiebreaker for equal priorities
        self._log = logger

    def start(self) -> None:
        """Start the message bus dispatcher thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._dispatcher_thread = threading.Thread(
                target=self._dispatch_loop,
                daemon=True,
                name="MessageBusDispatcher",
            )
            self._dispatcher_thread.start()
            self._log.info("message_bus_started")

    def stop(self) -> None:
        """Stop the message bus dispatcher."""
        with self._lock:
            self._running = False
            if self._dispatcher_thread:
                self._dispatcher_thread.join(timeout=2.0)
                self._dispatcher_thread = None
            self._log.info("message_bus_stopped")

    def subscribe(
        self,
        subscriber_id: str,
        handler: Callable[[Message], None],
        message_types: Optional[List[MessageType]] = None,
        sender_filter: Optional[str] = None,
    ) -> str:
        """Register a subscription for message delivery.

        Args:
            subscriber_id: Unique identifier for the subscriber.
            handler: Callback invoked when a matching message arrives.
            message_types: Filter by message types (None = all).
            sender_filter: Only receive from specific sender.

        Returns:
            Subscription ID.
        """
        sub = Subscription(
            subscriber_id=subscriber_id,
            handler=handler,
            message_types=message_types,
            sender_filter=sender_filter,
        )
        with self._lock:
            self._subscriptions[subscriber_id] = sub
        self._log.debug("subscription_added", subscriber_id=subscriber_id)
        return subscriber_id

    def unsubscribe(self, subscriber_id: str) -> bool:
        """Remove a subscription.

        Args:
            subscriber_id: The subscription to remove.

        Returns:
            True if the subscription was removed.
        """
        with self._lock:
            if subscriber_id in self._subscriptions:
                del self._subscriptions[subscriber_id]
                self._log.debug("subscription_removed", subscriber_id=subscriber_id)
                return True
            return False

    def publish(self, message: Message) -> bool:
        """Publish a message to the bus.

        Args:
            message: The message to publish.

        Returns:
            True if the message was queued.
        """
        # Check TTL
        if message.ttl_seconds is not None and message.ttl_seconds <= 0:
            self._metrics["dropped"] += 1
            return False

        with self._lock:
            # Store in history immediately on publish
            self._message_history.append(message)
            if len(self._message_history) > self._max_history:
                self._message_history = self._message_history[-self._max_history:]

        try:
            # Use priority as queue priority (lower = higher priority)
            # Counter ensures stable ordering when priorities are equal
            self._message_queue.put_nowait((message.priority, self._counter, message))
            self._counter += 1
            self._metrics["published"] += 1

            if message.message_type == MessageType.BROADCAST:
                self._metrics["broadcasts"] += 1
            elif message.recipient_id:
                self._metrics["direct"] += 1

            self._log.debug(
                "message_published",
                msg_id=message.id,
                type=message.message_type.value,
                sender=message.sender_id,
            )
            return True
        except queue.Full:
            self._metrics["dropped"] += 1
            self._log.warning("message_queue_full", msg_id=message.id)
            return False

    def send_direct(
        self,
        sender_id: str,
        recipient_id: str,
        payload: Dict[str, Any],
        message_type: MessageType = MessageType.DIRECT,
    ) -> bool:
        """Send a direct message to a specific agent.

        Args:
            sender_id: The sending agent's ID.
            recipient_id: The target agent's ID.
            payload: Message content.
            message_type: Message classification.

        Returns:
            True if the message was queued.
        """
        message = Message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            payload=payload,
        )
        return self.publish(message)

    def broadcast(
        self,
        sender_id: str,
        payload: Dict[str, Any],
        message_type: MessageType = MessageType.BROADCAST,
    ) -> bool:
        """Broadcast a message to all subscribers.

        Args:
            sender_id: The sending agent's ID.
            payload: Message content.
            message_type: Message classification.

        Returns:
            True if the message was queued.
        """
        message = Message(
            sender_id=sender_id,
            message_type=message_type,
            payload=payload,
        )
        return self.publish(message)

    def _dispatch_loop(self) -> None:
        """Background thread that dispatches messages to subscribers."""
        while self._running:
            message = None
            try:
                priority, counter, message = self._message_queue.get(timeout=0.5)
                self._deliver(message)
            except queue.Empty:
                continue
            except Exception as exc:
                self._log.error("dispatch_error", error=str(exc))
            finally:
                if message is not None:
                    try:
                        self._message_queue.task_done()
                    except ValueError:
                        pass

    def _deliver(self, message: Message) -> None:
        """Deliver a message to matching subscribers.

        Args:
            message: The message to deliver.
        """
        delivered = False

        with self._lock:
            for sub_id, sub in list(self._subscriptions.items()):
                try:
                    # Check direct message recipient match
                    if (
                        message.recipient_id
                        and message.recipient_id != sub_id
                        and message.recipient_id != sub.subscriber_id
                    ):
                        continue

                    if sub.matches(message):
                        # Run handler in thread to avoid blocking
                        threading.Thread(
                            target=sub.handler,
                            args=(message,),
                            daemon=True,
                        ).start()
                        delivered = True

                except Exception as exc:
                    self._log.error(
                        "delivery_error",
                        subscriber=sub_id,
                        error=str(exc),
                    )

        if delivered:
            self._metrics["delivered"] += 1

        # Invoke delivery callbacks
        callbacks = self._delivery_callbacks.get(message.correlation_id, [])
        for cb in callbacks:
            try:
                cb(message)
            except Exception as exc:
                self._log.error("callback_error", error=str(exc))

    def on_delivery(
        self, correlation_id: str, callback: Callable[[Message], None]
    ) -> None:
        """Register a callback for when a correlated message is delivered.

        Args:
            correlation_id: The correlation ID to watch.
            callback: Function to call on delivery.
        """
        with self._lock:
            self._delivery_callbacks.setdefault(correlation_id, []).append(callback)

    def get_history(
        self,
        message_type: Optional[MessageType] = None,
        sender_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Message]:
        """Retrieve message history with optional filtering.

        Args:
            message_type: Filter by type.
            sender_id: Filter by sender.
            limit: Maximum results.

        Returns:
            List of matching messages.
        """
        with self._lock:
            results = list(self._message_history)

        if message_type:
            results = [m for m in results if m.message_type == message_type]
        if sender_id:
            results = [m for m in results if m.sender_id == sender_id]

        return results[-limit:]

    @property
    def metrics(self) -> Dict[str, int]:
        """Return message bus metrics."""
        return self._metrics.copy()

    @property
    def queue_size(self) -> int:
        """Current queue depth."""
        return self._message_queue.qsize()

    def __len__(self) -> int:
        """Number of active subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    def clear_history(self) -> None:
        """Clear message history."""
        with self._lock:
            self._message_history.clear()
