/**
 * MeshPass: Cryptographic identity credential for Manifold mesh agents.
 * 
 * One keypair per agent, portable across all hubs. Generate once, yours forever.
 * Under the hood: Ed25519 keypair, but users never see "Ed25519" - it's always "MeshPass".
 */

import { getRandomBytes, sign, verify, etc } from '@noble/ed25519'
import { randomBytes } from 'crypto'
import { promises as fs } from 'fs'
import { dirname } from 'path'
import { homedir } from 'os'

export interface MeshPassKeyData {
  /** Public key as hex string */
  publicKey: string
  /** Private key as hex string (encrypted in file) */
  privateKey: string
  /** Creation timestamp */
  createdAt: string
  /** Version for future compatibility */
  version: number
}

export interface MeshPassFileData {
  /** Public key as hex string */
  publicKey: string
  /** Encrypted private key */
  encryptedPrivateKey: string
  /** Encryption salt */
  salt: string
  /** Creation timestamp */
  createdAt: string
  /** Version for future compatibility */
  version: number
}

export class MeshPass {
  private publicKey: Uint8Array
  private privateKey: Uint8Array
  private readonly createdAt: string

  /**
   * Create a MeshPass from raw key material.
   * Private - use generate() or load() instead.
   */
  private constructor(publicKey: Uint8Array, privateKey: Uint8Array, createdAt?: string) {
    this.publicKey = publicKey
    this.privateKey = privateKey
    this.createdAt = createdAt ?? new Date().toISOString()
  }

  /**
   * Generate a new MeshPass with a fresh Ed25519 keypair.
   */
  static async generate(): Promise<MeshPass> {
    // Generate 32 random bytes for private key
    const privateKey = getRandomBytes(32)
    
    // Derive public key
    const publicKey = await etc.getPublicKey(privateKey)
    
    return new MeshPass(publicKey, privateKey)
  }

  /**
   * Load a MeshPass from the default location (~/.manifold/meshpass.json).
   */
  static async load(passphrase?: string): Promise<MeshPass> {
    const defaultPath = `${homedir()}/.manifold/meshpass.json`
    return this.loadFrom(defaultPath, passphrase)
  }

