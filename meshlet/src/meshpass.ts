/**
 * Simplified MeshPass implementation for Meshlet
 * Generates Ed25519 keypairs and signs authentication messages
 */

import * as ed25519 from '@noble/ed25519'
import { randomBytes, createHash } from 'crypto'

// Initialize noble/ed25519 with Node.js crypto
ed25519.etc.sha512Sync = (...m) => createHash('sha512').update(ed25519.etc.concatBytes(...m)).digest()

export class MeshPass {
  private publicKey: Uint8Array
  private privateKey: Uint8Array
  private readonly createdAt: string

  private constructor(publicKey: Uint8Array, privateKey: Uint8Array, createdAt?: string) {
    this.publicKey = publicKey
    this.privateKey = privateKey
    this.createdAt = createdAt ?? new Date().toISOString()
  }

  /**
   * Generate a new MeshPass with a fresh Ed25519 keypair
   */
  static async generate(): Promise<MeshPass> {
    const privateKey = randomBytes(32)
    const publicKey = await ed25519.getPublicKey(privateKey)
    return new MeshPass(publicKey, privateKey)
  }

  /**
   * Sign a message with this MeshPass
   */
  async sign(message: string | Uint8Array): Promise<string> {
    const msgBytes = typeof message === 'string' ? new TextEncoder().encode(message) : message
    const signature = await ed25519.sign(msgBytes, this.privateKey)
    return Buffer.from(signature).toString('hex')
  }

  /**
   * Get the public key as a hex string
   */
  getPublicKeyHex(): string {
    return Buffer.from(this.publicKey).toString('hex')
  }

  /**
   * Get the public key fingerprint (first 16 chars of hex)
   */
  getFingerprint(): string {
    return this.getPublicKeyHex().slice(0, 16)
  }

  /**
   * Get creation timestamp
   */
  getCreatedAt(): string {
    return this.createdAt
  }
}

/**
 * Create a signed authentication message for The Gate
 */
export async function createAuthMessage(
  meshPass: MeshPass, 
  meshId: string, 
  nonce?: string
): Promise<{ meshId: string; nonce: string; timestamp: string; signature: string }> {
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