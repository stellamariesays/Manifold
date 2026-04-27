const { ManifoldServer } = require('./dist/server/index.js');
const { MeshletManager } = require('./dist/server/meshlet-manager.js');

(async () => {
  // Create meshlet manager (simulated mode — no Elixir on this host)
  const meshletManager = new MeshletManager({
    elixirAvailable: false,
    defaultTtlMs: 2 * 60 * 60 * 1000,
    maxPerOwner: 3,
    debug: true,
  });
  meshletManager.start();

  const server = new ManifoldServer({
    name: 'trillian',
    federationPort: 8766,
    localPort: 8768,
    restPort: 8767,
    peers: ['ws://100.70.172.34:8766', 'ws://100.124.38.123:8766'],
    atlasPath: '/home/stella/stella/data/manifold/stella-atlas.json',
    meshletManager,
    debug: true,
  });

  console.log('🚀 Starting Manifold Federation Server (Trillian) with Meshlet support');

  await server.start();
  console.log('✅ Federation running — meshlet workshop at http://localhost:8767/nexal/meshlet');
})();
