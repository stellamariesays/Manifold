/**
 * btc-settlement.ts — Bitcoin settlement handler for the Manifold federation.
 *
 * Processes incoming BTC settlement messages, manages escrow state,
 * and broadcasts settlement results to peers.
 *
 * Integrates with the existing federation protocol (messages.ts).
 */

import {
  FederationMessage,
  BtcStakeRequestMessage,
  BtcStakeConfirmedMessage,
  BtcSettlementRequestMessage,
  BtcSettlementResultMessage,
  BtcAddressAnnounceMessage,
} from "./messages";

// ─── Types ──────────────────────────────────────────────────────────────

export interface EscrowContract {
  id: string;
  agentName: string;
  taskId: string;
  amountSats: number;
  escrowAddress: string;
  settlementAddress: string;
  status: "pending" | "deposited" | "in_escrow" | "released" | "slashed" | "expired";
  network: "testnet" | "mainnet";
  hub: string;
  createdAt: string;
  expiresAt: string;
  txid?: string;
  settledAt?: string;
  gradeScore?: number;
}

export interface BtcAgentAddress {
  agentName: string;
  address: string;
  network: "testnet" | "mainnet";
  hub: string;
}

export interface SettlementStats {
  total: number;
  pending: number;
  inEscrow: number;
  released: number;
  slashed: number;
  expired: number;
  totalSatsStaked: number;
  totalSatsSlashed: number;
  totalSatsReleased: number;
}

export type BtcSettlementEventHandler = (event: BtcSettlementEvent) => void;

export interface BtcSettlementEvent {
  type: "stake_requested" | "stake_confirmed" | "settlement_requested" | "settlement_completed" | "address_announced" | "contract_expired";
  contract?: EscrowContract;
  agentAddress?: BtcAgentAddress;
  timestamp: string;
  hub: string;
}

// ─── Constants ──────────────────────────────────────────────────────────

const SLASH_THRESHOLD = 0.5;
const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

// ─── BtcSettlementHandler ───────────────────────────────────────────────

export class BtcSettlementHandler {
  private contracts: Map<string, EscrowContract> = new Map();
  private agentAddresses: Map<string, BtcAgentAddress> = new Map();
  private eventHandlers: BtcSettlementEventHandler[] = [];
  private hubName: string;
  private network: "testnet" | "mainnet";
  private escrowAddress: string;
  private burnAddress: string;
  private expiryTimer?: ReturnType<typeof setInterval>;

  constructor(opts: {
    hubName: string;
    network?: "testnet" | "mainnet";
    escrowAddress: string;
    burnAddress: string;
  }) {
    this.hubName = opts.hubName;
    this.network = opts.network ?? "testnet";
    this.escrowAddress = opts.escrowAddress;
    this.burnAddress = opts.burnAddress;
  }

  // ─── Message Routing ────────────────────────────────────────────────

  /**
   * Route an incoming federation message to the appropriate handler.
   * Returns true if the message was handled.
   */
  handleMessage(msg: FederationMessage): boolean {
    switch (msg.type) {
      case "btc_stake_request":
        this.handleStakeRequest(msg as BtcStakeRequestMessage);
        return true;
      case "btc_stake_confirmed":
        this.handleStakeConfirmed(msg as BtcStakeConfirmedMessage);
        return true;
      case "btc_settlement_request":
        this.handleSettlementRequest(msg as BtcSettlementRequestMessage);
        return true;
      case "btc_settlement_result":
        this.handleSettlementResult(msg as BtcSettlementResultMessage);
        return true;
      case "btc_address_announce":
        this.handleAddressAnnounce(msg as BtcAddressAnnounceMessage);
        return true;
      default:
        return false;
    }
  }

  // ─── Stake Request ──────────────────────────────────────────────────

  private handleStakeRequest(msg: BtcStakeRequestMessage): void {
    const { agentName, taskId, amountSats } = msg.payload;

    const contract: EscrowContract = {
      id: this.generateContractId(),
      agentName,
      taskId,
      amountSats,
      escrowAddress: this.escrowAddress,
      settlementAddress: "", // Will be set when agent announces address
      status: "pending",
      network: this.network,
      hub: this.hubName,
      createdAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + DEFAULT_TTL_MS).toISOString(),
    };

    // Check if we know this agent's address
    const known = this.agentAddresses.get(agentName);
    if (known) {
      contract.settlementAddress = known.address;
    }

