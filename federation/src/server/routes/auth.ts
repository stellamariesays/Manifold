/**
 * auth.ts — /auth/verify endpoint for nexal.network access code validation.
 *
 * POST /auth/verify  { username, code }
 *   → 200 { ok: true,  token: <jwt-ish>, username }
 *   → 401 { ok: false, error: 'invalid_code' | 'already_used' }
 *
 * Codes are stored in data/access-codes.json.
 * On first use the code is bound to the username (case-insensitive).
 * Subsequent logins with the same username+code are allowed (idempotent).
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
  // Simple HMAC token — not a full JWT but fine for this use case
  const secret = process.env.NEXAL_TOKEN_SECRET ?? 'nexal-secret-change-me'
  const payload = `${username.toLowerCase()}:${code.toUpperCase()}`
  const sig = crypto.createHmac('sha256', secret).update(payload).digest('hex').slice(0, 32)
  return Buffer.from(payload).toString('base64') + '.' + sig
}

export function buildAuthRouter(router: Router): void {
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

    // Already bound to a different username
    if (entry.username && entry.username !== normUser) {
      res.status(401).json({ ok: false, error: 'code_taken' })
      return
    }

    // Bind username on first use
    if (!entry.username) {
      entry.username = normUser
      entry.used = true
      saveCodes(codes)
    }

    const token = makeToken(normUser, normCode)
    res.json({ ok: true, token, username: normUser })
  })
}
