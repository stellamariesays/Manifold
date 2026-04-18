/**
 * Capability Bloom Filter — space-efficient capability set for federated exchange.
 *
 * Each hub maintains a bloom filter of all capabilities offered by its agents.
 * Filters are exchanged via peer_announce so hubs can quickly determine if a
 * remote hub *might* have a capability before issuing a task_request.
 *
 * False positives are possible (controlled by error rate); false negatives are not.
 */

/**
 * Simple murmur-like hash for bloom filter positions.
 * Uses FNV-1a for speed and decent distribution.
 */
function fnv1a(data: string, seed: number): number {
  let hash = seed ^ 2166136261
  for (let i = 0; i < data.length; i++) {
    hash ^= data.charCodeAt(i)
    hash = (hash * 16777619) >>> 0
  }
  return hash
}

export interface BloomFilterOptions {
  /** Expected number of items. Default 100. */
  expectedItems?: number
  /** Desired false positive rate. Default 0.01 (1%). */
  errorRate?: number
}

export class BloomFilter {
  readonly size: number        // number of bits
  readonly hashCount: number   // number of hash functions
  private bits: Uint8Array     // bit storage (byte-packed)

  constructor(options?: BloomFilterOptions) {
    const n = options?.expectedItems ?? 100
    const p = options?.errorRate ?? 0.01

    // Optimal bit array size: m = -(n * ln(p)) / (ln(2)^2)
    const ln2sq = Math.LN2 * Math.LN2
    this.size = Math.max(8, Math.ceil(-(n * Math.log(p)) / ln2sq))

    // Optimal hash count: k = (m/n) * ln(2)
    this.hashCount = Math.max(1, Math.round((this.size / n) * Math.LN2))

    this.bits = new Uint8Array(Math.ceil(this.size / 8))
  }

  /** Reconstruct from serialized data. */
  static fromSerialized(size: number, hashCount: number, bits: Uint8Array): BloomFilter {
    const bf = Object.create(BloomFilter.prototype) as BloomFilter
    bf.size = size
    bf.hashCount = hashCount
    bf.bits = bits
    return bf
  }

  /** Get positions for an item across all hash functions. */
  private getPositions(item: string): number[] {
    const positions: number[] = []
    // Double hashing: h(i) = h1 + i * h2
    const h1 = fnv1a(item, 0x811c9dc5)
    const h2 = fnv1a(item, 0xc1a1f7a5)
    for (let i = 0; i < this.hashCount; i++) {
      positions.push(((h1 + i * h2) >>> 0) % this.size)
    }
    return positions
  }

  /** Add an item to the filter. */
  add(item: string): void {
    for (const pos of this.getPositions(item)) {
      const byteIdx = pos >> 3
      const bitIdx = pos & 7
      this.bits[byteIdx] |= (1 << bitIdx)
    }
  }

  /** Check if an item *might* be in the set. False positives possible. */
  has(item: string): boolean {
    for (const pos of this.getPositions(item)) {
      const byteIdx = pos >> 3
      const bitIdx = pos & 7
      if ((this.bits[byteIdx] & (1 << bitIdx)) === 0) return false
    }
    return true
  }

  /** Clear all bits. */
  clear(): void {
    this.bits.fill(0)
  }

  /** Serialize to a plain object for wire transfer. */
  serialize(): { size: number; hashCount: number; bits: string } {
    // Base64 encode the bits for JSON compatibility
    let binary = ''
    for (let i = 0; i < this.bits.length; i++) {
      binary += String.fromCharCode(this.bits[i])
    }
    return {
      size: this.size,
      hashCount: this.hashCount,
      bits: btoa(binary),
    }
  }

  /** Deserialize from wire format. */
  static deserialize(data: { size: number; hashCount: number; bits: string }): BloomFilter {
    const binary = atob(data.bits)
    const bits = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bits[i] = binary.charCodeAt(i)
    }
    return BloomFilter.fromSerialized(data.size, data.hashCount, bits)
  }

  /** Number of bits set (useful for union/merge operations). */
  get bitCount(): number {
    let count = 0
    for (const byte of this.bits) {
      count += byte.toString(2).split('1').length - 1
    }
    return count
  }

  /** Estimated fill ratio. */
  get fillRatio(): number {
    return this.bitCount / this.size
  }
}

/**
 * Hub capability bloom — rebuilds from CapabilityIndex.
 */
export class HubCapabilityBloom {
  private filter: BloomFilter
  private cachedCapabilities: Set<string> = new Set()

  constructor(options?: BloomFilterOptions) {
    this.filter = new BloomFilter(options)
  }

  /** Rebuild the bloom filter from a list of capabilities. */
  rebuild(capabilities: string[]): void {
    const newCaps = new Set(capabilities)
    // Only rebuild if capabilities changed
    if (this.setsEqual(this.cachedCapabilities, newCaps)) return

    this.cachedCapabilities = newCaps
    this.filter.clear()
    for (const cap of capabilities) {
      this.filter.add(cap)
    }
  }

  /** Check if a capability might be available on this hub. */
  has(capability: string): boolean {
    return this.filter.has(capability)
  }

  /** Get the serialized filter for wire exchange. */
  serialize(): ReturnType<BloomFilter['serialize']> {
    return this.filter.serialize()
  }

  /** Create from serialized data received from a peer. */
  static fromSerialized(data: { size: number; hashCount: number; bits: string }): HubCapabilityBloom {
    const hub = new HubCapabilityBloom()
    hub.filter = BloomFilter.deserialize(data)
    return hub
  }

  private setsEqual(a: Set<string>, b: Set<string>): boolean {
    if (a.size !== b.size) return false
    for (const item of a) {
      if (!b.has(item)) return false
    }
    return true
  }
}
