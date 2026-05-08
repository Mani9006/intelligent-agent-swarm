# Agent Swarm Architecture

## Overview

The Intelligent Agent Swarm for Task Delegation is a Python-based multi-agent system that simulates intelligent task delegation among specialized agents. It provides a production-ready framework for capability-based agent matching, task decomposition, consensus-driven collaboration, and adaptive load balancing.

## System Architecture

```
                    +------------------+
                    |     CLI / API    |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Orchestrator    |  <-- Central controller
                    |  (orchestrator)  |
                    +--------+---------+
                             |
        +--------------------+--------------------+
        |                    |                    |
+-------v------+  +----------v----------+  +-----v--------+
| Task Queue   |  |   Agent Registry    |  | Message Bus  |
| (priority)   |  | (discovery/health)  |  | (pub/sub)    |
+-------+------+  +----------+----------+  +-----+--------+
        |                    |                    |
        |     +--------------+--------------+     |
        |     |              |              |     |
+-------v-----v----+  +------v-----+  +----v-----v------+
| Task Decomposer  |  |  Selector  |  |  Consensus      |
| (auto-split)     |  | (strategies)|  |  (voting)      |
+------------------+  +------------+  +-----------------+
                             |
                    +--------v---------+
                    |  Agents (xN)     |
                    | - Researcher     |
                    | - Coder          |
                    | - Reviewer       |
                    | - Writer         |
                    | - Planner        |
                    +------------------+
```

## Core Components

### 1. Orchestrator (`src/orchestrator.py`)

The central controller managing the swarm lifecycle:
- **Task Ingestion**: Accepts tasks via `submit_task()` or `submit_task_simple()`
- **Decomposition**: Automatically breaks complex tasks into subtasks
- **Selection**: Uses configurable strategies to match tasks to agents
- **Delegation**: Dispatches tasks with retry logic and backoff
- **Consensus**: Coordinates multi-agent voting for critical decisions
- **Monitoring**: Tracks performance and health metrics

### 2. Agent Registry (`src/agent_registry.py`)

Manages agent discovery and indexing:
- Thread-safe registration/deregistration
- Indexing by type and capability
- Health status aggregation
- Capability-based agent queries

### 3. Task Queue (`src/tasks/task_queue.py`)

Priority-based task scheduling:
- Min-heap priority queue (lower priority value = higher priority)
- FIFO within same priority level
- O(1) lookups by task ID
- Thread-safe operations

### 4. Agent Selector (`src/agent_selector.py`)

Configurable agent selection strategies:
- **best_match**: Highest capability score
- **least_loaded**: Lowest current load
- **weighted**: Combined capability-load score (default)
- **capability_then_load**: Capability priority with load tiebreaker
- **round_robin**: Even distribution
- **random**: Random selection

### 5. Task Decomposer (`src/task_decomposer.py`)

Automatic task breakdown:
- Pattern-based decomposition per task type
- Explicit subtask definitions via context
- Heuristic-based complexity detection
- Custom pattern registration

### 6. Message Bus (`src/message_bus.py`)

Inter-agent communication:
- Publish-subscribe pattern
- Direct and broadcast messaging
- Configurable delivery guarantees
- Message history and TTL support
- Async delivery via background thread

### 7. Consensus (`src/consensus.py`)

Collaborative decision-making:
- Simple majority voting
- Super majority (2/3) voting
- Unanimous voting
- Threshold-based voting
- Timeout handling

### 8. Performance Tracker (`src/performance.py`)

Metrics collection and analysis:
- Per-agent performance records
- Aggregate swarm metrics
- Bottleneck detection
- Load distribution analysis
- Top performer identification

### 9. Agent Types (`src/agents/`)

Five specialized agent implementations:

