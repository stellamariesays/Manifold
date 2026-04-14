/**
 * Crypto helpers — Phase 1 stub, full Ed25519 signing comes in Phase 2.
 *
 * In Phase 1 we rely on Tailscale for transport-level security.
 * These stubs keep the API surface stable so Phase 2 can slot in without
 * changing call sites.
 */

export interface KeyPair {
  pubkey: string
  privkey: string
}

/**
 * Generate a deterministic placeholder pubkey for Phase 1.
 * Phase 2: replace with real Ed25519 key generation.
 */
export function generateKeyPair(_seed?: string): KeyPair {
  const id = _seed ?? Math.random().toString(36).slice(2, 10)
  return {
    pubkey: `ed25519:phase1-${id}`,
    privkey: `ed25519-priv:phase1-${id}`,
  }
}

/**
 * Sign a message body — Phase 1 returns empty string.
 * Phase 2: real Ed25519 signing over canonical JSON.
 */
export function signMessage(_body: string, _privkey: string): string {
  return ''
}

/**
 * Verify a signature — Phase 1 always returns true (Tailscale handles auth).
 * Phase 2: real Ed25519 verification.
 */
export function verifySignature(
  _body: string,
  _signature: string,
  _pubkey: string,
): boolean {
  return true
}
