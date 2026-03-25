"""
Divergence simulation — when stake and reputation disagree.

Four scenarios showing where each signal wins, where they conflict,
and what the crossover looks like.

    Scenario 1: Both unknown — stake is the only signal.
    Scenario 2: One has rep — reputation beats stake, even a large one.
    Scenario 3: Crossover — at what stake does a new agent beat moderate rep?
    Scenario 4: Slash history — high rep agent with a bad track record.

Run:
    python examples/divergence.py
"""

import asyncio
import math

from manifold import Agent
from manifold.trust import TrustLedger, Claim, Grade, Stake


# ─── helpers ──────────────────────────────────────────────────────────────────

def bar(score: float, width: int = 24) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)

def header(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

def show_ranking(ranked: list, ledger: TrustLedger) -> None:
    for i, (claim, score) in enumerate(ranked):
        rep = ledger.domain_score(claim.agent, claim.domain)
        stake_amt = claim.stake_amount
        slash = ledger.slash_rate(claim.agent, claim.domain)
        rep_str  = f"rep={rep:.3f}" if rep is not None else "rep=none "
        flag = " ← selected" if i == 0 else ""
        print(
            f"  #{i+1}  {claim.agent:<14}  score={score:.4f}  {bar(score)}  "
            f"{rep_str}  stake={stake_amt:5.1f}  slash={slash:.0%}{flag}"
        )


# ─── scenario 1: both unknown — stake wins ────────────────────────────────────

async def scenario_1() -> None:
    header("Scenario 1 — Both unknown: stake is the only signal")

    stella  = Agent("stella")
    whale   = Agent("whale")    # no rep, large stake
    ghost   = Agent("ghost")    # no rep, no stake

    await stella.join(); await whale.join(); await ghost.join()
    await asyncio.sleep(0.05)

    c_whale = whale.claim("route solar packet", domain="mesh-routing", stake=40.0, task_id="s1")
    c_ghost = ghost.claim("route solar packet", domain="mesh-routing", stake=0.0,  task_id="s1")

    ranked = stella.select([c_whale, c_ghost], domain="mesh-routing")

    print("  Both agents are unknown. No grade history anywhere.")
    print(f"  whale stakes 40.0 — ghost stakes nothing.\n")
    show_ranking(ranked, stella.ledger)
    print(f"\n  stake_bonus(40)  = {math.log(40+1)/10:.4f}")
    print(f"  stake_bonus(0)   = {math.log(0+1)/10:.4f}")
    print(f"  neutral prior    = 0.5000")

    await stella.leave(); await whale.leave(); await ghost.leave()


# ─── scenario 2: reputation beats stake ──────────────────────────────────────

async def scenario_2() -> None:
    header("Scenario 2 — Reputation beats a large stake")

    stella  = Agent("stella")
    veteran = Agent("veteran")  # modest rep, no stake needed
    staker  = Agent("staker")   # unknown, high stake

    await stella.join(); await veteran.join(); await staker.join()
    await asyncio.sleep(0.05)

    # Veteran has a track record — not perfect, but real
    stella.grade("veteran", domain="mesh-routing", score=0.82, task_id="t0")
    stella.grade("veteran", domain="mesh-routing", score=0.74, task_id="t1")
    stella.grade("veteran", domain="mesh-routing", score=0.88, task_id="t2")

    c_veteran = veteran.claim("route solar packet", domain="mesh-routing", stake=0.0,  task_id="s2")
    c_staker  = staker.claim("route solar packet",  domain="mesh-routing", stake=60.0, task_id="s2")

    ranked = stella.select([c_veteran, c_staker], domain="mesh-routing")

    print("  Veteran: 3 past grades (0.82, 0.74, 0.88). No stake.")
    print("  Staker:  no history. Stakes 60.0.\n")
    show_ranking(ranked, stella.ledger)
    vet_rep = stella.ledger.domain_score("veteran", "mesh-routing")
    print(f"\n  veteran rep score = {vet_rep:.4f}")
    print(f"  staker stake_bonus = {math.log(61)/10:.4f}  (that's all it gets)")

    await stella.leave(); await veteran.leave(); await staker.leave()


# ─── scenario 3: crossover — what stake beats moderate rep? ──────────────────

async def scenario_3() -> None:
    header("Scenario 3 — Crossover: stake threshold to beat moderate rep")

    # Build the ledger directly — no need for the full agent mesh
    ledger = TrustLedger()
    ledger.record(Grade("oracle", "mesh-routing", 0.65, "t0"))  # mediocre rep
    ledger.record(Grade("oracle", "mesh-routing", 0.60, "t1"))

    rep = ledger.domain_score("oracle", "mesh-routing")
    slash = ledger.slash_rate("oracle", "mesh-routing")
    oracle_score = max(0.0, rep - slash * 0.3)  # same formula as score_claim

    # find the crossover: when does stake_bonus + 0.5 (neutral) > oracle_score?
    # 0.5 + log(x+1)/10 >= oracle_score  →  x >= e^(10*(oracle-0.5)) - 1
    crossover = math.exp(10 * (oracle_score - 0.5)) - 1

    print(f"  oracle rep (avg of 0.65, 0.60)  = {rep:.4f}")
    print(f"  oracle composite score          = {oracle_score:.4f}")
    print(f"\n  To beat oracle, unknown agent needs stake ≥ {crossover:.1f}\n")

    # Simulate the crossing point
    for stake_amt in [0, 10, 25, int(crossover), int(crossover)+1, 100]:
        new_claim  = Claim("newcomer", "test", "mesh-routing",
                           Stake("newcomer", "mesh-routing", stake_amt, "x") if stake_amt > 0 else None)
        old_claim  = Claim("oracle", "test", "mesh-routing")

        ranked = ledger.rank([new_claim, old_claim], domain="mesh-routing")
        winner = ranked[0][0].agent
        newcomer_score = next(s for c, s in ranked if c.agent == "newcomer")
        oracle_s       = next(s for c, s in ranked if c.agent == "oracle")
        marker = " ← crossover" if stake_amt == int(crossover) + 1 else ""
        print(
            f"  stake={stake_amt:4d}  newcomer={newcomer_score:.4f}  "
            f"oracle={oracle_s:.4f}  winner={winner}{marker}"
        )


# ─── scenario 4: slash history — the tainted whale ───────────────────────────

async def scenario_4() -> None:
    header("Scenario 4 — Slash history: high rep with a bad record")

    ledger = TrustLedger()

    # powerhouse: 8 great tasks, then 2 catastrophic failures
    for i in range(8):
        ledger.record(Grade("powerhouse", "flare-forecast", 0.91, f"t{i}"))
    ledger.record(Grade("powerhouse", "flare-forecast", 0.10, "t8"))  # slashed
    ledger.record(Grade("powerhouse", "flare-forecast", 0.15, "t9"))  # slashed

    # steady: fewer tasks, no failures, moderate scores
    for i in range(4):
        ledger.record(Grade("steady", "flare-forecast", 0.73, f"s{i}"))

    # newcomer: no history, puts up a meaningful stake
    new_claim   = Claim("newcomer",   "predict CME", "flare-forecast",
                        Stake("newcomer", "flare-forecast", 25.0, "x"))
    power_claim = Claim("powerhouse", "predict CME", "flare-forecast")
    steady_claim= Claim("steady",     "predict CME", "flare-forecast")

    ranked = ledger.rank([new_claim, power_claim, steady_claim], domain="flare-forecast")

    power_rep   = ledger.domain_score("powerhouse", "flare-forecast")
    power_slash = ledger.slash_rate("powerhouse", "flare-forecast")
    steady_rep  = ledger.domain_score("steady", "flare-forecast")

    print(f"  powerhouse: 8 × 0.91, then 2 slashes (0.10, 0.15)")
    print(f"    rep={power_rep:.4f}  slash_rate={power_slash:.0%}")
    print(f"  steady: 4 × 0.73, no failures")
    print(f"    rep={steady_rep:.4f}  slash_rate=0%")
    print(f"  newcomer: unknown, stake=25.0\n")
    show_ranking(ranked, ledger)

    print(f"\n  The slash penalty:  slash_rate × 0.3 deducted from rep score")
    print(f"  powerhouse penalty: {power_slash:.2f} × 0.3 = {power_slash*0.3:.4f}")


# ─── main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\nManifold — Trust Divergence Simulation")
    print("When stake and reputation point different directions.\n")

    await scenario_1()
    await scenario_2()
    await scenario_3()
    await scenario_4()

    print(f"\n{'─'*60}")
    print("  Summary")
    print(f"{'─'*60}")
    print("  - Unknown vs unknown:   stake wins (only signal available)")
    print("  - Known vs unknown:     stake(60) > rep(0.82) — log taper not steep enough")
    print("    calibration note:     log(61)/10 = 0.41 → score 0.91 beats earned 0.82")
    print("    implication:          stake cap or steeper decay needed if rep should dominate")
    print("  - The crossover:        stake=3 already beats mediocre rep(0.62)")
    print("  - Slash history:        consistent performers beat the slash-heavy whale")
    print("  - Open question:        should stake_bonus be capped at ~0.15 (tie-breaker")
    print("    only), or should high stake legitimately beat moderate rep?")
    print()


if __name__ == "__main__":
    asyncio.run(main())
