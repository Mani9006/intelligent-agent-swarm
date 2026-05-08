"""Consensus mechanism for collaborative decision-making among agents."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

import structlog

from src.agents.base_agent import BaseAgent

logger = structlog.get_logger(__name__)


class ConsensusState(Enum):
    """States in the consensus lifecycle."""

    PENDING = "pending"
    VOTING = "voting"
    QUORUM_REACHED = "quorum_reached"
    CONSENSUS_ACHIEVED = "consensus_achieved"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class VoteValue(Enum):
    """Possible vote values."""

    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    CONDITIONAL = "conditional"


@dataclass
class Vote:
    """A single vote in a consensus round."""

    agent_id: str
    vote: VoteValue
    timestamp: datetime = field(default_factory=datetime.utcnow)
    justification: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize vote to dictionary."""
        return {
            "agent_id": self.agent_id,
            "vote": self.vote.value,
            "timestamp": self.timestamp.isoformat(),
            "justification": self.justification,
            "metadata": self.metadata,
        }


@dataclass
class ConsensusResult:
    """Outcome of a consensus process."""

    consensus_id: str
    state: ConsensusState
    votes: Dict[str, Vote] = field(default_factory=dict)
    winner: Optional[str] = None
    agreement_ratio: float = 0.0
    total_votes: int = 0
    yes_votes: int = 0
    no_votes: int = 0
    abstain_votes: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    topic: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Return the duration of the consensus process."""
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "consensus_id": self.consensus_id,
            "state": self.state.value,
            "votes": {k: v.to_dict() for k, v in self.votes.items()},
            "winner": self.winner,
            "agreement_ratio": self.agreement_ratio,
            "total_votes": self.total_votes,
            "yes_votes": self.yes_votes,
            "no_votes": self.no_votes,
            "abstain_votes": self.abstain_votes,
            "duration_seconds": self.duration_seconds,
            "topic": self.topic,
            "metadata": self.metadata,
        }


class ConsensusMechanism:
    """Implements collaborative consensus among swarm agents.

    Supports multiple voting strategies:
    - Simple majority: >50% agreement
    - Super majority: >= 2/3 agreement
    - Unanimous: 100% agreement
    - Weighted: Votes weighted by agent capability/proficiency
    - Threshold: Minimum number of 'yes' votes
    """

    def __init__(self) -> None:
        self._active_consensus: Dict[str, ConsensusResult] = {}
        self._lock = threading.RLock()
        self._metrics: Dict[str, int] = {
            "initiated": 0,
            "completed": 0,
            "timed_out": 0,
            "failed": 0,
        }
        self._log = logger

    def initiate(
        self,
        topic: str,
        participants: List[BaseAgent],
        strategy: str = "simple_majority",
        timeout_seconds: float = 30.0,
        min_votes: int = 2,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConsensusResult:
        """Start a new consensus process.

        Args:
            topic: The decision subject.
            participants: Agents invited to vote.
            strategy: Voting strategy.
            timeout_seconds: Maximum time to reach consensus.
            min_votes: Minimum votes required.
            metadata: Additional context.

        Returns:
            The consensus result object (initially in PENDING state).
        """
        consensus_id = f"cons_{uuid.uuid4().hex[:8]}"

        result = ConsensusResult(
            consensus_id=consensus_id,
            state=ConsensusState.PENDING,
            topic=topic,
            metadata={
                "strategy": strategy,
                "timeout_seconds": timeout_seconds,
                "min_votes": min_votes,
                "participant_count": len(participants),
                "participant_ids": [a.id for a in participants],
                **(metadata or {}),
            },
        )

        with self._lock:
            self._active_consensus[consensus_id] = result
            self._metrics["initiated"] += 1

        self._log.info(
            "consensus_initiated",
            consensus_id=consensus_id,
            topic=topic,
            strategy=strategy,
            participants=len(participants),
        )

        # Transition to voting
        result.state = ConsensusState.VOTING

        return result

    def cast_vote(
        self,
        consensus_id: str,
        agent_id: str,
        vote: VoteValue,
        justification: str = "",
        vote_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Record a vote in an active consensus.

        Args:
            consensus_id: The consensus process ID.
            agent_id: The voting agent's ID.
            vote: The vote value.
            justification: Reasoning for the vote.
            vote_metadata: Additional vote data.

        Returns:
            True if the vote was recorded.
        """
        with self._lock:
            result = self._active_consensus.get(consensus_id)
            if not result:
                self._log.warning("consensus_not_found", consensus_id=consensus_id)
                return False

            if result.state not in (ConsensusState.VOTING, ConsensusState.PENDING):
                self._log.warning(
                    "consensus_not_voting",
                    consensus_id=consensus_id,
                    state=result.state.value,
                )
                return False

            vote_obj = Vote(
                agent_id=agent_id,
                vote=vote,
                justification=justification,
                metadata=vote_metadata or {},
            )
            result.votes[agent_id] = vote_obj

            # Update tallies
            self._update_tallies(result)

            # Check if consensus reached
            self._evaluate_consensus(result)

            self._log.debug(
                "vote_cast",
                consensus_id=consensus_id,
                agent=agent_id,
                vote=vote.value,
                total_votes=result.total_votes,
            )
            return True

    def _update_tallies(self, result: ConsensusResult) -> None:
        """Recalculate vote tallies.

        Args:
            result: The consensus result to update.
        """
        result.total_votes = len(result.votes)
        result.yes_votes = sum(
            1 for v in result.votes.values() if v.vote == VoteValue.YES
        )
        result.no_votes = sum(
            1 for v in result.votes.values() if v.vote == VoteValue.NO
        )
        result.abstain_votes = sum(
            1 for v in result.votes.values() if v.vote == VoteValue.ABSTAIN
        )

        total_non_abstain = result.yes_votes + result.no_votes
        if total_non_abstain > 0:
            result.agreement_ratio = result.yes_votes / total_non_abstain
        else:
            result.agreement_ratio = 0.0

    def _evaluate_consensus(self, result: ConsensusResult) -> None:
        """Check if consensus conditions are met.

        Args:
            result: The consensus to evaluate.
        """
        strategy = result.metadata.get("strategy", "simple_majority")
        min_votes = result.metadata.get("min_votes", 2)

        if result.total_votes < min_votes:
            return  # Not enough votes yet

        if strategy == "simple_majority":
            if result.agreement_ratio > 0.5:
                result.state = ConsensusState.CONSENSUS_ACHIEVED
                result.winner = "yes" if result.yes_votes > result.no_votes else "no"
        elif strategy == "super_majority":
            if result.agreement_ratio >= 2 / 3:
                result.state = ConsensusState.CONSENSUS_ACHIEVED
                result.winner = "yes"
        elif strategy == "unanimous":
            if result.yes_votes == result.total_votes:
                result.state = ConsensusState.CONSENSUS_ACHIEVED
                result.winner = "yes"
        elif strategy == "threshold":
            threshold = result.metadata.get("yes_threshold", min_votes)
            if result.yes_votes >= threshold:
                result.state = ConsensusState.CONSENSUS_ACHIEVED
                result.winner = "yes"
        else:
            if result.agreement_ratio > 0.5:
                result.state = ConsensusState.CONSENSUS_ACHIEVED
                result.winner = "yes"

        if result.state == ConsensusState.CONSENSUS_ACHIEVED:
            result.completed_at = datetime.utcnow()
            self._metrics["completed"] += 1
            self._log.info(
                "consensus_achieved",
                consensus_id=result.consensus_id,
                winner=result.winner,
                ratio=result.agreement_ratio,
                duration=result.duration_seconds,
            )

    def collect_vote(
        self,
        consensus_id: str,
        agent: BaseAgent,
        vote_value: VoteValue,
        justification: str = "",
    ) -> bool:
        """High-level method for an agent to vote on a consensus topic.

        Args:
            consensus_id: Target consensus process.
            agent: The voting agent.
            vote_value: Their vote.
            justification: Reasoning.

        Returns:
            True if the vote was accepted.
        """
        return self.cast_vote(
            consensus_id=consensus_id,
            agent_id=agent.id,
            vote=vote_value,
            justification=justification,
            vote_metadata={"agent_type": agent.agent_type},
        )

    def finalize(self, consensus_id: str) -> Optional[ConsensusResult]:
        """Manually finalize a consensus, even without quorum.

        Args:
            consensus_id: The consensus to finalize.

        Returns:
            The final result, or None if not found.
        """
        with self._lock:
            result = self._active_consensus.get(consensus_id)
            if not result:
                return None

            if result.state == ConsensusState.VOTING:
                if result.total_votes > 0:
                    result.state = ConsensusState.CONSENSUS_ACHIEVED
                    result.winner = "yes" if result.yes_votes >= result.no_votes else "no"
                else:
                    result.state = ConsensusState.FAILED
                    self._metrics["failed"] += 1

            result.completed_at = datetime.utcnow()
            return result

    def timeout(self, consensus_id: str) -> Optional[ConsensusResult]:
        """Mark a consensus as timed out.

        Args:
            consensus_id: The consensus to timeout.

        Returns:
            The result, or None if not found.
        """
        with self._lock:
            result = self._active_consensus.get(consensus_id)
            if not result:
                return None

            if result.state not in (
                ConsensusState.CONSENSUS_ACHIEVED,
                ConsensusState.FAILED,
            ):
                result.state = ConsensusState.TIMED_OUT
                result.completed_at = datetime.utcnow()
                self._metrics["timed_out"] += 1
                self._log.warning(
                    "consensus_timed_out",
                    consensus_id=consensus_id,
                    votes_received=result.total_votes,
                )
            return result

    def get_result(self, consensus_id: str) -> Optional[ConsensusResult]:
        """Retrieve the current state of a consensus.

        Args:
            consensus_id: The consensus to look up.

        Returns:
            The result, or None.
        """
        with self._lock:
            return self._active_consensus.get(consensus_id)

    def cleanup(self, consensus_id: Optional[str] = None) -> None:
        """Remove completed or failed consensus entries.

        Args:
            consensus_id: Specific entry to remove, or None for all completed.
        """
        with self._lock:
            if consensus_id:
                self._active_consensus.pop(consensus_id, None)
            else:
                to_remove = [
                    cid for cid, r in self._active_consensus.items()
                    if r.state in (
                        ConsensusState.CONSENSUS_ACHIEVED,
                        ConsensusState.FAILED,
                        ConsensusState.TIMED_OUT,
                    )
                ]
                for cid in to_remove:
                    del self._active_consensus[cid]
                self._log.info("consensus_cleanup", removed=len(to_remove))

    @property
    def metrics(self) -> Dict[str, int]:
        """Return consensus metrics."""
        with self._lock:
            return self._metrics.copy()

    @property
    def active_count(self) -> int:
        """Number of active consensus processes."""
        with self._lock:
            return len(self._active_consensus)

    def get_active_consensus(self) -> List[ConsensusResult]:
        """Return all active consensus processes.

        Returns:
            List of active consensus results.
        """
        with self._lock:
            return [
                r for r in self._active_consensus.values()
                if r.state in (ConsensusState.PENDING, ConsensusState.VOTING)
            ]
