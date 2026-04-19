/**
 * MeshID: Human-readable identity derived from a MeshPass.
 * 
 * Format: `name@hub#fingerprint` (e.g., `stella@satelliteA#a1b2c3d4`, `eddie@thefog#9f8e7d6c`)
 * The fingerprint suffix avoids collision with capability-index internal agent keys (name@hub).
 */

import { MeshPass } from './meshpass.js'

export interface MeshIDData {
  /** Human-readable name (e.g., "stella") */
  name: string
  /** Hub name (e.g., "satelliteA") */
  hub: string
  /** Public key fingerprint */
  fingerprint: string
  /** Full public key hex */
  publicKey: string
  /** Creation timestamp */
  createdAt: string
}

export class MeshID {
  readonly name: string
  readonly hub: string
  readonly fingerprint: string
  readonly publicKey: string
  readonly createdAt: string

  /**
   * Create a MeshID from components.
   * Private - use fromMeshPass() or parse() instead.
   */
  private constructor(name: string, hub: string, fingerprint: string, publicKey: string, createdAt: string) {
    this.name = name
    this.hub = hub
    this.fingerprint = fingerprint
    this.publicKey = publicKey
    this.createdAt = createdAt
  }

  /**
   * Create a MeshID from a MeshPass and identity components.
   */
  static fromMeshPass(meshPass: MeshPass, name: string, hub: string): MeshID {
    return new MeshID(
      name,
      hub,
      meshPass.getFingerprint(),
      meshPass.getPublicKeyHex(),
      new Date().toISOString()
    )
  }

  /**
   * Parse a MeshID string (format: "name@hub#fingerprint") and extract components.
   * Note: This only gives you the string components - you need a registry to resolve to keys.
   */
  static parse(meshIdString: string): { name: string; hub: string; fingerprint?: string } {
    if (!meshIdString.includes('@')) {
      throw new Error(`Invalid MeshID format: ${meshIdString} (expected name@hub#fingerprint)`)
    }

    const [nameHub, fingerprint] = meshIdString.split('#', 2)
    const [name, hub] = nameHub.split('@', 2)
    
    if (!name || !hub) {
      throw new Error(`Invalid MeshID format: ${meshIdString} (expected name@hub#fingerprint)`)
    }
    
    if (!fingerprint) {
      throw new Error(`Invalid MeshID format: ${meshIdString} (missing fingerprint suffix)`)
    }

    return { name, hub, fingerprint }
  }

  /**
   * Create a MeshID from resolved registry data.
   */
  static fromData(data: MeshIDData): MeshID {
    return new MeshID(data.name, data.hub, data.fingerprint, data.publicKey, data.createdAt)
  }

  /**
   * Get the string representation: "name@hub#fingerprint".
   */
  toString(): string {
    return `${this.name}@${this.hub}#${this.fingerprint.slice(0, 8)}`
  }

  /**
   * Get display name with full fingerprint: "stella@satelliteA#a1b2c3d4 (abc123def456789...)".
   */
  toDisplayString(): string {
    return `${this.toString()} (${this.fingerprint}...)`
  }
  
  /**
   * Get the legacy agent key format (name@hub) for internal use.
   * This is used by capability-index.ts for backward compatibility.
   */
  toAgentKey(): string {
    return `${this.name}@${this.hub}`
  }

  /**
   * Check if this MeshID matches a string.
   */
  matches(meshIdString: string): boolean {
    return this.toString() === meshIdString
  }

  /**
   * Check if this MeshID has the same fingerprint as another.
   */
  sameIdentity(other: MeshID): boolean {
    return this.fingerprint === other.fingerprint
  }

  /**
   * Verify a signature against this MeshID's public key.
   */
  async verify(message: string | Uint8Array, signature: string): Promise<boolean> {
    return MeshPass.verifyWithPublicKey(message, signature, this.publicKey)
  }

  /**
   * Export as data object.
   */
  toData(): MeshIDData {
    return {
      name: this.name,
      hub: this.hub,
      fingerprint: this.fingerprint,
      publicKey: this.publicKey,
      createdAt: this.createdAt
    }
  }
}

/**
 * Registry for resolving MeshID strings to public keys.
 * In a real system, this would be backed by a distributed registry or DHT.
 */
export class MeshIDRegistry {
  private registry = new Map<string, MeshIDData>()

  /**
   * Register a MeshID.
   */
  register(meshId: MeshID): void {
    this.registry.set(meshId.toString(), meshId.toData())
  }

  /**
   * Resolve a MeshID string to a MeshID object.
   */
  resolve(meshIdString: string): MeshID | null {
    const data = this.registry.get(meshIdString)
    return data ? MeshID.fromData(data) : null
  }

  /**
   * Check if a MeshID is registered.
   */
  has(meshIdString: string): boolean {
    return this.registry.has(meshIdString)
  }

  /**
   * Get all registered MeshIDs.
   */
  getAll(): MeshID[] {
    return Array.from(this.registry.values()).map(data => MeshID.fromData(data))
  }

  /**
   * Find MeshIDs by hub.
   */
  getByHub(hub: string): MeshID[] {
    return this.getAll().filter(meshId => meshId.hub === hub)
  }

  /**
   * Find MeshIDs by name pattern.
   */
  findByName(namePattern: RegExp): MeshID[] {
    return this.getAll().filter(meshId => namePattern.test(meshId.name))
  }

  /**
   * Remove a MeshID from the registry.
   */
  unregister(meshIdString: string): boolean {
    return this.registry.delete(meshIdString)
  }

  /**
   * Clear all registrations.
   */
  clear(): void {
    this.registry.clear()
  }

  /**
   * Get registry stats.
   */
  getStats(): { total: number; byHub: Record<string, number> } {
    const byHub: Record<string, number> = {}
    let total = 0

    for (const data of this.registry.values()) {
      total++
      byHub[data.hub] = (byHub[data.hub] || 0) + 1
    }

    return { total, byHub }
  }
}