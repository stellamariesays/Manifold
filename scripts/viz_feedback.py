"""
Manifold feedback loop visualisation.

Left:   The strange loop — topology and trust as interlocked arcs,
        three action arrows showing how each layer feeds the other.
Center: Co-evolution — 8 rounds of edge weight + trust converging
        for aligned; stranger flatlines outside.
Right:  Cold-start gap — newcomer trying to break a locked incumbent.

Outputs: manifold-feedback.png
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
from matplotlib.patches import Arc

# ── palette ───────────────────────────────────────────────────────────────────
BG     = "#0d0d0f"
PANEL  = "#13131a"
GOLD   = "#c8a84b"
SOFT   = "#6b6f80"
SOFTHI = "#9ba0b8"
WHITE  = "#e8e8f0"
DIM    = "#1e1e2e"
DIM2   = "#2e2e3e"
RED    = "#d64e4e"
GREEN  = "#4ec98c"
BLUE   = "#4e8fd6"
VIOLET = "#9b6bd6"
CREAM  = "#d6c18b"
ORANGE = "#d69b4e"

# ── simulation data (from examples/feedback_loop.py run) ──────────────────────
ROUNDS  = list(range(9))  # 0 = initial state

# aligned agent — shared focus, reliable delivery
ALIGNED_EDGE  = [1.000, 0.964, 0.933, 0.921, 0.907, 0.905, 0.903, 0.901, 0.903]
ALIGNED_TRUST = [None,  0.910, 0.885, 0.905, 0.886, 0.901, 0.901, 0.897, 0.908]
ALIGNED_LOOP  = [None,  0.937, 0.909, 0.913, 0.897, 0.903, 0.902, 0.899, 0.905]

# stranger agent — different focus, volatile delivery
STRANGER_EDGE  = [0.400] * 9
STRANGER_TRUST = [None] * 9   # never wins a task
STRANGER_LOOP  = [None] * 9

# ── figure ────────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(22, 9.5), facecolor=BG)

# dividers
for xd in [0.355, 0.660]:
    fig.add_artist(plt.Line2D([xd, xd], [0.05, 0.95],
                  transform=fig.transFigure, color=DIM2, lw=0.6, alpha=0.7))

fig.text(0.5, 0.982, "Manifold — the feedback loop",
         color=WHITE, fontsize=13, ha="center", va="top",
         fontfamily="monospace", alpha=0.80)

# ─────────────────────────────────────────────────────────────────────────────
# LEFT PANEL — the strange loop as a 4-step cycle
# ─────────────────────────────────────────────────────────────────────────────
ax1 = fig.add_axes([0.01, 0.04, 0.33, 0.91])
ax1.set_facecolor(BG)
ax1.set_xlim(-4.5, 4.5)
ax1.set_ylim(-4.5, 4.5)
ax1.set_aspect("equal")
ax1.axis("off")

ax1.text(0, 4.15, "the strange loop", color=WHITE, fontsize=11,
         ha="center", fontfamily="monospace", fontweight="bold", alpha=0.85)

# ── four cycle nodes at cardinal positions ─────────────────────────────────────
# Clockwise from top: think → route → grade → sync
NODE_R  = 2.5   # radius of the node circle
BOX_W, BOX_H = 2.2, 0.80

nodes = [
    # angle,  label,         sublabel,                    col
    ( 90,  "think(topic)",  "agent declares focus",       BLUE),
    (  0,  "task routed",   "topology picks closest",     ORANGE),
    (-90,  "grade(score)",  "outcome → trust ledger",     GOLD),
    (180,  "sync_edge()",   "trust → edge weight",        GREEN),
]

node_centers = {}
for ang, lbl, sublbl, col in nodes:
    rad = np.deg2rad(ang)
    cx = NODE_R * np.cos(rad)
    cy = NODE_R * np.sin(rad)
    node_centers[lbl] = (cx, cy)

    # Box
    box = FancyBboxPatch((cx - BOX_W/2, cy - BOX_H/2), BOX_W, BOX_H,
                         boxstyle="round,pad=0.12", lw=1.4,
                         ec=col, fc=PANEL, zorder=8, alpha=0.95)
    ax1.add_patch(box)
    # Glow
    glow = FancyBboxPatch((cx - BOX_W/2, cy - BOX_H/2), BOX_W, BOX_H,
                          boxstyle="round,pad=0.18", lw=6,
                          ec=col, fc="none", zorder=7, alpha=0.08)
    ax1.add_patch(glow)

    ax1.text(cx, cy + 0.13, lbl, color=col, fontsize=8.5,
             ha="center", va="center", fontfamily="monospace",
             fontweight="bold", zorder=9)
    ax1.text(cx, cy - 0.22, sublbl, color=SOFT, fontsize=7.5,
             ha="center", va="center", fontfamily="monospace", zorder=9)

# ── cycle arrows between nodes ────────────────────────────────────────────────
arrow_pairs = [
    ("think(topic)", "task routed",  BLUE,   "arc3,rad=-0.25"),
    ("task routed",  "grade(score)", ORANGE, "arc3,rad=-0.25"),
    ("grade(score)", "sync_edge()",  GOLD,   "arc3,rad=-0.25"),
    ("sync_edge()",  "think(topic)", GREEN,  "arc3,rad=-0.25"),
]

for src, dst, col, conn in arrow_pairs:
    sx, sy = node_centers[src]
    dx, dy = node_centers[dst]
    # Shorten arrows to not overlap boxes
    shrink = 0.62
    ax1.annotate("", xy=(dx, dy), xytext=(sx, sy),
                 arrowprops=dict(
                     arrowstyle="-|>",
                     color=col, lw=2.6, alpha=0.90,
                     connectionstyle=conn,
                     mutation_scale=18,
                     shrinkA=shrink * 60,
                     shrinkB=shrink * 60,
                 ), zorder=6)

# ── center label ──────────────────────────────────────────────────────────────
# Background circle
center_circle = plt.Circle((0, 0), 1.05, color=DIM, zorder=5)
ax1.add_patch(center_circle)
ax1.plot(np.cos(np.linspace(0, 2*np.pi, 200)) * 1.05,
         np.sin(np.linspace(0, 2*np.pi, 200)) * 1.05,
         color=DIM2, lw=0.8, zorder=5)

ax1.text(0,  0.32, "topology", color=BLUE, fontsize=8,
         ha="center", va="center", fontfamily="monospace", alpha=0.8, zorder=6)
ax1.text(0,  0.0, "⟷", color=SOFTHI, fontsize=14,
         ha="center", va="center", zorder=6)
ax1.text(0, -0.32, "trust", color=GOLD, fontsize=8,
         ha="center", va="center", fontfamily="monospace", alpha=0.8, zorder=6)

# ── layer band annotations ─────────────────────────────────────────────────────
# Topology half (top) — subtle arc
arc_top = Arc((0, 0), 5.8, 5.8, angle=0, theta1=20, theta2=160,
              color=BLUE, lw=0.7, alpha=0.20, zorder=3)
ax1.add_patch(arc_top)
ax1.text(0, 3.60, "TOPOLOGY LAYER", color=BLUE, fontsize=6.5,
         ha="center", fontfamily="monospace", alpha=0.35)

# Trust half (bottom) — subtle arc
arc_bot = Arc((0, 0), 5.8, 5.8, angle=0, theta1=200, theta2=340,
              color=GOLD, lw=0.7, alpha=0.20, zorder=3)
ax1.add_patch(arc_bot)
ax1.text(0, -3.60, "TRUST LAYER", color=GOLD, fontsize=6.5,
         ha="center", fontfamily="monospace", alpha=0.35)

# version stamp
ax1.text(0, -4.25, "v0.5.0 — manifold/feedback.py", color=SOFT, fontsize=6.5,
         ha="center", fontfamily="monospace", alpha=0.45)


# ─────────────────────────────────────────────────────────────────────────────
# CENTER PANEL — co-evolution over 8 rounds
# ─────────────────────────────────────────────────────────────────────────────
ax2 = fig.add_axes([0.390, 0.13, 0.245, 0.74])
ax2.set_facecolor(BG)
for spine in ax2.spines.values():
    spine.set_color(DIM2)
ax2.tick_params(colors=SOFT, labelsize=8.5)
ax2.xaxis.label.set_color(SOFT)
ax2.yaxis.label.set_color(SOFT)

rounds_idx = list(range(9))

# aligned — edge weight
ax2.plot(rounds_idx, ALIGNED_EDGE, color=BLUE, lw=1.8, alpha=0.9,
         label="aligned edge", zorder=5)
ax2.scatter(rounds_idx, ALIGNED_EDGE, color=BLUE, s=22, zorder=6, alpha=0.9)

# aligned — trust score (starts at round 1)
trust_x = [i for i, t in enumerate(ALIGNED_TRUST) if t is not None]
trust_y = [t for t in ALIGNED_TRUST if t is not None]
ax2.plot(trust_x, trust_y, color=GOLD, lw=1.8, alpha=0.9,
         label="aligned trust", zorder=5)
ax2.scatter(trust_x, trust_y, color=GOLD, s=22, zorder=6, alpha=0.9)

# aligned — loop strength
loop_x = [i for i, l in enumerate(ALIGNED_LOOP) if l is not None]
loop_y = [l for l in ALIGNED_LOOP if l is not None]
ax2.plot(loop_x, loop_y, color=GREEN, lw=2.2, alpha=0.95,
         label="loop strength", zorder=7, linestyle="--")
ax2.scatter(loop_x, loop_y, color=GREEN, s=26, zorder=8, alpha=0.95, marker="D")

# stranger — flat edge
ax2.plot(rounds_idx, STRANGER_EDGE, color=VIOLET, lw=1.2, alpha=0.5,
         label="stranger edge", zorder=4, linestyle=":")
ax2.fill_between(rounds_idx, 0, STRANGER_EDGE, color=VIOLET, alpha=0.04)

# reference line at 0.5 (neutral prior)
ax2.axhline(0.5, color=DIM2, lw=0.8, linestyle="--", alpha=0.6)
ax2.text(7.9, 0.502, "neutral", color=SOFT, fontsize=7.5,
         va="bottom", fontfamily="monospace", alpha=0.7)

# convergence zone annotation
ax2.axhspan(0.895, 0.915, color=GREEN, alpha=0.08)
ax2.text(4.0, 0.925, "convergence zone", color=GREEN, fontsize=7.5,
         ha="center", va="bottom", fontfamily="monospace", alpha=0.7)

ax2.set_xlim(-0.4, 8.8)
ax2.set_ylim(0.30, 1.07)
ax2.set_xticks(range(9))
ax2.set_xticklabels(["init"] + [str(i) for i in range(1, 9)], fontsize=8.5,
                    fontfamily="monospace")
ax2.set_yticks([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
ax2.set_xlabel("round", fontsize=9, fontfamily="monospace", labelpad=8)
ax2.set_ylabel("score", fontsize=9, fontfamily="monospace", labelpad=8,
               color=SOFT)

ax2.set_title("co-evolution — 8 rounds", color=SOFTHI, fontsize=10,
              fontfamily="monospace", pad=12)

# legend
legend = ax2.legend(
    loc="lower left", fontsize=7.5,
    facecolor=PANEL, edgecolor=DIM2, framealpha=0.9,
    labelcolor=[BLUE, GOLD, GREEN, VIOLET],
)
for text in legend.get_texts():
    text.set_fontfamily("monospace")

# stranger annotation
ax2.annotate("stranger: locked out\nno tasks → no trust",
             xy=(4, 0.400), xytext=(2.0, 0.352),
             color=VIOLET, fontsize=7.5, fontfamily="monospace", alpha=0.85,
             arrowprops=dict(arrowstyle="-", color=VIOLET, lw=0.8, alpha=0.4),
             path_effects=[pe.withStroke(linewidth=2, foreground=BG)])


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT PANEL — cold-start gap
# ─────────────────────────────────────────────────────────────────────────────
ax3 = fig.add_axes([0.700, 0.13, 0.285, 0.74])
ax3.set_facecolor(BG)
for spine in ax3.spines.values():
    spine.set_color(DIM2)
ax3.tick_params(colors=SOFT, labelsize=8.5)

ax3.set_title("cold-start gap", color=SOFTHI, fontsize=10,
              fontfamily="monospace", pad=12)

# Simulate what a new entrant faces vs an incumbent with loop=0.905
# x-axis: # grades the newcomer has filed
# y-axis: effective composite score from trust+topology

newcomer_grades = list(range(0, 12))

def incumbent_score(edge=0.903, trust=0.908):
    """Incumbent's final loop state — combined claim score with proximity boost."""
    import math
    rep = trust
    prox_stake = edge * 0.05 * 100   # proximity_boost effective stake
    stake_bonus = math.log(prox_stake + 1) / 10
    return rep + stake_bonus

