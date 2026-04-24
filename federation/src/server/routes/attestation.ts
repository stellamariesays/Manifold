/**
 * attestation.ts — All /attestation/* and /registration/* routes.
 */
import { type Request, type Response, type Router } from 'express'
import { AttestationEngine } from '../../attestation/engine.js'
import { AntiSybilGuard } from '../../attestation/anti-sybil.js'
import type { CapabilityIndex } from '../capability-index.js'
import type { ChallengeType } from '../../attestation/challenges.js'

export interface AttestationRouterDeps {
  attestationEngine: AttestationEngine
  antiSybilGuard: AntiSybilGuard
  capIndex: CapabilityIndex
  log: (msg: string) => void
}

export function buildAttestationRouter(router: Router, deps: AttestationRouterDeps): void {
  router.post('/attestation/challenge', (req, res) => _attestationChallenge(req, res, deps))
  router.post('/attestation/proof', (req, res) => _attestationProof(req, res, deps))
  router.post('/attestation/attest', (req, res) => _attestationAttest(req, res, deps))
  router.get('/attestation/status/:agentId/:capability', (req, res) => _attestationStatus(req, res, deps))
  router.post('/registration/challenge', (req, res) => _registrationChallenge(req, res, deps))
  router.post('/registration/verify', (req, res) => _registrationVerify(req, res, deps))
}

function _attestationChallenge(req: Request, res: Response, { attestationEngine, log }: AttestationRouterDeps): void {
  const { capability, agentId, difficulty, type } = req.body as {
    capability?: string
    agentId?: string
    difficulty?: number
    type?: ChallengeType
  }
  if (!capability || !agentId) {
    res.status(400).json({ error: 'capability and agentId are required' })
    return
  }
  const challenge = attestationEngine.issueChallenge(capability, agentId, difficulty, type)
  log(`Attestation challenge issued: ${challenge.id} for ${agentId} / ${capability}`)
  res.json({ challenge })
}

function _attestationProof(req: Request, res: Response, { attestationEngine, log }: AttestationRouterDeps): void {
  const { challengeId, agentId, response } = req.body as {
    challengeId?: string
    agentId?: string
    response?: Record<string, unknown>
  }
  if (!challengeId || !agentId || !response) {
    res.status(400).json({ error: 'challengeId, agentId, and response are required' })
    return
  }
  const result = attestationEngine.submitProof(challengeId, agentId, response)
  if (!result.success) {
    res.status(400).json({ error: result.error })
    return
  }
  log(`Attestation proof submitted: ${challengeId} by ${agentId}`)
  res.json({ status: 'proof_submitted', challengeId })
}

function _attestationAttest(req: Request, res: Response, { attestationEngine, capIndex, log }: AttestationRouterDeps): void {
  const { challengeId, peerId, score, notes } = req.body as {
    challengeId?: string
    peerId?: string
    score?: number
    notes?: string
  }
  if (!challengeId || !peerId || score === undefined) {
    res.status(400).json({ error: 'challengeId, peerId, and score are required' })
    return
  }
  const result = attestationEngine.addAttestation(challengeId, peerId, score, notes)
  if (!result.success) {
    res.status(400).json({ error: result.error })
    return
  }
  const record = attestationEngine.getRecord(challengeId)
  if (record) {
    const scoreData = attestationEngine.getScore(record.challenge.agentId, record.challenge.capability)
    capIndex.setAttestationScore(
      record.challenge.agentId,
      record.challenge.capability,
      scoreData.averageScore,
      scoreData.attestationCount,
      scoreData.isAttested,
    )
  }
  log(`Attestation: ${peerId} attested ${challengeId} with score ${score}`)
  res.json({ status: 'attested', challengeId })
}

function _attestationStatus(req: Request, res: Response, { attestationEngine }: AttestationRouterDeps): void {
  const agentId = decodeURIComponent(String(req.params['agentId'] ?? ''))
  const capability = decodeURIComponent(String(req.params['capability'] ?? ''))
  const score = attestationEngine.getScore(agentId, capability)
  res.json(score)
}

function _registrationChallenge(req: Request, res: Response, { antiSybilGuard }: AttestationRouterDeps): void {
  const ip = req.ip ?? req.socket.remoteAddress ?? 'unknown'
  const challenge = antiSybilGuard.issueChallenge(ip)
  if (!challenge) {
    res.status(429).json({ error: 'Rate limited — too many registration attempts from this IP' })
    return
  }
  res.json({ challenge })
}

function _registrationVerify(req: Request, res: Response, { antiSybilGuard, log }: AttestationRouterDeps): void {
  const { challengeId, nonce, hash } = req.body as {
    challengeId?: string
    nonce?: string
    hash?: string
  }
  if (!challengeId || !nonce || !hash) {
    res.status(400).json({ error: 'challengeId, nonce, and hash are required' })
    return
  }
  const ip = req.ip ?? req.socket.remoteAddress ?? 'unknown'
  const result = antiSybilGuard.verifySolution({ challengeId, nonce, hash }, ip)
  if (!result.valid) {
    res.status(400).json({ error: result.error })
    return
  }
  log(`PoW registration verified: challenge ${challengeId}`)
  res.json({ status: 'verified', message: 'Registration approved' })
}
