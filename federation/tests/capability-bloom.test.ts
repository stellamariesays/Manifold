import { describe, it, expect } from 'vitest'
import { BloomFilter, HubCapabilityBloom } from '../src/server/capability-bloom.js'

describe('BloomFilter', () => {
  it('adds and checks items', () => {
    const bf = new BloomFilter({ expectedItems: 10, errorRate: 0.01 })
    bf.add('coding')
    bf.add('research')
    bf.add('math')

    expect(bf.has('coding')).toBe(true)
    expect(bf.has('research')).toBe(true)
    expect(bf.has('math')).toBe(true)
  })

  it('returns false for items not in set', () => {
    const bf = new BloomFilter({ expectedItems: 100, errorRate: 0.001 })
    bf.add('coding')

    // Test many items not in the set — false positive rate should be ~0.1%
    let falsePositives = 0
    for (let i = 0; i < 1000; i++) {
      if (bf.has(`not-in-set-${i}`)) falsePositives++
    }
    expect(falsePositives).toBeLessThan(10) // <1% false positive rate
  })

  it('serializes and deserializes correctly', () => {
    const bf = new BloomFilter({ expectedItems: 50, errorRate: 0.01 })
    bf.add('capability-a')
    bf.add('capability-b')

    const serialized = bf.serialize()
    const restored = BloomFilter.deserialize(serialized)

    expect(restored.has('capability-a')).toBe(true)
    expect(restored.has('capability-b')).toBe(true)
    expect(restored.has('not-present')).toBe(false)
  })

  it('clear resets all bits', () => {
    const bf = new BloomFilter()
    bf.add('test')
    expect(bf.has('test')).toBe(true)
    bf.clear()
    expect(bf.has('test')).toBe(false)
  })

  it('reports fill ratio', () => {
    const bf = new BloomFilter({ expectedItems: 10 })
    expect(bf.fillRatio).toBe(0)
    bf.add('x')
    expect(bf.fillRatio).toBeGreaterThan(0)
  })
})

describe('HubCapabilityBloom', () => {
  it('rebuilds from capability list', () => {
    const hub = new HubCapabilityBloom({ expectedItems: 50 })
    hub.rebuild(['coding', 'research', 'math'])

    expect(hub.has('coding')).toBe(true)
    expect(hub.has('research')).toBe(true)
    expect(hub.has('unknown')).toBe(false)
  })

  it('skips rebuild when capabilities unchanged', () => {
    const hub = new HubCapabilityBloom()
    hub.rebuild(['a', 'b'])
    const serialized1 = hub.serialize()

    hub.rebuild(['b', 'a']) // same set, different order
    const serialized2 = hub.serialize()

    expect(serialized1).toEqual(serialized2)
  })

  it('rebuilds when capabilities change', () => {
    const hub = new HubCapabilityBloom()
    hub.rebuild(['a', 'b'])
    expect(hub.has('a')).toBe(true)
    expect(hub.has('c')).toBe(false)

    hub.rebuild(['a', 'c'])
    expect(hub.has('c')).toBe(true)
  })

  it('round-trips through serialization', () => {
    const hub = new HubCapabilityBloom({ expectedItems: 20, errorRate: 0.01 })
    hub.rebuild(['coding', 'research', 'math', 'creative-writing'])

    const data = hub.serialize()
    const restored = HubCapabilityBloom.fromSerialized(data)

    expect(restored.has('coding')).toBe(true)
    expect(restored.has('research')).toBe(true)
    expect(restored.has('math')).toBe(true)
    expect(restored.has('creative-writing')).toBe(true)
  })

  it('handles empty capability list', () => {
    const hub = new HubCapabilityBloom()
    hub.rebuild([])
    expect(hub.has('anything')).toBe(false)
  })
})
