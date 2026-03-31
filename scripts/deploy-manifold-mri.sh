#!/usr/bin/env bash
# deploy-manifold-mri.sh — build Stella's MRI and deploy to manifold.surge.sh
# Run from repo root: bash scripts/deploy-manifold-mri.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="/home/zaphod/manifold-mri-deploy"
SURGE_TOKEN="161326cdb6cb122b5efbf71f9e8f4dce"

echo "── Generating Stella MRI ──────────────────────────────────"
cd "$REPO_ROOT"
python3 scripts/stella_mri.py

echo "── Preparing deploy dir ───────────────────────────────────"
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"
cp scripts/stella_mri.html "$DEPLOY_DIR/index.html"

echo "── Sourcing nvm ───────────────────────────────────────────"
export NVM_DIR="$HOME/.nvm"
# shellcheck source=/dev/null
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

echo "── Deploying to manifold.surge.sh ─────────────────────────"
SURGE_TOKEN="$SURGE_TOKEN" npx surge "$DEPLOY_DIR" manifold.surge.sh

echo "Deployed → https://manifold.surge.sh"
