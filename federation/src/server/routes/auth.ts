/**
 * auth.ts — /auth/verify and /auth/token-check endpoints for nexal.network.
 *
 * POST /auth/verify  { username, code }
 *   → 200 { ok: true,  token, username }   — first use only; code consumed
 *   → 401 { ok: false, error: 'invalid_code' | 'code_taken' | 'already_used' }
 *
 * POST /auth/token-check  { token }
 *   → 200 { ok: true,  username }   — token valid
 *   → 401 { ok: false, error: 'invalid_token' }
 *
 * Single-use codes: once a code is redeemed the `used` flag is set and it
 * cannot be used again. The signed token is the sole long-lived credential.
 * To access from a new device, a fresh code is required.
 */
import { type Router } from 'express'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'

const CODES_PATH = path.resolve('./data/access-codes.json')

interface CodeEntry {
  code: string
  username: string | null
  used: boolean
}

function loadCodes(): CodeEntry[] {
  try {
    return JSON.parse(fs.readFileSync(CODES_PATH, 'utf8')) as CodeEntry[]
  } catch {
    return []
  }
}

function saveCodes(codes: CodeEntry[]): void {
  fs.writeFileSync(CODES_PATH, JSON.stringify(codes, null, 2))
}

function makeToken(username: string, code: string): string {
  const secret = process.env.NEXAL_TOKEN_SECRET ?? 'nexal-secret-change-me'
  const payload = `${username.toLowerCase()}:${code.toUpperCase()}`
  const sig = crypto.createHmac('sha256', secret).update(payload).digest('hex').slice(0, 32)
  return Buffer.from(payload).toString('base64') + '.' + sig
}

function verifyToken(token: string): { valid: boolean; username?: string } {
  try {
    const secret = process.env.NEXAL_TOKEN_SECRET ?? 'nexal-secret-change-me'
    const [b64, sig] = token.split('.')
    if (!b64 || !sig) return { valid: false }

    const payload = Buffer.from(b64, 'base64').toString('utf8')
    const expectedSig = crypto.createHmac('sha256', secret).update(payload).digest('hex').slice(0, 32)

    if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expectedSig))) {
      return { valid: false }
    }

    const username = payload.split(':')[0]
    return { valid: true, username }
  } catch {
    return { valid: false }
  }
}

export function buildAuthRouter(router: Router): void {

  // ── POST /auth/verify ─────────────────────────────────────────────────
  router.post('/auth/verify', (req, res) => {
    const { username, code } = req.body as { username?: string; code?: string }

    if (!username || !code) {
      res.status(400).json({ ok: false, error: 'missing_fields' })
      return
    }

    const normUser = username.trim().toLowerCase()
    const normCode = code.trim().toUpperCase()

    const codes = loadCodes()
    const entry = codes.find(c => c.code === normCode)

    if (!entry) {
      res.status(401).json({ ok: false, error: 'invalid_code' })
      return
    }

    // Code already used — single-use enforcement
    if (entry.used) {
      res.status(401).json({ ok: false, error: 'already_used' })
      return
    }

    // First use: bind username, mark consumed
    entry.username = normUser
    entry.used = true
    saveCodes(codes)

    const token = makeToken(normUser, normCode)
    res.json({ ok: true, token, username: normUser })
  })

  // ── POST /auth/token-check ────────────────────────────────────────────
  // Client calls this on load to validate a stored token without a code.
  router.post('/auth/token-check', (req, res) => {
    const { token } = req.body as { token?: string }

    if (!token) {
      res.status(400).json({ ok: false, error: 'missing_token' })
      return
    }

    const result = verifyToken(token)
    if (!result.valid) {
      res.status(401).json({ ok: false, error: 'invalid_token' })
      return
    }

    res.json({ ok: true, username: result.username })
  })
}
