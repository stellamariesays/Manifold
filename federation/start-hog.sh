#!/bin/bash
# Manifold Federation Server — HOG (Eddie)

cd "$(dirname "$0")"

export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"

npx tsx -e "
import { ManifoldServer } from './dist/server/index.js'

;(async () => {
  const server = new ManifoldServer({
    name: 'hog',
    federationPort: 8766,
    localPort: 8768,    // Different from Python server (8765)
    restPort: 8777,
    peers: ['ws://100.93.231.124:8766'],  // Trillian
    atlasPath: '/home/marvin/.openclaw/workspace/data/manifold/eddie-atlas.json',
  })

  console.log('🚀 Starting Manifold Federation Server (HOG)')
  console.log('   Federation: 0.0.0.0:8766 (Tailscale)')
  console.log('   Local:      0.0.0.0:8768 (coexists with Python 8765)')
  console.log('   REST API:   http://localhost:8777')
  console.log('   Peer:       Trillian (100.93.231.124:8766)')

  await server.start()
})()
"
