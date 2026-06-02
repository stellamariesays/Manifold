#!/bin/bash
# sanitize-check.sh — run before commits to catch secrets in tracked files
# Usage: ./scripts/sanitize-check.sh
# Returns 0 if clean, 1 if secrets found

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FOUND=0

echo "🔍 Scanning for secrets in $REPO_ROOT..."

# Check for common secret patterns
PATTERNS=(
  'ghp_[0-9a-zA-Z]{36}'
  'github_pat_[0-9a-zA-Z_]{82}'
  'sk-[0-9a-zA-Z]{48}'
  'xox[bpas]-[0-9a-zA-Z-]+'
  'eyJhb[Gg]ciOi'
  'privkey_path.*=.*["/]home'
  'PRIVATE_KEY.*=.*0x'
  'secret.*=.*["\x27][a-zA-Z0-9]{20}'
)

# Check for IPs that look like Tailscale (100.64-127.x.x)
check_tailscale_ips() {
  local matches
  matches=$(grep -rn '100\.\(6[4-9]\|[7-9][0-9]\|1[0-1][0-9]\|12[0-7]\)\.[0-9]\+\.[0-9]\+' \
    --include="*.md" --include="*.json" --include="*.py" --include="*.yaml" \
    "$REPO_ROOT/memory/" "$REPO_ROOT/docs/" 2>/dev/null | grep -v node_modules || true)
  
  if [ -n "$matches" ]; then
    echo "⚠️  Tailscale IPs found in tracked files:"
    echo "$matches"
    echo ""
    FOUND=1
  fi
}

# Check for wallet private key paths
check_privkey_paths() {
  local matches
  matches=$(grep -rn 'privkey_path\|privkey.*=' \
    --include="*.md" --include="*.json" --include="*.py" \
    "$REPO_ROOT/memory/" "$REPO_ROOT/docs/" 2>/dev/null | grep -v node_modules | grep -v REDACTED || true)
  
  if [ -n "$matches" ]; then
    echo "🔴 Private key paths found in tracked files:"
    echo "$matches"
    echo ""
    FOUND=1
  fi
}

# Check for actual tokens/keys (match token patterns followed by actual alphanumeric tokens, not code identifiers)
check_tokens() {
  local matches
  # ghp_ and github_pat_ are always real tokens
  matches=$(grep -rnE '(ghp_[0-9a-zA-Z]{30,}|github_pat_[0-9a-zA-Z_]{30,}|sk-[0-9a-zA-Z]{30,}|xox[bpas]-[0-9a-zA-Z]{20,}|eyJhb[Gg]ciOi[0-9a-zA-Z]{10,})' \
    --include="*.md" --include="*.json" --include="*.py" --include="*.env" \
    "$REPO_ROOT/" 2>/dev/null | grep -v node_modules | grep -v '.git/' || true)
  
  if [ -n "$matches" ]; then
    echo "🔴 Live tokens/keys found:"
    echo "$matches"
    echo ""
    FOUND=1
  fi
}

check_tailscale_ips
check_privkey_paths
check_tokens

if [ "$FOUND" -eq 1 ]; then
  echo "❌ Sanitization check FAILED — fix above issues before committing"
  exit 1
else
  echo "✅ Clean — no secrets detected"
  exit 0
fi
