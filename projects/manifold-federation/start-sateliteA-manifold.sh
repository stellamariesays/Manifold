#!/bin/bash
# Manifold Federation Server — stellasateliteA

cd "$(dirname "$0")"

npx tsx -e "
import { ManifoldServer } from './dist/server/index.js'

;(async () => {
  const server = new ManifoldServer({
    name: 'sateliteA',
    federationPort: 8766,
    localPort: 8768,    // Different from Python server (8765)
    restPort: 8767,
    peers: ['ws://100.70.172.34:8766'],  // HOG foundation server
    atlasPath: '/home/stella/openclaw-workspace/stella/data/manifold/stella-atlas.json',
  })

  console.log('🚀 Starting Manifold Federation Server (stellasateliteA)')
  console.log('   Federation: 0.0.0.0:8766 (Tailscale)')
  console.log('   Local:      0.0.0.0:8768 (coexists with Python 8765)')
  console.log('   REST API:   http://localhost:8767')
  console.log('   Peer:       HOG foundation (100.70.172.34:8766)')

  await server.start()
})()
"
