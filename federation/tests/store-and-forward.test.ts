import { describe, it, expect, beforeEach, vi } from 'vitest'
import { TaskRouter } from '../src/server/task-router.js'
import type { TaskRequest } from '../src/protocol/messages.js'

function makeTask(target: string, id?: string): TaskRequest {
  return {
    id: id ?? crypto.randomUUID(),
    target,
    command: 'run',
    args: {},
    origin: 'test-hub',
    caller: 'test-caller',
    timeout_ms: 5000,
  }
}

describe('Store-and-Forward Task Routing', () => {
  let router: TaskRouter
  let mockCapIndex: any
  let mockPeerRegistry: any
  let sentMessages: Array<{ hub: string; data: string }> = []

  beforeEach(() => {
    sentMessages = []
    mockCapIndex = { stats: () => ({ agents: 0, capabilities: 0, darkCircles: 0 }) }
    mockPeerRegistry = {
      getPeers: () => [],
      sendTo: (hub: string, data: string) => {
        sentMessages.push({ hub, data })
        return false // simulate unreachable
      },
      findHubsWithCapability: vi.fn(),
    }

    router = new TaskRouter({ hub: 'test-hub', defaultTimeoutMs: 5000, debug: false })
    router.start(mockCapIndex, mockPeerRegistry)
  })

  it('queues task when target hub is unreachable and no peers', () => {
    const task = makeTask('agent@remote-hub')
    router.routeTask(task, null)

    expect(router.getForwardQueueStats().size).toBe(1)
  })

  it('delivers queued task when drain finds reachable peer', () => {
    const task = makeTask('agent@remote-hub')
    router.routeTask(task, null)
    expect(router.getForwardQueueStats().size).toBe(1)

    // Clear and make the peer reachable
    sentMessages = []
    mockPeerRegistry.sendTo = (hub: string, data: string) => {
      sentMessages.push({ hub, data })
      return true
    }

    router.drainForwardQueue()
    expect(router.getForwardQueueStats().size).toBe(0)
    expect(sentMessages.some(m => m.hub === 'remote-hub')).toBe(true)
  })

  it('rejects task when forward queue is full', () => {
    // Fill the queue
    for (let i = 0; i < 250; i++) {
      router.routeTask(makeTask(`agent@hub-${i}`, `task-${i}`), null)
    }

    const results: any[] = []
    router.on('task:complete', ({ result }) => results.push(result))

    // This one should be rejected
    router.routeTask(makeTask('agent@full-hub'), null)
    expect(results.length).toBe(1)
    expect(results[0].status).toBe('rejected')
    expect(results[0].error).toContain('forward queue full')
  })

  it('expires tasks in forward queue past their timeout', () => {
    const task = makeTask('agent@slow-hub')
    task.timeout_ms = 1 // 1ms timeout — will expire immediately

    const results: any[] = []
    router.on('task:complete', ({ result }) => results.push(result))

    router.routeTask(task, null)
    // Wait a tick for the timeout
    return new Promise<void>(resolve => {
      setTimeout(() => {
        router.drainForwardQueue()
        expect(results.some(r => r.status === 'timeout')).toBe(true)
        router.stop()
        resolve()
      }, 50)
    })
  })

  it('handleForward routes locally if target matches hub', () => {
    const task = makeTask('agent@test-hub')
    // When forwarded to our hub, it should be routed locally
    // We can verify by checking the pending map
    router.handleForward({
      task,
      hopCount: 2,
      maxHops: 6,
      originHub: 'other-hub',
    })

    // Task should be in pending (routed locally or rejected as no runner)
    // At minimum it shouldn't throw
    expect(router.getForwardQueueStats().size).toBe(0)
  })

  it('handleForward re-forwards with incremented hopCount', () => {
    const task = makeTask('agent@far-hub')
    task.origin = 'origin-hub'

    // Provide peers to forward to
    mockPeerRegistry.getPeers = () => [
      { hub: 'peer-a' },
      { hub: 'peer-b' },
      { hub: 'origin-hub' }, // should be skipped
    ]
    // Direct send to far-hub fails, but send to peers succeeds
    mockPeerRegistry.sendTo = (hub: string, data: string) => {
      sentMessages.push({ hub, data })
      if (hub === 'far-hub') return false // target not directly reachable
      return true
    }

    router.handleForward({
      task,
      hopCount: 2,
      maxHops: 6,
      originHub: 'origin-hub',
    })

    // Should have forwarded to peer-a and peer-b, not origin-hub
    const forwardMsgs = sentMessages.filter(m => {
      try { return JSON.parse(m.data).type === 'task_forward' } catch { return false }
    })
    const forwardedHubs = forwardMsgs.map(m => m.hub)
    expect(forwardedHubs).toContain('peer-a')
    expect(forwardedHubs).toContain('peer-b')
    expect(forwardedHubs).not.toContain('origin-hub')

    // Check hopCount incremented
    const fwd = JSON.parse(forwardMsgs[0].data)
    expect(fwd.hopCount).toBe(3)
  })

  it('handleForward drops at max hops', () => {
    const task = makeTask('agent@far-hub')
    const sendSpy = vi.fn().mockReturnValue(true)
    mockPeerRegistry.sendTo = sendSpy
    mockPeerRegistry.getPeers = () => [{ hub: 'peer-a' }]

    router.handleForward({
      task,
      hopCount: 6,
      maxHops: 6,
      originHub: 'origin-hub',
    })

    expect(sendSpy).not.toHaveBeenCalled()
  })

  it('reports forward queue stats', () => {
    const stats = router.getForwardQueueStats()
    expect(stats.size).toBe(0)
    expect(stats.maxSize).toBe(200)
    expect(stats.oldestAgeMs).toBe(0)
  })
})
