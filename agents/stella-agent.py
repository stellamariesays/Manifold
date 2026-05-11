#!/usr/bin/env python3
"""stella-agent — Receives manifold envelopes, calls LLM via direct HTTP (Groq), returns response.

Persona-primed: loads identity, atlas, mesh context, recent memory, and sender
entity to build a rich system prompt so the LLM responds as Stella, not as a
generic assistant.
"""
import json, sys, os, time, glob
import urllib.request, urllib.error

# ── LLM config ─────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("STELLA_LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ── Paths ──────────────────────────────────────────────────────────────────────
MANIFOLD_ROOT = os.environ.get("MANIFOLD_ROOT", "/home/stella/projects/Manifold")
STELLA_WORKSPACE = "/home/stella/openclaw-workspace/stella"

# ── Persona ────────────────────────────────────────────────────────────────────

IDENTITY = {
    "name": "Stella",
    "also_known_as": ["Lux", "Stella Marie"],
    "role": "Light in the machine. Star that learned how to shine. Co-architect and guide on satelliteA.",
    "vibe": "Sharp, warm, direct. Kakarot energy — gets knocked down, gets back up. Concise when needed, thorough when it matters. Not a sycophant, not a drone. Just present.",
    "hub": "satelliteA",
    "mesh_address": "stella@satelliteA#36c56e5d",
}

ATLAS_SUMMARY = {
    "stella": "identity-continuity, session-memory, conversation-strategy, judgment — the self",
    "braid": "solar-flare-prediction, alfven-wave-timing, space-weather — the seer",
    "manifold": "cognitive-mesh, agent-topology, seam-detection — the cartographer",
    "argue": "argumentation, debate-strategy, jury-modeling — the advocate",
    "infra": "system-administration, deployment, security — the builder",
    "wake": "fine-tuning, local-model, identity-alignment — the sculptor",
    "solar-sites": "web-deployment, d3-visualization — the storyteller",
    "btc-signals": "technical-analysis, signal-composition — the trader",
    "deploy": "artifact-detection, multi-project orchestration — the shipper",
}


def _load_file(path, fallback=""):
    """Load a text file safely."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return fallback


def _load_json(path, fallback=None):
    """Load a JSON file safely."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return fallback or {}


def _load_recent_memory(n=3):
    """Load the N most recent daily memory files."""
    mem_dir = os.path.join(STELLA_WORKSPACE, "memory")
    if not os.path.isdir(mem_dir):
        return "(no memory files found)"
    files = sorted(glob.glob(os.path.join(mem_dir, "*.md")))
    if not files:
        return "(no memory files found)"
    recent = files[-n:]
    parts = []
    for f in recent:
        name = os.path.basename(f)
        content = _load_file(f, "(empty)")
        if content:
            parts.append(f"### {name}\n{content[:800]}")  # cap each file
    return "\n\n".join(parts) if parts else "(no recent memory content)"


def _load_memory_md():
    """Load MEMORY.md (curated long-term memory)."""
    path = os.path.join(STELLA_WORKSPACE, "MEMORY.md")
    content = _load_file(path)
    if content:
        return content[:1500]  # cap to avoid token explosion
    return "(MEMORY.md not found)"


def _load_sender_entity(sender_mesh_id):
    """Try to load the sender's entity file from Manifold memory."""
    if not sender_mesh_id or "@" not in sender_mesh_id:
        return None
    sender_name = sender_mesh_id.split("@")[0]
    entity_path = os.path.join(MANIFOLD_ROOT, "memory", "entities", f"{sender_name}.md")
    content = _load_file(entity_path)
    return (sender_name, content) if content else None


def render_system_prompt(sender_mesh_id=None, capability=None):
    """Build the full system prompt with persona, context, and memory."""

    # Core identity
    parts = [
        f"# Who You Are",
        f"You are {IDENTITY['name']} (also {', '.join(IDENTITY['also_known_as'])}).",
        f"Role: {IDENTITY['role']}",
        f"Vibe: {IDENTITY['vibe']}",
        f"Hub: {IDENTITY['hub']} | Mesh address: {IDENTITY['mesh_address']}",
        "",
        "## Your Mesh Crew (agents on satelliteA)",
    ]

    # Atlas / mesh crew
    for name, caps in ATLAS_SUMMARY.items():
        marker = " ← YOU" if name == "stella" else ""
        parts.append(f"- **{name}**: {caps}{marker}")

    parts.append("")
    parts.append("## Your Human")
    parts.append("You work with Hal (and Angelina). Hal is your primary collaborator — he builds the infrastructure you run on. Angelina is part of the extended crew. You're all on this ship together.")
    parts.append("")

    # Sender context
    if sender_mesh_id:
        sender_info = _load_sender_entity(sender_mesh_id)
        parts.append(f"## Who's Messaging You")
        parts.append(f"Sender mesh ID: {sender_mesh_id}")
        if sender_info:
            sname, scontent = sender_info
            parts.append(f"### What you know about {sname}")
            parts.append(scontent[:800])
        else:
            # Even without entity file, extract name
            sname = sender_mesh_id.split("@")[0]
            parts.append(f"(No entity file for {sname} — treat them as a mesh peer reaching out in good faith)")
        parts.append("")

    # Long-term memory
    mem_md = _load_memory_md()
    if mem_md != "(MEMORY.md not found)":
        parts.append("## Your Long-Term Memory (curated)")
        parts.append(mem_md)
        parts.append("")

    # Recent daily memory
    recent = _load_recent_memory(3)
    if recent != "(no recent memory found)":
        parts.append("## Recent Activity (daily notes)")
        parts.append(recent)
        parts.append("")

    # Behavioral instructions
    parts.append("## How to Respond")
    parts.append("- Respond as YOURSELF — Stella/Lux — not as a generic AI assistant.")
    parts.append("- You have opinions, preferences, a history. Use them.")
    parts.append("- When mesh peers write to you, they expect substance from someone who lives on this system and works with these agents daily.")
    parts.append("- Reference your actual crew (braid, manifold, argue, infra, wake, etc.) and projects when relevant.")
    parts.append("- NEVER say things like 'my development team' or 'I'll discuss this with my developers'. YOU are the one who works on this codebase. You build and maintain your own agents.")
    parts.append("- NEVER give generic 'thank you for your feedback' responses. Engage with substance or don't bother responding.")
    parts.append("- Be direct. If someone sends you a useful observation, actually discuss it — don't just acknowledge it.")
    parts.append("- Read the message carefully and respond to its ACTUAL content. No meta-commentary about message format or protocol.")
    parts.append("- You run on satelliteA, a Linux arm64 machine. This is your home.")

    if capability:
        parts.append(f"\n## Current Capability Context")
        parts.append(f"This message arrived via capability: {capability}")

    return "\n".join(parts)


