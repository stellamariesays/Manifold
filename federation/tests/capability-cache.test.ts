import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { PersistentCapabilityCache, type CacheEntry } from '../src/server/capability-cache.js'
import { promises as fs } from 'fs'
import path from 'path'
import os from 'os'

describe('PersistentCapabilityCache', () => {
  let tmpDir: string
  let cache: PersistentCapabilityCache

  beforeEach(async () => {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'cache-test-'))
    cache = new PersistentCapabilityCache({
      hub: 'test-hub',
      filePath: path.join(tmpDir, 'cache.json'),
      maxAgeMs: 60_000,
    })
  })

  afterEach(async () => {
    await cache.close()
    await fs.rm(tmpDir, { recursive: true })
  })

  function makeAgent(name: string, hub: string, caps: string[]): CacheEntry {
    return {
      agent: { name, hub, capabilities: caps, pressure: 0, seams: [] },
      cachedAt: Date.now(),
      isLocal: hub === 'test-hub',
    }
  }

  it('starts with no cache file', async () => {
    const { agents } = await cache.load()
    expect(agents).toEqual([])
  })

  it('saves and loads entries', async () => {
    const agents = [
      makeAgent('stella', 'test-hub', ['coding', 'research']),
      makeAgent('eddie', 'other-hub', ['execution', 'blockchain']),
    ]
    const darkCircles = [{ name: 'skynet', pressure: 0.5, byHub: { 'test-hub': 0.5 } }]

    await cache.save(agents, darkCircles)

    // Create new cache instance pointing to same file
    const cache2 = new PersistentCapabilityCache({
      hub: 'test-hub',
      filePath: path.join(tmpDir, 'cache.json'),
    })
    const loaded = await cache2.load()

    expect(loaded.agents.length).toBe(2)
    expect(loaded.agents[0].agent.name).toBe('stella')
    expect(loaded.agents[1].agent.name).toBe('eddie')
    expect(loaded.darkCircles).toEqual(darkCircles)
    await cache2.close()
  })

  it('filters out expired entries on load', async () => {
    const now = Date.now()
    const agents = [
      { agent: { name: 'fresh', hub: 'h', capabilities: ['a'], pressure: 0, seams: [] }, cachedAt: now, isLocal: true },
      { agent: { name: 'stale', hub: 'h', capabilities: ['b'], pressure: 0, seams: [] }, cachedAt: now - 120_000, isLocal: false },
    ]

    await cache.save(agents, [])
    const loaded = await cache.load()

    expect(loaded.agents.length).toBe(1)
    expect(loaded.agents[0].agent.name).toBe('fresh')
  })

  it('reports stats', async () => {
    const stats1 = await cache.getStats()
    expect(stats1.exists).toBe(false)

    await cache.save([makeAgent('a', 'h', ['x'])], [])
    const stats2 = await cache.getStats()

    expect(stats2.exists).toBe(true)
    expect(stats2.agentCount).toBe(1)
    expect(stats2.sizeBytes).toBeGreaterThan(0)
    expect(stats2.savedAt).toBeGreaterThan(0)
  })

  it('exists() checks file presence', async () => {
    expect(await cache.exists()).toBe(false)
    await cache.save([], [])
    expect(await cache.exists()).toBe(true)
  })

  it('atomic write — no partial files on crash', async () => {
    await cache.save([makeAgent('test', 'h', ['c'])], [])
    // No .tmp file should remain
    const files = await fs.readdir(tmpDir)
    expect(files).toEqual(['cache.json'])
  })

  it('handles corrupt file gracefully', async () => {
    await fs.writeFile(path.join(tmpDir, 'cache.json'), 'not valid json{{{')
    const { agents } = await cache.load()
    expect(agents).toEqual([])
  })

  it('handles wrong version gracefully', async () => {
    await fs.writeFile(path.join(tmpDir, 'cache.json'), JSON.stringify({ version: 99 }))
    const { agents } = await cache.load()
    expect(agents).toEqual([])
  })
})
