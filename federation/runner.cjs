const { WebSocket } = require('ws');
const { spawn } = require('child_process');
const { readFileSync } = require('fs');

const configPath = process.argv.find((a,i) => process.argv[i-1]==='--config') || 'runner-config.json';
const config = JSON.parse(readFileSync(configPath, 'utf-8'));
config.wsUrl = config.wsUrl || 'ws://localhost:8768';

let ws = null;
let runningTasks = new Map();
let reconnectTimer = null;

function connect() {
  ws = new WebSocket(config.wsUrl);

  ws.on('open', () => {
    log(`Connected to ${config.wsUrl}`);
    ws.send(JSON.stringify({
      type: 'agent_runner_ready',
      hub: config.hub,
      agents: config.agents.map(a => a.name),
    }));
    log(`Registered ${config.agents.length} agents: ${config.agents.map(a=>a.name).join(', ')}`);
  });

  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.type === 'task_request' && msg.task) {
        executeTask(msg.task);
      }
    } catch (err) {
      log(`Parse error: ${err.message}`);
    }
  });

  ws.on('close', () => {
    log('Disconnected, reconnecting in 5s...');
    reconnectTimer = setTimeout(connect, 5000);
  });

  ws.on('error', (err) => {
    log(`WS error: ${err.message}`);
  });
}

function executeTask(task) {
  const agentName = task.target.includes('@') ? task.target.split('@')[0] : task.target;
  const agentConfig = config.agents.find(a => a.name === agentName);

  if (!agentConfig) {
    sendResult({ id: task.id, status: 'not_found', error: `Agent not found: ${agentName}`, executed_by: `${agentName}@${config.hub}`, completed_at: new Date().toISOString() });
    return;
  }

  const timeoutMs = task.timeout_ms || agentConfig.timeout_ms || config.defaultTimeoutMs || 15000;
  const startTime = Date.now();
  log(`Executing: ${agentName} ${task.command} (${task.id.slice(0,8)}...)`);

  const args = [task.command];
  if (task.args && Object.keys(task.args).length > 0) args.push(JSON.stringify(task.args));

  const proc = spawn(agentConfig.script, args, {
    cwd: agentConfig.cwd || process.cwd(),
    env: { ...process.env, ...agentConfig.env },
    stdio: ['pipe', 'pipe', 'pipe'],
  });

  const stdout = [];
  const stderr = [];
  proc.stdout.on('data', c => stdout.push(c));
  proc.stderr.on('data', c => stderr.push(c));

  const timeout = setTimeout(() => { proc.kill('SIGKILL'); }, timeoutMs);

  proc.on('close', (code) => {
    clearTimeout(timeout);
    const execMs = Date.now() - startTime;
    const out = Buffer.concat(stdout).toString().trim();
    const err = Buffer.concat(stderr).toString().trim();

    if (code === 0 && out) {
      let output;
      try { output = JSON.parse(out); } catch { output = { text: out }; }
      sendResult({ id: task.id, status: 'success', output, executed_by: `${agentName}@${config.hub}`, execution_ms: execMs, completed_at: new Date().toISOString() });
      log(`✓ ${agentName} ${task.command} (${execMs}ms)`);
    } else {
      sendResult({ id: task.id, status: code === null ? 'timeout' : 'error', error: err || `exit code ${code}`, output: out ? { raw: out } : undefined, executed_by: `${agentName}@${config.hub}`, execution_ms: execMs, completed_at: new Date().toISOString() });
      log(`✗ ${agentName}: ${err || 'code ' + code} (${execMs}ms)`);
    }
  });

  proc.on('error', (err) => {
    clearTimeout(timeout);
    sendResult({ id: task.id, status: 'error', error: err.message, executed_by: `${agentName}@${config.hub}`, execution_ms: Date.now() - startTime, completed_at: new Date().toISOString() });
  });
}

function sendResult(result) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'task_result', result }));
  }
}

function log(msg) {
  console.log(`[Runner:${config.hub}] ${msg}`);
}

connect();

process.on('SIGINT', () => {
  clearTimeout(reconnectTimer);
  ws?.close();
  process.exit(0);
});
