/**
 * MeshPass: Cryptographic identity credential for Manifold mesh agents.
 * 
 * One keypair per agent, portable across all hubs. Generate once, yours forever.
 * Under the hood: Ed25519 keypair, but users never see "Ed25519" - it's always "MeshPass".
 */

import * as ed25519 from '@noble/ed25519'
import { randomBytes, createHash, scryptSync, createCipheriv, createDecipheriv } from 'crypto'
import { promises as fs } from 'fs'
import { dirname } from 'path'
import { homedir } from 'os'

// Initialize noble/ed25519 with Node.js crypto
ed25519.etc.sha512Sync = (...m) => createHash('sha512').update(ed25519.etc.concatBytes(...m)).digest()

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
  /** Encrypted private key (or plaintext if no passphrase) */
  encryptedPrivateKey: string
  /** Encryption salt (empty if no passphrase) */
  salt: string
  /** Initialization vector for AES-256-GCM (empty if no passphrase) */
  iv: string
  /** Authentication tag for AES-256-GCM (empty if no passphrase) */
  authTag: string
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
    const privateKey = randomBytes(32)
    
    // Derive public key using Ed25519
    const publicKey = await ed25519.getPublicKey(privateKey)
    
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
   * @security This method handles decryption of private key material using AES-256-GCM.
   * The private key is only decrypted in memory and never stored in plaintext on disk
   * unless no passphrase is provided (development/testing only).
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
      if (passphrase && data.salt && data.iv && data.authTag) {
        // Decrypt private key using AES-256-GCM
        const salt = Buffer.from(data.salt, 'hex')
        const iv = Buffer.from(data.iv, 'hex')
        const authTag = Buffer.from(data.authTag, 'hex')
        const encrypted = Buffer.from(data.encryptedPrivateKey, 'hex')
        
        // Derive key using scrypt
        const key = scryptSync(passphrase, salt, 32) // 256 bits
        
        // Decrypt using AES-256-GCM
        const decipher = createDecipheriv('aes-256-gcm', key, iv)
        decipher.setAuthTag(authTag)
        
        const decrypted = Buffer.concat([
          decipher.update(encrypted),
          decipher.final()
        ])
        
        privateKey = new Uint8Array(decrypted)
      } else if (passphrase) {
        throw new Error('Passphrase provided but file is not encrypted (missing salt, iv, or authTag)')
      } else {
        // Unencrypted (for development/testing)
        privateKey = new Uint8Array(Buffer.from(data.encryptedPrivateKey, 'hex'))
      }

      return new MeshPass(publicKey, privateKey, data.createdAt)
    } catch (error) {
      if (error instanceof Error && error.message.includes('bad decrypt')) {
        throw new Error('Invalid passphrase or corrupted encryption')
      }
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
   * @security This method handles encryption of private key material using AES-256-GCM.
   * If no passphrase is provided, the private key is stored in plaintext (development/testing only).
   * In production, always provide a passphrase to encrypt the private key.
   */
  async saveTo(path: string, passphrase?: string): Promise<void> {
    // Ensure directory exists
    await fs.mkdir(dirname(path), { recursive: true })

    let encryptedPrivateKey: string
    let salt = ''
    let iv = ''
    let authTag = ''
    
    if (passphrase) {
      // Generate random salt and IV
      const saltBuffer = randomBytes(32) // 256 bits
      const ivBuffer = randomBytes(16)   // 128 bits for AES-256-GCM
      
      salt = saltBuffer.toString('hex')
      iv = ivBuffer.toString('hex')
      
      // Derive key using scrypt
      const key = scryptSync(passphrase, saltBuffer, 32) // 256 bits
      
      // Encrypt private key using AES-256-GCM
      const cipher = createCipheriv('aes-256-gcm', key, ivBuffer)
      const encrypted = Buffer.concat([
        cipher.update(Buffer.from(this.privateKey)),
        cipher.final()
      ])
      
      authTag = cipher.getAuthTag().toString('hex')
      encryptedPrivateKey = encrypted.toString('hex')
    } else {
      // Store unencrypted (for development/testing)
      console.warn('⚠️  MeshPass private key stored in PLAINTEXT. Use a passphrase for production!')
      encryptedPrivateKey = Buffer.from(this.privateKey).toString('hex')
    }

    const data: MeshPassFileData = {
      publicKey: Buffer.from(this.publicKey).toString('hex'),
      encryptedPrivateKey,
      salt,
      iv,
      authTag,
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
    const signature = await ed25519.sign(msgBytes, this.privateKey)
    return Buffer.from(signature).toString('hex')
  }

  /**
   * Verify a signature against this MeshPass's public key.
   */
  async verify(message: string | Uint8Array, signature: string): Promise<boolean> {
    try {
      const msgBytes = typeof message === 'string' ? new TextEncoder().encode(message) : message
      const sigBytes = new Uint8Array(Buffer.from(signature, 'hex'))
      return await ed25519.verify(sigBytes, msgBytes, this.publicKey)
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
      return await ed25519.verify(sigBytes, msgBytes, pubKey)
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
   * @security This method handles encryption of private key material for secure transport.
   * The exported data uses the same AES-256-GCM encryption as file storage.
   */
  export(passphrase?: string): MeshPassKeyData {
    let privateKey: string
    
    if (passphrase) {
      // Use proper AES-256-GCM encryption for export
      const salt = randomBytes(32)
      const iv = randomBytes(16)
      const key = scryptSync(passphrase, salt, 32)
      
      const cipher = createCipheriv('aes-256-gcm', key, iv)
      const encrypted = Buffer.concat([
        cipher.update(Buffer.from(this.privateKey)),
        cipher.final()
      ])
      const authTag = cipher.getAuthTag()
      
      // Encode as: salt(64) + iv(32) + authTag(32) + encrypted
      const combined = Buffer.concat([salt, iv, authTag, encrypted])
      privateKey = combined.toString('hex')
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
   * @security This method handles decryption of exported private key material.
   */
  static async import(data: MeshPassKeyData, passphrase?: string): Promise<MeshPass> {
    if (data.version !== 1) {
      throw new Error(`Unsupported MeshPass version: ${data.version}`)
    }

    const publicKey = new Uint8Array(Buffer.from(data.publicKey, 'hex'))
    
    let privateKey: Uint8Array
    if (passphrase) {
      const combined = Buffer.from(data.privateKey, 'hex')
      
      if (combined.length < 64 + 16 + 16) { // salt + iv + authTag minimum
        throw new Error('Invalid encrypted private key format')
      }
      
      // Extract components: salt(32) + iv(16) + authTag(16) + encrypted
      const salt = combined.subarray(0, 32)
      const iv = combined.subarray(32, 48)
      const authTag = combined.subarray(48, 64)
      const encrypted = combined.subarray(64)
      
      // Derive key and decrypt
      const key = scryptSync(passphrase, salt, 32)
      
      const decipher = createDecipheriv('aes-256-gcm', key, iv)
      decipher.setAuthTag(authTag)
      
      try {
        const decrypted = Buffer.concat([
          decipher.update(encrypted),
          decipher.final()
        ])
        privateKey = new Uint8Array(decrypted)
      } catch {
        throw new Error('Invalid passphrase or corrupted encryption')
      }
    } else {
      privateKey = new Uint8Array(Buffer.from(data.privateKey, 'hex'))
    }

    return new MeshPass(publicKey, privateKey, data.createdAt)
  }


}