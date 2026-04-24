/**
 * Regression tests for Issue #23 — duplicate task ID rejection on cross-hub tasks.
 *
 * Before the fix, `TaskRouter` deduped by bare `taskId` globally.  Two different
 * origin hubs that happen to generate the same numeric/UUID task ID would collide:
 * the second task would be rejected with "Duplicate task ID" even though it came
 * from a completely different hub.
 *
 * After the fix, dedup is scoped to (originHub, taskId) via a composite key so
 * cross-hub tasks with coincident IDs are correctly treated as distinct.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { TaskRouter } from '../src/server/task-router.js'
import type { TaskRequest } from '../src/protocol/messages.js'

function makeTask(id: string, origin: string, target = 'agent@test-hub'): TaskRequest {
  return {
    id,
    target,
    command: 'run',
    args: {},
    origin,
    caller: `${origin}/caller`,
    timeout_ms: 5000,
  }
}

describe('Issue #23 — Cross-hub duplicate task ID dedup', () => {
  let router: TaskRouter
  let mockPeerRegistry: any
  let mockCapIndex: any

  beforeEach(() => {
    mockCapIndex = { stats: () => ({ agents: 0, capabilities: 0, darkCircles: 0 }) }
    mockPeerRegistry = {
      getPeers: () => [],
      sendTo: (_hub: string, _data: string) => false,
      findHubsWithCapability: () => [],
    }
    router = new TaskRouter({ hub: 'test-hub', defaultTimeoutMs: 5000, debug: false })
    router.start(mockCapIndex, mockPeerRegistry)
  })

  afterEach(() => {
    router.stop()
  })

  it('accepts two tasks with the same task ID from different origin hubs', () => {
    const sharedTaskId = 'task-collision-001'
    const taskFromHubA = makeTask(sharedTaskId, 'hub-a')
    const taskFromHubB = makeTask(sharedTaskId, 'hub-b')

    const rejections: string[] = []
    router.on('task:complete', ({ result }) => {
      if (result.status === 'rejected' && result.error === 'Duplicate task ID') {
        rejections.push(result.id)
      }
    })

    // Route task from hub-a (local hub has no runner, so it'll get not_found — that's fine)
    router.routeTask(taskFromHubA, null, 'hub-a')
    // Route task from hub-b with the same bare task ID but different origin
    router.routeTask(taskFromHubB, null, 'hub-b')

    // Neither should be rejected as a duplicate
    expect(rejections).toHaveLength(0)
  })

  it('still rejects a genuine duplicate: same task ID, same origin hub', () => {
    const taskId = 'task-genuine-dup-001'
    const task = makeTask(taskId, 'hub-a')
    const taskDup = makeTask(taskId, 'hub-a')

    const rejections: string[] = []
    router.on('task:complete', ({ result }) => {
      if (result.status === 'rejected' && result.error === 'Duplicate task ID') {
        rejections.push(result.id)
      }
    })

    // Register a fake runner so the first task enters pending state
    const fakeWs = {
      readyState: 1,
      send: (_data: string) => {},
      on: (_event: string, _fn: () => void) => {},
    } as any
    router.registerRunner(fakeWs, ['agent'])

    // Route the original (will be dispatched to runner → enters pending)
    const localTask = makeTask(taskId, 'test-hub', 'agent@test-hub')
    router.routeTask(localTask, null)

    // Route exact duplicate (same origin = test-hub, same id)
    const localTaskDup = makeTask(taskId, 'test-hub', 'agent@test-hub')
    router.routeTask(localTaskDup, null)

    // Second should be rejected as a genuine duplicate
    expect(rejections).toHaveLength(1)
    expect(rejections[0]).toBe(taskId)
  })

  it('getTaskStatus returns pending for a known task by bare ID', () => {
    const fakeWs = {
      readyState: 1,
      send: (_data: string) => {},
      on: (_event: string, _fn: () => void) => {},
    } as any
    router.registerRunner(fakeWs, ['agent'])

    const task = makeTask('status-check-001', 'test-hub', 'agent@test-hub')
    router.routeTask(task, null)

    expect(router.getTaskStatus('status-check-001')).toBe('pending')
  })

  it('pendingKey scoping: hub-a:task-X and hub-b:task-X are independent via local routing', () => {
    const sharedId = 'shared-99'

    // Register a runner so tasks targeting 'agent@test-hub' enter pending state
    const fakeWs = {
      readyState: 1,
      send: (_data: string) => {},
      on: (_event: string, _fn: () => void) => {},
    } as any
    router.registerRunner(fakeWs, ['agent'])

    // Both tasks target the local hub (so they enter pending, not forward queue)
    const taskA1 = makeTask(sharedId, 'hub-a', 'agent@test-hub')
    const taskA2 = makeTask(sharedId, 'hub-a', 'agent@test-hub')
    const taskB1 = makeTask(sharedId, 'hub-b', 'agent@test-hub')

    const dupRejections: string[] = []
    router.on('task:complete', ({ result }) => {
      if (result.status === 'rejected' && result.error === 'Duplicate task ID') {
        dupRejections.push(result.id)
      }
    })

    // Route A1 from hub-a — enters pending
    router.routeTask(taskA1, null, 'hub-a')
    // Route B1 from hub-b with same bare taskId but different origin — should NOT be rejected as dup
    router.routeTask(taskB1, null, 'hub-b')
    // Route A2 from hub-a again — same (origin, id) as A1 → genuine duplicate, must be rejected
    router.routeTask(taskA2, null, 'hub-a')

    // Exactly one rejection: A2 (genuine dup of A1 from same origin)
    expect(dupRejections).toHaveLength(1)
    expect(dupRejections[0]).toBe(sharedId)
  })
})
