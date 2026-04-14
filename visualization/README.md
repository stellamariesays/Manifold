# Manifold Visualizations

Visualization tools for the Manifold cognitive mesh and federation system.

## Files

### federation-snapshot.html
Static snapshot of the Manifold federation mesh showing:
- **2 hubs**: Trillian + HOG
- **15 agents**: 9 on Trillian, 6 on HOG
- **91 capabilities** across the mesh
- Force-directed graph with animated particle effects along federation link
- Color-coded agents by hub (green=Trillian, magenta=HOG)

**Captured:** 2026-04-14 23:51 WITA

**Live demo:** https://federation.surge.sh

**Usage:** Open in any modern browser. No dependencies, pure HTML/CSS/JavaScript.

### stella_mri.html
(Located in `scripts/stella_mri.html`)

Mesh Resonance Imaging visualization showing:
- Agent capabilities and seams
- High-curvature transition regions
- Dark circles (unclaimed capability gaps)
- Geodesic routing paths

## Development

The federation snapshot is baked data - update by:
1. Capturing new federation state via `/status` and `/agents` endpoints
2. Regenerating HTML with updated SNAPSHOT constant
3. Redeploying to surge.sh

For live federation visualization, run locally on a Tailscale-connected machine that can reach both hub endpoints.
