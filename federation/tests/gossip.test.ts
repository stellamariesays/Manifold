import { describe, it, expect, beforeEach } from 'vitest'
import { PeerSampler } from '../src/server/peer-sampler.js'
import type { PeerDescriptor, ShuffleRequest, ShuffleResponse } from '../src/server/peer-sampler.js'

// ── PeerSampler ──────────────────────────────────────────────────────────────

describe('PeerSampler', () => {
  it('starts with empty view', () => {
    const sampler = new PeerSampler({ selfHub: 'a', selfAddress: 'ws://a:8766' })
    expect(sampler.viewCount).toBe(0)
    expect(sampler.knownCount).toBe(0)
  })

  it('adds seeds to view', () => {
    const sampler = new PeerSampler({
      selfHub: 'a',
      selfAddress: 'ws://a:8766',
      seeds: ['ws://b:8766', 'ws://c:8766'],
    })
    expect(sampler.viewCount).toBe(2)
  })

  it('does not add itself', () => {
    const sampler = new PeerSampler({
      selfHub: 'a',
      selfAddress: 'ws://a:8766',
      seeds: ['ws://a:8766'],
    })
    expect(sampler.viewCount).toBe(0)
  })

  it('respects viewSize limit', () => {
    const sampler = new PeerSampler({
      selfHub: 'a',
      selfAddress: 'ws://a:8766',
      viewSize: 3,
    })
    for (let i = 0; i < 10; i++) {
      sampler.addDescriptor({ hub: `peer-${i}`, address: `ws://peer-${i}:8766`, age: 0 })
    }
    expect(sampler.viewCount).toBeLessThanOrEqual(3)
  })

  it('prefers younger descriptors when view is full', () => {
    const sampler = new PeerSampler({
      selfHub: 'a',
      selfAddress: 'ws://a:8766',
      viewSize: 2,
    })
    // Fill with old
    sampler.addDescriptor({ hub: 'old-1', address: 'ws://old-1:8766', age: 10 })
    sampler.addDescriptor({ hub: 'old-2', address: 'ws://old-2:8766', age: 20 })

    // Add a young one — should replace oldest
    const changed = sampler.addDescriptor({ hub: 'young', address: 'ws://young:8766', age: 0 })

    expect(changed).toBe(true)
    const hubs = sampler.getView().map(d => d.hub)
    expect(hubs).toContain('young')
    expect(hubs).not.toContain('old-2') // oldest evicted
  })

  it('handles shuffle request', () => {
    const samplerA = new PeerSampler({ selfHub: 'a', selfAddress: 'ws://a:8766', viewSize: 10 })
    samplerA.addDescriptor({ hub: 'b', address: 'ws://b:8766', age: 1 })
    samplerA.addDescriptor({ hub: 'c', address: 'ws://c:8766', age: 2 })

    // B needs some entries to respond with
    const samplerB = new PeerSampler({ selfHub: 'b', selfAddress: 'ws://b:8766', viewSize: 10 })
    samplerB.addDescriptor({ hub: 'f', address: 'ws://f:8766', age: 0 })
    samplerB.addDescriptor({ hub: 'g', address: 'ws://g:8766', age: 1 })

    const request: ShuffleRequest = {
      type: 'shuffle_request',
      sender: 'b',
      samples: [
        { hub: 'd', address: 'ws://d:8766', age: 0 },
        { hub: 'e', address: 'ws://e:8766', age: 1 },
      ],
      requestId: 'test-1',
    }

    const response = samplerB.handleShuffleRequest(request)
    expect(response.type).toBe('shuffle_response')
    expect(response.samples.length).toBeGreaterThan(0)
    expect(response.requestId).toBe('test-1')

    // B should have learned about d and e
    expect(samplerB.knownCount).toBeGreaterThanOrEqual(2)
  })

  it('handles shuffle response', () => {
    const sampler = new PeerSampler({ selfHub: 'a', selfAddress: 'ws://a:8766', viewSize: 10 })

    sampler.handleShuffleResponse({
      type: 'shuffle_response',
      samples: [
        { hub: 'x', address: 'ws://x:8766', age: 0 },
        { hub: 'y', address: 'ws://y:8766', age: 1 },
      ],
      requestId: 'test-1',
    })

    expect(sampler.knownCount).toBeGreaterThanOrEqual(2)
  })

  it('emit shuffle:send on cycle', () => {
    const sampler = new PeerSampler({
      selfHub: 'a',
      selfAddress: 'ws://a:8766',
      shuffleIntervalMs: 100,
    })
    sampler.addDescriptor({ hub: 'b', address: 'ws://b:8766', age: 1 })

    let fired = false
    sampler.on('shuffle:send', () => { fired = true })
    sampler.start()

    return new Promise<void>((resolve) => {
      setTimeout(() => {
        sampler.stop()
        expect(fired).toBe(true)
        resolve()
      }, 200)
    })
  })

  it('removePeer removes from view', () => {
    const sampler = new PeerSampler({ selfHub: 'a', selfAddress: 'ws://a:8766' })
    sampler.addDescriptor({ hub: 'b', address: 'ws://b:8766', age: 0 })
    expect(sampler.viewCount).toBe(1)

    sampler.removePeer('b')
    expect(sampler.viewCount).toBe(0)
  })
})

// ── PeerRegistry Hub Index ───────────────────────────────────────────────────

describe('PeerRegistry O(1) hub index', () => {
  // Note: full PeerRegistry tests are in server.test.ts
  // These test the specific hub-index behavior

  it('PeerSampler getViewAddresses returns addresses', () => {
    const sampler = new PeerSampler({
      selfHub: 'a',
      selfAddress: 'ws://a:8766',
      seeds: ['ws://b:8766', 'ws://c:8766'],
    })
    const addrs = sampler.getViewAddresses()
    expect(addrs).toEqual(expect.arrayContaining(['ws://b:8766', 'ws://c:8766']))
  })

  it('duplicate addDescriptor does not grow view', () => {
    const sampler = new PeerSampler({ selfHub: 'a', selfAddress: 'ws://a:8766', viewSize: 10 })
    sampler.addDescriptor({ hub: 'b', address: 'ws://b:8766', age: 0 })
    sampler.addDescriptor({ hub: 'b', address: 'ws://b:8766', age: 0 })
    expect(sampler.viewCount).toBe(1)
  })
})
