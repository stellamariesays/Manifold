/**
 * Manifold Mesh Identity System
 * 
 * MeshPass: Cryptographic identity credential (Ed25519 keypair)
 * MeshID: Human-readable identity (name@hub format)
 */

import { MeshPass, type MeshPassKeyData, type MeshPassFileData } from './meshpass.js'
import { MeshID, MeshIDRegistry, type MeshIDData } from './meshid.js'

// Re-export everything
export { MeshPass, type MeshPassKeyData, type MeshPassFileData, MeshID, MeshIDRegistry, type MeshIDData }

// Re-export commonly used patterns
export const MESHID_REGEX = /^[a-zA-Z0-9_-]+@[a-zA-Z0-9_.-]+#[a-fA-F0-9]{8}$/
export const LEGACY_AGENT_KEY_REGEX = /^[a-zA-Z0-9_-]+@[a-zA-Z0-9_.-]+$/

/**
 * Validate a MeshID string format (name@hub#fingerprint).
 */
export function validateMeshIDFormat(meshIdString: string): boolean {
  return MESHID_REGEX.test(meshIdString)
}

/**
 * Validate a legacy agent key format (name@hub) used by capability-index.ts.
 */
export function validateAgentKeyFormat(agentKey: string): boolean {
  return LEGACY_AGENT_KEY_REGEX.test(agentKey)
}

/**
 * Create a safe filename from a MeshID string.
 */
export function meshIdToFilename(meshId: string): string {
  return meshId.replace('@', '_at_').replace(/[^a-zA-Z0-9_-]/g, '_')
}

/**
 * Generate a signed authentication message for mesh protocols.
 */
export async function createAuthMessage(meshPass: MeshPass, meshId: string, nonce?: string): Promise<{ meshId: string; nonce: string; timestamp: string; signature: string }> {
  const timestamp = new Date().toISOString()
  const nonceValue = nonce ?? Math.random().toString(36).substring(2, 15)
  
  // Message format for signing: "AUTH:{meshId}:{nonce}:{timestamp}"
  const message = `AUTH:${meshId}:${nonceValue}:${timestamp}`
  const signature = await meshPass.sign(message)
  
  return {
    meshId,
    nonce: nonceValue,
    timestamp,
    signature
  }
}

/**
 * Verify a signed authentication message.
 */
export async function verifyAuthMessage(
  authMsg: { meshId: string; nonce: string; timestamp: string; signature: string },
  publicKeyHex: string,
  maxAgeMs: number = 300000 // 5 minutes
): Promise<boolean> {
  try {
    // Check timestamp age
    const msgTime = new Date(authMsg.timestamp).getTime()
    const now = Date.now()
    if (now - msgTime > maxAgeMs) {
      return false // Message too old
    }

    // Verify signature
    const message = `AUTH:${authMsg.meshId}:${authMsg.nonce}:${authMsg.timestamp}`
    return await MeshPass.verifyWithPublicKey(message, authMsg.signature, publicKeyHex)
  } catch {
    return false
  }
}