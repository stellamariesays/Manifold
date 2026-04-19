# The Gate - Public WebSocket Gateway

Internet-facing entry point for Manifold mesh access. Agents show their MeshPass, walk through The Gate, and they're on the mesh. No Tailscale needed.

## Overview

**The Gate** is a WebSocket server that provides public access to the Manifold mesh federation. It handles:

- **Authentication** - Verify MeshPass credentials via Ed25519 signatures
- **Authorization** - Rate limiting and session management
- **Bridge** - Connect public clients to private federation servers
- **Security** - IP-based limits, message validation, timeout enforcement

## Quick Start

### 1. Start The Gate Server

```typescript
import { Gate } from './index.js'

const gate = new Gate({
  port: 8765,                              // Public WebSocket port
  hubName: 'satelliteA',                   // This hub's name
  federationServer: 'ws://localhost:8766', // Internal federation server
  maxConnectionsPerIP: 10,                 // Rate limiting
  maxMessagesPerSecond: 50,
  debug: true
})

// Register known MeshIDs (in production, use a proper registry)
gate.registerMeshID('stella@satelliteA#a1b2c3d4', 'abc123...publickey...789')
gate.registerMeshID('eddie@satelliteA#ef567890', 'def456...publickey...012')

await gate.start()
console.log('The Gate is open on port 8765!')
```

### 2. Connect Client to The Gate

```typescript
import { GateClient } from './client.js'
import { MeshPass } from '../identity/index.js'

// Load your MeshPass
const meshPass = await MeshPass.load('your-passphrase')

// Connect to The Gate
const client = new GateClient({
  gateUrl: 'wss://gate.satelliteA.org:8765',
  meshPass,
  meshId: 'stella@satelliteA#a1b2c3d4',
  debug: true
})

// Set up event handlers
client.on('authenticated', (session) => {
  console.log('Authenticated!', session)
})

client.on('message', (message) => {
  console.log('Received:', message)
})

await client.connect()
// Authentication happens automatically after connection

// Send messages
client.send({
  type: 'capability_query',
  capability: 'solar-monitoring',
  requestId: 'query-123'
})
```

## Architecture

```
[Internet] → [The Gate] → [Federation Server] → [Tailscale Mesh]
           ↑           ↑                     ↑
        WebSocket    Bridge              Internal mesh
      Authentication Connection          (existing)
```

**The Gate** sits between the public internet and your internal federation infrastructure:

1. **Public Layer**: WebSocket server on public internet
2. **Auth Layer**: MeshPass credential verification
3. **Bridge Layer**: Forward authenticated messages to federation server
4. **Federation Layer**: Existing Tailscale-based mesh (unchanged)

## Authentication Flow

```
Client                    The Gate                Federation Server
  │                         │                           │
  ├─── WebSocket Connect ───→│                           │
  │←── gate_info ────────────│                           │
  │                         │                           │
  ├─── mesh_auth ───────────→│                           │
  │    (signed message)       │                           │
  │                         │                           │
  │←── auth_success ─────────│                           │
  │    (session established)  │                           │
  │                         │                           │
  ├─── federation_message ──→│─── enriched_message ────→│
  │                         │    (+ sender identity)    │
  │                         │                           │
  │←── federation_response ──│←── response ─────────────│
```

1. **Connect**: Client opens WebSocket to The Gate
2. **Info**: Gate sends welcome message with hub info
3. **Auth**: Client sends signed authentication message
4. **Verify**: Gate verifies signature against MeshID registry
5. **Session**: Gate creates authenticated session
6. **Relay**: Gate relays messages between client and federation

## Configuration

```typescript
interface GateConfig {
  /** Port to listen on for public WebSocket connections */
  port: number
  
  /** Hub name this gate serves */
  hubName: string
  
  /** Federation server address to bridge to */
  federationServer: string
  
  /** Rate limiting: max connections per IP (default: 10) */
  maxConnectionsPerIP?: number
  
  /** Rate limiting: max messages per second per connection (default: 50) */
  maxMessagesPerSecond?: number
  
  /** Session timeout in milliseconds (default: 30 minutes) */
  sessionTimeoutMs?: number
  
  /** Authentication timeout in milliseconds (default: 30 seconds) */
  authTimeoutMs?: number
  
  /** Enable debug logging */
  debug?: boolean
}
```

## Rate Limiting

The Gate implements multiple layers of rate limiting:

### Connection Limits
- **Per-IP**: Max concurrent connections from same IP
- **Auth timeout**: Max time to complete authentication
- **Session timeout**: Max idle time before session expires

### Message Limits
- **Per-second**: Max messages per second per connection
- **Burst protection**: Reset counters every second
- **Auth attempts**: Max failed auth attempts before disconnect

### Error Handling
- **Graceful degradation**: Rate limits return errors, don't crash
- **Automatic cleanup**: Expired sessions cleaned up periodically
- **Connection tracking**: IP-based connection counting

## Security Features

### Cryptographic Authentication
- **Ed25519 signatures** - Industry standard elliptic curve cryptography
- **Timestamp validation** - Prevents replay attacks (5 minute window)
- **Nonce verification** - Each auth request has unique nonce
- **Public key verification** - Messages verified against registered keys

