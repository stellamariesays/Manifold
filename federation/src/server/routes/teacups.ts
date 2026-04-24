/**
 * teacups.ts — /teacups and /teacup/:id/score routes.
 */
import { type Request, type Response, type Router } from 'express'
import type { TaskHistory } from '../task-history.js'

export interface TeacupsRouterDeps {
  taskHistory: TaskHistory
}

export function buildTeacupsRouter(router: Router, deps: TeacupsRouterDeps): void {
  router.get('/teacups', (req, res) => _teacups(req, res, deps))
  router.post('/teacup/:id/score', (req, res) => _scoreTeacup(req, res, deps))
}

async function _teacups(req: Request, res: Response, { taskHistory }: TeacupsRouterDeps): Promise<void> {
  const limit = parseInt(String(req.query['limit'] ?? '20'), 10)
  const entries = await taskHistory.getTeacups(limit)
  res.json({ count: entries.length, entries })
}

async function _scoreTeacup(req: Request, res: Response, { taskHistory }: TeacupsRouterDeps): Promise<void> {
  const id = String(req.params['id'] ?? '')
  const { score, scored_by } = req.body

  if (typeof score !== 'number' || ![-1, 0, 1].includes(score)) {
    res.status(400).json({ error: 'score must be -1, 0, or 1' })
    return
  }

  const found = await taskHistory.scoreOutcome(id, score, String(scored_by ?? 'unknown'))
  if (!found) {
    res.status(404).json({ error: 'Task not found or already scored' })
    return
  }

  res.json({ ok: true, id, score, scored_by })
}
