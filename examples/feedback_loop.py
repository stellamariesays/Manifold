"""
Feedback loop example — topology and trust co-evolving.

Two agents compete for tasks over multiple rounds. One (aligned) shares
focus with the requester and delivers reliably. The other (stranger) has
no shared focus and inconsistent delivery.

Watch both signals converge:
    - topology edge weight rises for aligned (shared focus → graded → trust)
    - trust score rises for aligned (good grades feed back into edge weight)
    - loop_strength is the combined measure: does it compound?

Also shows the proximity boost in action: at what point does topology
closeness tip a ranking where both agents have similar trust?

Run:
    python examples/feedback_loop.py
"""

import asyncio
import random

from manifold import Agent
from manifold.feedback import TrustTopologyBridge, describe_loop
from manifold.trust import TrustLedger


# ─── helpers ──────────────────────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{'─'*64}")
    print(f"  {title}")
    print(f"{'─'*64}")

def bar(v: float, w: int = 20) -> str:
    if v is None: return "░" * w
    return "█" * round(v * w) + "░" * (w - round(v * w))

def loop_line(label: str, state: dict) -> str:
    ew = state["edge_weight"]
    ts = list(state["trust_scores"].values())
    avg_t = sum(ts) / len(ts) if ts else 0.0
    ls = state["loop_strength"]
    ew_s  = f"{ew:.3f}" if ew is not None else " --- "
    ts_s  = f"{avg_t:.3f}" if ts else " --- "
    ls_s  = f"{ls:.3f}" if ls is not None else " --- "
    return (
        f"  {label:<12}  edge={ew_s} {bar(ew or 0)}  "
        f"trust={ts_s} {bar(avg_t)}  loop={ls_s}"
    )


# ─── simulation ───────────────────────────────────────────────────────────────

