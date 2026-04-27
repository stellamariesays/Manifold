/**
 * admin.ts — Admin endpoints for access code management.
 *
 * GET /admin/codes — returns full code list (API-key protected via x-api-key header)
 */
import { type Request, type Response, type Router } from 'express'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DATA_PATH = resolve(__dirname, '../../../data/access-codes.json')

const ADMIN_API_KEY = process.env.ADMIN_API_KEY ?? ''

interface CodeEntry {
  code: string
  username: string | null
  createdAt: string
  usedAt: string | null
}

function loadCodes(): CodeEntry[] {
  return JSON.parse(readFileSync(DATA_PATH, 'utf-8'))
}

export function buildAdminRouter(router: Router): void {
  router.get('/admin/codes', (req: Request, res: Response) => {
    const key = req.headers['x-api-key']
    if (!ADMIN_API_KEY || key !== ADMIN_API_KEY) {
      res.status(401).json({ error: 'Invalid or missing API key' })
      return
    }

    const codes = loadCodes()
    res.json({ count: codes.length, codes })
  })
}
