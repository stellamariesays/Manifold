/**
 * nexal.ts — Nexal topology UI handlers.
 *
 * Serves the nexal visualization pages (public, no auth).
 */
import { type Request, type Response, type Router } from 'express'
import { readFileSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

export function registerNexalRoutes(app: { get: (path: string, handler: (req: Request, res: Response) => void) => void }): void {
  app.get('/nexal', _nexalInterfaceHandler)
  app.get('/nexal/', _nexalInterfaceHandler)
  app.get('/nexal_test', _nexalTestInterface)
  app.get('/nexal_test/', _nexalTestInterface)
  app.get('/nexal-topology', _nexalTestInterface)
  app.get('/nexal-topology/', _nexalTestInterface)
  app.get('/topology', _nexalTestInterface)
  app.get('/topology/', _nexalTestInterface)
  app.get('/api/topology', _nexalTestInterface)
  app.get('/api/topology/', _nexalTestInterface)
}

function _nexalInterfaceHandler(req: Request, res: Response): void {
  const useTopology = req.query['topology'] === 'true' || req.query['v'] === 'topology'
  try {
    const __filename = fileURLToPath(import.meta.url)
    const __dirname = dirname(__filename)
    const filePath = useTopology
      ? join(__dirname, '../../../public/nexal_test/index.html')
      : join(__dirname, '../../../public/nexal/index.html')
    const html = readFileSync(filePath, 'utf-8')
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    res.send(html)
  } catch (error) {
    console.error(`[nexal] Failed to serve nexal interface: ${error}`)
    res.status(500).json({ error: 'Failed to load nexal interface' })
  }
}

function _nexalTestInterface(_req: Request, res: Response): void {
  try {
    const __filename = fileURLToPath(import.meta.url)
    const __dirname = dirname(__filename)
    const filePath = join(__dirname, '../../../public/nexal_test/index.html')
    const html = readFileSync(filePath, 'utf-8')
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    res.send(html)
  } catch (error) {
    console.error(`[nexal] Failed to serve nexal test interface: ${error}`)
    res.status(500).json({ error: 'Failed to load nexal test interface' })
  }
}
