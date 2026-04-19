import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { MeshPass } from '../src/identity/meshpass.js'
import { promises as fs } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

describe('MeshPass', () => {
  let testDir: string

  beforeEach(async () => {
    // Create a temporary directory for test files
    testDir = await fs.mkdtemp(join(tmpdir(), 'meshpass-test-'))
  })

  afterEach(async () => {
    // Clean up test files
    try {
      await fs.rm(testDir, { recursive: true, force: true })
    } catch {
      // Ignore cleanup errors
    }
  })

  describe('generate', () => {
    it('should generate a new MeshPass with valid keypair', async () => {
      const meshPass = await MeshPass.generate()
      
      expect(meshPass).toBeDefined()
      expect(meshPass.getPublicKeyHex()).toMatch(/^[a-f0-9]{64}$/)
      expect(meshPass.getFingerprint()).toMatch(/^[a-f0-9]{16}$/)
    })

    it('should generate different keypairs each time', async () => {
      const meshPass1 = await MeshPass.generate()
      const meshPass2 = await MeshPass.generate()
      
      expect(meshPass1.getPublicKeyHex()).not.toBe(meshPass2.getPublicKeyHex())
      expect(meshPass1.getFingerprint()).not.toBe(meshPass2.getFingerprint())
    })
  })

  describe('save and load', () => {
    it('should save to file and load back without passphrase', async () => {
      const original = await MeshPass.generate()
      const filePath = join(testDir, 'test-meshpass.json')
      
      // Save without passphrase
      await original.saveTo(filePath)
      
      // Verify file exists and has expected structure
      const fileContent = await fs.readFile(filePath, 'utf-8')
      const data = JSON.parse(fileContent)
      expect(data).toHaveProperty('publicKey')
      expect(data).toHaveProperty('encryptedPrivateKey')
      expect(data).toHaveProperty('salt', '')
      expect(data).toHaveProperty('iv', '')
      expect(data).toHaveProperty('authTag', '')
      expect(data).toHaveProperty('version', 1)
      
      // Load back
      const loaded = await MeshPass.loadFrom(filePath)
      
      expect(loaded.getPublicKeyHex()).toBe(original.getPublicKeyHex())
      expect(loaded.getFingerprint()).toBe(original.getFingerprint())
    })

    it('should save to file and load back with passphrase (AES-256-GCM)', async () => {
      const original = await MeshPass.generate()
      const filePath = join(testDir, 'test-encrypted.json')
      const passphrase = 'super-secret-password-123'
      
      // Save with passphrase
      await original.saveTo(filePath, passphrase)
      
      // Verify file structure includes encryption data
      const fileContent = await fs.readFile(filePath, 'utf-8')
      const data = JSON.parse(fileContent)
      expect(data.salt).toMatch(/^[a-f0-9]{64}$/) // 32 bytes = 64 hex chars
      expect(data.iv).toMatch(/^[a-f0-9]{32}$/)   // 16 bytes = 32 hex chars
      expect(data.authTag).toMatch(/^[a-f0-9]{32}$/) // 16 bytes = 32 hex chars
      expect(data.encryptedPrivateKey).not.toBe(original.getPublicKeyHex())
      
      // Load back with correct passphrase
      const loaded = await MeshPass.loadFrom(filePath, passphrase)
      
      expect(loaded.getPublicKeyHex()).toBe(original.getPublicKeyHex())
      expect(loaded.getFingerprint()).toBe(original.getFingerprint())
    })

    it('should reject wrong passphrase on load', async () => {
      const original = await MeshPass.generate()
      const filePath = join(testDir, 'test-wrong-pass.json')
      
      await original.saveTo(filePath, 'correct-password')
      
      await expect(MeshPass.loadFrom(filePath, 'wrong-password')).rejects.toThrow(
        /Invalid passphrase|bad decrypt|unable to authenticate/i
      )
    })

    it('should warn when saving without passphrase', async () => {
      const original = await MeshPass.generate()
      const filePath = join(testDir, 'test-warning.json')
      
      // Mock console.warn
      const originalWarn = console.warn
      const warnMock = vi.fn()
      console.warn = warnMock
      
      try {
        await original.saveTo(filePath)
        expect(warnMock).toHaveBeenCalledWith('⚠️  MeshPass private key stored in PLAINTEXT. Use a passphrase for production!')
      } finally {
        console.warn = originalWarn
      }
    })

    it('should throw error when passphrase provided but file is not encrypted', async () => {
      const original = await MeshPass.generate()
      const filePath = join(testDir, 'test-plaintext.json')
      
      // Save without passphrase
      await original.saveTo(filePath)
      
      // Try to load with passphrase
      await expect(MeshPass.loadFrom(filePath, 'some-password')).rejects.toThrow(
        'Passphrase provided but file is not encrypted'
      )
    })
  })

  describe('signing and verification', () => {
    it('should sign a message and verify the signature', async () => {
      const meshPass = await MeshPass.generate()
      const message = 'Hello, Manifold mesh!'
      
      const signature = await meshPass.sign(message)
      expect(signature).toMatch(/^[a-f0-9]+$/)
      
      const isValid = await meshPass.verify(message, signature)
      expect(isValid).toBe(true)
    })

    it('should sign binary data and verify the signature', async () => {
      const meshPass = await MeshPass.generate()
      const message = new Uint8Array([1, 2, 3, 4, 5])
      
      const signature = await meshPass.sign(message)
      const isValid = await meshPass.verify(message, signature)
      expect(isValid).toBe(true)
    })

    it('should reject tampered signatures', async () => {
      const meshPass = await MeshPass.generate()
      const message = 'Original message'
      
      const signature = await meshPass.sign(message)
      
      // Tamper with the signature
      const tamperedSig = signature.slice(0, -2) + '00'
      
      const isValid = await meshPass.verify(message, tamperedSig)
      expect(isValid).toBe(false)
    })

    it('should reject signatures with wrong message', async () => {
      const meshPass = await MeshPass.generate()
      const originalMessage = 'Original message'
      const tamperedMessage = 'Tampered message'
      
      const signature = await meshPass.sign(originalMessage)
      const isValid = await meshPass.verify(tamperedMessage, signature)
      expect(isValid).toBe(false)
    })

    it('should verify signatures with static public key', async () => {
      const meshPass = await MeshPass.generate()
      const message = 'Test message'
      
      const signature = await meshPass.sign(message)
      const publicKeyHex = meshPass.getPublicKeyHex()
      
      const isValid = await MeshPass.verifyWithPublicKey(message, signature, publicKeyHex)
      expect(isValid).toBe(true)
      
      // Test with wrong public key
      const otherMeshPass = await MeshPass.generate()
      const wrongPubKey = otherMeshPass.getPublicKeyHex()
      const isWrongValid = await MeshPass.verifyWithPublicKey(message, signature, wrongPubKey)
      expect(isWrongValid).toBe(false)
    })

    it('should handle invalid signature format gracefully', async () => {
      const meshPass = await MeshPass.generate()
      const message = 'Test message'
      
      // Invalid hex
      const isValid1 = await meshPass.verify(message, 'invalid-hex')
      expect(isValid1).toBe(false)
      
      // Too short
      const isValid2 = await meshPass.verify(message, 'abc123')
      expect(isValid2).toBe(false)
      
      // Empty
      const isValid3 = await meshPass.verify(message, '')
      expect(isValid3).toBe(false)
    })
  })

  describe('import/export', () => {
    it('should export and import without passphrase', async () => {
      const original = await MeshPass.generate()
      
      const exported = original.export()
      expect(exported).toHaveProperty('publicKey')
      expect(exported).toHaveProperty('privateKey')
      expect(exported).toHaveProperty('version', 1)
      
      const imported = await MeshPass.import(exported)
      expect(imported.getPublicKeyHex()).toBe(original.getPublicKeyHex())
      
      // Test signing works on imported key
      const message = 'Test after import'
      const origSig = await original.sign(message)
      const impSig = await imported.sign(message)
      
      expect(await original.verify(message, impSig)).toBe(true)
      expect(await imported.verify(message, origSig)).toBe(true)
    })

    it('should export and import with passphrase (AES-256-GCM)', async () => {
      const original = await MeshPass.generate()
      const passphrase = 'export-import-password'
      
      const exported = original.export(passphrase)
      
      // Exported private key should be longer due to salt+iv+tag+encrypted
      expect(exported.privateKey.length).toBeGreaterThan(64) // More than just the raw key
      
      const imported = await MeshPass.import(exported, passphrase)
      expect(imported.getPublicKeyHex()).toBe(original.getPublicKeyHex())
      
      // Test signing works on imported key
      const message = 'Test encrypted import'
      const signature = await imported.sign(message)
      expect(await original.verify(message, signature)).toBe(true)
    })

    it('should reject wrong passphrase on import', async () => {
      const original = await MeshPass.generate()
      
      const exported = original.export('correct-password')
      
      await expect(MeshPass.import(exported, 'wrong-password')).rejects.toThrow(
        'Invalid passphrase or corrupted encryption'
      )
    })

    it('should handle invalid export format', async () => {
      const invalidExport = {
        publicKey: 'invalid-hex-string',
        privateKey: 'invalid-hex-string',
        version: 1,
        createdAt: new Date().toISOString()
      }
      
      await expect(MeshPass.import(invalidExport)).rejects.toThrow()
    })

    it('should reject unsupported version', async () => {
      const original = await MeshPass.generate()
      const exported = original.export()
      exported.version = 999 // Unsupported version
      
      await expect(MeshPass.import(exported)).rejects.toThrow('Unsupported MeshPass version: 999')
    })
  })

  describe('round-trip compatibility', () => {
    it('should maintain consistency across save/load/export/import cycles', async () => {
      const original = await MeshPass.generate()
      const passphrase = 'roundtrip-test-123'
      const filePath = join(testDir, 'roundtrip.json')
      
      // Save to file with encryption
      await original.saveTo(filePath, passphrase)
      
      // Load from file
      const loaded = await MeshPass.loadFrom(filePath, passphrase)
      
      // Export with different passphrase
      const exported = loaded.export('different-password')
      
      // Import with new passphrase
      const imported = await MeshPass.import(exported, 'different-password')
      
      // All should have same public key
      expect(imported.getPublicKeyHex()).toBe(original.getPublicKeyHex())
      expect(imported.getFingerprint()).toBe(original.getFingerprint())
      
      // All should be able to sign/verify the same messages
      const testMessage = 'Roundtrip consistency test'
      const origSignature = await original.sign(testMessage)
      const importedSignature = await imported.sign(testMessage)
      
      expect(await imported.verify(testMessage, origSignature)).toBe(true)
      expect(await original.verify(testMessage, importedSignature)).toBe(true)
    })
  })
})