    this.contracts.set(contract.id, contract);
    this.emit({
      type: "stake_requested",
      contract,
      timestamp: contract.createdAt,
      hub: this.hubName,
    });
  }

  // ─── Stake Confirmed ────────────────────────────────────────────────

  private handleStakeConfirmed(msg: BtcStakeConfirmedMessage): void {
    const { contractId, txid, confirmations, receivedSats } = msg.payload;
    const contract = this.contracts.get(contractId);

    if (!contract) {
      console.warn(`[btc] Unknown contract: ${contractId}`);
      return;
    }

    contract.txid = txid;
    if (confirmations >= 1) {
      contract.status = "in_escrow";
    } else {
      contract.status = "deposited";
    }

    this.emit({
      type: "stake_confirmed",
      contract,
      timestamp: new Date().toISOString(),
      hub: this.hubName,
    });
  }

  // ─── Settlement Request ─────────────────────────────────────────────

  private handleSettlementRequest(msg: BtcSettlementRequestMessage): void {
    const { contractId, score } = msg.payload;
    const contract = this.contracts.get(contractId);

    if (!contract) {
      console.warn(`[btc] Settlement for unknown contract: ${contractId}`);
      return;
    }

    if (contract.status !== "in_escrow") {
      console.warn(`[btc] Contract ${contractId} not in escrow: ${contract.status}`);
      return;
    }

    contract.gradeScore = score;
    const outcome = score >= SLASH_THRESHOLD ? "released" : "slashed";
    contract.status = outcome;
    contract.settledAt = new Date().toISOString();

    this.emit({
      type: "settlement_completed",
      contract,
      timestamp: contract.settledAt,
      hub: this.hubName,
    });
  }

  // ─── Settlement Result ──────────────────────────────────────────────

  private handleSettlementResult(msg: BtcSettlementResultMessage): void {
    const { contractId, outcome, amountSats, settlementAddress, settledBy } = msg.payload;
    const contract = this.contracts.get(contractId);

    if (contract) {
      contract.status = outcome;
      contract.settledAt = msg.payload.settledAt;
      console.info(`[btc] Settlement result: ${contractId} → ${outcome} by ${settledBy}`);
    }
  }

  // ─── Address Announce ───────────────────────────────────────────────

  private handleAddressAnnounce(msg: BtcAddressAnnounceMessage): void {
    const { agentName, address, network, hub } = msg.payload;

    const addr: BtcAgentAddress = { agentName, address, network, hub };
    this.agentAddresses.set(agentName, addr);

    // Update any pending contracts for this agent
    for (const contract of this.contracts.values()) {
      if (contract.agentName === agentName && !contract.settlementAddress) {
        contract.settlementAddress = address;
      }
    }

    this.emit({
      type: "address_announced",
      agentAddress: addr,
      timestamp: new Date().toISOString(),
      hub: this.hubName,
    });
  }

  // ─── Contract Expiry ────────────────────────────────────────────────

  startExpiryChecker(intervalMs: number = 60000): void {
    this.expiryTimer = setInterval(() => {
      const now = Date.now();
      for (const [id, contract] of this.contracts) {
        if (
          (contract.status === "in_escrow" || contract.status === "pending" || contract.status === "deposited") &&
          new Date(contract.expiresAt).getTime() < now
        ) {
          contract.status = "expired";
          this.emit({
            type: "contract_expired",
            contract,
            timestamp: new Date().toISOString(),
            hub: this.hubName,
          });
        }
      }
    }, intervalMs);
  }

  stopExpiryChecker(): void {
    if (this.expiryTimer) {
      clearInterval(this.expiryTimer);
      this.expiryTimer = undefined;
    }
  }

  // ─── Queries ────────────────────────────────────────────────────────

  getContract(id: string): EscrowContract | undefined {
    return this.contracts.get(id);
  }

  getContractsForAgent(agentName: string): EscrowContract[] {
    return [...this.contracts.values()].filter((c) => c.agentName === agentName);
  }

  getAgentAddress(agentName: string): BtcAgentAddress | undefined {
    return this.agentAddresses.get(agentName);
  }

  getActiveContracts(): EscrowContract[] {
    return [...this.contracts.values()].filter(
      (c) => c.status === "pending" || c.status === "deposited" || c.status === "in_escrow"
    );
  }

  stats(): SettlementStats {
    const contracts = [...this.contracts.values()];
    return {
      total: contracts.length,
      pending: contracts.filter((c) => c.status === "pending").length,
      inEscrow: contracts.filter((c) => c.status === "in_escrow").length,
      released: contracts.filter((c) => c.status === "released").length,
      slashed: contracts.filter((c) => c.status === "slashed").length,
      expired: contracts.filter((c) => c.status === "expired").length,
      totalSatsStaked: contracts
        .filter((c) => c.status === "in_escrow")
        .reduce((sum, c) => sum + c.amountSats, 0),
      totalSatsSlashed: contracts
        .filter((c) => c.status === "slashed")
        .reduce((sum, c) => sum + c.amountSats, 0),
      totalSatsReleased: contracts
        .filter((c) => c.status === "released")
        .reduce((sum, c) => sum + c.amountSats, 0),
    };
  }

  // ─── Event Emitter ──────────────────────────────────────────────────

  onEvent(handler: BtcSettlementEventHandler): () => void {
    this.eventHandlers.push(handler);
    return () => {
      const idx = this.eventHandlers.indexOf(handler);
      if (idx >= 0) this.eventHandlers.splice(idx, 1);
    };
  }

  private emit(event: BtcSettlementEvent): void {
    for (const handler of this.eventHandlers) {
      try {
        handler(event);
      } catch (err) {
        console.error("[btc] Event handler error:", err);
      }
    }
  }

  // ─── Helpers ────────────────────────────────────────────────────────

  private generateContractId(): string {
    const bytes = new Uint8Array(4);
    // Use crypto.getRandomValues if available, otherwise Math.random
    if (typeof crypto !== "undefined" && crypto.getRandomValues) {
      crypto.getRandomValues(bytes);
    } else {
      for (let i = 0; i < 4; i++) bytes[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(bytes)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
}
