const { AgentRunner } = require('./dist/runtime/agent-runner.js');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
let configPath = 'runner-config.json';

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--config' && args[i + 1]) configPath = args[++i];
}

const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
if (!config.wsUrl) config.wsUrl = 'ws://localhost:8768';

const runner = new AgentRunner(config);
runner.start().then(() => {
  console.log(`Agent runner started with ${config.agents.length} agents`);
}).catch((err) => {
  console.error('Failed to start:', err);
  process.exit(1);
});

process.on('SIGINT', () => {
  runner.stop().then(() => process.exit(0));
});