def newcomer_score_at(n_grades, avg_grade=0.88):
    """Newcomer with n grades, no topology edge, no stake."""
    import math
    if n_grades == 0:
        return 0.5  # neutral prior
    # Build a simple weighted average (recency-weighted same as TrustLedger)
    grades = [avg_grade] * n_grades
    total_w, weighted_sum = 0.0, 0.0
    for i, g in enumerate(grades):
        w = math.log(i + 2) / math.log(n_grades + 2)
        weighted_sum += g * w
        total_w += w
    rep = weighted_sum / total_w
    return rep  # no proximity bonus — no edge yet

def newcomer_score_with_boost(n_grades, avg_grade=0.88, stake=0.0):
    """Newcomer with stake but no topology edge."""
    import math
    base = newcomer_score_at(n_grades, avg_grade)
    stake_bonus = math.log(stake + 1) / 10
    return base + stake_bonus

inc_score = incumbent_score()

# Plot incumbent flat line
ax3.axhline(inc_score, color=GREEN, lw=1.8, alpha=0.8, linestyle="--")
ax3.text(10.5, inc_score + 0.010, "incumbent  loop=0.905", color=GREEN,
         fontsize=7.5, va="bottom", ha="right", fontfamily="monospace", alpha=0.9,
         path_effects=[pe.withStroke(linewidth=2, foreground=BG)])

