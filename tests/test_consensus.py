"""Tests for the consensus mechanism."""

from __future__ import annotations

import time

import pytest

from src.agents.coder import CoderAgent
from src.agents.planner import PlannerAgent
from src.agents.researcher import ResearcherAgent
from src.consensus import (
    ConsensusMechanism,
    ConsensusState,
    Vote,
    VoteValue,
)


class TestConsensusMechanism:
    """Test suite for the ConsensusMechanism."""

    def test_create_mechanism(self) -> None:
        """Test creating a consensus mechanism."""
        cm = ConsensusMechanism()
        assert cm.active_count == 0
        assert cm.metrics["initiated"] == 0

    def test_initiate_consensus(self) -> None:
        """Test initiating a consensus process."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1")]

        result = cm.initiate(
            topic="Test topic",
            participants=agents,
            strategy="simple_majority",
        )
        assert result.consensus_id is not None
        assert result.state == ConsensusState.VOTING
        assert result.topic == "Test topic"
        assert cm.active_count == 1

    def test_cast_vote(self) -> None:
        """Test casting a vote."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1")]

        result = cm.initiate("Test", agents, "simple_majority")
        vote_result = cm.cast_vote(
            result.consensus_id,
            "R1",
            VoteValue.YES,
            "Looks good",
        )
        assert vote_result is True

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.total_votes == 1
        assert updated.yes_votes == 1

    def test_consensus_achieved_simple_majority(self) -> None:
        """Test simple majority consensus."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1"), PlannerAgent("P1")]

        result = cm.initiate("Test", agents, "simple_majority", min_votes=2)

        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "C1", VoteValue.YES)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.state == ConsensusState.CONSENSUS_ACHIEVED
        assert updated.winner == "yes"
        assert updated.agreement_ratio == 1.0

    def test_consensus_not_reached(self) -> None:
        """Test when consensus is not reached."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1")]

        result = cm.initiate("Test", agents, "unanimous", min_votes=2)
        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "C1", VoteValue.NO)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.state != ConsensusState.CONSENSUS_ACHIEVED

    def test_super_majority(self) -> None:
        """Test super majority strategy."""
        cm = ConsensusMechanism()
        agents = [
            ResearcherAgent("R1"),
            CoderAgent("C1"),
            PlannerAgent("P1"),
        ]

        result = cm.initiate("Test", agents, "super_majority", min_votes=3)

        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "C1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "P1", VoteValue.YES)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.state == ConsensusState.CONSENSUS_ACHIEVED
        assert updated.agreement_ratio == 1.0

    def test_unanimous_consensus(self) -> None:
        """Test unanimous consensus."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1")]

        result = cm.initiate("Test", agents, "unanimous", min_votes=2)

        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "C1", VoteValue.YES)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.state == ConsensusState.CONSENSUS_ACHIEVED

    def test_threshold_strategy(self) -> None:
        """Test threshold-based consensus."""
        cm = ConsensusMechanism()
        agents = [
            ResearcherAgent("R1"),
            CoderAgent("C1"),
            PlannerAgent("P1"),
        ]

        result = cm.initiate(
            "Test",
            agents,
            "threshold",
            min_votes=2,
            metadata={"yes_threshold": 2},
        )

        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "C1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "P1", VoteValue.NO)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.state == ConsensusState.CONSENSUS_ACHIEVED
        assert updated.yes_votes == 2

    def test_vote_with_abstain(self) -> None:
        """Test that abstain votes don't count toward consensus."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1")]

        result = cm.initiate("Test", agents, "simple_majority", min_votes=2)

        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)
        cm.cast_vote(result.consensus_id, "C1", VoteValue.ABSTAIN)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.yes_votes == 1
        assert updated.no_votes == 0
        assert updated.abstain_votes == 1
        # With only 1 non-abstain vote, ratio should be 1.0
        assert updated.agreement_ratio == 1.0

    def test_vote_not_found_consensus(self) -> None:
        """Test casting vote for nonexistent consensus."""
        cm = ConsensusMechanism()
        result = cm.cast_vote("nonexistent", "R1", VoteValue.YES)
        assert result is False

    def test_finalize_consensus(self) -> None:
        """Test manually finalizing consensus."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1"), CoderAgent("C1")]

        result = cm.initiate("Test", agents, "simple_majority")
        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)

        finalized = cm.finalize(result.consensus_id)
        assert finalized is not None
        assert finalized.state == ConsensusState.CONSENSUS_ACHIEVED

    def test_finalize_empty(self) -> None:
        """Test finalizing with no votes."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority")
        finalized = cm.finalize(result.consensus_id)
        assert finalized is not None
        assert finalized.state == ConsensusState.FAILED

    def test_timeout_consensus(self) -> None:
        """Test consensus timeout."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority")
        timed = cm.timeout(result.consensus_id)
        assert timed is not None
        assert timed.state == ConsensusState.TIMED_OUT

    def test_collect_vote(self) -> None:
        """Test the high-level collect_vote method."""
        cm = ConsensusMechanism()
        agent = ResearcherAgent("R1")
        result = cm.initiate("Test", [agent], "simple_majority")

        vote_result = cm.collect_vote(
            result.consensus_id,
            agent,
            VoteValue.YES,
            "Approved",
        )
        assert vote_result is True

    def test_cleanup(self) -> None:
        """Test cleaning up completed consensus entries."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test1", agents, "simple_majority")
        cm.finalize(result.consensus_id)

        assert cm.active_count == 1
        cm.cleanup()
        assert cm.active_count == 0

    def test_cleanup_specific(self) -> None:
        """Test cleaning up a specific consensus."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority")
        cm.cleanup(result.consensus_id)
        assert cm.active_count == 0

    def test_vote_to_dict(self) -> None:
        """Test vote serialization."""
        vote = Vote(
            agent_id="R1",
            vote=VoteValue.YES,
            justification="Looks good",
        )
        d = vote.to_dict()
        assert d["agent_id"] == "R1"
        assert d["vote"] == "yes"
        assert d["justification"] == "Looks good"

    def test_get_active_consensus(self) -> None:
        """Test getting active consensus processes."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority")
        active = cm.get_active_consensus()
        assert len(active) == 1
        assert active[0].consensus_id == result.consensus_id

    def test_metrics_updated(self) -> None:
        """Test that metrics are tracked."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority", min_votes=1)
        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)

        metrics = cm.metrics
        assert metrics["initiated"] == 1
        assert metrics["completed"] == 1

    def test_consensus_result_to_dict(self) -> None:
        """Test consensus result serialization."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority")
        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        d = updated.to_dict()
        assert d["consensus_id"] == result.consensus_id
        assert d["topic"] == "Test"
        assert "votes" in d
        assert "duration_seconds" in d

    def test_duration_property(self) -> None:
        """Test the duration property of consensus result."""
        cm = ConsensusMechanism()
        agents = [ResearcherAgent("R1")]

        result = cm.initiate("Test", agents, "simple_majority")
        time.sleep(0.01)
        cm.cast_vote(result.consensus_id, "R1", VoteValue.YES)

        updated = cm.get_result(result.consensus_id)
        assert updated is not None
        assert updated.duration_seconds >= 0.01