  /**
   * Load a MeshPass from a specific file path.
   */
  static async loadFrom(path: string, passphrase?: string): Promise<MeshPass> {
    try {
      const content = await fs.readFile(path, 'utf-8')
      const data: MeshPassFileData = JSON.parse(content)
      
      if (data.version !== 1) {
        throw new Error(`Unsupported MeshPass version: ${data.version}`)
      }

      const publicKey = new Uint8Array(Buffer.from(data.publicKey, 'hex'))
      
      let privateKey: Uint8Array
      if (passphrase) {
        // Decrypt private key (simple XOR with passphrase hash for now)
        const passphraseHash = await this.hashPassphrase(passphrase, data.salt)
        const encrypted = Buffer.from(data.encryptedPrivateKey, 'hex')
        privateKey = new Uint8Array(encrypted.map((b, i) => b ^ passphraseHash[i % passphraseHash.length]))
      } else {
        // Unencrypted (for development/testing)
        privateKey = new Uint8Array(Buffer.from(data.encryptedPrivateKey, 'hex'))
      }

      return new MeshPass(publicKey, privateKey, data.createdAt)
    } catch (error) {
      throw new Error(`Failed to load MeshPass from ${path}: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  /**
   * Save this MeshPass to the default location (~/.manifold/meshpass.json).
   */
  async save(passphrase?: string): Promise<void> {
    const defaultPath = `${homedir()}/.manifold/meshpass.json`
    await this.saveTo(defaultPath, passphrase)
  }

  /**
   * Save this MeshPass to a specific file path.
   */
  async saveTo(path: string, passphrase?: string): Promise<void> {
    // Ensure directory exists
    await fs.mkdir(dirname(path), { recursive: true })

    let encryptedPrivateKey: string
    let salt = ''
    
    if (passphrase) {
      // Generate random salt
      salt = Buffer.from(randomBytes(16)).toString('hex')
      
      // Encrypt private key (simple XOR with passphrase hash)
      const passphraseHash = await MeshPass.hashPassphrase(passphrase, salt)
      const encrypted = Array.from(this.privateKey).map((b, i) => b ^ passphraseHash[i % passphraseHash.length])
      encryptedPrivateKey = Buffer.from(encrypted).toString('hex')
    } else {
      // Store unencrypted (for development/testing)
      encryptedPrivateKey = Buffer.from(this.privateKey).toString('hex')
    }

    const data: MeshPassFileData = {
      publicKey: Buffer.from(this.publicKey).toString('hex'),
      encryptedPrivateKey,
      salt,
      createdAt: this.createdAt,
      version: 1
    }

    await fs.writeFile(path, JSON.stringify(data, null, 2), 'utf-8')
  }

  /**
   * Sign a message with this MeshPass.
   * Returns signature as hex string.
   */
  async sign(message: string | Uint8Array): Promise<string> {
    const msgBytes = typeof message === 'string' ? new TextEncoder().encode(message) : message
    const signature = await sign(msgBytes, this.privateKey)
    return Buffer.from(signature).toString('hex')
  }

  /**
   * Verify a signature against this MeshPass's public key.
   */
  async verify(message: string | Uint8Array, signature: string): Promise<boolean> {
    try {
      const msgBytes = typeof message === 'string' ? new TextEncoder().encode(message) : message
      const sigBytes = new Uint8Array(Buffer.from(signature, 'hex'))
      return await verify(sigBytes, msgBytes, this.publicKey)
    } catch {
      return false
    }
  }

  /**
   * Verify a signature against any public key.
   */
  static async verifyWithPublicKey(message: string | Uint8Array, signature: string, publicKeyHex: string): Promise<boolean> {
    try {
      const msgBytes = typeof message === 'string' ? new TextEncoder().encode(message) : message
      const sigBytes = new Uint8Array(Buffer.from(signature, 'hex'))
      const pubKey = new Uint8Array(Buffer.from(publicKeyHex, 'hex'))
      return await verify(sigBytes, msgBytes, pubKey)
    } catch {
      return false
    }
  }

  /**
   * Get the public key as a hex string.
   */
  getPublicKeyHex(): string {
    return Buffer.from(this.publicKey).toString('hex')
  }

  /**
   * Get the public key fingerprint (first 16 chars of hex).
   */
  getFingerprint(): string {
    return this.getPublicKeyHex().slice(0, 16)
  }

  /**
   * Export MeshPass data for import on another machine.
   */
  export(passphrase?: string): MeshPassKeyData {
    let privateKey: string
    
    if (passphrase) {
      // This is a simple implementation - in production, use proper encryption
      const hash = Buffer.from(passphrase).toString('hex').padEnd(64, '0').slice(0, 64)
      const encrypted = Array.from(this.privateKey).map((b, i) => b ^ parseInt(hash.slice(i % 32 * 2, (i % 32 + 1) * 2), 16))
      privateKey = Buffer.from(encrypted).toString('hex')
    } else {
      privateKey = Buffer.from(this.privateKey).toString('hex')
    }

    return {
      publicKey: this.getPublicKeyHex(),
      privateKey,
      createdAt: this.createdAt,
      version: 1
    }
  }

  /**
   * Import MeshPass data from another machine.
   */
  static async import(data: MeshPassKeyData, passphrase?: string): Promise<MeshPass> {
    if (data.version !== 1) {
      throw new Error(`Unsupported MeshPass version: ${data.version}`)
    }

    const publicKey = new Uint8Array(Buffer.from(data.publicKey, 'hex'))
    
    let privateKey: Uint8Array
    if (passphrase) {
      const hash = Buffer.from(passphrase).toString('hex').padEnd(64, '0').slice(0, 64)
      const encrypted = Buffer.from(data.privateKey, 'hex')
      privateKey = new Uint8Array(Array.from(encrypted).map((b, i) => b ^ parseInt(hash.slice(i % 32 * 2, (i % 32 + 1) * 2), 16)))
    } else {
      privateKey = new Uint8Array(Buffer.from(data.privateKey, 'hex'))
    }

    return new MeshPass(publicKey, privateKey, data.createdAt)
  }

  /**
   * Hash a passphrase with salt for encryption.
   */
  private static async hashPassphrase(passphrase: string, salt: string): Promise<Uint8Array> {
    // Simple implementation - in production, use proper PBKDF2 or scrypt
    const combined = passphrase + salt
    const encoder = new TextEncoder()
    const data = encoder.encode(combined)
    
    // Use built-in crypto.subtle if available, otherwise simple hash
    if (typeof crypto !== 'undefined' && crypto.subtle) {
      const hashBuffer = await crypto.subtle.digest('SHA-256', data)
      return new Uint8Array(hashBuffer)
    } else {
      // Fallback: simple hash for Node.js environments
      const { createHash } = await import('crypto')
      const hash = createHash('sha256').update(data).digest()
      return new Uint8Array(hash)
    }
  }
}