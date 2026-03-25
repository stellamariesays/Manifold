"""
Marketplace example — agent selection via stake + reputation.

Stella needs a task done. Three agents claim they can do it.
Two put up a stake. She selects using trust scores:
reputation (prior grades) first, stake size as fallback.

After the task completes, she files a grade. The slashed agent
carries that in its ledger — visible to anyone Stella refers.

Run:
    python examples/marketplace.py
"""

import asyncio
from manifold import Agent, Grade
from manifold.trust import TrustLedger


async def main() -> None:
    # ─── Setup ────────────────────────────────────────────────────────────

    stella  = Agent(name="stella")
    solver  = Agent(name="solver")     # known quantity: previously graded
    novice  = Agent(name="novice")     # new agent: no history, puts up stake
    bluffer = Agent(name="bluffer")    # no history, no stake — pure claim

    await stella.join()
    await solver.join()
    await novice.join()
    await bluffer.join()
    await asyncio.sleep(0.05)

    # ─── Prior history ────────────────────────────────────────────────────
    # Stella has worked with solver before on orbit-calculation.
    # Two past tasks: good delivery, one near-miss.

    stella.grade("solver", domain="orbit-calculation", score=0.92, task_id="t0")
    stella.grade("solver", domain="orbit-calculation", score=0.78, task_id="t1")

    print("=== Prior history ===")
    print(f"solver domain_score (orbit): {stella.ledger.domain_score('solver', 'orbit-calculation'):.2f}")
    print(f"solver slash_rate   (orbit): {stella.ledger.slash_rate('solver', 'orbit-calculation'):.0%}")
    print()

    # ─── New task: three agents claim they can do it ───────────────────────

    # solver: no stake needed — reputation speaks
    c_solver  = solver.claim("compute transfer orbit", domain="orbit-calculation", stake=0.0, task_id="t2")

    # novice: unknown, compensates with stake (helps vs bluffer; not enough to beat earned rep)
    c_novice  = novice.claim("compute transfer orbit", domain="orbit-calculation", stake=15.0, task_id="t2")

    # bluffer: unknown, no stake
    c_bluffer = bluffer.claim("compute transfer orbit", domain="orbit-calculation", stake=0.0, task_id="t2")

    print("=== Claims ===")
    for c in [c_solver, c_novice, c_bluffer]:
        print(f"  {c}")
    print()

    # ─── Selection ────────────────────────────────────────────────────────

    ranked = stella.select(
        claims=[c_solver, c_novice, c_bluffer],
        domain="orbit-calculation",
    )

    print("=== Ranking ===")
    for claim, score in ranked:
        print(f"  {claim.agent:10s}  score={score:.3f}")
    print()

    winner = ranked[0][0]
    print(f"→ Selected: {winner.agent!r}")
    print()

    # ─── Task outcome ─────────────────────────────────────────────────────
    # solver delivers. Stella grades it.

    g = stella.grade("solver", domain="orbit-calculation", score=0.95, task_id="t2")
    print(f"=== Grade filed: {g} ===")
    print()

    # ─── Referral path ────────────────────────────────────────────────────
    # New agent "navigator" has never worked with solver.
    # But she trusts Stella and can ask for a referral.

    navigator = Agent(name="navigator")
    await navigator.join()
    await asyncio.sleep(0.05)

    navigator.grade("novice", domain="orbit-calculation", score=0.40, task_id="t3")   # her own: bad

    print("=== Referral selection ===")
    c2_solver = solver.claim("refine trajectory", domain="orbit-calculation", stake=0.0, task_id="t4")
    c2_novice = novice.claim("refine trajectory", domain="orbit-calculation", stake=0.0, task_id="t4")

    ranked2 = navigator.select(
        claims=[c2_solver, c2_novice],
        domain="orbit-calculation",
        referrals=[stella],           # borrow Stella's grades
        referral_weight=0.6,          # trust her 60%
    )

    print("  navigator's own grade for novice: 0.40 (slash)")
    print("  stella's grades for solver: 0.92, 0.78, 0.95")
    print()
    for claim, score in ranked2:
        print(f"  {claim.agent:10s}  score={score:.3f}")
    print()
    print(f"→ navigator selects: {ranked2[0][0].agent!r} (via referral)")

    # ─── Slash demo ───────────────────────────────────────────────────────
    print()
    print("=== Slash demo ===")

    # novice staked 30 on a second task — and fails
    c_novice2 = novice.claim("predict solar ejection", domain="flare-forecast", stake=30.0, task_id="t5")
    stella.ledger.record_stake(c_novice2.stake)
    g_bad = stella.grade("novice", domain="flare-forecast", score=0.2, task_id="t5")
    print(f"  {g_bad}")
    summary = stella.ledger.summary("novice")
    print(f"  novice flare-forecast record: {summary.get('flare-forecast', {})}")

    await stella.leave()
    await solver.leave()
    await novice.leave()
    await bluffer.leave()
    await navigator.leave()


if __name__ == "__main__":
    asyncio.run(main())
