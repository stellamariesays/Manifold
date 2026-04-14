"""
MRI — interactive cognitive mesh visualizer.

Renders the full Manifold topology as a self-contained diagnostic HTML page:
force-directed agent graph, Sophia heat regions, fog gap zones, bottleneck
indicators, and an optional Glossolalia coordination-pressure sidebar.

Like a brain scan — you see the structure, the hot regions, the dark holes,
the bottleneck, the seam between agents where Sophia lives.

Usage::

    atlas = agent.atlas()
    snapshot = capture(atlas, agent_a="braid", agent_b="stella")
    html = generate_html(snapshot)
    with open("mri.html", "w") as f:
        f.write(html)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .atlas import Atlas
from .sophia import SophiaReading, SophiaRegion, sophia_scan
from .bottleneck import BottleneckReading, bottleneck_topology
from .bleed import BleedReading, bleed_rate
from .glossolalia import GlossolaliaReading, GlossolaliaProbe
from .chart import _tokenize


# ── Snapshot dataclass ─────────────────────────────────────────────────────


@dataclass
class MRISnapshot:
    """
    A frozen diagnostic snapshot of the cognitive mesh.

    :param atlas_data: Serialized graph from atlas.export_json() — nodes, edges,
                       holes, curvature summary.
    :param sophia: Sophia wisdom-signal reading from sophia_scan().
    :param bottleneck: Bottleneck topology reading, or None if the mesh has
                       insufficient structure to compute one.
    :param bleed: Curvature-decay readings per region. Empty list if fewer
                  than two atlas snapshots were available.
    :param holes: Topic strings with no multi-agent coverage (from atlas.holes()).
    :param glossolalia: Coordination-pressure probe result, or None if no
                        agent pair was supplied to capture().
    :param captured_at: ISO 8601 UTC timestamp of when the snapshot was taken.
    """

    atlas_data: dict
    sophia: SophiaReading
    bottleneck: Optional[BottleneckReading]
    bleed: list[BleedReading]
    holes: list[str]
    glossolalia: Optional[GlossolaliaReading]
    captured_at: str


# ── capture() ──────────────────────────────────────────────────────────────


def capture(
    atlas: Atlas,
    atlas_history: Optional[list[Atlas]] = None,
    agent_a: Optional[str] = None,
    agent_b: Optional[str] = None,
    coordination_pressure: float = 0.0,
) -> MRISnapshot:
    """
    Build a complete MRISnapshot from an Atlas and optional extras.

    Runs :func:`sophia_scan`, :func:`bottleneck_topology`, and optionally
    :func:`bleed_rate` and a :class:`GlossolaliaProbe`.  All failures are
    caught gracefully — a minimal snapshot is always returned.

    :param atlas: A built Atlas snapshot (from ``agent.atlas()`` or
                  ``Atlas.build(registry)``).
    :param atlas_history: Ordered list of Atlas snapshots (oldest first) for
                          bleed-rate computation.  Requires ≥ 2 items.
                          Defaults to ``None`` → bleed list is empty.
    :param agent_a: First agent for the Glossolalia probe.  Both *agent_a*
                    and *agent_b* must be supplied to enable the probe.
    :param agent_b: Second agent for the Glossolalia probe.
    :param coordination_pressure: Pressure scalar for the Glossolalia probe
                                   (0.0 = full suppression, 1.0 = no change).
    :returns: A fully populated MRISnapshot ready for :func:`generate_html`.

    Example::

        atlas = agent.atlas()
        snap = capture(atlas, agent_a="oracle", agent_b="analyst")
        html = generate_html(snap)
    """
    # Sophia scan — always available
    sophia: SophiaReading = sophia_scan(atlas)

    # Bottleneck — requires at least one transition map
    bottleneck_reading: Optional[BottleneckReading] = None
    try:
        # Derive a flow map from mean per-term transition coverage
        term_coverages: dict[str, list[float]] = {}
        for tm in atlas._maps.values():
            for term in tm.overlap:
                term_coverages.setdefault(term, []).append(tm.coverage)
        flow_map: dict[str, float] = {
            term: sum(covs) / len(covs)
            for term, covs in term_coverages.items()
        }
        bottleneck_reading = bottleneck_topology(atlas, flow_map)
    except (ValueError, ZeroDivisionError):
        pass  # Mesh too sparse — no bottleneck reading

    # Bleed rate — requires ≥ 2 atlas snapshots
    bleed_readings: list[BleedReading] = []
    history = atlas_history or []
    if len(history) >= 2:
        try:
            bleed_readings = bleed_rate(history)
        except ValueError:
            pass

    # Holes
    holes: list[str] = atlas.holes()

    # Glossolalia probe — only if both agent names supplied
    glossolalia_reading: Optional[GlossolaliaReading] = None
    if agent_a and agent_b:
        try:
            probe = GlossolaliaProbe(
                atlas,
                agent_a,
                agent_b,
                coordination_pressure=coordination_pressure,
            )
            glossolalia_reading = probe.scan()
        except (ValueError, KeyError):
            pass  # Agent not found or invalid config

    captured_at = datetime.now(timezone.utc).isoformat()

    return MRISnapshot(
        atlas_data=atlas.export_json(),
        sophia=sophia,
        bottleneck=bottleneck_reading,
        bleed=bleed_readings,
        holes=holes,
        glossolalia=glossolalia_reading,
        captured_at=captured_at,
    )


# ── Serialisation helpers ──────────────────────────────────────────────────


def _region_to_dict(r: SophiaRegion) -> dict:
    return {
        "topic": r.topic,
        "density": r.density,
        "curvature": r.curvature,
        "agent_count": r.agent_count,
        "interpretation": r.interpretation,
    }


def _sophia_to_dict(s: SophiaReading) -> dict:
    return {
        "score": s.score,
        "dense_regions": [_region_to_dict(r) for r in s.dense_regions],
        "gradient": [list(pair) for pair in s.gradient],
        "interpretation": s.interpretation,
    }


def _bottleneck_to_dict(b: Optional[BottleneckReading]) -> Optional[dict]:
    if b is None:
        return None
    return {
        "perceived_bottleneck": b.perceived_bottleneck,
        "actual_bottleneck": b.actual_bottleneck,
        "attention_displacement": b.attention_displacement,
        "topology_note": b.topology_note,
        "flow_shortfall": b.flow_shortfall,
    }


def _bleed_to_dict(readings: list[BleedReading]) -> list[dict]:
    return [
        {
            "region": r.region,
            "original_curvature": r.original_curvature,
            "current_curvature": r.current_curvature,
            "bleed_rate": r.bleed_rate,
            "estimated_flat_at": r.estimated_flat_at,
            "closing_mode": r.closing_mode,
        }
        for r in readings
    ]


def _glossolalia_to_dict(g: Optional[GlossolaliaReading]) -> Optional[dict]:
    if g is None:
        return None
    return {
        "sophia_before": g.sophia_before,
        "sophia_after": g.sophia_after,
        "delta": g.delta,
        "emergent_regions": [_region_to_dict(r) for r in g.emergent_regions],
        "coordination_pressure": g.coordination_pressure,
        "interpretation": g.interpretation,
    }


def _snapshot_to_json_dict(snapshot: MRISnapshot) -> dict:
    """Return a fully JSON-serialisable dict for the snapshot."""
    return {
        "atlas": snapshot.atlas_data,
        "sophia": _sophia_to_dict(snapshot.sophia),
        "bottleneck": _bottleneck_to_dict(snapshot.bottleneck),
        "bleed": _bleed_to_dict(snapshot.bleed),
        "holes": snapshot.holes,
        "glossolalia": _glossolalia_to_dict(snapshot.glossolalia),
        "captured_at": snapshot.captured_at,
    }


# ── HTML generation ────────────────────────────────────────────────────────


def generate_html(snapshot: MRISnapshot) -> str:
    """
    Generate a fully self-contained MRI diagnostic HTML page.

    Embeds snapshot data as inline JSON and renders a D3.js v7 force-directed
    graph of the cognitive mesh.  No external files required beyond the D3 CDN.

    :param snapshot: An MRISnapshot from :func:`capture`.
    :returns: Complete HTML string.  Write directly to a ``.html`` file.

    Example::

        html = generate_html(snapshot)
        Path("mri.html").write_text(html)
    """
    data = _snapshot_to_json_dict(snapshot)
    json_str = json.dumps(data, ensure_ascii=False, indent=None)
    # Safe for embedding inside <script>: escape end-tag and comment openers
    json_str = json_str.replace("</", "<\\/").replace("<!--", "<\\!--")

    return _HTML_TEMPLATE.replace("__SNAPSHOT_JSON__", json_str)


# ── HTML template ──────────────────────────────────────────────────────────

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Manifold MRI</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #0a0a0f;
  color: #c8d4e8;
  font-family: 'Courier New', Courier, monospace;
  overflow: hidden;
  width: 100vw;
  height: 100vh;
}

/* ── Title ────────────────────────────────────────────────── */
#title {
  position: absolute;
  top: 16px;
  left: 20px;
  font-size: 18px;
  letter-spacing: 0.15em;
  color: #4a9eff;
  z-index: 10;
  text-transform: uppercase;
  pointer-events: none;
}
#title .subtitle {
  color: #22334a;
  font-size: 10px;
  display: block;
  margin-top: 4px;
  letter-spacing: 0.12em;
}

/* ── Timestamp ────────────────────────────────────────────── */
#timestamp {
  position: absolute;
  bottom: 16px;
  right: 20px;
  font-size: 10px;
  color: #22334a;
  z-index: 10;
  pointer-events: none;
}
body.has-sidebar #timestamp { right: 300px; }

/* ── Bleed info ───────────────────────────────────────────── */
#bleed-info {
  position: absolute;
  top: 16px;
  right: 20px;
  font-size: 11px;
  z-index: 10;
  cursor: default;
  text-align: right;
}
body.has-sidebar #bleed-info { right: 300px; }
#bleed-info .bleed-value { font-size: 13px; font-weight: bold; }
#bleed-info .bleed-region { color: #334455; font-size: 10px; }

#bleed-tooltip {
  display: none;
  position: absolute;
  top: 42px;
  right: 0;
  background: #0d1220;
  border: 1px solid #1a2a4a;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 10px;
  z-index: 200;
  max-width: 200px;
  color: #8899aa;
  line-height: 1.6;
  white-space: nowrap;
}

/* ── Graph canvas ─────────────────────────────────────────── */
#graph {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  transition: right 0.2s;
}
body.has-sidebar #graph { right: 280px; }

/* ── Sidebar ──────────────────────────────────────────────── */
#sidebar {
  display: none;
  position: absolute;
  top: 0; right: 0;
  width: 280px; height: 100%;
  background: #0d0d18;
  border-left: 1px solid #1a1a3e;
  padding: 16px 14px;
  overflow-y: auto;
  z-index: 10;
}
body.has-sidebar #sidebar { display: block; }

#sidebar h2 {
  font-size: 11px;
  letter-spacing: 0.18em;
  color: #4a9eff;
  text-transform: uppercase;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid #1a1a3e;
}

.sb-row {
  margin-bottom: 10px;
}
.sb-label {
  color: #334455;
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 2px;
}
.sb-value {
  color: #c8d4e8;
  font-size: 12px;
}

#emergence-delta {
  font-size: 36px;
  font-weight: bold;
  margin: 10px 0 6px;
  letter-spacing: 0.05em;
}
.delta-pos { color: #00cc66; }
.delta-neg { color: #ff4444; }
.delta-zero { color: #445566; }

.sb-interp {
  font-size: 10px;
  color: #6677aa;
  line-height: 1.5;
  margin-bottom: 14px;
  font-style: italic;
  padding-bottom: 12px;
  border-bottom: 1px solid #1a1a3e;
}

.seam-title {
  font-size: 9px;
  color: #334455;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 8px;
  margin-top: 4px;
}
.seam-region {
  margin-bottom: 5px;
  padding: 5px 7px;
  background: #0a0a1a;
  border: 1px solid #1a1a3e;
  border-radius: 3px;
  font-size: 10px;
  overflow: hidden;
}
.seam-region .sr-topic { color: #4a9eff; }
.seam-region .sr-density { color: #ffd700; float: right; }
.seam-region .sr-interp { color: #334455; font-size: 9px; margin-top: 3px; clear: both; }

/* ── Legend ───────────────────────────────────────────────── */
#legend {
  position: absolute;
  bottom: 16px;
  left: 20px;
  z-index: 10;
  font-size: 10px;
  color: #334455;
  pointer-events: none;
}
.leg-item {
  display: flex;
  align-items: center;
  margin-bottom: 5px;
  gap: 7px;
}
.leg-dot {
  width: 11px; height: 11px;
  border-radius: 50%;
  flex-shrink: 0;
}
.leg-ring {
  width: 11px; height: 11px;
  border-radius: 50%;
  border: 2px solid #ff4444;
  flex-shrink: 0;
}
.leg-dash {
  width: 18px; height: 0;
  border-top: 2px dashed #ff4444;
  flex-shrink: 0;
}
.leg-outline {
  width: 11px; height: 11px;
  border-radius: 50%;
  border: 1px solid #ffd700;
  background: transparent;
  flex-shrink: 0;
}
.leg-fog {
  width: 11px; height: 11px;
  border-radius: 50%;
  background: #1a0a1a;
  border: 1px solid #2a1a2a;
  flex-shrink: 0;
}

/* ── Tooltip ──────────────────────────────────────────────── */
#tooltip {
  position: absolute;
  background: #0d1220;
  border: 1px solid #1a2a4a;
  border-radius: 4px;
  padding: 10px 12px;
  font-size: 11px;
  pointer-events: none;
  display: none;
  z-index: 100;
  max-width: 230px;
  line-height: 1.65;
}
.tt-name { color: #4a9eff; font-size: 13px; margin-bottom: 6px; font-weight: bold; }
.tt-row  { color: #556677; }
.tt-row span { color: #c8d4e8; }

/* ── SVG elements ─────────────────────────────────────────── */
.node-label {
  fill: #556688;
  font-size: 11px;
  font-family: 'Courier New', Courier, monospace;
  text-anchor: middle;
  pointer-events: none;
  user-select: none;
}
.sophia-label {
  font-family: 'Courier New', Courier, monospace;
  text-anchor: middle;
  pointer-events: none;
  user-select: none;
  opacity: 0.9;
}
.fog-label {
  fill: #2a1a3a;
  font-size: 9px;
  font-family: 'Courier New', Courier, monospace;
  text-anchor: middle;
  pointer-events: none;
  user-select: none;
}

/* ── Bottleneck pulse ─────────────────────────────────────── */
@keyframes bottleneck-pulse {
  0%   { stroke-opacity: 1;   r: var(--br); }
  50%  { stroke-opacity: 0.25; r: calc(var(--br) + 5px); }
  100% { stroke-opacity: 1;   r: var(--br); }
}
.bottleneck-ring {
  animation: bottleneck-pulse 1.5s ease-in-out infinite;
  fill: none;
  stroke: #ff4444;
  stroke-width: 2.5;
}
</style>
</head>
<body>

<div id="title">
  Manifold MRI
  <span class="subtitle">cognitive mesh diagnostic</span>
</div>

<div id="bleed-info">
  <div id="bleed-tooltip"></div>
</div>

<div id="graph">
  <svg id="main-svg" width="100%" height="100%"></svg>
</div>

<div id="sidebar">
  <h2>Glossolalia Probe</h2>
</div>

<div id="legend">
  <div class="leg-item"><div class="leg-dot" style="background:#4a9eff"></div><span>agent node</span></div>
  <div class="leg-item"><div class="leg-dot" style="background:#ffd700"></div><span>highest sophia coverage</span></div>
  <div class="leg-item"><div class="leg-ring"></div><span>bottleneck</span></div>
  <div class="leg-item"><div class="leg-dash"></div><span>seam gap</span></div>
  <div class="leg-item"><div class="leg-outline"></div><span>sophia hot region</span></div>
  <div class="leg-item"><div class="leg-fog"></div><span>fog gap</span></div>
</div>

<div id="timestamp"></div>
<div id="tooltip"></div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
(function () {
'use strict';

// ── Embedded snapshot ────────────────────────────────────────
const SNAPSHOT = __SNAPSHOT_JSON__;

const snap      = SNAPSHOT;
const atlas     = snap.atlas;
const sophia    = snap.sophia;
const bottleneck = snap.bottleneck;
const bleedList  = snap.bleed;
const holes      = snap.holes;
const glossolalia = snap.glossolalia;

// ── Sidebar / body class ─────────────────────────────────────
if (glossolalia !== null && glossolalia !== undefined) {
  document.body.classList.add('has-sidebar');
  buildSidebar(glossolalia);
}

// ── Timestamp ────────────────────────────────────────────────
document.getElementById('timestamp').textContent = snap.captured_at;

// ── Bleed info ───────────────────────────────────────────────
buildBleedInfo(bleedList);

// ── Dimensions ───────────────────────────────────────────────
const sidebarW = glossolalia ? 280 : 0;
const W = window.innerWidth - sidebarW;
const H = window.innerHeight;

const svg = d3.select('#main-svg')
  .attr('width', W)
  .attr('height', H);

// ── Data copies (D3 forceLink mutates source/target) ─────────
const nodes = atlas.nodes.map(n => Object.assign({}, n));
const simEdges = atlas.edges.map(e => Object.assign({}, e));
// Keep original edge list for attribute lookup (source/target as strings)
const edgesRaw = atlas.edges;

// ── Scale helpers ─────────────────────────────────────────────
const vocabSizes = nodes.map(n => n.vocab_size);
const vsMin = d3.min(vocabSizes) || 0;
const vsMax = d3.max(vocabSizes) || 1;
const sizeScale = d3.scaleLinear()
  .domain([vsMin, vsMax === vsMin ? vsMin + 1 : vsMax])
  .range([20, 60])
  .clamp(true);

const overlapSizes = edgesRaw.map(e => e.overlap_size);
const osMin = d3.min(overlapSizes) || 0;
const osMax = d3.max(overlapSizes) || 1;
const thicknessScale = d3.scaleLinear()
  .domain([osMin, osMax === osMin ? osMin + 1 : osMax])
  .range([1, 4])
  .clamp(true);

// ── Token helpers ─────────────────────────────────────────────
function tokenize(s) {
  return s.toLowerCase().replace(/[-_]/g, ' ').split(/\s+/).filter(t => t.length > 0);
}
function nodeCoversTokens(node, tokens) {
  const tset = new Set(tokens);
  return node.vocabulary.some(v => tset.has(v));
}

// ── Identify bottleneck node ──────────────────────────────────
let bottleneckNodeId = null;
if (bottleneck && bottleneck.actual_bottleneck) {
  const btTokens = tokenize(bottleneck.actual_bottleneck);
  const covering = nodes.filter(n => nodeCoversTokens(n, btTokens));
  if (covering.length > 0) {
    covering.sort((a, b) => b.vocab_size - a.vocab_size);
    bottleneckNodeId = covering[0].id;
  }
}

// ── Identify sophia-dense node (most dense-region coverage) ──
let sophiaNodeId = null;
if (sophia.dense_regions.length > 0) {
  const topN = sophia.dense_regions.slice(0, 5);
  const counts = {};
  nodes.forEach(n => { counts[n.id] = 0; });
  topN.forEach(region => {
    const toks = tokenize(region.topic);
    nodes.forEach(n => { if (nodeCoversTokens(n, toks)) counts[n.id]++; });
  });
  const ranked = nodes.slice().sort((a, b) => counts[b.id] - counts[a.id]);
  if (ranked.length > 0 && counts[ranked[0].id] > 0) sophiaNodeId = ranked[0].id;
}

// ── Seam gaps: shared vocab but no transition map ─────────────
const edgeSet = new Set();
edgesRaw.forEach(e => {
  edgeSet.add(e.source + '|' + e.target);
  edgeSet.add(e.target + '|' + e.source);
});

const seamGaps = [];
for (let i = 0; i < nodes.length; i++) {
  for (let j = i + 1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j];
    if (edgeSet.has(a.id + '|' + b.id)) continue;
    const av = new Set(a.vocabulary);
    const shared = b.vocabulary.some(v => av.has(v));
    if (shared) seamGaps.push({ sourceId: a.id, targetId: b.id });
  }
}

// ── Node lookup map ───────────────────────────────────────────
// Will be updated each tick via simulation node positions
const nodeById = new Map(nodes.map(n => [n.id, n]));

// ── Force simulation ──────────────────────────────────────────
const simulation = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(simEdges).id(d => d.id).distance(200).strength(0.4))
  .force('charge', d3.forceManyBody().strength(-500))
  .force('center', d3.forceCenter(W / 2, H / 2))
  .force('collide', d3.forceCollide(d => sizeScale(d.vocab_size) + 20));
window._manifoldSimulation = simulation;

// ── SVG layers ────────────────────────────────────────────────

// Background
svg.append('rect').attr('width', W).attr('height', H).attr('fill', '#0a0a0f');

// Seam gap lines
const gapGroup = svg.append('g').attr('class', 'gap-lines');
const gapLines = gapGroup.selectAll('line')
  .data(seamGaps)
  .join('line')
  .attr('stroke', '#ff4444')
  .attr('stroke-width', 1.2)
  .attr('stroke-dasharray', '5,4')
  .attr('opacity', 0.35)
  .attr('fill', 'none');

// Normal edge lines
const edgeGroup = svg.append('g').attr('class', 'edge-lines');
const edgeLines = edgeGroup.selectAll('line')
  .data(simEdges)
  .join('line')
  .attr('stroke', d => d3.interpolateRgb('#1a1a2e', '#4a9eff')(d.coverage))
  .attr('stroke-opacity', d => Math.max(0.15, d.coverage))
  .attr('stroke-width', d => thicknessScale(d.overlap_size))
  .attr('fill', 'none');

// Fog zones (holes near centre)
const fogGroup = svg.append('g').attr('class', 'fog-zones');
const fogData = holes.slice(0, 8).map((topic, i) => {
  const angle = (i / Math.max(holes.length, 1)) * 2 * Math.PI - Math.PI / 2;
  const r = 55 + i * 8;
  return { topic, x: W / 2 + Math.cos(angle) * r, y: H / 2 + Math.sin(angle) * r };
});

const fogGs = fogGroup.selectAll('g')
  .data(fogData)
  .join('g')
  .attr('transform', d => `translate(${d.x},${d.y})`);

fogGs.append('circle')
  .attr('r', 18)
  .attr('fill', '#1a0a1a')
  .attr('stroke', '#2a1a2a')
  .attr('stroke-width', 1)
  .attr('opacity', 0.75);

fogGs.append('text')
  .attr('class', 'fog-label')
  .attr('y', 4)
  .text(d => d.topic.length > 10 ? d.topic.slice(0, 9) + '…' : d.topic);

// Node groups
const nodeGroup = svg.append('g').attr('class', 'nodes');
const nodeGs = nodeGroup.selectAll('g')
  .data(nodes)
  .join('g')
  .attr('class', 'node-g')
  .style('cursor', 'grab')
  .call(d3.drag()
    .on('start', dragStarted)
    .on('drag',  dragged)
    .on('end',   dragEnded));

// Main circle
nodeGs.append('circle')
  .attr('r', d => sizeScale(d.vocab_size))
  .attr('fill', d => d.id === sophiaNodeId ? '#ffd700' : '#4a9eff')
  .attr('fill-opacity', d => d.id === sophiaNodeId ? 0.9 : 0.8)
  .attr('stroke', d => d.id === sophiaNodeId ? '#b8a000' : '#1a2a4a')
  .attr('stroke-width', 1.5);

// Bottleneck ring (animated, drawn on top of main circle)
nodeGs.filter(d => d.id === bottleneckNodeId)
  .append('circle')
  .attr('class', 'bottleneck-ring')
  .style('--br', d => sizeScale(d.vocab_size) + 6 + 'px')
  .attr('r', d => sizeScale(d.vocab_size) + 6)
  .attr('stroke', '#ff4444')
  .attr('stroke-width', 2.5)
  .attr('fill', 'none');

// Node label
nodeGs.append('text')
  .attr('class', 'node-label')
  .attr('y', d => sizeScale(d.vocab_size) + 15)
  .text(d => d.id);

// ── Sophia heat labels ────────────────────────────────────────
const topRegions = sophia.dense_regions.slice(0, 5);
const densities = topRegions.map(r => r.density);
const dMin = d3.min(densities) || 0;
const dMax = d3.max(densities) || 1;

const fontScale = d3.scaleLinear()
  .domain([dMin, dMax === dMin ? dMin + 0.001 : dMax])
  .range([10, 14]).clamp(true);

const colorInterp = d3.scaleLinear()
  .domain([0, 1])
  .range(['#334455', '#ffd700'])
  .interpolate(d3.interpolateRgb);

// Build sophia label data: each region paired with its top-2 covering nodes
const sophiaLabelData = topRegions.map(region => {
  const toks = tokenize(region.topic);
  const covering = nodes.filter(n => nodeCoversTokens(n, toks));
  covering.sort((a, b) => b.vocab_size - a.vocab_size);
  return { region, covering: covering.slice(0, 2) };
}).filter(d => d.covering.length >= 1);

const sophiaGroup = svg.append('g').attr('class', 'sophia-labels');
const sophiaLabels = sophiaGroup.selectAll('text')
  .data(sophiaLabelData)
  .join('text')
  .attr('class', 'sophia-label')
  .attr('font-size', d => fontScale(d.region.density) + 'px')
  .attr('fill', d => colorInterp(d.region.density))
  .text(d => d.region.topic);

// ── Tooltip ───────────────────────────────────────────────────
const tooltipEl = document.getElementById('tooltip');

nodeGs
  .on('mouseover', (event, d) => {
    const topVocab = d.vocabulary.slice(0, 3).join(', ');
    const topDomain = d.domain.slice(0, 4).join(', ') + (d.domain.length > 4 ? ' …' : '');
    tooltipEl.innerHTML =
      `<div class="tt-name">${d.id}</div>` +
      `<div class="tt-row">vocab_size: <span>${d.vocab_size}</span></div>` +
      `<div class="tt-row">focus: <span>${d.focus || '—'}</span></div>` +
      `<div class="tt-row">domains: <span>${topDomain}</span></div>` +
      `<div class="tt-row">top vocab: <span>${topVocab}</span></div>`;
    tooltipEl.style.display = 'block';
    tooltipEl.style.left = (event.pageX + 14) + 'px';
    tooltipEl.style.top  = (event.pageY - 10) + 'px';
  })
  .on('mousemove', event => {
    tooltipEl.style.left = (event.pageX + 14) + 'px';
    tooltipEl.style.top  = (event.pageY - 10) + 'px';
  })
  .on('mouseout', () => { tooltipEl.style.display = 'none'; });

// ── Tick handler ──────────────────────────────────────────────
simulation.on('tick', () => {
  // Edge lines (D3 has replaced source/target with node objects)
  edgeLines
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y);

  // Seam gap lines (source/target are ID strings; look up live positions)
  gapLines
    .attr('x1', d => { const n = nodeById.get(d.sourceId); return n ? n.x : W/2; })
    .attr('y1', d => { const n = nodeById.get(d.sourceId); return n ? n.y : H/2; })
    .attr('x2', d => { const n = nodeById.get(d.targetId); return n ? n.x : W/2; })
    .attr('y2', d => { const n = nodeById.get(d.targetId); return n ? n.y : H/2; });

  // Nodes
  nodeGs.attr('transform', d => `translate(${d.x},${d.y})`);

  // Sophia labels — midpoint of top two covering nodes
  sophiaLabels.attr('transform', d => {
    if (d.covering.length === 0) return `translate(${W/2},${H/2})`;
    if (d.covering.length === 1) {
      const n = d.covering[0];
      return `translate(${n.x},${n.y - sizeScale(n.vocab_size) - 22})`;
    }
    const mx = (d.covering[0].x + d.covering[1].x) / 2;
    const my = (d.covering[0].y + d.covering[1].y) / 2;
    return `translate(${mx},${my})`;
  });
});

// ── Drag handlers ─────────────────────────────────────────────
function dragStarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d)   { d.fx = event.x; d.fy = event.y; }
function dragEnded(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}

// ── Sidebar builder ───────────────────────────────────────────
function buildSidebar(g) {
  if (!g) return;
  const el = document.getElementById('sidebar');
  const deltaClass = g.delta > 0 ? 'delta-pos' : g.delta < 0 ? 'delta-neg' : 'delta-zero';
  const sign = g.delta > 0 ? '+' : '';

  el.innerHTML +=
    `<h2>Glossolalia Probe</h2>` +
    `<div class="sb-row"><div class="sb-label">coordination pressure</div>` +
    `<div class="sb-value">${g.coordination_pressure.toFixed(2)}</div></div>` +
    `<div class="sb-row"><div class="sb-label">sophia before</div>` +
    `<div class="sb-value">${g.sophia_before.toFixed(4)}</div></div>` +
    `<div class="sb-row"><div class="sb-label">sophia after</div>` +
    `<div class="sb-value">${g.sophia_after.toFixed(4)}</div></div>` +
    `<div id="emergence-delta" class="${deltaClass}">${sign}${g.delta.toFixed(4)}</div>` +
    `<div class="sb-interp">${g.interpretation}</div>`;

  if (g.emergent_regions && g.emergent_regions.length > 0) {
    el.innerHTML += `<div class="seam-title">emergent regions</div>`;
    g.emergent_regions.slice(0, 6).forEach(r => {
      el.innerHTML +=
        `<div class="seam-region">` +
        `<span class="sr-density">${r.density.toFixed(4)}</span>` +
        `<span class="sr-topic">${r.topic}</span>` +
        `<div class="sr-interp">${r.interpretation}</div>` +
        `</div>`;
    });
  }
}

// ── Bleed info builder ────────────────────────────────────────
function buildBleedInfo(bleed) {
  const el = document.getElementById('bleed-info');
  const tipEl = document.getElementById('bleed-tooltip');

  if (!bleed || bleed.length === 0) {
    el.innerHTML = `<span style="color:#22334a">bleed: n/a</span>`;
    return;
  }
  const top = bleed[0];
  const color = top.bleed_rate > 0.3 ? '#ff9900' : '#445566';
  el.innerHTML =
    `<span class="bleed-value" style="color:${color}">bleed: ${top.bleed_rate.toFixed(3)}</span>` +
    `<br><span class="bleed-region">${top.region} · ${top.closing_mode}</span>`;

  el.addEventListener('mouseenter', () => {
    tipEl.innerHTML =
      `<strong style="color:#c8d4e8">${top.region}</strong><br>` +
      `rate: ${top.bleed_rate.toFixed(4)}/cycle<br>` +
      `mode: ${top.closing_mode}<br>` +
      `curvature: ${top.original_curvature.toFixed(3)} → ${top.current_curvature.toFixed(3)}`;
    tipEl.style.display = 'block';
  });
  el.addEventListener('mouseleave', () => { tipEl.style.display = 'none'; });
}

})(); // IIFE
</script>
</body>
</html>"""
