import { describe, it, expect } from 'vitest'
import { validateMessage, parseMessage, isValidMessage } from '../src/protocol/validation.js'

describe('Protocol validation', () => {
  it('validates peer_announce', () => {
    const msg = {
      type: 'peer_announce',
      hub: 'trillian',
      address: 'ws://100.64.230.118:8766',
      timestamp: new Date().toISOString(),
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('rejects peer_announce with invalid URL', () => {
    const msg = {
      type: 'peer_announce',
      hub: 'trillian',
      address: 'not-a-url',
      timestamp: new Date().toISOString(),
    }
    expect(() => validateMessage(msg)).toThrow()
  })

  it('validates capability_query', () => {
    const msg = {
      type: 'capability_query',
      capability: 'solar-prediction',
      requestId: 'uuid-123',
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates capability_query with optional fields', () => {
    const msg = {
      type: 'capability_query',
      capability: 'solar-prediction',
      minPressure: 0.5,
      requestId: 'uuid-123',
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('rejects capability_query with minPressure > 1', () => {
    const msg = {
      type: 'capability_query',
      capability: 'foo',
      minPressure: 1.5,
      requestId: 'uuid-123',
    }
    expect(() => validateMessage(msg)).toThrow()
  })

  it('validates capability_response', () => {
    const msg = {
      type: 'capability_response',
      requestId: 'uuid-123',
      agents: [
        {
          name: 'braid',
          hub: 'trillian',
          capabilities: ['solar-prediction'],
          pressure: 0.6,
        },
      ],
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates agent_request', () => {
    const msg = {
      type: 'agent_request',
      target: 'deploy@trillian',
      task: { type: 'deployment', payload: {} },
      timeout: 300,
      requestId: 'uuid-456',
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates mesh_sync', () => {
    const msg = {
      type: 'mesh_sync',
      hub: 'trillian',
      agents: [
        {
          name: 'stella',
          hub: 'trillian',
          capabilities: ['deployment-versioning'],
        },
      ],
      darkCircles: [{ name: 'deployment-strategy', pressure: 0.7 }],
      timestamp: new Date().toISOString(),
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates ping', () => {
    const msg = { type: 'ping', timestamp: new Date().toISOString() }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates pong', () => {
    const msg = { type: 'pong', timestamp: new Date().toISOString() }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates error', () => {
    const msg = { type: 'error', code: 'NOT_FOUND', message: 'Agent not found' }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('rejects unknown message type', () => {
    const msg = { type: 'unknown_type' }
    expect(() => validateMessage(msg)).toThrow()
  })

  it('parseMessage returns null for invalid JSON', () => {
    expect(parseMessage('not json')).toBeNull()
  })

  it('parseMessage returns null for invalid message', () => {
    expect(parseMessage('{"type":"invalid"}')).toBeNull()
  })

  it('parseMessage returns parsed message for valid JSON', () => {
    const msg = { type: 'ping', timestamp: new Date().toISOString() }
    const result = parseMessage(JSON.stringify(msg))
    expect(result).not.toBeNull()
    expect(result!.type).toBe('ping')
  })

  it('isValidMessage returns true for valid message', () => {
    const msg = { type: 'ping', timestamp: new Date().toISOString() }
    expect(isValidMessage(msg)).toBe(true)
  })

  it('isValidMessage returns false for invalid message', () => {
    expect(isValidMessage({ type: 'garbage' })).toBe(false)
    expect(isValidMessage(null)).toBe(false)
    expect(isValidMessage('string')).toBe(false)
  })

  it('validates peer_bye', () => {
    const msg = {
      type: 'peer_bye',
      hub: 'trillian',
      timestamp: new Date().toISOString(),
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates agent_response success', () => {
    const msg = {
      type: 'agent_response',
      requestId: 'uuid-789',
      success: true,
      result: { status: 'acknowledged' },
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })

  it('validates agent_response failure', () => {
    const msg = {
      type: 'agent_response',
      requestId: 'uuid-789',
      success: false,
      error: 'Agent not found',
    }
    expect(() => validateMessage(msg)).not.toThrow()
  })
})