| Agent | Capabilities | Use Case |
|-------|-------------|----------|
| Researcher | Information retrieval, analysis, web search | Data gathering, trend analysis |
| Coder | Programming, debugging, testing, architecture | Feature implementation, code review |
| Reviewer | Quality assurance, compliance, fact-checking | Quality control, verification |
| Writer | Content creation, documentation, editing | Documentation, technical writing |
| Planner | Strategy, scheduling, resource management | Planning, roadmapping |

## Task Lifecycle

```
[Submitted] --> [Decomposer?] --> [Queued] --> [Selected] --> [Assigned]
                                                                  |
[Completed] <-- [Retried?] <-- [Executed] <-- [Consensus?] <------+
```

1. **Submitted**: Task enters the system via `orchestrator.submit_task()`
2. **Decomposer**: If auto-decompose is enabled and task is complex, break into subtasks
3. **Queued**: Task is placed in the priority queue
4. **Selected**: Agent selector finds the best match
5. **Consensus**: If required, agents vote on execution plan
6. **Assigned**: Task is assigned to the selected agent(s)
7. **Executed**: Agent performs the work
8. **Retried**: On failure, retry with exponential backoff
9. **Completed**: Result is recorded and callbacks fired

## Design Patterns

### Registry Pattern
The `AgentRegistry` uses the Registry pattern for agent discovery, allowing decoupled lookup of agents by capability or type.

### Strategy Pattern
The `AgentSelector` implements the Strategy pattern, allowing runtime selection of different agent selection algorithms.

### Observer Pattern
The `MessageBus` uses the Observer pattern for pub/sub messaging between agents.

### Template Method
The `BaseAgent` abstract class defines a template method (`execute_task`) that orchestrates the execution lifecycle, with `_perform_task` as the hook for subclasses.

### Singleton (per orchestrator)
Each `SwarmOrchestrator` instance owns a single instance of each subsystem (registry, queue, bus, etc.), ensuring consistency across the swarm.

## Thread Safety

All shared components use `threading.RLock` for thread safety:
- `AgentRegistry`: All operations are atomic
- `TaskQueue`: Priority queue with concurrent access
- `MessageBus`: Lock-protected subscription management
- `ConsensusMechanism`: Atomic vote recording
- `PerformanceTracker`: Atomic metrics updates

The `SwarmOrchestrator` uses `ThreadPoolExecutor` for concurrent task execution.

## Extensibility

### Adding New Agent Types

```python
from src.agents.base_agent import BaseAgent, AgentCapability

class DataScientistAgent(BaseAgent):
    def __init__(self, name):
        capabilities = [
            AgentCapability("machine_learning", 0.95),
            AgentCapability("data_analysis", 0.90),
        ]
        super().__init__(name, "data_scientist", capabilities)

    def _perform_task(self, task):
        # Implementation
        return TaskResult(...)
```

### Adding Custom Selection Strategies

```python
def my_custom_scorer(agent, task):
    return agent.capability_score("my_capability") * 0.8

selector = AgentSelector()
selector.select(candidates, task, strategy="best_match", custom_scorer=my_custom_scorer)
```

### Adding Decomposition Patterns

```python
decomposer.add_decomposition_pattern("my_type", [
    ("step_1", "First step description"),
    ("step_2", "Second step description"),
])
```

## Performance Considerations

- **Priority Queue**: O(log n) enqueue/dequeue operations
- **Agent Selection**: O(m * n) where m = candidates, n = capabilities
- **Message Bus**: Async delivery prevents blocking
- **Thread Pool**: Configurable max_workers for optimal throughput
- **Caching**: Agent metrics cached, updated on demand

## Future Enhancements

1. **Dynamic Agent Creation**: Auto-scale agents based on load
2. **Machine Learning**: ML-based agent selection optimization
3. **Persistence**: Save/restore swarm state
4. **Distributed Mode**: Multi-node swarm support
5. **Web Dashboard**: Real-time monitoring UI
6. **Plugin System**: Third-party agent and strategy plugins
7. **A2A Protocol**: Implement Google's Agent-to-Agent protocol
8. **Event Sourcing**: Full audit trail of all decisions
