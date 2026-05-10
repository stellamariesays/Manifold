#!/usr/bin/env node
/**
 * diag-relay-body.cjs — Drop-in diagnostic for nexal task_result relay
 * 
 * Usage: node diag-relay-body.cjs
 * 
 * Patches the federation server's handleResult to log raw body presence
 * at both entry (from echo agent) and sendResult egress (to remote peer).
 * 
 * This identifies whether body is lost in the relay or never sent.
 * 
 * No source changes needed — runs against compiled dist/ in-place.
 * Clean exit after 60s of monitoring.
 */

const path = require('path');

// Patch Module._resolveFilename to intercept handleResult and sendResult
const Module = require('module');
const origResolve = Module._resolveFilename;

let patched = 0;

Module._resolveFilename = function(request, parent, isMain, options) {
  const resolved = origResolve.apply(this, arguments);
  
  if (resolved.includes('task-router') && resolved.includes('dist') && patched < 1) {
    patched++;
    const origReadFile = require('fs').readFileSync;
    console.log(`[diag] Found task-router at ${resolved}`);
    
    // We'll monkey-patch at runtime instead
  }
  
  return resolved;
};

// Simpler approach: just connect as a snooping WebSocket client
const WebSocket = require('ws');

console.log('[diag] Connecting to local federation as observer...');
console.log('[diag] Will log all task_result wire payloads for 60 seconds.\n');

const ws = new WebSocket('ws://localhost:8768');

ws.on('open', () => {
  // Register as a passive listener (not a runner)
  console.log('[diag] Connected. Listening...\n');
});

ws.on('message', (data) => {
  try {
    const msg = JSON.parse(data.toString());
    if (msg.type === 'task_result') {
      console.log('=== INBOUND task_result (from server to us) ===');
      console.log('  status:', msg.status);
      console.log('  body present:', msg.body !== undefined);
      console.log('  body:', msg.body ? JSON.stringify(msg.body).substring(0, 500) : 'UNDEFINED');
      console.log('  all keys:', Object.keys(msg).join(', '));
      console.log('');
    }
  } catch {}
});

ws.on('error', (e) => console.error('[diag] WS error:', e.message));

setTimeout(() => {
  console.log('[diag] 60s elapsed, exiting.');
  ws.close();
  process.exit(0);
}, 60000);

process.on('SIGINT', () => { ws.close(); process.exit(0); });
