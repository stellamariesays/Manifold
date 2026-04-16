# Manifold Federation — Production Deployment

The federation server and agent runner can run as systemd user services for reliability (auto-restart, survive logout, boot persistence).

## Quick Start

### 1. Create a server config

```bash
cp federation/config.example.json federation/config-myhub.json
# Edit config-myhub.json — set name, peers, atlasPath
```

### 2. Install systemd services

```bash
cp contrib/systemd/manifold-federation.service.example \
   ~/.config/systemd/user/manifold-federation.service
cp contrib/systemd/manifold-runner.service.example \
   ~/.config/systemd/user/manifold-runner.service

# Edit both files — replace paths with your actual install locations
```

### 3. Enable and start

```bash
systemctl --user daemon-reload
systemctl --user enable --now manifold-federation.service
systemctl --user enable --now manifold-runner.service
```

### 4. Verify

```bash
systemctl --user status manifold-federation.service
curl http://localhost:8777/status
```

## Standalone Mode

The `standalone.mts` entry point reads config from a JSON file:

```bash
# Via env var
MANIFOLD_CONFIG=config.json npx tsx standalone.mts

# Via flag
npx tsx standalone.mts --config config.json
```

Config fields:
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | ✅ | — | Hub name |
| `federationPort` | — | 8766 | P2P WebSocket port |
| `localPort` | — | 8768 | Runner WebSocket port |
| `restPort` | — | 8777 | REST API port |
| `peers` | — | `[]` | Peer WebSocket URLs |
| `atlasPath` | — | — | Path to atlas JSON |
| `debug` | — | `false` | Verbose logging |

## Persistence

```bash
# Ensure services survive user logout
loginctl enable-linger $(whoami)
```