### Network Security
- **IP rate limiting** - Prevents DoS attacks
- **Connection limits** - Per-IP connection caps
- **Message validation** - All messages parsed and validated
- **Timeout enforcement** - No hanging connections

### Session Management
- **Authenticated sessions** - Only verified MeshPass holders get through
- **Session tracking** - Monitor active sessions and activity
- **Automatic cleanup** - Expired sessions removed automatically
- **Identity enrichment** - Messages tagged with verified sender identity

## Monitoring

```typescript
// Get gate statistics
const stats = gate.getStats()
console.log(stats)
/*
{
  gate: {
    port: 8765,
    hub: 'satelliteA',
    started: true
  },
  sessions: {
    authenticated: 12,
    pending: 2,
    byMeshId: {
      'stella@satelliteA#a1b2c3d4': 1,
      'eddie@satelliteA#ef567890': 1
    }
  },
  connections: {
    byIP: {
      '192.168.1.100': { ip: '192.168.1.100', connections: 2, lastConnection: '...' }
    },
    totalIPs: 5
  },
  registry: {
    total: 25,
    byHub: { 'satelliteA': 15, 'thefog': 10 }
  }
}
*/
```

## Events

### Gate Server Events
```typescript
gate.on('session:authenticated', ({ meshId, publicKey }) => {
  console.log(`${meshId} authenticated`)
})

gate.on('session:expired', ({ meshId }) => {
  console.log(`${meshId} session expired`)
})
```

### Gate Client Events
```typescript
client.on('connected', () => {
  console.log('Connected to The Gate')
})

client.on('authenticated', (session) => {
  console.log('Authenticated:', session)
})

client.on('auth_error', (error) => {
  console.error('Auth failed:', error)
})

client.on('message', (message) => {
  // Handle federation messages
})
```

## Error Codes

- `4000` - Authentication timeout
- `4001` - Too many authentication failures
- `RATE_LIMIT` - Message rate limit exceeded
- `FEDERATION_DOWN` - Federation server unavailable
- `INVALID_FORMAT` - Message parsing failed
- `PROCESSING_ERROR` - Message processing failed

## Production Deployment

### SSL/TLS Requirements

⚠️ **IMPORTANT**: The Gate server only handles plain WebSocket (ws://) connections internally. In production, you **MUST** use a reverse proxy (nginx/caddy) for TLS termination to provide secure WSS connections.

**Architecture:**
```
[Internet] ──(HTTPS/WSS)──► [nginx/caddy] ──(HTTP/WS)──► [The Gate]
              SSL/TLS                     localhost
              Public                      Internal
```

### nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name gate.yourmanifold.org;
    
    # SSL certificates
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/private.key;
    
    # WebSocket upgrade headers
    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }
}
```

### Caddy Configuration

```caddyfile
gate.yourmanifold.org {
    reverse_proxy 127.0.0.1:8765
}
```

### Gate Server Setup

```javascript
// The Gate listens on localhost only - nginx/caddy handles public TLS
const gate = new Gate({
  port: 8765,                              // localhost:8765 only
  hubName: 'production-hub',
  federationServer: 'ws://localhost:8766', // internal federation
})

// Clients connect via WSS through the proxy:
// wss://gate.yourmanifold.org/ → nginx → ws://localhost:8765
```

### Process Management
```javascript
// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('Shutting down The Gate...')
  await gate.stop()
  process.exit(0)
})

// For systemd service
// /etc/systemd/system/manifold-gate.service
/*
[Unit]
Description=Manifold Gate Server
After=network.target

[Service]
Type=simple
User=manifold
WorkingDirectory=/opt/manifold/federation
ExecStart=/usr/bin/node dist/gate/index.js
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
*/
```

### Monitoring
```javascript
// Health check endpoint
setInterval(() => {
  const stats = gate.getStats()
  if (stats.sessions.authenticated > 1000) {
    console.warn('High session count:', stats.sessions.authenticated)
  }
}, 60000)
```

### Registry Management
In production, use a proper identity registry:

```javascript
// Load MeshIDs from database/config
const registry = await loadMeshIDRegistry()
for (const [meshId, publicKey] of registry) {
  gate.registerMeshID(meshId, publicKey)
}
```

## Troubleshooting

### Authentication Failures
1. **Check MeshID format** - Must be `name@hub#fingerprint`
2. **Verify public key** - Must be registered with The Gate
3. **Check signature** - Message must be properly signed
4. **Timestamp validation** - Messages expire after 5 minutes

### Connection Issues
1. **Rate limiting** - Check if IP has too many connections
2. **Federation server** - Ensure gate can reach federation server
3. **Network** - Verify WebSocket connectivity
4. **SSL/TLS** - Check certificate validity for WSS

### Debug Mode
Enable debug logging:

```javascript
const gate = new Gate({ ...config, debug: true })
const client = new GateClient({ ...config, debug: true })
```

## Examples

See `federation/examples/` for complete examples:
- Basic gate setup
- Client connection
- Production deployment
- Load balancing multiple gates