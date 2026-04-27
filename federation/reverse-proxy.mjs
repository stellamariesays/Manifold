/**
 * reverse-proxy.js — Lightweight reverse proxy for Manifold nexal.
 *
 * Listens on port 3000, proxies to federation REST API on 8767.
 * Handles WebSocket upgrade for meshlet WS connections.
 * Adds CORS headers for browser access.
 *
 * Usage: node reverse-proxy.js
 */
import { createServer } from 'http'
import pkg from 'http-proxy'
const { createProxyServer } = pkg

const TARGET = process.env.TARGET || 'http://localhost:8767'
const PORT = parseInt(process.env.PORT || '3000', 10)

const proxy = createProxyServer({
  target: TARGET,
  ws: true,
  changeOrigin: true,
})

const server = createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Meshlet-Owner')

  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    res.end()
    return
  }

  proxy.web(req, res, { target: TARGET }, (err) => {
    console.error(`[proxy] Error: ${err.message}`)
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Bad Gateway' }))
    }
  })
})

// WebSocket upgrade
server.on('upgrade', (req, socket, head) => {
  proxy.ws(req, socket, head, { target: TARGET.replace('http', 'ws') })
})

server.listen(PORT, () => {
  console.log(`🔄 Reverse proxy listening on :${PORT} → ${TARGET}`)
})
