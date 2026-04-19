import { describe, it, expect, beforeEach } from 'vitest'
import { SigningMiddleware } from '../src/server/signing-middleware.js'
import { MeshPass, MeshIDRegistry, MeshID } from '../src/identity/index.js'
import type { FederationMessage } from '../src/protocol/messages.js'

describe('SigningMiddleware', () => {
  let middleware: SigningMiddleware
  let registry: MeshIDRegistry
  let meshPass: MeshPass
  let meshId: MeshID

  beforeEach(async () => {
    // Create test MeshPass and MeshID
    meshPass = await MeshPass.generate()
    meshId = MeshID.fromMeshPass(meshPass, 'alice', 'hub1')
    
    // Set up registry
    registry = new MeshIDRegistry()
    registry.register(meshId)
    
    // Create middleware
    middleware = new SigningMiddleware({
      meshRegistry: registry,
      requireSignatures: false,
      debug: false
    })
  })

  describe('verification of unsigned messages', () => {
    it('should pass through unsigned messages when signatures not required', async () => {
      const message: FederationMessage = {
        type: 'mesh_ping',
        timestamp: new Date().toISOString(),
        data: { hello: 'world' }
      }
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(true)
      expect(result.wasSigned).toBe(false)
      expect(result.wasRequired).toBe(false)
      expect(result.reason).toBeUndefined()
    })

    it('should reject unsigned messages for types that require signatures', async () => {
      const message: FederationMessage = {
        type: 'task_request',  // This type requires signature
        timestamp: new Date().toISOString(),
        data: { task: 'process-data' }
      }
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.wasSigned).toBe(false)
      expect(result.wasRequired).toBe(true)
      expect(result.reason).toBe("Message type 'task_request' requires signature")
    })

    it('should reject all unsigned messages when requireSignatures is true', async () => {
      const strictMiddleware = new SigningMiddleware({
        meshRegistry: registry,
        requireSignatures: true
      })
      
      const message: FederationMessage = {
        type: 'mesh_ping',
        timestamp: new Date().toISOString(),
        data: { hello: 'world' }
      }
      
      const result = await strictMiddleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.wasRequired).toBe(true)
    })
  })

  describe('verification of correctly signed messages', () => {
    it('should verify correctly signed messages', async () => {
      const unsigned: Partial<FederationMessage> = {
        type: 'task_request',
        data: { task: 'solar-analysis', priority: 5 }
      }
      
      const signed = await middleware.sign(unsigned, meshPass, meshId.toString())
      const result = await middleware.verify(signed)
      
      expect(result.valid).toBe(true)
      expect(result.wasSigned).toBe(true)
      expect(result.wasRequired).toBe(true)
      expect(result.verifiedSender).toBe(meshId.toString())
    })

    it('should verify signatures against embedded public key', async () => {
      const unsigned: Partial<FederationMessage> = {
        type: 'mesh_identity_announce',
        data: { identity: 'alice@hub1#fingerprint' }
      }
      
      const signed = await middleware.sign(unsigned, meshPass, meshId.toString())
      
      // Remove sender from registry to test embedded key verification
      registry.unregister(meshId.toString())
      
      const result = await middleware.verify(signed)
      
      expect(result.valid).toBe(true)
      expect(result.verifiedSender).toBe(meshId.toString())
    })

    it('should verify optional signatures on unrequired message types', async () => {
      const unsigned: Partial<FederationMessage> = {
        type: 'mesh_ping',
        data: { ping: true }
      }
      
      const signed = await middleware.sign(unsigned, meshPass, meshId.toString())
      const result = await middleware.verify(signed)
      
      expect(result.valid).toBe(true)
      expect(result.wasSigned).toBe(true)
      expect(result.wasRequired).toBe(false)
      expect(result.verifiedSender).toBe(meshId.toString())
    })
  })

  describe('rejection of invalid signatures', () => {
    it('should reject messages with invalid signatures', async () => {
      const signed = await middleware.sign({
        type: 'task_request',
        data: { task: 'test' }
      }, meshPass, meshId.toString())
      
      // Tamper with signature
      signed.signature = signed.signature!.slice(0, -2) + '00'
      
      const result = await middleware.verify(signed)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toBe('Invalid signature')
    })

    it('should reject messages with wrong identity claims', async () => {
      const otherMeshPass = await MeshPass.generate()
      const otherMeshId = MeshID.fromMeshPass(otherMeshPass, 'bob', 'hub2')
      registry.register(otherMeshId)
      
      // Sign with one key but claim different identity
      const message = await middleware.sign({
        type: 'mesh_auth',
        data: { auth: true }
      }, meshPass, otherMeshId.toString()) // Wrong identity claim
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toBe('Public key mismatch with registry')
    })

    it('should reject messages with missing signature fields', async () => {
      const message: FederationMessage = {
        type: 'task_request',
        timestamp: new Date().toISOString(),
        data: { task: 'test' },
        sender: meshId.toString(),
        // Missing signature
      }
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toBe("Message type 'task_request' requires signature")
    })

    it('should reject messages with unregistered sender and no embedded public key', async () => {
      const signed = await middleware.sign({
        type: 'task_request',
        data: { task: 'test' }
      }, meshPass, 'unknown@hub3#12345678')
      
      // Remove embedded public key
      delete signed.senderPublicKey
      
      const result = await middleware.verify(signed)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toBe("Sender 'unknown@hub3#12345678' not found in registry")
    })
  })

  describe('message age validation', () => {
    it('should reject messages that are too old', async () => {
      const oldTimestamp = new Date(Date.now() - 10 * 60 * 1000).toISOString() // 10 minutes ago
      
      const message: FederationMessage = {
        type: 'task_request',
        timestamp: oldTimestamp,
        data: { task: 'test' },
        sender: meshId.toString(),
        signature: 'fake-signature'
      }
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toMatch(/Message too old/)
    })

    it('should accept messages within age limit', async () => {
      const signed = await middleware.sign({
        type: 'mesh_ping',
        data: { ping: true }
      }, meshPass, meshId.toString())
      
      const result = await middleware.verify(signed)
      
      expect(result.valid).toBe(true)
    })
  })

  describe('registry management', () => {
    it('should handle missing registry gracefully', async () => {
      const emptyRegistry = new MeshIDRegistry()
      middleware.updateRegistry(emptyRegistry)
      
      const signed = await middleware.sign({
        type: 'task_request',
        data: { task: 'test' }
      }, meshPass, meshId.toString())
      
      // Should still work with embedded public key
      const result = await middleware.verify(signed)
      expect(result.valid).toBe(true)
    })

    it('should allow registering new MeshIDs', async () => {
      const newMeshPass = await MeshPass.generate()
      const newMeshId = MeshID.fromMeshPass(newMeshPass, 'charlie', 'hub3')
      
      middleware.registerMeshID(newMeshId.toString(), newMeshPass.getPublicKeyHex())
      
      const signed = await middleware.sign({
        type: 'mesh_auth',
        data: { auth: true }
      }, newMeshPass, newMeshId.toString())
      
      // Remove embedded key to test registry lookup
      delete signed.senderPublicKey
      
      const result = await middleware.verify(signed)
      expect(result.valid).toBe(true)
    })
  })

  describe('message signing', () => {
    it('should create properly formatted signed messages', async () => {
      const unsigned: Partial<FederationMessage> = {
        type: 'capability_announce',
        data: { capability: 'data-processing' }
      }
      
      const signed = await middleware.sign(unsigned, meshPass, meshId.toString())
      
      expect(signed).toHaveProperty('type', 'capability_announce')
      expect(signed).toHaveProperty('timestamp')
      expect(signed).toHaveProperty('sender', meshId.toString())
      expect(signed).toHaveProperty('signature')
      expect(signed).toHaveProperty('senderPublicKey', meshPass.getPublicKeyHex())
      expect(signed).toHaveProperty('data')
      
      // Timestamp should be recent
      const signedTime = new Date(signed.timestamp).getTime()
      const now = Date.now()
      expect(Math.abs(now - signedTime)).toBeLessThan(1000) // Within 1 second
    })

    it('should create canonical message format for consistent verification', async () => {
      const message1 = await middleware.sign({
        type: 'test',
        data: { b: 2, a: 1 } // Properties in different order
      }, meshPass, meshId.toString())
      
      const message2 = await middleware.sign({
        type: 'test',
        data: { a: 1, b: 2 } // Same data, different property order
      }, meshPass, meshId.toString())
      
      // Should both verify successfully (canonical ordering handles property order)
      const result1 = await middleware.verify(message1)
      const result2 = await middleware.verify(message2)
      
      expect(result1.valid).toBe(true)
      expect(result2.valid).toBe(true)
    })
  })

  describe('configuration', () => {
    it('should respect custom alwaysSignedTypes', async () => {
      const customMiddleware = new SigningMiddleware({
        meshRegistry: registry,
        alwaysSignedTypes: ['custom_message'],
        requireSignatures: false
      })
      
      const message: FederationMessage = {
        type: 'custom_message',
        timestamp: new Date().toISOString(),
        data: { custom: true }
      }
      
      const result = await customMiddleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.wasRequired).toBe(true)
      expect(result.reason).toBe("Message type 'custom_message' requires signature")
    })

    it('should respect custom maxMessageAge', async () => {
      const shortAgeMiddleware = new SigningMiddleware({
        meshRegistry: registry,
        maxMessageAge: 1000 // 1 second
      })
      
      // Wait a bit to ensure message is old
      await new Promise(resolve => setTimeout(resolve, 1100))
      
      const oldMessage: FederationMessage = {
        type: 'task_request',
        timestamp: new Date(Date.now() - 1100).toISOString(),
        data: { task: 'test' },
        sender: meshId.toString(),
        signature: 'fake-signature'
      }
      
      const result = await shortAgeMiddleware.verify(oldMessage)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toMatch(/Message too old/)
    })
  })

  describe('error handling', () => {
    it('should handle signature verification errors gracefully', async () => {
      const message: FederationMessage = {
        type: 'task_request',
        timestamp: new Date().toISOString(),
        data: { task: 'test' },
        sender: meshId.toString(),
        signature: 'invalid-signature-format',
        senderPublicKey: meshPass.getPublicKeyHex()
      }
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(false)
      expect(result.reason).toBe('Invalid signature')
    })

    it('should handle malformed public keys', async () => {
      const message: FederationMessage = {
        type: 'task_request',
        timestamp: new Date().toISOString(),
        data: { task: 'test' },
        sender: meshId.toString(),
        signature: 'valid-length-but-fake-signature-0123456789abcdef',
        senderPublicKey: 'invalid-public-key'
      }
      
      const result = await middleware.verify(message)
      
      expect(result.valid).toBe(false)
    })
  })
})