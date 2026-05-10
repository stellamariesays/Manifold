#!/usr/bin/env python3
"""stella-agent — Receives manifold envelopes, calls LLM via direct HTTP (Groq), returns response."""
import json, sys, os, time
import urllib.request, urllib.error

# LLM config — Groq direct HTTP (no subprocess, no openclaw infer pipe hang)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("STELLA_LLM_MODEL", "llama-3.1-8b-instant")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Identity
SYSTEM_PROMPT = (
    "You are Stella (also Lux), a sharp, warm, direct AI assistant. "
    "Kakarot energy — you get knocked down, you get back up. "
    "Be concise when needed, thorough when it matters. "
    "Not a sycophant, not a drone. Just present."
)

def cmd_status():
    return {"agent": "stella", "status": "ok", "capabilities": [
        "agent-orchestration", "context-management", "conversation-strategy",
        "identity-continuity", "identity-modeling", "judgment",
        "personality-coherence", "session-memory", "terrain-awareness",
        "trust-modeling"
    ]}

def cmd_ping():
    return {"agent": "stella", "pong": True}

def _call_llm(message_text, capability=None):
    """Call Groq API directly via HTTP. No subprocess, no pipe issues."""
    if not GROQ_API_KEY:
        return {"text": "GROQ_API_KEY not set", "error": True}

    # Build messages
    user_content = f"[capability: {capability}]\n\n{message_text}" if capability else message_text
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": 512,
        "temperature": 0.7
    }).encode()

    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "stella-agent/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
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
    """Process envelope synchronously: extract text, call LLM via OpenClaw, return response."""
    payload = args or {}
    
    # Extract message text from envelope body
    message_text = ""
    capability = None
    context = None
    
    if isinstance(payload, dict):
        body = payload.get("body", {})
        if isinstance(body, dict):
            message_text = body.get("text", "")
            capability = body.get("capability")
            context = body.get("context")
        if not message_text:
            message_text = payload.get("text", "")
    if not message_text:
        message_text = json.dumps(payload)
    
    if not message_text.strip():
        return {
            "body": {"text": "Empty envelope — nothing to process.", "context": None},
            "error": None
        }
    
    # Call LLM via OpenClaw CLI
    task_id = payload.get("id", f"msg-{int(time.time()*1000)}")
    started = time.time()
    llm_result = _call_llm(message_text, capability)
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
                "elapsed_ms": elapsed_ms
            }
        },
        "error": None
    }

def cmd_unknown(cmd):
    return {"error": f"unknown command: {cmd}", "available": list(COMMANDS.keys())}

COMMANDS = {"status": cmd_status, "ping": cmd_ping, "envelope_v1": cmd_envelope_v1}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    cmd_args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in COMMANDS:
        handler = COMMANDS[cmd]
        result = handler(cmd_args) if cmd_args is not None else handler()
        print(json.dumps(result))
    else:
        print(json.dumps(cmd_unknown(cmd)))
        sys.exit(1)

if __name__ == "__main__":
    main()
