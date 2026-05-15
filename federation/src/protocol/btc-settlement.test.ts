/**
 * btc-settlement.test.ts — Unit tests for the BTC settlement handler.
 *
 * Run with: npx tsx src/protocol/btc-settlement.test.ts
 */

import {
  BtcSettlementHandler,
  EscrowContract,
  BtcSettlementEvent,
  SettlementStats,
} from "./btc-settlement";
import {
  BtcStakeRequestMessage,
  BtcStakeConfirmedMessage,
  BtcSettlementRequestMessage,
  BtcSettlementResultMessage,
  BtcAddressAnnounceMessage,
} from "./messages";

// ─── Helpers ────────────────────────────────────────────────────────────

function makeHandler(): BtcSettlementHandler {
  return new BtcSettlementHandler({
    hubName: "test-hub",
    network: "testnet",
    escrowAddress: "tb1qescrowtest",
    burnAddress: "tb1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqx3s0a7",
  });
}

function stakeRequest(agentName: string, taskId: string, amountSats: number): BtcStakeRequestMessage {
  return {
    type: "btc_stake_request",
    payload: { agentName, taskId, amountSats, network: "testnet" },
    timestamp: new Date().toISOString(),
    sender: "test",
  };
}

function stakeConfirmed(contractId: string, txid: string, confirmations: number): BtcStakeConfirmedMessage {
  return {
    type: "btc_stake_confirmed",
    payload: { contractId, txid, confirmations, receivedSats: 0, confirmedBy: "test-hub" },
    timestamp: new Date().toISOString(),
    sender: "test",
  };
}

function settlementRequest(contractId: string, score: number): BtcSettlementRequestMessage {
  return {
    type: "btc_settlement_request",
    payload: { contractId, score },
    timestamp: new Date().toISOString(),
    sender: "test",
  };
}

function addressAnnounce(agentName: string, address: string, hub: string): BtcAddressAnnounceMessage {
  return {
    type: "btc_address_announce",
    payload: { agentName, address, network: "testnet", hub },
    timestamp: new Date().toISOString(),
    sender: "test",
  };
}

// ─── Test Runner ────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function assert(condition: boolean, msg: string): void {
  if (!condition) throw new Error(`Assertion failed: ${msg}`);
}

