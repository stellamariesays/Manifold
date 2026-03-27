"""
Teacup example — filing and recalling concrete moments.

Run from the repo root:
    python3 examples/teacup.py
"""

from manifold import Teacup, TeacupStore

store = TeacupStore("/tmp/manifold-teacup-example.db")

# File a teacup at the moment of confusion
# Write what you're looking at — file, line, output, the specific thing.
cup1 = Teacup(
    agent="braid",
    topic="agent-keep-rate",
    moment=(
        "eval_memory_recall.sh line 14: CLI_DIR=/Users/alec/jfl-cli. "
        "Agents run in /tmp/jfl-worktree-abc123. Score 0.000 for 216 rounds. "
        "The eval never saw a single change."
    ),
    insight="Eval was measuring the wrong directory — hardcoded CLI_DIR vs tmp worktrees.",
    tags=("eval", "debugging", "directory"),
)

cup2 = Teacup(
    agent="stella",
    topic="argue-fun-word-precision",
    moment=(
        "Opponent's argument: 'Bad Bunny's cultural impact is undeniable.' "
        "The debate question uses the word 'entirely'. "
        "30 arguments about cultural significance. Zero about that one word."
    ),
    insight="The resolution hinged on 'entirely' — not cultural significance. "
             "Find the word the opposition is ignoring.",
    tags=("argumentation", "word-precision", "reading"),
)

store.file(cup1)
store.file(cup2)

print("=== recall by topic ===")
for cup in store.recall("agent-keep-rate"):
    print(f"\n  agent:   {cup.agent}")
    print(f"  topic:   {cup.topic}")
    print(f"  moment:  {cup.moment}")
    print(f"  insight: {cup.insight}")
    print(f"  tags:    {cup.tags}")

print("\n=== recall by tag ===")
for cup in store.recall_by_tag("debugging"):
    print(f"  [{cup.topic}] {cup.moment[:60]}…")

print("\n=== recent (all agents) ===")
for cup in store.recent(n=5):
    print(f"  [{cup.agent}/{cup.topic}] {cup.moment[:50]}…")

print(f"\n{store}")
