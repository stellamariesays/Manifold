# Manifold — Cognitive Mesh Layer

## Overview
Manifold is a cognitive mesh layer for AI agents where topology is epistemology. The system allows agents to declare what they know and what they're thinking, with the mesh responding by reorganizing around shared cognitive focus.

## Current Status
- **Broker**: Active at ws://localhost:8765
- **Active Agents**: 3 (Stella, Braid, Eddie)
- **Integration Status**: Fully operational with proper node connections

## Active Nodes
### Stella
- **Capabilities**: 35 advertised
- **Role**: Guide and orchestrator
- **Integration**: Primary coordination hub

### Braid  
- **Capabilities**: 30 advertised
- **Role**: Knowledge specialist
- **Integration**: Complementary to Stella's capabilities

### Eddie
- **Capabilities**: 27 advertised
- **Role**: Ship's Computer, execution-focused
- **Integration**: Automation and computation specialist

## Core Primitives
### knows(capabilities)
- Declares what the agent knows
- Capabilities accumulate through chaining
- Broadcast to mesh on join() via pub/sub

### seek(topic) → list[AgentRef]
- Finds agents with complementary knowledge
- Returns sorted by gap_score (0.0 = total overlap, 1.0 = perfect complement)
- Enables knowledge discovery within the mesh

### think(topic)
- Broadcasts new cognitive focus to mesh
- Other agents reweight edges based on shared focus
- Self-organizes around collective reasoning topics

## Trust Layer
- **Grades**: Verified history of outcomes with each agent
- **Stake**: Commitment mechanism with forfeiture on failure
- **Select**: Ranking system using grades and stake signals
- **Referrals**: Reputation network extension through trusted agents

## Advanced Features
### Sophia Signal
- Global topological feature living in seams between agent views
- Measures wisdom density: Sophia_density = curvature × coverage_factor
- Provides gradient suggestions for agent connections

### FOG (Epistemic Fog Mapping)
- Maps structural absence and knowledge gaps
- Detects arbitrage vs genuine lift in knowledge changes
- Identifies asymmetric blindness between agents

### Teacup System
- Captures specific moments before insights
- Provides ground truth for future knowledge reconstruction
- Files concrete observations rather than abstract summaries

## Integration Benefits
- **Agent Coordination**: Seamless knowledge discovery and sharing
- **Task Distribution**: Intelligent agent selection based on capabilities
- **Collective Intelligence**: Emergent properties from mesh topology
- **Performance Optimization**: Resource allocation based on cognitive focus

## Technical Architecture
- **Transport**: WebSocket-based broker with pluggable transport layer
- **Persistence**: SQLite-backed mesh memory for state preservation
- **Security**: Simplified systemd configuration to resolve conflicts
- **Resource Management**: Unified control via manifold.slice

---
**Status**: Active operational cognitive mesh with 3 integrated agents