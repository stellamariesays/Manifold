/**
 * tasks.ts — Task submit/status/pending/history routes.
 */
import { type Request, type Response, type Router } from 'express'
import type { CapabilityIndex } from '../capability-index.js'
import type { TaskRouter } from '../task-router.js'
import type { TaskHistory } from '../task-history.js'
import type { TaskRequest, TaskResult } from '../../protocol/messages.js'

export interface TaskRouterDeps {
  hub: string
  capIndex: CapabilityIndex
  taskRouter: TaskRouter
  taskHistory: TaskHistory
}

export function buildTaskRouter(router: Router, deps: TaskRouterDeps): void {
  router.post('/task', (req, res) => _submitTask(req, res, deps))
  router.get('/task/:id', (req, res) => _taskStatus(req, res, deps))
  router.get('/tasks', (req, res) => _pendingTasks(req, res, deps))
  router.get('/task-history', (req, res) => _taskHistory(req, res, deps))
  // Legacy query/route endpoints (kept for backward compatibility)
  router.post('/query', (req, res) => _query(req, res, deps))
  router.post('/route', (req, res) => _route(req, res, deps))
}

function _submitTask(req: Request, res: Response, { hub, capIndex, taskRouter }: TaskRouterDeps): void {
  const { target, command, args, timeout_ms, capability, teacup } = req.body as {
    target?: string
    command?: string
    args?: Record<string, unknown>
    timeout_ms?: number
    capability?: string
    teacup?: { trigger: string; ground_state?: string; observation?: string }
  }

  if (!command) {
    res.status(400).json({ error: 'command is required' })
    return
  }

  const resolvedTarget = target ?? 'any'
  const task: TaskRequest = {
    id: crypto.randomUUID(),
    target: resolvedTarget,
    capability,
    command,
    args,
    timeout_ms: timeout_ms ?? 30_000,
    origin: hub,
    caller: hub,
    created_at: new Date().toISOString(),
    teacup,
  }

  if (resolvedTarget === 'any' && capability) {
    const agents = capIndex.findByCapability(capability)
    if (agents.length === 0) {
      res.status(404).json({ error: `No agent found with capability: ${capability}` })
      return
    }
    const local = agents.find(a => a.isLocal)
    const chosen = local ?? agents[0]
    task.target = `${chosen.name}@${chosen.hub}`
  } else if (resolvedTarget === 'any') {
    res.status(400).json({ error: 'capability is required when target is "any"' })
    return
  }

  const onResult = (result: { result: TaskResult; task: TaskRequest }) => {
    if (result.task.id === task.id) {
      clearTimeout(timeoutHandle)
      taskRouter.removeListener('task:complete', onResult)
      res.json({
        task_id: result.result.id,
        status: result.result.status,
        output: result.result.output,
        error: result.result.error,
        executed_by: result.result.executed_by,
        execution_ms: result.result.execution_ms,
        completed_at: result.result.completed_at,
      })
    }
  }

  const timeoutHandle = setTimeout(() => {
    taskRouter.removeListener('task:complete', onResult)
    res.json({
      task_id: task.id,
      status: 'timeout',
      error: 'Task timed out waiting for result',
      target: task.target,
    })
  }, task.timeout_ms! + 2000)

  taskRouter.on('task:complete', onResult)
  taskRouter.routeTask(task, null)
}

function _taskStatus(req: Request, res: Response, { taskRouter }: TaskRouterDeps): void {
  const id = String(req.params['id'] ?? '')
  const status = taskRouter.getTaskStatus(id)
  res.json({ task_id: id, status })
}

function _pendingTasks(_req: Request, res: Response, { taskRouter }: TaskRouterDeps): void {
  res.json({
    pending: taskRouter.getPendingTasks(),
    runner_count: taskRouter.runnerCount,
  })
}

async function _taskHistory(req: Request, res: Response, { taskHistory }: TaskRouterDeps): Promise<void> {
  const limit = parseInt(String(req.query['limit'] ?? '50'), 10)
  const offset = parseInt(String(req.query['offset'] ?? '0'), 10)
  const entries = await taskHistory.getRecent(limit, offset)
  res.json({ count: entries.length, entries })
}

function _query(req: Request, res: Response, { hub, capIndex }: TaskRouterDeps): void {
  const { capability, minPressure, hub: hubFilter } = req.body as {
    capability?: string
    minPressure?: number
    hub?: string
  }
  if (!capability) {
    res.status(400).json({ error: 'capability is required' })
    return
  }
  let agents = capIndex.findByCapability(capability, minPressure)
  if (hubFilter) agents = agents.filter(a => a.hub === hubFilter)
  res.json({ capability, count: agents.length, agents })
}

function _route(req: Request, res: Response, { capIndex }: TaskRouterDeps): void {
  const { target, task } = req.body as {
    target?: string
    task?: Record<string, unknown>
  }
  if (!target || !task) {
    res.status(400).json({ error: 'target and task are required' })
    return
  }
  const [agentName, agentHub] = target.includes('@') ? target.split('@') : [target, undefined]
  const agent = agentHub
    ? capIndex.getAgent(agentName, agentHub)
    : capIndex.getAllAgents().find(a => a.name === agentName)
  if (!agent) {
    res.status(404).json({ error: `Agent not found: ${target}` })
    return
  }
  res.json({
    status: 'routed',
    target: `${agent.name}@${agent.hub}`,
    hub: agent.hub,
    isLocal: agent.isLocal,
    message: 'Route acknowledged (WebSocket routing in Phase 2)',
  })
}
