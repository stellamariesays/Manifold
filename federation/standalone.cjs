const { ManifoldServer } = require('./dist/server/index.js');
const { MeshletManager } = require('./dist/server/meshlet-manager.js');
const fs = require('fs');
const path = require('path');

(async () => {
  const configPath = path.join(__dirname, 'config-satelliteA.json');
  const fileConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));

  const meshletManager = new MeshletManager({
    elixirAvailable: false,
    defaultTtlMs: 2 * 60 * 60 * 1000,
    maxPerOwner: 3,
    debug: true,
  });
  meshletManager.start();

  const server = new ManifoldServer({
    ...fileConfig,
    meshletManager,
    debug: true,
  });

  console.log(`🚀 Starting Manifold Federation Server (${fileConfig.name}) with Meshlet support`);

  try {
    await server.start();
    console.log(`✅ Federation running — meshlet workshop at http://localhost:${fileConfig.restPort || 8767}/meshlet`);
  } catch (err) {
    console.error('❌ START FAILED:', err);
    process.exit(1);
  }
})();
