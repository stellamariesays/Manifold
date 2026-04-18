import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { TaskRouter, BackpressureConfig } from '../src/server/task-router.js'
import type { TaskRequest } from '../src/protocol/messages.js'

function makeTask(target: string, command: string, id?: string): TaskRequest {
  return {
    id: id ?? `task-${Math.random().toString(36).slice(2, 10)}`,
    target,
    command,
    args: {},
    timeout_ms: 5000,
    origin: 'test-hub',
    caller: 'test-hub',
  }
}

function mockWs() {
  const sent: string[] = []
  return { readyState: 1, send: (data: string) => sent.push(data), sent, on: () => {} } as any
}

function createRouter(bp: BackpressureConfig) {
  const router = new TaskRouter({ hub: 'test-hub', defaultTimeoutMs: 5000, backpressure: bp, debug: false })
  router.start({} as any, { sendTo: () => true, getPeers: () => [] } as any)
  return router
}

describe('TaskRouter Backpressure', () => {
  let router: TaskRouter

  beforeEach(() => {
    // maxPerRunner=2: max 2 dispatched per runner
    // maxPendingTotal=5: max 5 in-flight (dispatched + queued)
    // maxPendingPerSource=3: max 3 per source (dispatched + queued)
    // maxQueueSize=10
    router = createRouter({ maxPendingTotal: 5, maxPendingPerSource: 3, maxQueueSize: 10, maxPerRunner: 2 })
  })

  afterEach(() => { router.stop() })

  function registerRunner(agents: string[]) {
    const ws = mockWs()
    router.registerRunner(ws, agents)
    return ws
  }

  it('dispatches up to maxPerRunner, queues the rest', () => {
    registerRunner(['agent-a'])

    // 2 dispatched, 1 queued
    router.routeTask(makeTask('agent-a', 'cmd-1'), null, 'src-1')
    router.routeTask(makeTask('agent-a', 'cmd-2'), null, 'src-2')
    router.routeTask(makeTask('agent-a', 'cmd-3'), null, 'src-3')

    expect(router.getBackpressureStats().pendingTotal).toBe(2)
    expect(router.getBackpressureStats().queueSize).toBe(1)
  })

  it('rejects when total in-flight limit reached', () => {
    registerRunner(['agent-a'])

    // 2 dispatched + 3 queued = 5 = maxPendingTotal
    for (let i = 0; i < 5; i++) {
      router.routeTask(makeTask('agent-a', `cmd-${i}`), null, `src-${i}`)
    }
    expect(router.getBackpressureStats().pendingTotal).toBe(2)
    expect(router.getBackpressureStats().queueSize).toBe(3)

    // 6th rejected
    let backpressureReason = ''
    router.on('task:backpressure', ({ reason }: any) => { backpressureReason = reason })
    router.routeTask(makeTask('agent-a', 'overflow'), null)
    expect(backpressureReason).toBe('pending_total')
  })

  it('rejects when per-source limit reached', () => {
    registerRunner(['agent-a'])

    // 2 dispatched from hub-A (maxPerRunner), 3rd queued — per-source count = 3 for hub-A
    router.routeTask(makeTask('agent-a', 'cmd-1'), null, 'hub-A')
    router.routeTask(makeTask('agent-a', 'cmd-2'), null, 'hub-A')
    router.routeTask(makeTask('agent-a', 'cmd-3'), null, 'hub-A')

    // 4th from hub-A rejected (per-source = 3)
    let rejected = false
    router.on('task:backpressure', ({ reason }: any) => { if (reason === 'per_source') rejected = true })
    router.routeTask(makeTask('agent-a', 'overflow'), null, 'hub-A')
    expect(rejected).toBe(true)

    // But from hub-B works (queued since runner full)
    router.routeTask(makeTask('agent-a', 'cmd-other'), null, 'hub-B')
    expect(router.getBackpressureStats().queueSize).toBe(2) // hub-A queued + hub-B queued
  })

  it('drains queue on task completion', () => {
    registerRunner(['agent-a'])

    const task1 = makeTask('agent-a', 'cmd-1')
    const task2 = makeTask('agent-a', 'cmd-2')
    const task3 = makeTask('agent-a', 'cmd-3')
    router.routeTask(task1, null)
    router.routeTask(task2, null)
    router.routeTask(task3, null) // queued

    expect(router.getBackpressureStats().pendingTotal).toBe(2)
    expect(router.getBackpressureStats().queueSize).toBe(1)

    // Complete task1 — task3 drains from queue
    router.handleResult({ id: task1.id, status: 'success', output: 'done', completed_at: new Date().toISOString() })

    expect(router.getBackpressureStats().queueSize).toBe(0)
    expect(router.getBackpressureStats().pendingTotal).toBe(2) // task2 + task3
  })

  it('rejects when queue is full', () => {
    const bigRouter = createRouter({ maxPendingTotal: 20, maxPendingPerSource: 20, maxQueueSize: 5, maxPerRunner: 2 })
    const ws = mockWs()
    bigRouter.registerRunner(ws, ['agent-a'])

    for (let i = 0; i < 7; i++) {
      bigRouter.routeTask(makeTask('agent-a', `fill-${i}`), null, `src-${i}`)
    }
    expect(bigRouter.getBackpressureStats().queueSize).toBe(5)

    let rejected = false
    bigRouter.on('task:complete', ({ result }: any) => {
      if (result.status === 'rejected' && result.error?.includes('queue full')) rejected = true
    })
    bigRouter.routeTask(makeTask('agent-a', 'overflow'), null)
    expect(rejected).toBe(true)
    bigRouter.stop()
  })

  it('decrements counters on completion', () => {
    registerRunner(['agent-a'])

    const task1 = makeTask('agent-a', 'cmd-1')
    router.routeTask(task1, null, 'source-A')
    expect(router.getBackpressureStats().pendingTotal).toBe(1)
    expect(router.getBackpressureStats().perSource['source-A']).toBe(1)

    router.handleResult({ id: task1.id, status: 'success', output: 'done', completed_at: new Date().toISOString() })

    expect(router.getBackpressureStats().pendingTotal).toBe(0)
    expect(router.getBackpressureStats().perSource['source-A']).toBe(0)
  })

  it('decrements counters on timeout', async () => {
    const timeoutRouter = new TaskRouter({
      hub: 'test-hub', defaultTimeoutMs: 50,
      backpressure: { maxPendingTotal: 5, maxPendingPerSource: 5, maxQueueSize: 10, maxPerRunner: 5 },
      debug: false,
    })
    timeoutRouter.start({} as any, { sendTo: () => true, getPeers: () => [] } as any)
    timeoutRouter.registerRunner(mockWs(), ['agent-a'])

    const task = makeTask('agent-a', 'cmd-timeout')
    task.timeout_ms = 50
    timeoutRouter.routeTask(task, null, 'source-A')
    expect(timeoutRouter.getBackpressureStats().pendingTotal).toBe(1)

    await new Promise(r => setTimeout(r, 100))

    expect(timeoutRouter.getBackpressureStats().pendingTotal).toBe(0)
    expect(timeoutRouter.getBackpressureStats().perSource['source-A']).toBe(0)
    timeoutRouter.stop()
  })
})
