/**
 * standalone.mts — Generic entry point for Manifold Federation Server.
 *
 * Reads config from a JSON file (via MANIFOLD_CONFIG env var or --config flag).
 * Designed for systemd / process managers — logs to stdout/stderr.
 *
 * Usage:
 *   MANIFOLD_CONFIG=/path/to/config.json npx tsx standalone.mts
 *   npx tsx standalone.mts --config /path/to/config.json
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ManifoldServer } from "./dist/server/index.js";

// ── Config schema ──────────────────────────────────────────────────────────────

interface StandaloneConfig {
  /** Hub name (e.g. "hog", "satelliteA") */
  name: string;
  /** Federation WebSocket port (peer-to-peer). Default: 8766 */
  federationPort?: number;
  /** Local WebSocket port (runners connect here). Default: 8768 */
  localPort?: number;
  /** REST API port. Default: 8777 */
  restPort?: number;
  /** Peer addresses to connect to on startup */
  peers?: string[];
  /** Path to atlas JSON file */
  atlasPath?: string;
  /** Enable debug logging. Default: false */
  debug?: boolean;
}

// ── Error handlers ─────────────────────────────────────────────────────────────

process.on("unhandledRejection", (err) => {
  console.error("[FATAL] Unhandled rejection:", err);
  process.exit(1);
});

process.on("uncaughtException", (err) => {
  console.error("[FATAL] Uncaught exception:", err);
  process.exit(1);
});

// ── Config loading ─────────────────────────────────────────────────────────────

function loadConfig(): StandaloneConfig {
  // 1. --config flag
  const configIdx = process.argv.indexOf("--config");
  const configPath =
    configIdx !== -1 && process.argv[configIdx + 1]
      ? process.argv[configIdx + 1]
      : process.env.MANIFOLD_CONFIG;

  if (!configPath) {
    console.error(
      "Usage: MANIFOLD_CONFIG=config.json npx tsx standalone.mts\n" +
        "   or: npx tsx standalone.mts --config config.json"
    );
    process.exit(1);
  }

  const resolved = resolve(configPath);
  console.log(`[standalone] Loading config from ${resolved}`);

  try {
    const raw = readFileSync(resolved, "utf-8");
    return JSON.parse(raw) as StandaloneConfig;
  } catch (err) {
    console.error(`[standalone] Failed to load config: ${err}`);
    process.exit(1);
  }
}

// ── Main ────────────────────────────────────────────────────────────────────────

async function main() {
  const config = loadConfig();

  if (!config.name) {
    console.error("[standalone] Config error: 'name' is required");
    process.exit(1);
  }

  const server = new ManifoldServer({
    name: config.name,
    federationPort: config.federationPort ?? 8766,
    localPort: config.localPort ?? 8768,
    restPort: config.restPort ?? 8777,
    peers: config.peers ?? [],
    atlasPath: config.atlasPath,
    debug: config.debug ?? false,
  });

  await server.start();
  console.log(
    `[standalone] Hub "${config.name}" running ` +
      `(federation=${config.federationPort ?? 8766}, ` +
      `local=${config.localPort ?? 8768}, ` +
      `rest=${config.restPort ?? 8777})`
  );
}

main();
