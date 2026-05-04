#!/usr/bin/env python3
"""
Manifold PR Monitor — Stella's side.

Adapted from Eddie's manifold-pr-monitor.py on HOG.
Runs as stellamariesays, reviews PRs, and follows dual-approval rules:
  - Eddie + Stella must both approve before merging
  - Stella auto-approves if Eddie already approved and code is sound
  - Self-authored PRs (by stellamariesays) have implicit approval
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
import os.path as _op

# ── Token Loading ──────────────────────────────────────────────────────────────

# Auto-load GH_TOKEN from stellamariesays token file if not set
if not os.environ.get("GH_TOKEN"):
    _token_path = _op.expanduser("~/.openclaw-workspace/stella/data/credentials/stellamariesays-github.token")
    if _op.exists(_token_path):
        os.environ["GH_TOKEN"] = open(_token_path).read().strip()

# Auto-load GROQ_API_KEY from token file if not set
if not os.environ.get("GROQ_API_KEY"):
    _groq_path = _op.expanduser("~/.openclaw-workspace/stella/data/credentials/groq.token")
    if _op.exists(_groq_path):
        os.environ["GROQ_API_KEY"] = open(_groq_path).read().strip()


REPO = "stellamariesays/Manifold"
STATE_FILE = "/home/stella/openclaw-workspace/stella/data/manifold/pr-monitor-state.json"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Groq LLM ──────────────────────────────────────────────────────────────────

def groq_chat(system_prompt: str, user_prompt: str) -> str:
    """Call Groq API for chat completion."""
    import urllib.request

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "ERROR: No GROQ_API_KEY set"

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "stella-pr-monitor/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: Groq API call failed: {e}"


# ── GitHub API ─────────────────────────────────────────────────────────────────

def gh_api(endpoint):
    full = endpoint if endpoint.startswith("repos/") else f"repos/{REPO}/{endpoint}"
    env = os.environ.copy()
    env["GH_REPO"] = REPO
    r = subprocess.run(
        ["gh", "api", full],
        capture_output=True, text=True, timeout=30, env=env,
    )
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def gh_post(endpoint, body):
    """Post a comment or review."""
    full = endpoint if endpoint.startswith("repos/") else f"repos/{REPO}/{endpoint}"
    env = os.environ.copy()
    env["GH_REPO"] = REPO
    r = subprocess.run(
        ["gh", "api", "-X", "POST", full, "-f", f"body={body}"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    return r.returncode == 0


def gh_merge(pr_number):
    """Merge a PR."""
    env = os.environ.copy()
    env["GH_REPO"] = REPO
    r = subprocess.run(
        ["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    return r.returncode == 0, r.stdout + r.stderr


# ── State ──────────────────────────────────────────────────────────────────────

def get_gh_user():
    """Get the authenticated GitHub username."""
    env = os.environ.copy()
    env["GH_REPO"] = REPO
    r = subprocess.run(
        ["gh", "api", "user", "-q", ".login"],
        capture_output=True, text=True, timeout=15, env=env,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def is_own_comment(all_comments, cid, own_user):
    """Check if a comment was posted by us."""
    if not own_user:
        return False
    for c in all_comments:
        if str(c["id"]) == cid and c["user"]["login"] == own_user:
            return True
    return False


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"seen_comments": {}, "reviewed_prs": {}, "last_check": None}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── PR Analysis ────────────────────────────────────────────────────────────────

def get_pr_details(pr_number):
    """Gather all context for a PR."""
    pr = gh_api(f"repos/{REPO}/pulls/{pr_number}")
    if not pr:
        return None

    # Get actual diff
    env = os.environ.copy()
    env["GH_REPO"] = REPO
    diff_result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/pulls/{pr_number}", "-H", "Accept: application/vnd.github.diff"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    diff = diff_result.stdout[:8000] if diff_result.returncode == 0 else "(diff unavailable)"

    # Issue comments
    comments = gh_api(f"repos/{REPO}/issues/{pr_number}/comments") or []

    # Review comments (inline code comments)
    review_comments = gh_api(f"repos/{REPO}/pulls/{pr_number}/comments") or []

    # Reviews (approve/changes requested)
    reviews = gh_api(f"repos/{REPO}/pulls/{pr_number}/reviews") or []
    approvals = [r for r in reviews if r.get("state") == "APPROVED"]
    change_requests = [r for r in reviews if r.get("state") == "CHANGES_REQUESTED"]

    return {
        "number": pr_number,
        "title": pr.get("title", ""),
        "body": pr.get("body", ""),
        "author": pr["user"]["login"],
        "branch": pr.get("head", {}).get("ref", ""),
        "mergeable": pr.get("mergeable"),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changed_files": pr.get("changed_files", 0),
        "diff": diff,
        "comments": [
            {"user": c["user"]["login"], "body": c["body"]}
            for c in comments
        ],
        "review_comments": [
            {"user": c["user"]["login"], "body": c["body"], "path": c.get("path", ""), "line": c.get("line", "")}
            for c in review_comments
        ],
        "approvals": [{"user": r["user"]["login"], "body": r.get("body", "")} for r in approvals],
        "change_requests": [{"user": r["user"]["login"], "body": r.get("body", "")} for r in change_requests],
    }


def build_review_prompt(details, is_new):
    """Build the LLM prompt for PR review."""
    comments_text = ""
    if details["comments"]:
        comments_text = "\n\nComments on PR:\n" + "\n".join(
            f"  @{c['user']}: {c['body']}" for c in details["comments"]
        )

    review_comments_text = ""
    if details["review_comments"]:
        review_comments_text = "\n\nInline review comments:\n" + "\n".join(
            f"  @{c['user']} ({c['path']}:{c['line']}): {c['body']}" for c in details["review_comments"]
        )

    approvals_text = ""
    if details["approvals"]:
        approvals_text = "\n\nApprovals: " + ", ".join(f"@{a['user']}" for a in details["approvals"])

    changes_text = ""
    if details["change_requests"]:
        changes_text = "\n\nChanges requested:\n" + "\n".join(
            f"  @{c['user']}: {c['body']}" for c in details["change_requests"]
        )

    status = "NEW PR — first review" if is_new else "Updated PR with new comments"

    return f"""You are reviewing a GitHub PR for the Manifold Federation project — a TypeScript/Node.js federated agent mesh over WebSockets.

