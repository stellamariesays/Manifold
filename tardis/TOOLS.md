# TOOLS.md - Local Notes
Dense lookup tables → `data/reference/toolbox.md`

## 🐙 GitHub
**Account:** `stellamariesays` | **Tokens:** `data/credentials/` ⚠️ solar-github.token needs rotation

## 🎙️ Voice Style
**Default:** Fast (1.5x). Slow for: important info, comedic timing, technical numbers.
**Outgoing TTS:** Hard cap 60s (~150 words). Soft target 30s casual.
**Incoming:** ≤60s auto-process | 60-300s ask first | >300s decline unless Hal approves.

## 🤖 Pi Coding Agent
**HOG (preferred):** `ssh marvin@100.70.172.34 'export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh" && pi'`
**Trillian:** `/home/zaphod/.npm-global/bin/pi` | **Fallback:** `scripts/pi-wrapper.sh`

## ⚙️ System Crontab
Script-runners (no LLM): state-gen (15min), btc-signal (15min), solar-watch (hourly), git-commit (23:00), backup (03:00), rsync (03:05).
OpenClaw cron: reasoning tasks only.
