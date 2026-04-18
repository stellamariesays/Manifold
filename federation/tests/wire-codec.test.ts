import { describe, it, expect } from 'vitest'
import { encode, decode, detectFormat, estimateSavings, type WireFormat } from '../src/protocol/wire-codec.js'

describe('Wire Codec', () => {
  const sampleMsg = {
    type: 'mesh_sync',
    hub: 'trillian',
    agents: [
      { name: 'stella', hub: 'trillian', capabilities: ['coding', 'research', 'math'], pressure: 0.8, seams: [] },
      { name: 'eddie', hub: 'trillian', capabilities: ['execution', 'blockchain'], pressure: 0.3, seams: ['crypto'] },
    ],
    darkCircles: [
      { name: 'skynet', pressure: 0.5 },
    ],
    timestamp: new Date().toISOString(),
  }

  it('encodes and decodes JSON correctly', () => {
    const encoded = encode(sampleMsg, 'json')
    expect(typeof encoded).toBe('string')
    const decoded = decode(encoded as string)
    expect(decoded).toEqual(sampleMsg)
  })

  it('encodes and decodes MessagePack correctly', () => {
    const encoded = encode(sampleMsg, 'msgpack')
    expect(Buffer.isBuffer(encoded)).toBe(true)
    const decoded = decode(encoded as Buffer)
    expect(decoded).toEqual(sampleMsg)
  })

  it('detects JSON format', () => {
    expect(detectFormat('{"type":"test"}')).toBe('json')
    expect(detectFormat(Buffer.from('{"type":"test"}'))).toBe('json')
  })

  it('detects MessagePack format', () => {
    const encoded = encode(sampleMsg, 'msgpack')
    expect(detectFormat(encoded as Buffer)).toBe('msgpack')
  })

  it('MessagePack is smaller than JSON', () => {
    const savings = estimateSavings(sampleMsg)
    expect(savings.msgpackSize).toBeLessThan(savings.jsonSize)
    expect(savings.savings).toBeGreaterThan(0)
  })

  it('handles round-trip with all protocol message types', () => {
    const messages = [
      { type: 'peer_announce', hub: 'test', address: 'ws://localhost:8766', timestamp: new Date().toISOString() },
      { type: 'mesh_sync', hub: 'test', agents: [], darkCircles: [], timestamp: new Date().toISOString() },
      { type: 'task_request', task: { id: 't1', target: 'agent@hub', command: 'run', args: {} } },
      { type: 'task_result', result: { id: 't1', status: 'success', output: 'done', completed_at: new Date().toISOString() } },
      { type: 'capability_query', query: 'coding', requestId: 'r1' },
    ]

    for (const format of ['json', 'msgpack'] as WireFormat[]) {
      for (const msg of messages) {
        const encoded = encode(msg, format)
        const decoded = decode(encoded as any)
        expect(decoded).toEqual(msg)
      }
    }
  })

  it('handles empty objects and arrays', () => {
    for (const format of ['json', 'msgpack'] as WireFormat[]) {
      expect(decode(encode({}, format) as any)).toEqual({})
      expect(decode(encode([], format) as any)).toEqual([])
      expect(decode(encode({ a: [] }, format) as any)).toEqual({ a: [] })
    }
  })

  it('estimates savings correctly', () => {
    const small = { a: 1 }
    const savings = estimateSavings(small)
    expect(savings.jsonSize).toBeGreaterThan(0)
    expect(savings.msgpackSize).toBeGreaterThan(0)
    // Small objects may not save much or could even be larger with msgpack overhead
    expect(savings.savings).toBeGreaterThanOrEqual(-1)
    expect(savings.savings).toBeLessThanOrEqual(1)
  })
})