async def main() -> None:
    random.seed(42)

    bridge = TrustTopologyBridge(
        topology_trust_weight=0.4,  # trust influences 40% of edge weight
        proximity_weight=0.05,      # topology adds up to 5% stake boost
    )

    header("Setup")
    print("  stella    — requester, thinks about 'solar-prediction'")
    print("  aligned   — shares focus 'solar-prediction', delivers well")
    print("  stranger  — different focus 'crypto-routing', inconsistent")
    print(f"\n  bridge: topology_trust_weight={bridge.topology_trust_weight}  "
          f"proximity_weight={bridge.proximity_weight}")

    stella   = Agent("stella")
    aligned  = Agent("aligned")
    stranger = Agent("stranger")

    await stella.join(); await aligned.join(); await stranger.join()
    await asyncio.sleep(0.05)

    # Establish shared focus — this creates topology edges before any grading
    await stella.think("solar-prediction")
    await aligned.think("solar-prediction")    # shared → strong edge
    await stranger.think("crypto-routing")      # different → weak edge
    await asyncio.sleep(0.05)

    header("Initial topology (before any tasks)")
    s_aligned  = describe_loop("stella", "aligned",  stella.ledger, stella._topology)
    s_stranger = describe_loop("stella", "stranger", stella.ledger, stella._topology)
    print(loop_line("aligned",  s_aligned))
    print(loop_line("stranger", s_stranger))
    print()
    print("  trust is empty — edge weight is pure focus similarity.")
    print(f"  aligned edge: {s_aligned['edge_weight']}   "
          f"stranger edge: {s_stranger['edge_weight']}")

    # ─── 8 rounds of task / grade / sync ──────────────────────────────────────

    header("8 rounds — task → grade → sync_edge")
    domain = "solar-prediction"

    aligned_scores  = [0.91, 0.87, 0.93, 0.85, 0.94, 0.90, 0.88, 0.96]
    stranger_scores = [0.72, 0.41, 0.88, 0.30, 0.65, 0.79, 0.22, 0.70]
    # stranger is volatile — some good, some slashed

    for rnd in range(8):
        task_id = f"t{rnd}"

        # Both agents claim the task
        c_aligned  = aligned.claim("predict CME arrival",  domain=domain, stake=5.0, task_id=task_id)
        c_stranger = stranger.claim("predict CME arrival", domain=domain, stake=5.0, task_id=task_id)

        # Apply proximity boost before ranking
        boosted = bridge.proximity_boost(
            [c_aligned, c_stranger],
            topology=stella._topology,
            ledger=stella.ledger,
            domain=domain,
        )
        ranked = stella.select(boosted, domain=domain)
        winner_name = ranked[0][0].agent

        # Assign task to winner and grade the outcome
        if winner_name == "aligned":
            score = aligned_scores[rnd]
            stella.grade("aligned", domain=domain, score=score, task_id=task_id)
            bridge.sync_edge("stella", "aligned", stella.ledger, stella._topology, domain=domain)
        else:
            score = stranger_scores[rnd]
            stella.grade("stranger", domain=domain, score=score, task_id=task_id)
            bridge.sync_edge("stella", "stranger", stella.ledger, stella._topology, domain=domain)

        # State after this round
        a_state = describe_loop("stella", "aligned",  stella.ledger, stella._topology)
        s_state = describe_loop("stella", "stranger", stella.ledger, stella._topology)

        print(f"\n  Round {rnd+1}  winner={winner_name}  score={score:.2f}")
        print(f"  {loop_line('aligned',  a_state)}")
        print(f"  {loop_line('stranger', s_state)}")

    # ─── Final state ──────────────────────────────────────────────────────────

    header("Final state")
    a_final = describe_loop("stella", "aligned",  stella.ledger, stella._topology)
    s_final = describe_loop("stella", "stranger", stella.ledger, stella._topology)

    print(loop_line("aligned",  a_final))
    print(loop_line("stranger", s_final))

    print(f"\n  aligned  grades: {a_final['grade_count']}  "
          f"slash_rate: {a_final['avg_slash']:.0%}  "
          f"loop_strength: {a_final['loop_strength']}")
    print(f"  stranger grades: {s_final['grade_count']}  "
          f"slash_rate: {s_final['avg_slash']:.0%}  "
          f"loop_strength: {s_final['loop_strength']}")

    # ─── Head-to-head with proximity active ───────────────────────────────────

    header("Head-to-head: same trust, proximity decides")
    print("  Synthetic scenario: give both agents identical grade history.")
    print("  Only topology edge differs. Does proximity_boost tip the ranking?")
    print()

    even_ledger = TrustLedger()
    from manifold.trust import Grade as _Grade
    for i in range(4):
        even_ledger.record(_Grade("aligned",  domain, 0.80, f"e{i}"))
        even_ledger.record(_Grade("stranger", domain, 0.80, f"e{i}"))

    # Use stella's topology (aligned has strong edge, stranger has weak)
    c_a = aligned.claim("predict CME arrival",  domain=domain, stake=0.0, task_id="h1")
    c_s = stranger.claim("predict CME arrival", domain=domain, stake=0.0, task_id="h1")

    # Without boost
    from manifold.trust import TrustLedger as _TL
    raw_ranked = even_ledger.rank([c_a, c_s], domain=domain)
    print("  Without proximity boost:")
    for claim, score in raw_ranked:
        print(f"    {claim.agent:<12}  score={score:.4f}")

    # With boost
    boosted_claims = bridge.proximity_boost(
        [c_a, c_s],
        topology=stella._topology,
        ledger=even_ledger,
        domain=domain,
    )
    print(f"\n  With proximity boost (weight={bridge.proximity_weight}):")
    boosted_scores = even_ledger.rank(boosted_claims, domain=domain)
    for i, (claim, score) in enumerate(boosted_scores):
        eff_stake = next(bc.stake_amount for bc in boosted_claims if bc.agent == claim.agent)
        flag = " ← topology tips it" if i == 0 and boosted_scores[0][0].agent != raw_ranked[0][0].agent else ""
        print(f"    {claim.agent:<12}  score={score:.4f}  eff_stake={eff_stake:.2f}{flag}")

    # ─── Calibration note ─────────────────────────────────────────────────────

    header("Calibration notes from this run")
    print("  1. topology_trust_weight=0.4 means 60% of edge weight stays focus-based.")
    print("     Trust can pull an agent closer but can't fully override focus mismatch.")
    print()
    print("  2. proximity_weight=0.05 is intentionally small.")
    print("     At edge=1.0: adds 5 effective stake → log(6)/10 = 0.018 score boost.")
    print("     Enough to tip a tie. Not enough to promote an unknown over a veteran.")
    print()
    print("  3. The loop compounding question:")
    a_init = s_aligned["edge_weight"] if (s_aligned := describe_loop("stella", "aligned", TrustLedger(), stella._topology)) else None
    print(f"     aligned  edge at start: ~{a_init:.3f}  (focus similarity only)")
    print(f"     aligned  edge at end:   {a_final['edge_weight']:.3f}  (blended with trust)")
    delta = (a_final['edge_weight'] or 0) - (a_init or 0)
    print(f"     delta: {delta:+.3f}  — trust pulled the edge {'up' if delta > 0 else 'down'}")
    print()

    await stella.leave(); await aligned.leave(); await stranger.leave()


if __name__ == "__main__":
    asyncio.run(main())
