/**
 * MeshID: Human-readable identity derived from a MeshPass.
 * 
 * Format: `name@hub` (e.g., `stella@satelliteA`, `eddie@thefog`)
 * Under the hood it resolves to a public key fingerprint, but users see the friendly name.
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
   * Parse a MeshID string (format: "name@hub") and resolve it to public key.
   * Note: This only gives you the string components - you need a registry to resolve to keys.
   */
  static parse(meshIdString: string): { name: string; hub: string } {
    if (!meshIdString.includes('@')) {
      throw new Error(`Invalid MeshID format: ${meshIdString} (expected name@hub)`)
    }

    const [name, hub] = meshIdString.split('@', 2)
    if (!name || !hub) {
      throw new Error(`Invalid MeshID format: ${meshIdString} (expected name@hub)`)
    }

    return { name, hub }
  }

  /**
   * Create a MeshID from resolved registry data.
   */
  static fromData(data: MeshIDData): MeshID {
    return new MeshID(data.name, data.hub, data.fingerprint, data.publicKey, data.createdAt)
  }

  /**
   * Get the string representation: "name@hub".
   */
  toString(): string {
    return `${this.name}@${this.hub}`
  }

  /**
   * Get display name with fingerprint: "stella@satelliteA (abc123...)".
   */
  toDisplayString(): string {
    return `${this.toString()} (${this.fingerprint}...)`
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