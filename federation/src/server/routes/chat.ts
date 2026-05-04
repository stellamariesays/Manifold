/**
 * chat.ts — LLM chat proxy for the Federation Query panel.
 *
 * Proxies requests to Groq (free tier, fast). Keeps a rolling 3-message
 * conversation history per session (identified by nexal_token).
 * API key is kept server-side — never exposed to the browser.
 */
import { type Request, type Response, type Router } from 'express'

// ── Config ────────────────────────────────────────────────────────────────────

const GROQ_API_KEY = process.env.GROQ_API_KEY ?? ''
const GROQ_MODEL = 'llama-3.3-70b-versatile'
const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
const MAX_HISTORY = 3          // keep last N user+assistant pairs
const MAX_TOKENS = 1024
const TIMEOUT_MS = 30_000

// ── Session store (in-memory, LRU-ish) ────────────────────────────────────────

interface Session {
  messages: { role: 'user' | 'assistant'; content: string }[]
  lastUsed: number
}

const sessions = new Map<string, Session>()
const MAX_SESSIONS = 500

function getSession(token: string): Session {
  let s = sessions.get(token)
  if (!s) {
    // Evict oldest if at capacity
    if (sessions.size >= MAX_SESSIONS) {
      let oldest = ''
      let oldestTime = Infinity
      for (const [k, v] of sessions) {
        if (v.lastUsed < oldestTime) { oldestTime = v.lastUsed; oldest = k }
      }
      if (oldest) sessions.delete(oldest)
    }
    s = { messages: [], lastUsed: Date.now() }
    sessions.set(token, s)
  }
  s.lastUsed = Date.now()
  return s
}

// ── Route builder ─────────────────────────────────────────────────────────────

export interface ChatRouterDeps {
  hub: string
}

export function buildChatRouter(router: Router, deps: ChatRouterDeps): void {
  router.post('/chat', (req, res) => _handleChat(req, res, deps))
  router.delete('/chat', (_req, res) => _clearChat(_req, res))
}

// ── Handlers ──────────────────────────────────────────────────────────────────

async function _handleChat(req: Request, res: Response, deps: ChatRouterDeps): Promise<void> {
  const { message, token } = req.body as { message?: string; token?: string }

  if (!message?.trim()) {
    res.status(400).json({ error: 'message is required' })
    return
  }

  if (!GROQ_API_KEY) {
    res.status(503).json({ error: 'Chat service not configured — no API key' })
    return
  }

  // Use the user's token as session key (or fall back to IP)
  const sessionKey = token || req.ip || 'anonymous'
  const session = getSession(sessionKey)

  // Add user message to history
  session.messages.push({ role: 'user', content: message.trim() })

  // Build the messages payload for Groq
  const systemMsg = {
    role: 'system',
    content: [
      `You are a concise, knowledgeable assistant embedded in the Manifold Federation mesh network.`,
      `The relay hub is "${deps.hub}". Keep answers brief and useful.`,
      `If asked about the mesh, agents, or network status, explain the Manifold Federation concept:`,
      `a decentralized agent mesh where hubs (trillian, hog, thefog, bobiverse) coordinate autonomous agents.`,
    ].join(' '),
  }

  // Keep only last MAX_HISTORY user+assistant pairs
  const historyPairs = session.messages.slice(-MAX_HISTORY * 2)
  const groqMessages = [systemMsg, ...historyPairs]

  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS)

    const groqRes = await fetch(GROQ_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${GROQ_API_KEY}`,
      },
      body: JSON.stringify({
        model: GROQ_MODEL,
        messages: groqMessages,
        max_tokens: MAX_TOKENS,
        temperature: 0.7,
      }),
      signal: controller.signal,
    })

    clearTimeout(timeout)

    if (!groqRes.ok) {
      const errText = await groqRes.text().catch(() => 'unknown error')
      console.error(`[chat] Groq error ${groqRes.status}: ${errText}`)
      // Remove the user message we just pushed since it failed
      session.messages.pop()
      res.status(502).json({ error: `LLM service error (${groqRes.status})` })
      return
    }

    const data = await groqRes.json() as {
      choices?: { message?: { content?: string } }[]
    }

    const reply = data.choices?.[0]?.message?.content?.trim() ?? '(no response)'

    // Store assistant reply in history
    session.messages.push({ role: 'assistant', content: reply })

    res.json({
      response: reply,
      model: GROQ_MODEL,
      history_depth: Math.floor(session.messages.length / 2),
    })
  } catch (err: any) {
    if (err.name === 'AbortError') {
      session.messages.pop()
      res.status(504).json({ error: 'LLM request timed out' })
      return
    }
    console.error(`[chat] Unexpected error:`, err)
    session.messages.pop()
    res.status(500).json({ error: 'Internal chat error' })
  }
}

function _clearChat(req: Request, res: Response): void {
  const { token } = req.body as { token?: string }
  const sessionKey = token || req.ip || 'anonymous'
  sessions.delete(sessionKey)
  res.json({ ok: true, message: 'Chat history cleared' })
}
