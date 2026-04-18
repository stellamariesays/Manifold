import { describe, it, expect, beforeEach } from 'vitest'
import { DetectionCoord } from '../src/server/detection-coord.js'
import type { DetectionLedger } from '../src/server/detection-ledger.js'
import type { DetectionClaim } from '../src/protocol/messages.js'

function makeClaim(domain: string): DetectionClaim {
  return {
    id: crypto.randomUUID(),
    domain,
    signal_type: 'price_move',
    source: 'test-agent@test-hub',
    confidence: 0.8,
    summary: `Test claim in ${domain}`,
    timestamp: new Date().toISOString(),
  }
}

function makeLedger(): DetectionLedger {
  const claims: any[] = []
  return {
    addClaim: (claim: any) => { claims.push(claim); return claim },
    addVerification: () => ({} as any),
    addChallenge: () => ({} as any),
    resolveOutcome: () => ({} as any),
    getClaimsByDomain: (d: string) => claims.filter((c: any) => c.domain === d),
    getOpenClaims: () => claims,
    getTrustScores: () => ({}),
    getStats: () => ({ total: claims.length }),
    getClaim: (id: string) => claims.find((c: any) => c.id === id),
  } as any
}

describe('Domain-based Detection Routing', () => {
  let coord: DetectionCoord
  let ledger: DetectionLedger
  let sentTo: Array<{ hub: string; msg: string }> = []

  beforeEach(() => {
    ledger = makeLedger()
    sentTo = []
  })

  it('broadcasts when no subscribers', () => {
    let broadcastMsg: any = null
    coord = new DetectionCoord({
      hub: 'test-hub',
      ledger,
      broadcastFn: undefined,
      debug: false,
    })
    coord.setBroadcast((msg) => { broadcastMsg = msg })

    const claim = makeClaim('crypto')
    coord.handleMessage({ type: 'detection_claim', claim } as any)

    expect(broadcastMsg).toBeTruthy()
    expect((broadcastMsg as any).claim.domain).toBe('crypto')
  })

  it('routes to subscribed hubs only', () => {
    const peerReg = {
      sendTo: (hub: string, msg: string) => {
        sentTo.push({ hub, msg })
        return true
      },
    } as any

    coord = new DetectionCoord({
      hub: 'test-hub',
      ledger,
      peerRegistry: peerReg,
      domainRoutingEnabled: true,
    })

    coord.subscribe('crypto', 'alice@hub-a')
    coord.subscribe('crypto', 'bob@hub-b')
    coord.subscribe('nlp', 'carol@hub-c')

    const claim = makeClaim('crypto')
    coord.handleMessage({ type: 'detection_claim', claim } as any)

    const hubs = sentTo.map(s => s.hub)
    expect(hubs).toContain('hub-a')
    expect(hubs).toContain('hub-b')
    expect(hubs).not.toContain('hub-c')
  })

  it('maintains domain hub index', () => {
    coord = new DetectionCoord({ hub: 'test-hub', ledger })

    coord.subscribe('crypto', 'alice@hub-a')
    coord.subscribe('crypto', 'bob@hub-b')
    coord.subscribe('crypto', 'carol@test-hub') // local

    const hubs = coord.getHubsForDomain('crypto')
    expect(hubs).toContain('hub-a')
    expect(hubs).toContain('hub-b')
    expect(hubs).toContain('test-hub')
    expect(hubs.length).toBe(3)
  })

  it('reports domain routing stats', () => {
    coord = new DetectionCoord({ hub: 'test-hub', ledger })

    coord.subscribe('crypto', 'alice@hub-a')
    coord.subscribe('crypto', 'bob@hub-b')
    coord.subscribe('nlp', 'carol@hub-c')

    const stats = coord.getDomainRoutingStats()
    expect(stats.domains).toBe(2)
    expect(stats.totalSubscriptions).toBe(3)
    expect(stats.domainBreakdown.crypto).toBe(2)
    expect(stats.domainBreakdown.nlp).toBe(1)
  })

  it('unsubscribes agents', () => {
    coord = new DetectionCoord({ hub: 'test-hub', ledger })
    coord.subscribe('crypto', 'alice@hub-a')
    coord.subscribe('crypto', 'bob@hub-b')

    coord.unsubscribe('crypto', 'alice@hub-a')

    const stats = coord.getDomainRoutingStats()
    expect(stats.totalSubscriptions).toBe(1)
  })

  it('handles agent without hub suffix as local', () => {
    coord = new DetectionCoord({ hub: 'test-hub', ledger })
    coord.subscribe('crypto', 'local-agent')

    const hubs = coord.getHubsForDomain('crypto')
    expect(hubs).toContain('test-hub')
  })
})
