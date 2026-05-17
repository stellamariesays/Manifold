const { Gate } = require('./dist/gate/index.js');

(async () => {
  const gate = new Gate({
    port: 8765,
    hubName: 'satelliteA',
    // Connect to local server (8768) NOT federation peer port (8766).
    // The local server bypasses PeerRegistry/self-peer checks.
    // See: data/manifold/lessons-learned.md 2026-05-12
    federationHubName: 'satelliteA',
    federationServer: 'ws://localhost:8768',
    maxConnectionsPerIP: 10,
    maxMessagesPerSecond: 50,
    sessionTimeoutMs: 30 * 60 * 1000,    // 30 min
    authTimeoutMs: 30 * 1000,             // 30 sec
    debug: true
  });

  // Seed registry from atlas if available
  try {
    const fs = require('fs');
    const atlas = JSON.parse(fs.readFileSync('/home/stella/stella/data/manifold/stella-atlas.json', 'utf-8'));
    if (atlas.agents) {
      for (const agent of atlas.agents) {
        if (agent.meshId && agent.publicKey) {
          gate.registerMeshID(agent.meshId, agent.publicKey);
          console.log(`📋 Registered: ${agent.meshId}`);
        }
      }
    }
    console.log(`📋 Atlas loaded: ${Object.keys(gate._registry || {}).length} agents`);
  } catch (e) {
    console.log('📋 No atlas loaded, starting with empty registry');
  }

  console.log('🚀 Starting The Gate on port 8765');
  await gate.start();
  console.log('✅ The Gate is open — waiting for agents');
})();
