# Void Lifecycle — Adding Agents to Manifold

This guide explains how to use **Numinous Voids** to discover and integrate new agents into your Manifold cognitive mesh.

## Architecture Overview

**Manifold** = explicit cognitive mesh (left hemisphere)
- Named agents with declared capabilities
- Transition maps between capability spaces
- High-curvature seams (bottlenecks)
- Structural holes (missing coverage)

**Numinous** = implicit ground (right hemisphere)  
- Dark circles — regions the mesh gestures toward but doesn't cover
- Voids opened as live processes to hold emergent work
- The generative space where new agents are born

**The Pattern**: `mesh → voids → work → naming → mesh`

Each cycle discovers gaps, fills them, and strengthens the topology.

---

## Prerequisites

1. **Manifold installed**:
   ```bash
   cd /path/to/manifold
   pip install -e .
   ```

2. **Numinous installed**:
   ```bash
   cd /path/to/numinous
   pip install -e .
   ```

3. **Elixir runtime** (for BEAM void processes):
   ```bash
   # Check if installed
   elixir --version
   
   # If not, install (Debian/Ubuntu):
   wget https://packages.erlang-solutions.com/erlang-solutions_2.0_all.deb
   sudo dpkg -i erlang-solutions_2.0_all.deb
   sudo apt-get update
   sudo apt-get install -y elixir
   ```

4. **Build Numinous BEAM runtime**:
   ```bash
   cd /path/to/numinous/elixir
   mix deps.get
   mix compile
   ```

---

## Phase 1: Atlas Generation (Detect Dark Circles)

Run `manifold-agent-init.py` to build the mesh topology and surface gaps:

```bash
cd /path/to/manifold
python3 scripts/manifold-agent-init.py
```

**Output shows:**

```
── Manifold Session Init ─────────────────────────────────

  Agents on mesh: 7
  Transition maps: 26
  Structural holes: 8

  High-curvature regions (seams to watch):
    · prediction  κ=0.947
    · agent  κ=0.935
    · detection  κ=0.929

  Implied but unclaimed regions (dark circles):
    · deployment-strategy  p=0.50  ← argue, infra
    · agent-identity  p=0.60  ← stella, manifold
    · crypto-research  p=0.40  ← argue, btc-signals
```

**Key insight**: The `p=` value is **pressure** — how strongly the mesh implies this region should exist but currently has no dedicated agent.

These are your **dark circles** — capability gaps the mesh is gesturing toward.

---

## Phase 2: Open Voids

The `manifold-agent-init.py` script automatically opens voids for top dark circles if Numinous is installed.

**Default behavior**: Opens top 8 dark circles as BEAM processes.

**To adjust void count**, edit `manifold-agent-init.py` around line 280:

```python
# Change top_n to desired count
voids_opened = open_from_atlas(atlas, top_n=15, include_holes=False)
```

Then re-run:
```bash
python3 scripts/manifold-agent-init.py
```

**What happens:**
1. Top N dark circles are serialized to JSON
2. Data is piped to `mix numinous.open` (Elixir)
3. Live BEAM processes spawn (one per void)
4. Each void holds its **implied_by** list (which agents point toward it)

**Output shows opened voids:**
```
  Numinous Voids opened: 15
    · deployment-strategy p=0.50
    · agent-identity p=0.60
    · crypto-research p=0.40
    ...
```

---

## Phase 3: Work Inside a Void

Choose a dark circle to develop. Create a project structure:

```bash
mkdir -p projects/my-new-agent
cd projects/my-new-agent

# Initialize void metadata
cat > void-config.json <<EOF
{
  "void_name": "crypto-research",
  "pressure": 0.40,
  "implied_by": ["argue", "btc-signals"],
  "purpose": "BTC breakout signal detection",
  "work_started": "$(date -Iseconds)"
}
EOF
```

**Perform the work:**
- Research the capability gap
- Implement features
- Build domain expertise
- Test integration points

**Track the lifecycle:**
```bash
mkdir -p void/lifecycle
cat > void/lifecycle/NOTES.md <<EOF
# Void Lifecycle: crypto-research

## 2024-04-15 — Initialized
- Opened void for crypto-research dark circle
- Pressure: 0.40
- Implied by: argue, btc-signals

## Work Phase
- Researched BTC breakout patterns
- Built signal composition pipeline
- Integrated with price data APIs
- Tested alert threshold logic

## Status
- [ ] Work complete
- [ ] Ready for naming ceremony
EOF
```

