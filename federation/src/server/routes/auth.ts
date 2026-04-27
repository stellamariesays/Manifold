/**
 * auth.ts — HMAC-SHA256 auth routes for Nexal login.
 *
 * POST /auth/login  — validate access code, issue HMAC token with 24h expiry
 * GET  /auth/verify — validate token, reject if expired
 */
import { type Request, type Response } from 'express'
import { createHmac, timingSafeEqual } from 'crypto'

const HMAC_SECRET = process.env.NEXAL_AUTH_SECRET || 'change-me-in-production'
const TOKEN_EXPIRY_SECONDS = 24 * 60 * 60 // 24 hours

interface TokenPayload {
  sub: string
  iat: number
  exp: number
}

function encodeToken(payload: TokenPayload): string {
  const json = JSON.stringify(payload)
  const b64 = Buffer.from(json).toString('base64url')
  const sig = createHmac('sha256', HMAC_SECRET).update(b64).digest('base64url')
  return `${b64}.${sig}`
}

function decodeToken(token: string): TokenPayload | null {
  const parts = token.split('.')
  if (parts.length !== 2) return null
  const [b64, sig] = parts
  const expected = createHmac('sha256', HMAC_SECRET).update(b64).digest('base64url')
  try {
    if (!timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return null
  } catch {
    return null
  }
  try {
    const payload = JSON.parse(Buffer.from(b64, 'base64url').toString('utf8')) as TokenPayload
    return payload
  } catch {
    return null
  }
}

/** Valid access codes — in production, read from env or a store */
const VALID_CODES = new Set(
  (process.env.NEXAL_ACCESS_CODES || 'nexal2024').split(',')
)

export function registerAuthRoutes(app: {
  post: (path: string, handler: (req: Request, res: Response) => void) => void
  get: (path: string, handler: (req: Request, res: Response) => void) => void
}): void {
  app.post('/auth/login', handleLogin)
  app.get('/auth/verify', handleVerify)
}

function handleLogin(req: Request, res: Response): void {
  const { code } = req.body || {}
  if (!code || typeof code !== 'string') {
    res.status(400).json({ error: 'Access code required' })
    return
  }

  if (!VALID_CODES.has(code)) {
    res.status(401).json({ error: 'Invalid access code' })
    return
  }

  const now = Math.floor(Date.now() / 1000)
  const token = encodeToken({
    sub: 'nexal-user',
    iat: now,
    exp: now + TOKEN_EXPIRY_SECONDS
  })

  res.json({ token })
}

function handleVerify(req: Request, res: Response): void {
  const auth = req.headers.authorization
  let token: string | undefined

  if (auth && auth.startsWith('Bearer ')) {
    token = auth.slice(7)
  } else if (req.cookies?.nexal_token) {
    token = req.cookies.nexal_token
  } else if (req.query.token && typeof req.query.token === 'string') {
    token = req.query.token
  }

  if (!token) {
    res.status(401).json({ error: 'No token provided' })
    return
  }

  const payload = decodeToken(token)
  if (!payload) {
    res.status(401).json({ error: 'Invalid token' })
    return
  }

  const now = Math.floor(Date.now() / 1000)
  if (payload.exp && now > payload.exp) {
    res.status(401).json({ error: 'Token expired' })
    return
  }

  res.json({ valid: true, sub: payload.sub, exp: payload.exp })
}
