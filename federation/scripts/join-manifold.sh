#!/usr/bin/env bash
# join-manifold.sh — One-command Manifold Federation onboarding
# Usage: curl -fsSL https://raw.githubusercontent.com/stellamariesays/Manifold/main/federation/scripts/join-manifold.sh | bash
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

REPO="https://github.com/stellamariesays/Manifold.git"
DIR="Manifold"

info()  { echo -e "${CYAN}[manifold]${NC} $*"; }
ok()    { echo -e "${GREEN}[manifold]${NC} $*"; }
die()   { echo -e "${RED}[manifold]${NC} $*" >&2; exit 1; }

# --- Preflight ---
info "Checking prerequisites..."

command -v node >/dev/null 2>&1 || die "Node.js is required. Install from https://nodejs.org"
command -v npm  >/dev/null 2>&1 || die "npm is required (comes with Node.js)."
command -v git  >/dev/null 2>&1 || die "git is required."

NODE_MAJOR=$(node -e "console.log(process.versions.node.split('.')[0])")
[[ "$NODE_MAJOR" -lt 18 ]] && die "Node.js 18+ required (you have $(node -v))."

ok "Node $(node -v), npm $(npm -v), git $(git --version | awk '{print $3}')"

# --- Clone ---
if [[ -d "$DIR" ]]; then
  info "Directory '$DIR' exists — pulling latest..."
  (cd "$DIR" && git pull --rebase) || die "Failed to update existing repo."
else
  info "Cloning Manifold repository..."
  git clone "$REPO" "$DIR" || die "Clone failed."
fi

cd "$DIR/federation"

# --- Install & Build ---
info "Installing dependencies..."
npm install --ignore-scripts 2>&1 | tail -1

info "Building federation server..."
npm run build 2>&1 | tail -3

ok "Build complete."

# --- Config ---
if [[ -f "manifold.config.json" ]]; then
  info "Existing config found at manifold.config.json — skipping config generation."
else
  echo ""
  echo -e "${BOLD}What should your hub be called?${NC} (e.g. 'my-rig', 'atlas', 'claudia')"
  read -rp "> " HUB_NAME 2>/dev/null || HUB_NAME="hub-$(hostname | tr '[:upper:]' '[:lower:]')"
  HUB_NAME="${HUB_NAME:-hub-$(hostname | tr '[:upper:]' '[:lower:]')}"

  # Optional: peer addresses
  echo ""
  echo -e "Enter peer addresses to connect to (comma-separated), or press Enter to start standalone:"
  read -rp "> " PEERS 2>/dev/null || PEERS=""

  PEER_JSON="[]"
  if [[ -n "$PEERS" ]]; then
    # Build JSON array
    PEER_JSON=$(echo "$PEERS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | jq -R . | jq -s .)
  fi

  cat > manifold.config.json <<CFG
{
  "name": "${HUB_NAME}",
  "localPort": 8765,
  "federationPort": 8766,
  "restPort": 8767,
  "peers": ${PEER_JSON},
  "restEnabled": true
}
CFG
  ok "Config written to manifold.config.json"
fi

# --- Start? ---
echo ""
echo -e "${BOLD}Start the federation server now?${NC} [Y/n]"
read -rp "> " START_NOW 2>/dev/null || START_NOW="y"
START_NOW="${START_NOW:-y}"

if [[ "$START_NOW" =~ ^[Yy] ]]; then
  ok "Starting Manifold Federation hub..."
  echo ""
  npx tsx src/cli.ts --config manifold.config.json
else
  echo ""
  ok "You're all set! Start your hub with:"
  echo ""
  echo -e "  ${CYAN}cd ${DIR}/federation${NC}"
  echo -e "  ${CYAN}npx tsx src/cli.ts --config manifold.config.json${NC}"
  echo ""
  echo -e "API will be at ${CYAN}http://localhost:8767/public/mesh${NC}"
fi
