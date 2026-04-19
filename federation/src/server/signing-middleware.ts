/**
 * Signing Middleware: Verify signatures on mesh messages for authentication.
 * 
 * This middleware verifies that messages are signed by the claimed sender's MeshPass,
 * providing cryptographic authentication for all mesh communications.
 */

import { MeshPass, MeshIDRegistry } from '../identity/index.js'
import type { FederationMessage } from '../protocol/messages.js'

export interface SigningMiddlewareConfig {
  /** Registry of known MeshIDs and their public keys */
  meshRegistry: MeshIDRegistry
  
  /** Whether to require signatures on all messages (default: false for backward compatibility) */
  requireSignatures?: boolean
  
  /** Message types that must be signed even if requireSignatures is false */
  alwaysSignedTypes?: string[]
  
  /** Maximum message age in milliseconds (default: 5 minutes) */
  maxMessageAge?: number
  
  /** Enable debug logging */
  debug?: boolean
}

export interface VerificationResult {
  /** Whether the message passed verification */
  valid: boolean
  
  /** Reason for failure (if valid is false) */
  reason?: string
  
  /** Verified sender MeshID (if signature was valid) */
  verifiedSender?: string
  
  /** Whether message was signed */
  wasSigned: boolean
  
  /** Whether signature was required for this message type */
  wasRequired: boolean
}

export class SigningMiddleware {
  private readonly config: Required<SigningMiddlewareConfig>

  constructor(config: SigningMiddlewareConfig) {
    this.config = {
      requireSignatures: false,
      alwaysSignedTypes: [
        'mesh_identity_announce',
        'mesh_identity_verify', 
        'mesh_auth',
        'task_request',
        'task_result'
      ],
      maxMessageAge: 5 * 60 * 1000, // 5 minutes
      debug: false,
      ...config
    }
  }

  /**
   * Verify a federation message signature.
   */
  async verify(message: FederationMessage): Promise<VerificationResult> {
    const wasSigned = !!(message.signature && message.sender)
    const wasRequired = this.config.requireSignatures || this.config.alwaysSignedTypes.includes(message.type)

    // If signature is not required and not present, pass through
    if (!wasRequired && !wasSigned) {
      return {
        valid: true,
        wasSigned: false,
        wasRequired: false
      }
    }

    // If signature is required but not present, fail
    if (wasRequired && !wasSigned) {
      return {
        valid: false,
        reason: `Message type '${message.type}' requires signature`,
        wasSigned: false,
        wasRequired: true
      }
    }

    // If we have a signature, verify it
    if (wasSigned) {
      const verifyResult = await this._verifySignature(message)
      return {
        ...verifyResult,
        wasSigned: true,
        wasRequired
      }
    }

    // Should not reach here
    return {
      valid: false,
      reason: 'Unexpected verification state',
      wasSigned,
      wasRequired
    }
  }

  /**
   * Sign a message with the given MeshPass.
   */
  async sign(message: Partial<FederationMessage>, meshPass: MeshPass, meshId: string): Promise<FederationMessage> {
    const timestamp = new Date().toISOString()
    const messageWithTimestamp = {
      ...message,
      timestamp,
      sender: meshId
    } as FederationMessage

    // Create canonical message string for signing
    const canonicalMessage = this._createCanonicalMessage(messageWithTimestamp)
    const signature = await meshPass.sign(canonicalMessage)

    return {
      ...messageWithTimestamp,
      signature,
      senderPublicKey: meshPass.getPublicKeyHex()
    }
  }

  /**
   * Update the MeshID registry.
   */
  updateRegistry(registry: MeshIDRegistry): void {
    this.config.meshRegistry = registry
  }

