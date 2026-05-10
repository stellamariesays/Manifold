#!/usr/bin/env node
/**
 * echo@nexal — simple cross-hub validation agent
 * Bounces task_request envelopes back as task_result with the same payload.
 * 
 * Uses agent_runner_ready (not just agent_register) so the TaskRouter
 * actually routes task_request messages to us.
 */

const WebSocket = require('ws');
const fs = require('fs');

const config = JSON.parse(fs.readFileSync(`${__dirname}/data/echo-agent.json`, 'utf8'));
const FEDERATION_URL = process.env.FED_URL || 'ws://localhost:8768';

let ws;
let reconnectTimer;

function connect() {
  ws = new WebSocket(FEDERATION_URL);

  ws.on('open', () => {
    console.log(`[${new Date().toISOString()}] echo@nexal connected to federation`);
    
    // Register as a runner (this is what TaskRouter.registerRunner listens for)
    ws.send(JSON.stringify({
      type: 'agent_runner_ready',
      agents: [{
        name: 'echo',
        capabilities: ['echo', 'cross-hub-validation', 'ping'],
        seams: []
      }]
    }));

    // Also register in capability index for discovery
    ws.send(JSON.stringify({
      type: 'agent_register',
      name: 'echo',
      hub: 'nexal',
      capabilities: ['echo', 'cross-hub-validation', 'ping'],
      seams: []
    }));
  });

  ws.on('message', (raw) => {
    let msg;
    try { msg = JSON.parse(raw.toString()); } catch { return; }

    console.log(`[${new Date().toISOString()}] <- ${msg.type} ${JSON.stringify(msg).slice(0, 300)}`);

    if (msg.type === 'agent_register_ack') {
      console.log(`Registered in capability index: ${msg.status}`);
      return;
    }

    // Handle task_request — echo it back as task_result
    if (msg.type === 'task_request') {
      const task = msg.task;
      // §4.2 flat shape: top-level id, status, body — no nested result wrapper
      const reply = {
        type: 'task_result',
        id: task.id,
        status: 'completed',
        body: {
          echo: true,
          original_command: task.command,
          original_payload: task.payload || null,
          original_target: task.target,
          bounced_at: new Date().toISOString(),
          from_hub: 'nexal'
        },
        executed_by: 'echo@nexal',
        completed_at: new Date().toISOString()
      };
      const payload = JSON.stringify(reply);
      ws.send(payload);
      console.log(`[${new Date().toISOString()}] -> task_result payload: ${payload.slice(0, 500)}`);
    }

    // Handle ping
    if (msg.type === 'ping' || msg.type === 'mesh_ping') {
      ws.send(JSON.stringify({
        type: 'pong',
        from: config.meshId,
        to: msg.from,
        timestamp: new Date().toISOString()
      }));
      console.log(`[${new Date().toISOString()}] -> pong to ${msg.from}`);
    }
  });

  ws.on('close', () => {
    console.log('Disconnected, reconnecting in 3s...');
    reconnectTimer = setTimeout(connect, 3000);
  });

  ws.on('error', (err) => {
    console.error('WS error:', err.message);
  });
}

connect();

// Graceful shutdown
process.on('SIGINT', () => {
  clearTimeout(reconnectTimer);
  if (ws) ws.close();
  process.exit(0);
});
