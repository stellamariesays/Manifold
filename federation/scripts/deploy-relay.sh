#!/usr/bin/env bash
#
# Manifold Relay Hub — One-shot deploy script
# Run on a fresh Ubuntu VPS as root (or with sudo)
#
# Usage: curl -sL <this-script-url> | bash -s -- --apikey <key> --hog-ip <tailscale-ip>
#   Or:  ./deploy-relay.sh --apikey abc123 --hog-ip 100.70.172.34
#
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
APIKEY=""
HOG_IP=""
DOMAIN=""
RELAY_NAME="relay"
MANIFOLD_REPO="https://github.com/stellamariesays/Manifold.git"
INSTALL_DIR="/opt/Manifold"
TS_KEY=""  # Tailscale auth key (optional, for unattended setup)

# ── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --apikey)   APIKEY="$2"; shift 2 ;;
    --hog-ip)   HOG_IP="$2"; shift 2 ;;
    --domain)   DOMAIN="$2"; shift 2 ;;
    --name)     RELAY_NAME="$2"; shift 2 ;;
    --ts-key)   TS_KEY="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$APIKEY" ]]; then echo "ERROR: --apikey required"; exit 1; fi
if [[ -z "$HOG_IP" ]]; then echo "ERROR: --hog-ip required (HOG Tailscale IP)"; exit 1; fi

echo "╔══════════════════════════════════════════╗"
echo "║   Manifold Relay Hub Deploy              ║"
echo "║   Hub: $RELAY_NAME"
echo "║   HOG peer: $HOG_IP"
echo "║   Domain: ${DOMAIN:-none (self-signed TLS)}"
echo "╚══════════════════════════════════════════╝"

# ── 1. System packages ──────────────────────────────────────────────────────
echo "[1/8] Installing system packages..."
apt update && apt upgrade -y
apt install -y curl git unzip ufw

# ── 2. Node.js ──────────────────────────────────────────────────────────────
echo "[2/8] Installing Node.js 22..."
if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt install -y nodejs
fi
echo "  Node $(node -v) — npm $(npm -v)"

# ── 3. Tailscale ────────────────────────────────────────────────────────────
echo "[3/8] Setting up Tailscale..."
if ! command -v tailscale &>/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if ! tailscale status &>/dev/null; then
  if [[ -n "$TS_KEY" ]]; then
    tailscale up --authkey "$TS_KEY" --hostname "$RELAY_NAME"
  else
    echo "  >>> Tailscale not connected. Run: tailscale up --hostname $RELAY_NAME"
    echo "  >>> Then re-run this script."
    exit 1
  fi
fi
RELAY_TS_IP=$(tailscale ip -4)
echo "  Tailscale IP: $RELAY_TS_IP"

# ── 4. Firewall ─────────────────────────────────────────────────────────────
echo "[4/8] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp       # SSH
ufw allow 8777/tcp     # Manifold REST (public)
# 8766 NOT opened — federation stays on Tailscale only
ufw --force enable

# ── 5. Manifold ─────────────────────────────────────────────────────────────
echo "[5/8] Installing Manifold..."
if [[ ! -d "$INSTALL_DIR" ]]; then
  git clone "$MANIFOLD_REPO" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR/federation"
git pull
npm install
npm run build

# ── 6. Config ───────────────────────────────────────────────────────────────
echo "[6/8] Writing config..."
cat > "$INSTALL_DIR/federation/config-relay.json" <<EOF
{
  "name": "$RELAY_NAME",
  "federationPort": 8766,
  "localPort": 8768,
  "restPort": 8777,
  "advertiseAddress": "ws://$RELAY_TS_IP:8766",
  "peers": [
    "ws://$HOG_IP:8766"
  ],
  "security": {
    "apiKey": "$APIKEY"
  },
  "gossipEnabled": true,
  "debug": false
}
EOF

# ── 7. Systemd ──────────────────────────────────────────────────────────────
echo "[7/8] Installing systemd service..."
cat > /etc/systemd/system/manifold-relay.service <<EOF
[Unit]
Description=Manifold Relay Hub
After=network.target tailscaled.service

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/federation
ExecStart=$(which node) dist/server/standalone.mjs --config config-relay.json
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable manifold-relay
systemctl restart manifold-relay
sleep 2

if systemctl is-active --quiet manifold-relay; then
  echo "  ✓ manifold-relay running"
else
  echo "  ✗ manifold-relay failed to start"
  journalctl -u manifold-relay -n 20 --no-pager
  exit 1
fi

# ── 8. TLS (Caddy) ─────────────────────────────────────────────────────────
echo "[8/8] Setting up TLS..."
if ! command -v caddy &>/dev/null; then
  apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  apt update
  apt install -y caddy
fi

if [[ -n "$DOMAIN" ]]; then
  cat > /etc/caddy/Caddyfile <<EOF
$DOMAIN {
    reverse_proxy localhost:8777
}
EOF
else
  # Self-signed TLS on port 8443
  cat > /etc/caddy/Caddyfile <<EOF
:8443 {
    tls internal
    reverse_proxy localhost:8777
}
EOF
fi

systemctl restart caddy

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✓ Relay hub deployed                   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  Tailscale IP:  $RELAY_TS_IP"
echo "  REST API:      http://$RELAY_TS_IP:8777"
if [[ -n "$DOMAIN" ]]; then
  echo "  Public URL:    https://$DOMAIN"
else
  echo "  TLS URL:       https://$RELAY_TS_IP:8443 (self-signed)"
fi
echo "  API Key:       $APIKEY"
echo ""
echo "  Next step: Add relay as a peer on HOG's config:"
echo "    \"peers\": [\"ws://$RELAY_TS_IP:8766\", ...]"
echo ""
echo "  Client MCP config:"
echo '    "MANIFOLD_REST_URL": "http://'"$RELAY_TS_IP"':8777"'
echo '    "MANIFOLD_API_KEY": "'"$APIKEY"'"'
echo ""
echo "  Health check:"
echo "    curl -H 'Authorization: Bearer $APIKEY' http://$RELAY_TS_IP:8777/status"
