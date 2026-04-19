# Manifold Relay Hub — VPS Deployment Guide

A public-facing Manifold federation hub that acts as a gateway for external AI clients (Claude Code, Cursor, etc.) to reach the private mesh.

## Architecture

```
Trusted client (Claude Code, Cursor, etc.)
    ↓ HTTPS + API key
Relay Hub (public VPS)
    ↓ Tailscale (encrypted p2p, port 8766)
Private hubs: HOG ↔ thefog ↔ satelliteA
```

The relay is just another hub in the mesh — no secrets, no wallets, no agent state. It routes tasks in, results out.

## VPS Requirements

- **OS:** Ubuntu 22.04+ (arm64 or amd64)
- **RAM:** 512MB minimum
- **Disk:** 5GB
- **Network:** Public IP + Tailscale
- **Cost:** ~$4-5/mo (Hetzner, DigitalOcean, Vultr, etc.)

## Deployment

### 1. Provision & Harden

```bash
# On the VPS
apt update && apt upgrade -y
apt install -y curl git nodejs npm tailscale ufw

# Firewall — only SSH + the Manifold REST port
ufw allow 22/tcp
ufw allow 8777/tcp
ufw enable

# Tailscale
tailscale up
# Note the Tailscale IP (e.g. 100.x.x.x)
```

### 2. Install Manifold

```bash
cd /opt
git clone https://github.com/stellamariesays/Manifold.git
cd Manifold/federation
npm install
npm run build
```

### 3. Generate API Key

```bash
openssl rand -hex 32
# Save this — it goes in the config and is shared with trusted clients
```

### 4. Create Config

```json
// /opt/Manifold/federation/config-relay.json
{
  "name": "relay",
  "federationPort": 8766,
  "localPort": 8768,
  "restPort": 8777,
  "advertiseAddress": "ws://100.x.x.x:8766",
  "peers": [
    "ws://100.70.172.34:8766"
  ],
  "security": {
    "apiKey": "YOUR_GENERATED_API_KEY"
  },
  "gossipEnabled": true,
  "debug": false
}
```

- `advertiseAddress` — use the VPS's **Tailscale IP**
- `peers` — Tailscale IPs of private hubs (HOG = 100.70.172.34)
- `security.apiKey` — the key from step 3. Required for REST API access.

### 5. TLS with Caddy (reverse proxy)

```bash
apt install -y caddy
```

```json
// /etc/caddy/Caddyfile
your-domain.com {
    reverse_proxy localhost:8777
}

# Or without a domain, using self-signed:
# :8443 {
#     tls internal
#     reverse_proxy localhost:8777
# }
```

```bash
systemctl restart caddy
```

### 6. Systemd Service

```ini
# /etc/systemd/system/manifold-relay.service
[Unit]
Description=Manifold Relay Hub
After=network.target tailscaled.service

[Service]
Type=simple
WorkingDirectory=/opt/Manifold/federation
ExecStart=/usr/bin/node dist/server/standalone.mjs --config config-relay.json
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable manifold-relay
systemctl start manifold-relay
```

### 7. Add Relay to Private Hubs

On HOG (and other private hubs), add the relay as a peer:

```json
// config-hog.json — add to peers array
"peers": [
  "ws://100.x.x.x:8766",
  "ws://100.86.105.39:8766",
  ...
]
```

Then restart: `systemctl --user restart manifold-federation.service`

## Client Configuration

### Claude Code / Cursor / Windsurf

Trusted clients need:
1. The public URL (or Tailscale IP if on tailnet)
2. The API key

```json
{
  "mcpServers": {
    "manifold": {
      "command": "node",
      "args": ["/path/to/manifold/federation/dist/mcp/manifold-mcp-server.js"],
      "env": {
        "MANIFOLD_REST_URL": "https://your-domain.com",
        "MANIFOLD_API_KEY": "YOUR_GENERATED_API_KEY"
      }
    }
  }
}
```

### On Tailscale (zero-trust, no public port needed)

If the client's machine is on your Tailscale network:
- Close port 8777 on the VPS firewall
- Client points directly at `http://100.x.x.x:8777`
- No TLS needed (Tailscale encrypts)
- API key still required

## Security Layers

| Layer | Protection |
|-------|-----------|
| Tailscale | Only tailnet members can reach federation port (8766) |
| API Key | REST API requires key in `Authorization: Bearer <key>` header |
| TLS (Caddy) | Encrypts REST traffic from client to relay |
| UFW | Only SSH + REST port open; federation port on Tailscale only |
| No state on relay | VPS has no wallets, keys, or agent data — pure router |

## Blast Radius

If the VPS is compromised:
- Attacker sees federation traffic (mesh sync, task routing) — no secrets
- No private keys, no wallets, no agent scripts on the relay
- Rotate the API key, kill the VPS, redeploy from git in 5 minutes
- Private hubs are unaffected — they just lose the relay peer

## Monitoring

```bash
# Check relay health
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:8777/status

# Check mesh connectivity
curl -H "Authorization: Bearer YOUR_KEY" http://localhost:8777/peers

# Logs
journalctl -u manifold-relay -f
```
