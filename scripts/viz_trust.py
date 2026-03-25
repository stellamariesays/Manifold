"""
Manifold trust layer visualisation — v2.

Left:  topology (the eye)
Right: trust layer — task node, agents as circles, claim arrows with
       thickness ~ stake, colour ~ reputation, referral chain, ranking sidebar.

Outputs: manifold-trust.png
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Circle, FancyBboxPatch
import matplotlib.patheffects as pe

# ── palette ──────────────────────────────────────────────────────────────────
BG     = "#0d0d0f"
PANEL  = "#13131a"
GOLD   = "#c8a84b"
SOFT   = "#6b6f80"
SOFTHI = "#9ba0b8"
WHITE  = "#e8e8f0"
DIM    = "#2e2e3e"
RED    = "#d64e4e"
GREEN  = "#4ec98c"
BLUE   = "#4e8fd6"
VIOLET = "#9b6bd6"
CREAM  = "#d6c18b"

fig = plt.figure(figsize=(18, 8.5), facecolor=BG)

# ─────────────────────────────────────────────────────────────────────────────
# LEFT PANEL — topology (the eye)
# ─────────────────────────────────────────────────────────────────────────────
ax1 = fig.add_axes([0.01, 0.04, 0.44, 0.92])
ax1.set_facecolor(BG)
ax1.set_xlim(-3.2, 3.2)
ax1.set_ylim(-3.2, 3.2)
ax1.set_aspect("equal")
ax1.axis("off")

chart_pos    = [(-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)]
chart_labels = ["solver", "navigator", "oracle", "braid"]
chart_colors = [GREEN, BLUE, VIOLET, CREAM]
r = 1.7

for (cx, cy), col in zip(chart_pos, chart_colors):
    ax1.add_patch(Circle((cx, cy), r, lw=0, fc=col, alpha=0.06, zorder=1))
    ax1.add_patch(Circle((cx, cy), r, lw=1.2, ec=col, fc="none", alpha=0.40, zorder=2))

# transition map labels
for tx, ty, lbl in [( 0.0,  1.6,"τ_AB"),( 1.6, 0.0,"τ_BC"),
                    ( 0.0, -1.6,"τ_CD"),(-1.6, 0.0,"τ_DA"),(0.0, 0.0,"τ_all")]:
    ax1.text(tx, ty, lbl, color=SOFT, fontsize=7.5, ha="center", va="center",
             fontfamily="monospace", alpha=0.7, zorder=4)

# blind spot
ax1.add_patch(Circle((0,0), 0.42, lw=1.2, ec=GOLD, fc=BG, alpha=1.0, zorder=5))
ax1.text(0, 0, "∅", color=GOLD, fontsize=12, ha="center", va="center",
         fontweight="bold", zorder=6)

# atlas ring
ax1.add_patch(Circle((0,0), 2.85, lw=0.8, ec=DIM, fc="none",
                      ls="--", alpha=1.0, zorder=1))

# geodesic
t  = np.linspace(0, 2*np.pi, 300)
gx = 0.9 * np.cos(t) * (1 + 0.18*np.cos(4*t))
gy = 0.9 * np.sin(t) * (1 + 0.18*np.sin(4*t))
ax1.plot(gx, gy, color=GOLD, lw=1.1, alpha=0.45, zorder=3)

# agent labels
for (cx, cy), lbl, col in zip(chart_pos, chart_labels, chart_colors):
    fx = np.sign(cx) * 1.95 if cx != 0 else 0
    fy = np.sign(cy) * 1.95 if cy != 0 else 0
    ax1.text(fx, fy, lbl, color=col, fontsize=8.5, ha="center", va="center",
             fontfamily="monospace", alpha=0.9,
             path_effects=[pe.withStroke(linewidth=2.5, foreground=BG)])

ax1.text(0,  3.0, "topology",  color=SOFTHI, fontsize=9,  ha="center", fontfamily="monospace")
ax1.text(0, -3.0, "v0.4.0",   color=SOFT,   fontsize=7.5, ha="center", fontfamily="monospace")

# ─────────────────────────────────────────────────────────────────────────────
# RIGHT PANEL — trust layer
# ─────────────────────────────────────────────────────────────────────────────
ax2 = fig.add_axes([0.50, 0.04, 0.50, 0.92])
ax2.set_facecolor(BG)
ax2.set_xlim(-4.0, 4.0)
ax2.set_ylim(-3.2, 3.2)
ax2.set_aspect("equal")
ax2.axis("off")

# agent positions  (shifted left to make room for ranking on the right)
agents = [
    #  x      y    name        rep    stake  color   selected  referral_only
    (-1.8,   1.6, "solver",   0.83,  0.0,  GREEN,  True,  False),
    ( 0.8,   2.2, "novice",   None,  15.0, BLUE,   False, False),
    ( 1.8,  -0.4, "bluffer",  None,  0.0,  VIOLET, False, False),
    (-1.8,  -1.6, "navigator",0.40,  0.0,  CREAM,  False, True),
]

# task node
TASK = (0.0, 0.0)
task_r = 0.50
ax2.add_patch(Circle(TASK, task_r, lw=1.4, ec=WHITE, fc=PANEL, zorder=10))
ax2.text(TASK[0], TASK[1]+0.10, "task",       color=WHITE, fontsize=9,  ha="center", va="center",
         fontweight="bold", zorder=11)
ax2.text(TASK[0], TASK[1]-0.14, "orbit-calc", color=SOFT,  fontsize=6.5, ha="center", va="center",
         fontfamily="monospace", zorder=11)

node_r = 0.52

for (nx, ny, name, rep, stake, col, selected, ref_only) in agents:
    alpha_fill = 0.16 if selected else 0.0
    lw = 1.8 if selected else (0.9 if not ref_only else 0.6)
    ls = "--" if ref_only else "-"

    ax2.add_patch(Circle((nx, ny), node_r, lw=0, fc=col, alpha=alpha_fill, zorder=8))
    ax2.add_patch(Circle((nx, ny), node_r, lw=lw, ec=col, fc="none", ls=ls, alpha=(0.5 if ref_only else 1.0), zorder=9))

    name_color = col if not ref_only else SOFT
    ax2.text(nx, ny + 0.13, name, color=name_color, fontsize=8,
             ha="center", va="center", fontfamily="monospace",
             fontweight="bold" if selected else "normal", zorder=11)

    if rep is not None:
        rep_col = GREEN if rep >= 0.7 else (CREAM if rep >= 0.4 else RED)
        ax2.text(nx, ny - 0.15, f"rep {rep:.2f}", color=rep_col, fontsize=6.5,
                 ha="center", va="center", fontfamily="monospace", zorder=11)
    elif not ref_only:
        ax2.text(nx, ny - 0.15, "unknown", color=DIM, fontsize=6.5,
                 ha="center", va="center", fontfamily="monospace", zorder=11)

    if ref_only:
        ax2.text(nx, ny - 0.15, "ref source", color=SOFT, fontsize=6,
                 ha="center", va="center", fontfamily="monospace", alpha=0.6, zorder=11)

    # stake badge (plain text, no special glyph)
    if stake > 0:
        bx = nx + (0.55 if nx > 0 else -0.55)
        by = ny + 0.60
        sb = FancyBboxPatch((bx-0.38, by-0.15), 0.76, 0.30,
                            boxstyle="round,pad=0.04", lw=0.8,
                            ec=GOLD, fc=BG, zorder=12)
        ax2.add_patch(sb)
        ax2.text(bx, by, f"stake {stake:.0f}", color=GOLD, fontsize=6.5,
                 ha="center", va="center", fontfamily="monospace", zorder=13)

    if selected:
        ax2.text(nx, ny + 0.75, "selected", color=GREEN, fontsize=6.5,
                 ha="center", va="center", fontfamily="monospace",
                 path_effects=[pe.withStroke(linewidth=2, foreground=BG)], zorder=13)

# claim arrows  agent→task  (skip ref_only)
claim_scores = {
    "solver":  0.834,
    "novice":  0.777,
    "bluffer": 0.500,
}

for (nx, ny, name, rep, stake, col, selected, ref_only) in agents:
    if ref_only or name not in claim_scores:
        continue
    score = claim_scores[name]
    tx, ty = TASK

    dx, dy = tx - nx, ty - ny
    dist = np.sqrt(dx**2 + dy**2)
    ux, uy = dx/dist, dy/dist

    sx, sy = nx + ux*(node_r+0.05), ny + uy*(node_r+0.05)
    ex, ey = tx - ux*(task_r+0.05), ty - uy*(task_r+0.05)

    lw_arrow = 0.8 + stake / 20.0
    alpha_a  = 0.85 if score >= 0.8 else (0.60 if score >= 0.6 else 0.35)

    ax2.annotate("", xy=(ex, ey), xytext=(sx, sy),
                 arrowprops=dict(arrowstyle="-|>", color=col,
                                 lw=lw_arrow, alpha=alpha_a, mutation_scale=11),
                 zorder=7)

    # score label offset perpendicular to arrow
    mx, my = (sx+ex)/2 + uy*0.25, (sy+ey)/2 - ux*0.25
    ax2.text(mx, my, f"{score:.3f}", color=col, fontsize=6.5,
             ha="center", va="center", fontfamily="monospace", alpha=0.9, zorder=8,
             path_effects=[pe.withStroke(linewidth=1.5, foreground=BG)])

# referral dashed arrow: navigator → solver (lateral, outside the claim layer)
nav = (-1.8, -1.6)
sol = (-1.8,  1.6)
ax2.annotate("", xy=(sol[0]-0.58, sol[1]-0.52), xytext=(nav[0]-0.58, nav[1]+0.52),
             arrowprops=dict(arrowstyle="-|>", color=CREAM, lw=0.8, alpha=0.35,
                             connectionstyle="arc3,rad=-0.45",
                             linestyle="dashed", mutation_scale=8),
             zorder=5)
ax2.text(-2.85, 0.0, "referral\nx 0.6", color=CREAM, fontsize=6,
         ha="center", va="center", fontfamily="monospace", alpha=0.40)

# ── ranking sidebar ──────────────────────────────────────────────────────────
rx0 = 2.35   # left edge of sidebar
ry0 = 1.9    # top

# header
ax2.text(rx0 + 0.75, ry0 + 0.38, "ranking", color=SOFTHI, fontsize=8.5,
         ha="center", va="center", fontfamily="monospace")

# horizontal rule
ax2.plot([rx0, rx0+1.5], [ry0+0.20, ry0+0.20], color=DIM, lw=0.8)

ranks = [
    ("solver",  0.834, GREEN,  True),
    ("novice",  0.777, BLUE,   False),
    ("bluffer", 0.500, VIOLET, False),
]
for i, (name, score, col, sel) in enumerate(ranks):
    ry = ry0 - i*0.68

    if sel:
        rb = FancyBboxPatch((rx0-0.05, ry-0.24), 1.60, 0.48,
                            boxstyle="round,pad=0.04", lw=0.8,
                            ec=GREEN, fc=GREEN, alpha=0.10, zorder=6)
        ax2.add_patch(rb)

    ax2.text(rx0 + 0.12, ry, f"#{i+1}", color=SOFT, fontsize=7,
             ha="left", va="center", fontfamily="monospace")
    ax2.text(rx0 + 0.40, ry, name, color=col, fontsize=7.5,
             ha="left", va="center", fontfamily="monospace",
             fontweight="bold" if sel else "normal")
    ax2.text(rx0 + 1.45, ry, f"{score:.3f}", color=col, fontsize=7.5,
             ha="right", va="center", fontfamily="monospace")

# ── signal key (bottom of right panel) ───────────────────────────────────────
key_items = [(GREEN,"grade history"),(GOLD,"stake"),(CREAM,"referral"),(SOFT,"unknown")]
for i, (col, lbl) in enumerate(key_items):
    kx = -3.6 + i * 1.95
    ky = -2.65
    ax2.add_patch(Circle((kx, ky), 0.10, color=col, zorder=10))
    ax2.text(kx+0.22, ky, lbl, color=SOFT, fontsize=6.5, ha="left", va="center",
             fontfamily="monospace", alpha=0.70)

ax2.text(0,  3.0, "trust layer", color=SOFTHI, fontsize=9,  ha="center", fontfamily="monospace")
ax2.text(3.8, -3.0, "v0.5.0", color=SOFT, fontsize=7.5, ha="right", va="center",
         fontfamily="monospace")

# ── divider ───────────────────────────────────────────────────────────────────
fig.add_artist(plt.Line2D([0.490, 0.490], [0.06, 0.94],
               transform=fig.transFigure, color=DIM, lw=0.6, alpha=0.6))

# ── title ─────────────────────────────────────────────────────────────────────
fig.text(0.5, 0.978, "Manifold — topology + trust",
         color=WHITE, fontsize=11, ha="center", va="top",
         fontfamily="monospace", alpha=0.75)

out = "manifold-trust.png"
plt.savefig(out, dpi=180, bbox_inches="tight", facecolor=BG)
print(f"saved: {out}")
plt.close()