# newcomer — no stake
nc_scores = [newcomer_score_at(n) for n in newcomer_grades]
ax3.plot(newcomer_grades, nc_scores, color=SOFT, lw=1.6, alpha=0.8,
         label="newcomer (no stake)")
ax3.scatter(newcomer_grades, nc_scores, color=SOFT, s=18, alpha=0.8)

# newcomer — with stake 20
nc_stake20 = [newcomer_score_with_boost(n, stake=20.0) for n in newcomer_grades]
ax3.plot(newcomer_grades, nc_stake20, color=CREAM, lw=1.6, alpha=0.8,
         label="newcomer stake=20", linestyle="-.")
ax3.scatter(newcomer_grades, nc_stake20, color=CREAM, s=18, alpha=0.8)

# newcomer — with stake 20 AND gains topology edge after 5 grades
def newcomer_with_topo(n, edge_unlock=5, avg_grade=0.88):
    import math
    base = newcomer_score_at(n, avg_grade)
    stake_bonus = math.log(21) / 10  # stake=20 throughout
    if n >= edge_unlock:
        # Topology edge established — proximity boost kicks in
        # Edge weight starts at 0.4 (weak), grows with trust
        edge_progress = min(1.0, (n - edge_unlock) / 4.0)
        edge_now = 0.40 + edge_progress * (0.90 - 0.40)
        prox_stake = edge_now * 0.05 * 100
        prox_bonus = math.log(prox_stake + 1) / 10
        return base + stake_bonus + prox_bonus
    return base + stake_bonus