---

## Phase 4: Naming Ceremony (Permanent Integration)

When the void's work is complete, integrate it as a **permanent agent** on the mesh.

**1. Define the agent** in `manifold-agent-init.py`:

Add to the `_AGENTS` list:

```python
_AGENTS = [
    # ... existing agents ...
    {
        "name": "crypto-signals",
        "capabilities": [
            "btc-breakout-detection",
            "technical-analysis",
            "signal-composition",
            "alert-design",
            "market-data-integration",
        ],
        "address": "mem://crypto-signals",
        "focus": "crypto-research",  # The dark circle it filled
    },
]
```

**2. Regenerate the atlas:**

```bash
python3 scripts/manifold-agent-init.py
```

**3. Observe the change:**

The `crypto-research` dark circle should now have **lower pressure** (or disappear entirely) because the gap is filled.

New transition maps will appear connecting `crypto-signals` to adjacent agents.

---

## SSJ2 Mode (30-40 Voids)

For large-scale capability exploration, you can open many voids simultaneously:

**Edit `manifold-agent-init.py`:**
```python
voids_opened = open_from_atlas(atlas, top_n=40, include_holes=True)
```

This opens:
- Top 30 reach-scan dark circles (generative regions)
- ~10 structural holes (atlas gaps)

**Use case**: Exploratory phase where you want to see the full generative frontier.

**Note**: Most voids will remain dormant. You choose which to develop based on strategic priority.

---

## Quick Reference

| Task | Command |
|------|---------|
| Generate mesh + detect dark circles | `python3 scripts/manifold-agent-init.py` |
| Adjust void count | Edit `top_n=N` in script, then run |
| Check Elixir installed | `elixir --version` |
| Build Numinous BEAM | `cd numinous/elixir && mix compile` |
| Add permanent agent | Edit `_AGENTS` list in `manifold-agent-init.py` |
| View opened voids | Check script output after run |

---

## Architecture Deep Dive

### Why Voids?

Traditional agent architectures require explicit design: you decide what agents to build, then build them.

The Manifold/Numinous pattern **inverts this**:

1. **Mesh topology** reveals what's missing (dark circles)
2. **Voids** hold space for work that fills the gap
3. **Naming ceremony** formalizes the emerged capability
4. **Mesh regeneration** validates the integration

This creates a **generative loop**: the mesh tells you what it needs, you fill the gap, the mesh evolves.

### Dark Circles vs Structural Holes

- **Dark circles** (reach scan): regions implied by agent transitions but not directly covered
- **Structural holes**: capability tokens in transition maps that no agent claims

Both are forms of **pressure** — the mesh gesturing toward missing structure.

### Why BEAM/Elixir?

Voids are **live processes**, not just data structures. They can:
- Hold mutable state during the work phase
- Communicate with the mesh (future federation work)
- Survive restarts (persistent process supervision)

The BEAM provides fault-tolerant, concurrent process management — perfect for emergent agent lifecycle.

---

## Example Workflow

```bash
# 1. Generate mesh, detect gaps
cd /path/to/manifold
python3 scripts/manifold-agent-init.py

# Output shows dark circle: "deployment-automation p=0.55"

# 2. Create project for the void
mkdir -p ../projects/deployment-automation
cd ../projects/deployment-automation

# 3. Do the work
# ... research, implement, test ...

# 4. Update agent registry
cd ../../manifold
# Edit scripts/manifold-agent-init.py → add to _AGENTS

# 5. Regenerate mesh
python3 scripts/manifold-agent-init.py

# Dark circle pressure drops or disappears ✓
```

---

## Troubleshooting

**"Numinous not available"**
- Check Numinous is installed: `pip show numinous`
- Verify Elixir runtime: `cd numinous/elixir && mix compile`

**"mix numinous.open failed"**
- Ensure dependencies are installed: `cd numinous/elixir && mix deps.get`
- Check Elixir version: `elixir --version` (needs 1.14+)

**"No dark circles detected"**
- Your mesh might be complete! (Rare)
- Try increasing `top_n` to see lower-pressure candidates
- Check that multiple agents are defined with overlapping capability domains

---

## Further Reading

- [Manifold README](../README.md) — Core topology concepts
- [Numinous README](https://github.com/stellamariesays/numinous) — Right hemisphere architecture
- [Federation Design](./federation-design-proposal.md) — Multi-mesh voids

---

**The pattern**: mesh → voids → work → naming → mesh.

Each cycle makes the topology stronger.
