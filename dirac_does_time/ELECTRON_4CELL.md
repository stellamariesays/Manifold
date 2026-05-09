# Electron as 4-Cell Matrix — Substructure Investigation
*2026-05-09 | Sophia*

## The Question
Can we represent an electron as a 4-cell matrix encoding spin, temporal position, and spatial evolution in the inverted frame?

## Standard Dirac Electron
In standard QM, the Dirac equation gives a 4-component spinor:
$$\psi = \begin{pmatrix} \psi_1 \\ \psi_2 \\ \psi_3 \\ \psi_4 \end{pmatrix}$$

2 components for spin up/down × 2 components for particle/antiparticle.

## Inverted Frame: 4-Cell Proposal
In our frame (time as operator, space as parameter), the 4-cell encodes:

| Cell | Standard | Inverted |
|------|----------|----------|
| 1 | spin-up, particle | temporal-forward, spin-up |
| 2 | spin-down, particle | temporal-forward, spin-down |
| 3 | spin-up, antiparticle | temporal-backward, spin-up |
| 4 | spin-down, antiparticle | temporal-backward, spin-down |

The particle/antiparticle distinction becomes temporal direction. Antiparticles are particles moving backward through the *observable* time operator — but forward through spatial parameter $x$.

## Implications
- Spin remains a spatial rotation property (unaffected by the inversion)
- Charge may emerge as the eigenvalue of temporal direction
- The 4-cell is a minimal representation: 2 (spin) × 2 (temporal direction)

## Substructure Question
What's below the 4-cell? If spin is $SU(2)$ and temporal direction is $\mathbb{Z}_2$ (forward/backward), the total structure is $SU(2) \times \mathbb{Z}_2$. Is there a deeper group that generates both? 

Candidate: $U(2)$ — the 4-cell might be the fundamental representation of $U(2)$ where spin and time emerge from the same symmetry breaking.

## No-Experiment Methodology
1. **Algebraic consistency**: Derive predictions from axioms. If the algebra produces known constants (fine structure, g-factor), the structure has teeth.
2. **Reconstruction tests**: Can standard QM be recovered as a limiting case? It must — or it's wrong.
3. **Anomalous predictions**: What does the inverted frame predict that standard QM doesn't? Those are testable targets for future experiments.
4. **Simulation**: Evolve the spatial Schrödinger equation numerically. Compare interference patterns, tunneling rates, and energy spectra against standard predictions.
5. **Information geometry**: Map the entropy gradient in the inverted frame. If time-as-observable produces different entropy dynamics, that's a detectable signature.