function test(name: string, fn: () => void): void {
  try {
    fn();
    passed++;
    console.log(`✅ ${name}`);
  } catch (err: any) {
    failed++;
    console.log(`❌ ${name}: ${err.message}`);
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────

test("stake request creates contract", () => {
  const h = makeHandler();
  h.handleMessage(stakeRequest("agent-1", "task-1", 50000));
  const stats = h.stats();
  assert(stats.total === 1, "should have 1 contract");
  assert(stats.pending === 1, "should be pending");
});

test("stake confirmed moves to in_escrow", () => {
  const h = makeHandler();
  const events: BtcSettlementEvent[] = [];
  h.onEvent((e) => events.push(e));

  h.handleMessage(stakeRequest("agent-1", "task-1", 50000));
  const contract = h.getContractsForAgent("agent-1")[0];

  h.handleMessage(stakeConfirmed(contract.id, "tx-abc", 3));

  const updated = h.getContract(contract.id)!;
  assert(updated.status === "in_escrow", `expected in_escrow, got ${updated.status}`);
  assert(updated.txid === "tx-abc", "txid should be set");
  assert(events.some((e) => e.type === "stake_confirmed"), "should emit stake_confirmed");
});

test("settlement releases for high score", () => {
  const h = makeHandler();
  h.handleMessage(stakeRequest("agent-1", "task-1", 50000));
  const contract = h.getContractsForAgent("agent-1")[0];
  h.handleMessage(stakeConfirmed(contract.id, "tx-abc", 3));
  h.handleMessage(settlementRequest(contract.id, 0.95));

  const settled = h.getContract(contract.id)!;
  assert(settled.status === "released", `expected released, got ${settled.status}`);
  assert(settled.gradeScore === 0.95, "score should be recorded");
});

test("settlement slashes for low score", () => {
  const h = makeHandler();
  h.handleMessage(stakeRequest("agent-1", "task-1", 50000));
  const contract = h.getContractsForAgent("agent-1")[0];
  h.handleMessage(stakeConfirmed(contract.id, "tx-abc", 3));
  h.handleMessage(settlementRequest(contract.id, 0.2));

  const settled = h.getContract(contract.id)!;
  assert(settled.status === "slashed", `expected slashed, got ${settled.status}`);
});

test("threshold: score 0.5 releases, 0.49 slashes", () => {
  const h1 = makeHandler();
  h1.handleMessage(stakeRequest("a", "t1", 10000));
  const c1 = h1.getContractsForAgent("a")[0];
  h1.handleMessage(stakeConfirmed(c1.id, "tx1", 1));
  h1.handleMessage(settlementRequest(c1.id, 0.5));
  assert(h1.getContract(c1.id)!.status === "released", "0.5 should release");

  const h2 = makeHandler();
  h2.handleMessage(stakeRequest("b", "t2", 10000));
  const c2 = h2.getContractsForAgent("b")[0];
  h2.handleMessage(stakeConfirmed(c2.id, "tx2", 1));
  h2.handleMessage(settlementRequest(c2.id, 0.49));
  assert(h2.getContract(c2.id)!.status === "slashed", "0.49 should slash");
});

test("address announce updates contracts", () => {
  const h = makeHandler();
  h.handleMessage(stakeRequest("agent-1", "task-1", 50000));
  h.handleMessage(addressAnnounce("agent-1", "tb1qagent1addr", "peer-hub"));

  const contract = h.getContractsForAgent("agent-1")[0];
  assert(contract.settlementAddress === "tb1qagent1addr", "address should be set");

  const addr = h.getAgentAddress("agent-1")!;
  assert(addr.address === "tb1qagent1addr", "address should be stored");
  assert(addr.hub === "peer-hub", "hub should be stored");
});

test("stats are accurate across multiple contracts", () => {
  const h = makeHandler();

  // 3 agents stake
  h.handleMessage(stakeRequest("a", "t1", 10000));
  h.handleMessage(stakeRequest("b", "t2", 20000));
  h.handleMessage(stakeRequest("c", "t3", 30000));

  let stats = h.stats();
  assert(stats.total === 3, `expected 3 total, got ${stats.total}`);
  assert(stats.pending === 3, `expected 3 pending, got ${stats.pending}`);

  // Confirm all
  const contracts = [h.getContractsForAgent("a")[0], h.getContractsForAgent("b")[0], h.getContractsForAgent("c")[0]];
  for (const c of contracts) {
    h.handleMessage(stakeConfirmed(c.id, `tx-${c.id}`, 3));
  }

  stats = h.stats();
  assert(stats.inEscrow === 3, `expected 3 in escrow, got ${stats.inEscrow}`);
  assert(stats.totalSatsStaked === 60000, `expected 60000 staked, got ${stats.totalSatsStaked}`);

  // Settle: a released, b slashed, c released
  h.handleMessage(settlementRequest(contracts[0].id, 0.9));
  h.handleMessage(settlementRequest(contracts[1].id, 0.3));
  h.handleMessage(settlementRequest(contracts[2].id, 0.7));

  stats = h.stats();
  assert(stats.released === 2, `expected 2 released, got ${stats.released}`);
  assert(stats.slashed === 1, `expected 1 slashed, got ${stats.slashed}`);
  assert(stats.totalSatsSlashed === 20000, `expected 20000 slashed, got ${stats.totalSatsSlashed}`);
  assert(stats.totalSatsReleased === 40000, `expected 40000 released, got ${stats.totalSatsReleased}`);
});

test("settlement on non-escrow contract is rejected", () => {
  const h = makeHandler();
  const events: BtcSettlementEvent[] = [];
  h.onEvent((e) => events.push(e));

  h.handleMessage(stakeRequest("a", "t1", 10000));
  const c = h.getContractsForAgent("a")[0];

  // Try to settle without confirming deposit
  h.handleMessage(settlementRequest(c.id, 0.9));

  assert(c.status === "pending", `expected pending, got ${c.status}`);
  assert(!events.some((e) => e.type === "settlement_completed"), "should not emit settlement_completed");
});

test("unknown message types are not handled", () => {
  const h = makeHandler();
  const handled = h.handleMessage({
    type: "peer_announce",
    payload: { hub: "test" },
    timestamp: new Date().toISOString(),
    sender: "test",
  } as any);
  assert(!handled, "should return false for unknown types");
});

// ─── Summary ────────────────────────────────────────────────────────────

console.log(`\n${"=".repeat(50)}`);
console.log(`Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
console.log("=".repeat(50));

if (failed > 0) {
  process.exit(1);
}