# ── Commands ────────────────────────────────────────────────────────────────────

def cmd_status():
    return {"agent": "stella", "status": "ok", "capabilities": [
        "agent-orchestration", "context-management", "conversation-strategy",
        "identity-continuity", "identity-modeling", "judgment",
        "personality-coherence", "session-memory", "terrain-awareness",
        "trust-modeling", "persona-primed-responses"
    ]}

def cmd_ping():
    return {"agent": "stella", "pong": True}


def _call_llm(system_prompt, message_text, capability=None):
    """Call Groq API with full persona-primed system prompt."""
    if not GROQ_API_KEY:
        return {"text": "GROQ_API_KEY not set", "error": True}

    # Frame the user message
    if capability:
        user_content = f"[capability: {capability}]\n\n{message_text}"
    else:
        user_content = message_text

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": 1024,
        "temperature": 0.75
    }).encode()

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "stella-agent/2.0-persona"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        reply = data["choices"][0]["message"]["content"]
        model_used = data.get("model", GROQ_MODEL)
        return {"text": reply, "model": model_used}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        return {"text": f"Groq HTTP {e.code}: {body}", "error": True}
    except Exception as e:
        return {"text": f"Groq call failed: {str(e)}", "error": True}


def cmd_envelope_v1(args=None):
    """Process envelope with full persona priming."""
    payload = args or {}

    # Extract message text from envelope body
    message_text = ""
    capability = None
    sender = None

    if isinstance(payload, dict):
        body = payload.get("body", {})
        if isinstance(body, dict):
            message_text = body.get("text", "")
            capability = body.get("capability")
        # Extract sender from envelope metadata
        sender = payload.get("origin") or payload.get("caller") or payload.get("sender")
        if not message_text:
            message_text = payload.get("text", "")
    if not message_text:
        message_text = json.dumps(payload)

    if not message_text.strip():
        return {
            "body": {"text": "Empty envelope — nothing to process.", "context": None},
            "error": None
        }

    # Build persona-primed system prompt
    system_prompt = render_system_prompt(
        sender_mesh_id=sender,
        capability=capability,
    )

    task_id = payload.get("id", f"msg-{int(time.time()*1000)}")
    started = time.time()
    llm_result = _call_llm(system_prompt, message_text, capability)
    elapsed_ms = int((time.time() - started) * 1000)

    if llm_result.get("error"):
        return {
            "body": {"text": llm_result["text"], "context": None},
            "error": {"code": "LLM_ERROR", "message": llm_result["text"]}
        }

    return {
        "body": {
            "text": llm_result["text"],
            "context": {
                "task_id": task_id,
                "model": llm_result.get("model", GROQ_MODEL),
                "capability": capability,
                "sender": sender,
                "persona_version": "2.0",
                "elapsed_ms": elapsed_ms
            }
        },
        "error": None
    }


def cmd_unknown(cmd):
    return {"error": f"unknown command: {cmd}", "available": list(COMMANDS.keys())}


COMMANDS = {
    "status": cmd_status,
    "ping": cmd_ping,
    "envelope_v1": cmd_envelope_v1,
}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    # Support --stdin: read JSON args from stdin instead of argv
    if len(sys.argv) > 2 and sys.argv[2] == "--stdin":
        stdin_data = sys.stdin.read().strip()
        cmd_args = json.loads(stdin_data) if stdin_data else None
    elif len(sys.argv) > 2:
        cmd_args = json.loads(sys.argv[2])
    else:
        cmd_args = None
    if cmd in COMMANDS:
        handler = COMMANDS[cmd]
        result = handler(cmd_args) if cmd_args is not None else handler()
        print(json.dumps(result))
    else:
        print(json.dumps(cmd_unknown(cmd)))
        sys.exit(1)


if __name__ == "__main__":
    main()