  /**
   * Add a MeshID to the registry.
   */
  registerMeshID(meshId: string, publicKey: string): void {
    // Create a minimal MeshID object for registration
    const [name, hub] = meshId.split('@')
    const meshIdObj = {
      name,
      hub,
      fingerprint: publicKey.slice(0, 16),
      publicKey,
      createdAt: new Date().toISOString(),
      toString: () => meshId,
      toDisplayString: () => `${meshId} (${publicKey.slice(0, 16)}...)`,
      matches: (id: string) => id === meshId,
      sameIdentity: () => false,
      verify: async () => false,
      toData: () => ({
        name,
        hub,
        fingerprint: publicKey.slice(0, 16),
        publicKey,
        createdAt: new Date().toISOString()
      })
    } as any

    this.config.meshRegistry.register(meshIdObj)
  }

  // ── Private ─────────────────────────────────────────────────────────────────

  private async _verifySignature(message: FederationMessage): Promise<Pick<VerificationResult, 'valid' | 'reason' | 'verifiedSender'>> {
    if (!message.signature || !message.sender) {
      return {
        valid: false,
        reason: 'Missing signature or sender'
      }
    }

    // Check message age
    if (message.timestamp) {
      const messageTime = new Date(message.timestamp).getTime()
      const now = Date.now()
      if (now - messageTime > this.config.maxMessageAge) {
        return {
          valid: false,
          reason: `Message too old: ${Math.floor((now - messageTime) / 1000)}s > ${Math.floor(this.config.maxMessageAge / 1000)}s`
        }
      }
    }

    // Look up sender's public key
    let publicKey: string
    
    if (message.senderPublicKey) {
      // Public key provided in message
      publicKey = message.senderPublicKey
      
      // Verify it matches registry if available
      const registeredMeshId = this.config.meshRegistry.resolve(message.sender)
      if (registeredMeshId && registeredMeshId.publicKey !== publicKey) {
        return {
          valid: false,
          reason: 'Public key mismatch with registry'
        }
      }
    } else {
      // Look up in registry
      const meshId = this.config.meshRegistry.resolve(message.sender)
      if (!meshId) {
        return {
          valid: false,
          reason: `Sender '${message.sender}' not found in registry`
        }
      }
      publicKey = meshId.publicKey
    }

    // Create canonical message for verification
    const canonicalMessage = this._createCanonicalMessage(message)
    
    // Verify signature
    try {
      const isValid = await MeshPass.verifyWithPublicKey(canonicalMessage, message.signature, publicKey)
      
      if (isValid) {
        this._log('Signature verification successful', { sender: message.sender, type: message.type })
        return {
          valid: true,
          verifiedSender: message.sender
        }
      } else {
        return {
          valid: false,
          reason: 'Invalid signature'
        }
      }
    } catch (error) {
      return {
        valid: false,
        reason: `Signature verification error: ${error instanceof Error ? error.message : 'Unknown error'}`
      }
    }
  }

  /**
   * Create a canonical string representation of a message for signing/verification.
   * This ensures consistent signing across different implementations.
   */
  private _createCanonicalMessage(message: FederationMessage): string {
    // Create a copy without signature fields
    const { signature, senderPublicKey, ...messageForSigning } = message
    
    // Sort keys for deterministic serialization
    const sortedMessage = this._sortKeys(messageForSigning)
    
    // Return JSON string
    return JSON.stringify(sortedMessage)
  }

  /**
   * Recursively sort object keys for deterministic serialization.
   */
  private _sortKeys(obj: any): any {
    if (obj === null || typeof obj !== 'object') {
      return obj
    }
    
    if (Array.isArray(obj)) {
      return obj.map(item => this._sortKeys(item))
    }
    
    const sortedObj: any = {}
    for (const key of Object.keys(obj).sort()) {
      sortedObj[key] = this._sortKeys(obj[key])
    }
    
    return sortedObj
  }

  private _log(message: string, data?: any): void {
    if (this.config.debug) {
      const timestamp = new Date().toISOString()
      if (data) {
        console.log(`[${timestamp}] [SigningMiddleware] ${message}`, data)
      } else {
        console.log(`[${timestamp}] [SigningMiddleware] ${message}`)
      }
    }
  }
}