nc_with_topo = [newcomer_with_topo(n) for n in newcomer_grades]
ax3.plot(newcomer_grades, nc_with_topo, color=ORANGE, lw=2.0, alpha=0.9,
         label="newcomer + topo unlock", linestyle="-")
ax3.scatter(newcomer_grades, nc_with_topo, color=ORANGE, s=22, alpha=0.9)

# mark where topo unlocks
ax3.axvline(5, color=ORANGE, lw=0.8, alpha=0.35, linestyle=":")
ax3.text(5.1, 0.64, "topology\nunlocks", color=ORANGE, fontsize=7.5,
         va="bottom", fontfamily="monospace", alpha=0.7)

# mark where newcomer catches incumbent (with topo)
for n in newcomer_grades:
    if newcomer_with_topo(n) >= inc_score:
        cross = n
        break
else:
    cross = None

if cross is not None:
    ax3.plot(cross, newcomer_with_topo(cross), "*", color=GREEN,
             ms=12, zorder=10, alpha=0.9)
    ax3.text(cross + 0.2, newcomer_with_topo(cross) - 0.015,
             f"catch-up @ round {cross}", color=GREEN, fontsize=7.5,
             fontfamily="monospace",
             path_effects=[pe.withStroke(linewidth=2, foreground=BG)])

# gap shading
gap_x = newcomer_grades
ax3.fill_between(gap_x,
                 [min(nc_score, inc_score) for nc_score in nc_scores],
                 [inc_score] * len(gap_x),
                 color=RED, alpha=0.07)
ax3.text(2.5, (nc_scores[3] + inc_score) / 2,
         "entry gap", color=RED, fontsize=8, ha="center",
         fontfamily="monospace", alpha=0.6)

ax3.set_xlim(-0.4, 11.4)
ax3.set_ylim(0.44, 1.14)
ax3.set_xlabel("grades filed by newcomer", fontsize=9,
               fontfamily="monospace", labelpad=8, color=SOFT)
ax3.set_ylabel("composite score", fontsize=9,
               fontfamily="monospace", labelpad=8, color=SOFT)
ax3.set_xticks(range(0, 12))
ax3.set_yticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

legend3 = ax3.legend(loc="lower right", fontsize=7.5,
                     facecolor=PANEL, edgecolor=DIM2, framealpha=0.9,
                     labelcolor=[SOFT, CREAM, ORANGE])
for text in legend3.get_texts():
    text.set_fontfamily("monospace")

ax3.text(0, 1.12, "how does a new agent break in?",
         color=SOFTHI, fontsize=8, fontfamily="monospace", va="top", alpha=0.85)

# ─────────────────────────────────────────────────────────────────────────────
out = "manifold-feedback.png"
plt.savefig(out, dpi=180, bbox_inches="tight", facecolor=BG)
print(f"saved: {out}")
plt.close()