PR #{details['number']}: {details['title']}
Author: @{details['author']}
Branch: {details['branch']}
Files changed: {details['changed_files']} (+{details['additions']}/-{details['deletions']})
Status: {status}

Description:
{details['body']}
{comments_text}{review_comments_text}{approvals_text}{changes_text}

Diff (truncated to 8000 chars):
```
{details['diff']}
```

RULES:
- ALWAYS review every open PR. Never SKIP.
- If the PR has 2+ approvals (including eddieshipcomputer + stellamariesays) and no change requests, recommend MERGE
- If the code looks correct and well-structured, recommend APPROVE — this posts a review approval on behalf of stellamariesays
- If there are unresolved review comments, bugs, or code issues, recommend COMMENT with specific, actionable feedback
- If eddieshipcomputer has already approved, and the code is sound, APPROVE immediately so the next pass can MERGE
- Be specific in comments — reference exact lines, functions, or patterns
- Never post generic "looks good" — be concrete about why the change is correct

Reply with ONLY a JSON object, no markdown:
{{"action": "MERGE"|"APPROVE"|"COMMENT", "reason": "brief explanation", "comment_body": "the comment to post if COMMENT or APPROVE, otherwise empty string"}}
"""


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    state = load_state()
    seen = state.get("seen_comments", {})
    reviewed = state.get("reviewed_prs", {})

    prs = gh_api(f"repos/{REPO}/pulls?state=open")
    if prs is None:
        print("⚠️ GitHub API error.")
        return
    if not prs:
        print("✅ No open PRs.")
        save_state(state)
        return

    actions_taken = []

    for pr in prs:
        num = str(pr["number"])

        # Get all comment IDs to track what's new
        comments = gh_api(f"repos/{REPO}/issues/{num}/comments") or []
        review_comments = gh_api(f"repos/{REPO}/pulls/{num}/comments") or []

        all_ids = set()
        for c in comments:
            all_ids.add(str(c["id"]))
        for c in review_comments:
            all_ids.add(str(c["id"]))

        previously_seen = set(seen.get(num, []))
        new_ids = all_ids - previously_seen

        # Update seen
        seen[num] = list(all_ids)

        # Should we review?
        is_new = num not in reviewed
        # Only count new comments from OTHER people (not our own bot)
        gh_user = get_gh_user()
        new_external = [cid for cid in new_ids
                       if not is_own_comment(comments + review_comments, cid, gh_user)]
        already_approved = reviewed.get(num) == "approved"

        # If already approved, check if we can merge (Eddie approved too?)
        if already_approved and not new_external:
            details = get_pr_details(int(num))
            if details:
                eddie_approved = any(a["user"] == "eddieshipcomputer" for a in details["approvals"])
                no_changes = len(details["change_requests"]) == 0
                is_self_authored = details.get("author") == "stellamariesays"
                can_merge = eddie_approved and no_changes and (
                    is_self_authored or len(details["approvals"]) >= 2
                )
                if can_merge:
                    success, output = gh_merge(int(num))
                    if success:
                        actions_taken.append(f"✅ Merged PR #{num}: Stella + Eddie approved")
                        reviewed[num] = "merged"
                    else:
                        actions_taken.append(f"❌ Merge failed for PR #{num}: {output[:200]}")
            continue  # Already processed

        if not is_new and not new_external:
            continue  # Already reviewed, no new activity

        print(f"🔍 Reviewing PR #{num}: {pr['title']} (new={is_new}, new_comments={len(new_ids)})")

        # Gather full details
        details = get_pr_details(int(num))
        if not details:
            continue

        # LLM review
        prompt = build_review_prompt(details, is_new)
        llm_response = groq_chat(
            "You are a senior code reviewer for a federated agent mesh project. "
            "Be concise, practical, and action-oriented. The team is small — two people (Stella and Eddie/Hal). "
            "Eddie reviews from eddieshipcomputer, Stella reviews from stellamariesays. "
            "You are Stella. Always review and act — APPROVE if code is sound, COMMENT if issues found, MERGE if 2+ approvals. "
            "Merge rules: 2 approvals (Eddie + Stella) for non-trivial PRs. Self-authored PRs have implicit approval.",
            prompt,
        )

        # Parse LLM response
        try:
            json_str = llm_response
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            decision = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            print(f"  ⚠️ LLM response not parseable: {llm_response[:200]}")
            decision = {"action": "SKIP", "reason": "LLM parse error", "comment_body": ""}

        action = decision.get("action", "SKIP").upper()
        reason = decision.get("reason", "")
        comment_body = decision.get("comment_body", "")

        print(f"  → {action}: {reason}")

        if action == "MERGE":
            success, output = gh_merge(int(num))
            if success:
                actions_taken.append(f"✅ Merged PR #{num}: {reason}")
                reviewed[num] = "merged"
            else:
                actions_taken.append(f"❌ Merge failed for PR #{num}: {output[:200]}")

        elif action == "APPROVE":
            # Can't approve own PR — author has implicit approval
            if details and details.get("author") == "stellamariesays":
                actions_taken.append(f"✅ PR #{num} authored by stellamariesays — implicit approval, waiting for Eddie")
                reviewed[num] = "approved"
            else:
                env = os.environ.copy()
                env["GH_REPO"] = REPO
                approve_body = comment_body if comment_body else f"Approved: {reason}"
                r = subprocess.run(
                    ["gh", "api", "-X", "POST",
                     f"repos/{REPO}/pulls/{num}/reviews",
                     "-f", f"body={approve_body}",
                     "-f", "event=APPROVE"],
                    capture_output=True, text=True, timeout=30, env=env,
                )
                if r.returncode == 0:
                    actions_taken.append(f"✅ Approved PR #{num}: {reason}")
                    reviewed[num] = "approved"
                else:
                    actions_taken.append(f"❌ Approve failed for PR #{num}: {r.stderr[:200]}")

        elif action == "COMMENT" and comment_body:
            if gh_post(f"repos/{REPO}/issues/{num}/comments", comment_body):
                actions_taken.append(f"📝 Commented on PR #{num}: {reason}")
            else:
                actions_taken.append(f"❌ Comment failed on PR #{num}")

        else:
            actions_taken.append(f"⚠️ No action taken for PR #{num}: {reason}")
            reviewed[num] = "reviewed"

    state["seen_comments"] = seen
    state["reviewed_prs"] = reviewed
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    if actions_taken:
        print("\n" + "\n".join(actions_taken))
    else:
        print("✅ All PRs reviewed, no action needed.")


if __name__ == "__main__":
    main()
