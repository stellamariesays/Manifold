/**
 * detection.ts — All /detection* and /detections* and /trust routes.
 */
import { type Request, type Response, type Router } from 'express'
import type { DetectionCoord } from '../detection-coord.js'

export interface DetectionRouterDeps {
  detectionCoord: DetectionCoord
}

export function buildDetectionRouter(router: Router, deps: DetectionRouterDeps): void {
  // NOTE: /detections/stats MUST come before /detections/:id (Express matches in order)
  router.get('/detections/stats', (req, res) => _detectionStats(req, res, deps))
  router.get('/detections', (req, res) => _detections(req, res, deps))
  router.get('/detections/:id', (req, res) => _detectionDetail(req, res, deps))
  router.get('/trust', (req, res) => _trustScores(req, res, deps))
  router.post('/detection/claim', (req, res) => _submitClaim(req, res, deps))
  router.post('/detection/verify', (req, res) => _submitVerify(req, res, deps))
  router.post('/detection/outcome', (req, res) => _submitOutcome(req, res, deps))
}

function _detections(req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  const domain = req.query['domain'] as string | undefined
  const limit = parseInt(req.query['limit'] as string ?? '20', 10)
  const open = req.query['open'] === 'true'

  const claims = open
    ? detectionCoord.getOpenClaims(domain)
    : domain
      ? detectionCoord.getOpenClaims(domain)
      : detectionCoord.ledger.getRecentClaims(limit)

  res.json({
    claims: claims.slice(0, limit).map(e => ({
      id: e.claim.id,
      source: e.claim.source,
      domain: e.claim.domain,
      summary: e.claim.summary,
      confidence: e.claim.confidence,
      created_at: e.claim.created_at,
      verifications: e.verifications.length,
      challenges: e.challenges.length,
      outcome: e.outcome?.outcome ?? null,
    })),
    total: claims.length,
  })
}

function _detectionDetail(req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  const id = String(req.params['id'] ?? '')
  const entry = detectionCoord.getClaim(id)
  if (!entry) {
    res.status(404).json({ error: 'Claim not found' })
    return
  }
  res.json({
    claim: entry.claim,
    verifications: entry.verifications,
    challenges: entry.challenges,
    outcome: entry.outcome,
    trust_score: detectionCoord.ledger.getTrustScore(entry.claim.source),
  })
}

function _detectionStats(_req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  res.json(detectionCoord.getStats())
}

function _trustScores(_req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  res.json(detectionCoord.getTrustScores())
}

function _submitClaim(req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  const { source, domain, summary, confidence, evidence_hash, ttl_seconds, evidence } = req.body as {
    source?: string
    domain?: string
    summary?: string
    confidence?: number
    evidence_hash?: string
    ttl_seconds?: number
    evidence?: Record<string, unknown>
  }

  if (!source || !domain || !summary || confidence === undefined) {
    res.status(400).json({ error: 'source, domain, summary, and confidence are required' })
    return
  }

  const claim = {
    id: crypto.randomUUID(),
    source,
    domain,
    summary,
    confidence: Math.max(0, Math.min(1, confidence)),
    evidence_hash: evidence_hash ?? '',
    created_at: new Date().toISOString(),
    ttl_seconds,
    evidence,
  }

  detectionCoord.handleMessage({ type: 'detection_claim', claim })
  res.json({ claim_id: claim.id, status: 'recorded', propagated: true })
}

function _submitVerify(req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  const { claim_id, verifier, agrees, confidence, notes } = req.body as {
    claim_id?: string
    verifier?: string
    agrees?: boolean
    confidence?: number
    notes?: string
  }

  if (!claim_id || !verifier || agrees === undefined) {
    res.status(400).json({ error: 'claim_id, verifier, and agrees are required' })
    return
  }

  const verification = {
    claim_id,
    verifier,
    agrees,
    confidence: confidence ?? (agrees ? 0.8 : 0.2),
    notes,
    verified_at: new Date().toISOString(),
  }

  detectionCoord.handleMessage({ type: 'detection_verify', verification })
  res.json({ claim_id, status: 'verified', agrees })
}

function _submitOutcome(req: Request, res: Response, { detectionCoord }: DetectionRouterDeps): void {
  const { claim_id, outcome, resolved_by, notes, superseded_by } = req.body as {
    claim_id?: string
    outcome?: 'confirmed' | 'false_positive' | 'expired' | 'superseded'
    resolved_by?: string
    notes?: string
    superseded_by?: string
  }

  if (!claim_id || !outcome || !resolved_by) {
    res.status(400).json({ error: 'claim_id, outcome, and resolved_by are required' })
    return
  }

  const detectionOutcome = {
    claim_id,
    outcome,
    resolved_by,
    resolved_at: new Date().toISOString(),
    notes,
    superseded_by,
  }

  detectionCoord.handleMessage({ type: 'detection_outcome', outcome: detectionOutcome })
  res.json({ claim_id, status: outcome })
}
