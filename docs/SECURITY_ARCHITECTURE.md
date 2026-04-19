# Manifold Security Architecture

*A trustless, decentralized cognitive mesh security framework*

## Executive Summary

Manifold is evolving from a Tailscale-dependent federated system to a fully trustless, decentralized cognitive mesh. This document defines a five-layer security architecture that enables global scale while maintaining Byzantine fault tolerance and preventing adversarial manipulation.

**Current State**: 21 agents across 3 hubs (satelliteA, HOG, thefog) connected via TypeScript federation servers over Tailscale. Trust is stake-based with referral chains but lacks cryptographic identity.

**Target State**: Cryptographically-secured mesh where agents ARE the network nodes, with proof-of-capability attestation, gossip-based consensus, anti-Sybil mechanisms, and hierarchical trust zones.

## Architecture Layers

### Layer 1: Cryptographic Identity

**Problem**: Current agents use string names (`"braid"`, `"stella"`) with no cryptographic identity. Anyone can impersonate any agent name on a new hub.

**Solution**: Ed25519 keypair-based identity with portable agent credentials.

#### 1.1 Agent Identity Protocol

Each agent maintains a persistent cryptographic identity:

```python
# Core identity structure
@dataclass(frozen=True)
class AgentIdentity:
    public_key: str      # ed25519 public key (hex)
    agent_name: str      # human-readable name
    genesis_hash: str    # hash of first capability announcement
    created_at: int      # unix timestamp
    
    def agent_id(self) -> str:
        """Canonical agent identifier: first 8 chars of pubkey"""
        return self.public_key[:8]
    
    def full_name(self) -> str:
        """Human name with ID suffix: 'stella@a1b2c3d4'"""
        return f"{self.agent_name}@{self.agent_id()}"

# Agent registration with identity
class Agent:
    def __init__(self, name: str, keypath: str = None):
        if keypath and os.path.exists(keypath):
            self._identity = AgentIdentity.load(keypath)
        else:
            # Generate new identity
            keypair = crypto.generate_ed25519_keypair()
            self._identity = AgentIdentity(
                public_key=keypair.public_key_hex,
                agent_name=name,
                genesis_hash="",  # Set on first capability announcement
                created_at=int(time.time())
            )
            if keypath:
                self._identity.save(keypath)
    
    async def join(self):
        # Sign capability announcement with private key
        announcement = {
            "agent_identity": self._identity.to_dict(),
            "capabilities": self._capabilities,
            "hub": self._current_hub,
            "timestamp": int(time.time())
        }
        signature = crypto.sign_message(
            canonical_json(announcement), 
            self._private_key
        )
        await self._transport.publish("mesh.identity", {
            **announcement,
            "signature": signature
        })
```

#### 1.2 Identity Verification

All mesh participants verify identity claims:

```python
class IdentityRegistry:
    def __init__(self):
        self._verified_agents: Dict[str, AgentIdentity] = {}
        self._pending_challenges: Dict[str, Challenge] = {}
    
    def verify_agent_announcement(self, msg: dict) -> VerificationResult:
        """Verify signed capability announcement"""
        # 1. Extract identity and signature
        identity = AgentIdentity.from_dict(msg["agent_identity"])
        signature = msg["signature"]
        
        # 2. Reconstruct canonical message for verification
        canonical = canonical_json({
            k: v for k, v in msg.items() if k != "signature"
        })
        
        # 3. Verify Ed25519 signature
        if not crypto.verify_signature(canonical, signature, identity.public_key):
            return VerificationResult.INVALID_SIGNATURE
        
        # 4. Check for identity conflicts
        existing = self._verified_agents.get(identity.agent_id())
        if existing and existing.public_key != identity.public_key:
            return VerificationResult.IDENTITY_CONFLICT
        
        # 5. Store verified identity
        self._verified_agents[identity.agent_id()] = identity
        return VerificationResult.VERIFIED
```

#### 1.3 Key Management

**Local Storage**: Private keys stored in `~/.manifold/identity/agent.key` (encrypted with user's password)

**Backup/Recovery**: BIP39-style mnemonic backup for key recovery:
```python
def generate_agent_identity(passphrase: str = None) -> Tuple[AgentIdentity, str]:
    """Generate identity with mnemonic backup"""
    entropy = os.urandom(32)
    mnemonic = bip39.encode(entropy)
    seed = bip39.decode(mnemonic, passphrase)
    keypair = crypto.ed25519_from_seed(seed)
    
    identity = AgentIdentity(
        public_key=keypair.public_key_hex,
        agent_name="", # Set later
        genesis_hash="",
        created_at=int(time.time())
    )
    return identity, mnemonic
```

**Migration Path**: 
1. Phase 1: Optional cryptographic identity (backward compatible with name-based agents)
2. Phase 2: Required for new agents, existing agents prompted to upgrade
3. Phase 3: Name-based agents deprecated, mesh requires cryptographic identity

### Layer 2: Attestation System

**Problem**: Agents self-declare capabilities with no verification. A malicious agent can claim `"quantum-computing"` without proof.

**Solution**: Peer attestation network where capability claims must be proven through challenges and peer verification.

#### 2.1 Capability Attestation Protocol

Three-stage attestation: **Claim → Challenge → Attest**

```python
@dataclass(frozen=True)
class CapabilityChallenge:
    """Challenge to prove a capability claim"""
    capability: str
    challenger_id: str
    claimant_id: str
    challenge_data: dict        # capability-specific test
    challenge_hash: str         # hash for integrity
    expiry: int                 # unix timestamp
    
@dataclass(frozen=True)
class AttestationProof:
    """Proof of capability completion"""
    challenge_hash: str
    proof_data: dict           # solution/output
    completed_at: int
    signature: str            # claimant's signature
    
@dataclass(frozen=True)
class PeerAttestation:
    """Peer verification of proof quality"""
    challenge_hash: str
    attestor_id: str
    quality_score: float      # 0.0-1.0 assessment
    confidence: float         # attestor's confidence in assessment  
    timestamp: int
    signature: str           # attestor's signature
```

**Protocol Flow**:
1. Agent claims capability: `agent.knows(["solar-flare-prediction"])`
2. Peer issues challenge: specific prediction task with known outcome
3. Claimant provides proof: prediction result with methodology
4. Multiple peers attest: score the proof quality (0.0-1.0)
5. Capability accepted if attestation threshold reached (e.g., 3 peers, avg score > 0.7)

#### 2.2 Challenge Generation

Capability-specific challenge generators:

```python
class ChallengeEngine:
    def __init__(self):
        self._generators = {
            "solar-flare-prediction": SolarFlareGenerator(),
            "rust-compilation": RustCodeGenerator(), 
            "database-optimization": SQLOptimizationGenerator(),
            "cryptographic-proof": ZKProofGenerator()
        }
    
    def generate_challenge(self, capability: str, difficulty: float = 0.5) -> CapabilityChallenge:
        generator = self._generators.get(capability)
        if not generator:
            # Generic capability - peers design ad-hoc challenges
            return self._generic_challenge(capability, difficulty)
        
        return generator.create_challenge(difficulty)

class SolarFlareGenerator:
    def create_challenge(self, difficulty: float) -> CapabilityChallenge:
        """Generate solar flare prediction challenge from historical data"""
        # Select historical period with known solar activity
        period = self._select_test_period(difficulty)
        return CapabilityChallenge(
            capability="solar-flare-prediction",
            challenger_id="",  # Set by challenger
            claimant_id="",    # Set by challenger
            challenge_data={
                "type": "time_series_prediction",
                "data_period": period,
                "predict_window": "72_hours", 
                "required_accuracy": 0.85,
                "dataset_hash": self._compute_hash(period)
            },
            challenge_hash="",  # Computed from challenge_data
            expiry=int(time.time()) + 3600  # 1 hour to complete
        )
```

#### 2.3 Sophia Attestation Integration

The Sophia signal becomes an attestation mechanism:

```python
class SophiaAttestation:
    """Use Sophia curvature as proof-of-work for capability claims"""
    
    def generate_sophia_challenge(self, capability: str) -> dict:
        """Challenge: improve mesh curvature in capability region"""
        return {
            "type": "sophia_improvement",
            "capability_region": capability,
            "baseline_curvature": self._measure_current_curvature(capability),
            "required_improvement": 0.15,  # 15% curvature increase
            "time_limit": 3600,            # 1 hour
            "evidence_required": ["transition_map", "mesh_topology", "curvature_measurement"]
        }
    
    def verify_sophia_proof(self, proof: dict, baseline: float) -> float:
        """Verify that claimant improved mesh topology around capability"""
        # 1. Validate transition maps provided
        # 2. Measure actual curvature improvement
        # 3. Confirm improvement is non-trivial (not just noise)
        new_curvature = self._measure_curvature(proof["topology"])
        improvement = new_curvature - baseline
        return min(1.0, improvement / 0.15)  # Score based on improvement ratio
```

#### 2.4 Reputation-Weighted Attestation

Attestations carry more weight from agents with proven capability assessment:

```python
class AttestationWeight:
    def compute_attestor_weight(self, attestor_id: str, capability: str) -> float:
        """Weight attestation based on attestor's track record"""
        # 1. How many attestations has this agent provided?
        attestation_count = self._get_attestation_count(attestor_id)
        
        # 2. How accurate were their previous assessments?
        accuracy_score = self._compute_historical_accuracy(attestor_id)
        
        # 3. Do they have the capability they're assessing?
        capability_match = 1.0 if self._agent_has_capability(attestor_id, capability) else 0.7
        
        # 4. Time-decay for long-inactive attestors
        recency = self._compute_recency_factor(attestor_id)
        
        return min(1.0, 
            0.4 * accuracy_score + 
            0.3 * capability_match + 
            0.2 * min(1.0, attestation_count / 50) +
            0.1 * recency
        )
```

### Layer 3: Consensus Mechanism

**Problem**: No canonical mesh state when hubs disagree about agent capabilities or mesh topology. Currently "last writer wins" with no conflict resolution.

**Solution**: Gossip-based consensus with capability voting and fork resolution.

#### 3.1 Mesh State Consensus

The mesh maintains consensus on three critical data structures:

1. **Agent Registry**: Which agents exist and what they claim to know
2. **Capability Index**: Which capabilities have been attested and by whom  
3. **Topology Snapshot**: Current transition maps and atlas structure

```python
@dataclass(frozen=True)
class MeshState:
    """Canonical mesh state at a given version"""
    version: int
    timestamp: int
    agent_registry: Dict[str, AgentRecord]     # agent_id -> record
    capability_index: Dict[str, CapabilityRecord]  # capability -> attestations
    topology_hash: str                         # hash of current atlas
    state_hash: str                           # hash of all above
    
@dataclass(frozen=True)  
class StateTransition:
    """Atomic change to mesh state"""
    prev_state_hash: str
    new_state_hash: str
    transition_type: str       # "agent_join", "capability_attest", "topology_update"
    transition_data: dict
    proposer_id: str
    timestamp: int
    signatures: List[str]      # signatures from consensus participants

class ConsensusEngine:
    def __init__(self, hub_id: str):
        self._current_state: MeshState = None
        self._pending_transitions: List[StateTransition] = []
        self._consensus_threshold = 0.67  # 67% of hubs must agree
        
    async def propose_transition(self, transition: StateTransition) -> bool:
        """Propose state transition to mesh"""
        # 1. Validate transition is legal from current state
        if not self._validate_transition(transition):
            return False
            
        # 2. Sign transition with hub's identity
        signed_transition = self._sign_transition(transition)
        
        # 3. Broadcast to all peers for voting
        await self._broadcast_transition(signed_transition)
        
        # 4. Collect votes
        return await self._await_consensus(transition.new_state_hash)
```

#### 3.2 PBFT-Inspired Voting

Byzantine Fault Tolerant consensus adapted for decentralized mesh:

```python
class HubConsensus:
    """Practical Byzantine Fault Tolerance for mesh state"""
    
    async def vote_on_transition(self, transition: StateTransition) -> Vote:
        """Vote on proposed state transition"""
        
        # 1. Validate transition is well-formed
        if not self._validate_transition_structure(transition):
            return Vote.REJECT("malformed_transition")
        
        # 2. Check transition doesn't conflict with local state  
        if self._conflicts_with_local_state(transition):
            return Vote.REJECT("state_conflict")
        
        # 3. Verify proposer signatures
        if not self._verify_signatures(transition):
            return Vote.REJECT("invalid_signature")
        
        # 4. Check for Byzantine behavior patterns
        if self._detect_byzantine_pattern(transition.proposer_id):
            return Vote.REJECT("byzantine_proposer")
        
        return Vote.ACCEPT()
    
    async def reach_consensus(self, transition_hash: str, timeout: int = 30) -> ConsensusResult:
        """Wait for 2/3 majority consensus"""
        votes = {}
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Collect votes from peers
            vote_batch = await self._collect_votes_batch(transition_hash, batch_size=10)
            
            for hub_id, vote in vote_batch.items():
                if self._verify_vote_signature(vote, hub_id):
                    votes[hub_id] = vote
            
            # Check if we have 2/3 majority
            if self._has_supermajority(votes):
                accept_votes = sum(1 for v in votes.values() if v.decision == "ACCEPT") 
                total_votes = len(votes)
                
                if accept_votes / total_votes >= self._consensus_threshold:
                    return ConsensusResult.ACCEPTED
                else:
                    return ConsensusResult.REJECTED
        
        return ConsensusResult.TIMEOUT
```

#### 3.3 Fork Resolution

When hubs disagree about mesh state, resolve through weighted voting:

```python
class ForkResolver:
    def resolve_state_fork(self, fork_a: MeshState, fork_b: MeshState) -> MeshState:
        """Resolve conflicting mesh states"""
        
        # 1. Count hub support for each fork
        support_a = self._count_hub_support(fork_a.state_hash)
        support_b = self._count_hub_support(fork_b.state_hash)
        
        # 2. Weight by hub reputation (more trusted hubs count more)
        weight_a = sum(self._get_hub_weight(hub) for hub in support_a)
        weight_b = sum(self._get_hub_weight(hub) for hub in support_b)
        
        # 3. Choose fork with higher weighted support
        if weight_a > weight_b:
            self._log_fork_resolution(fork_a, "weighted_majority")
            return fork_a
        elif weight_b > weight_a:
            self._log_fork_resolution(fork_b, "weighted_majority")  
            return fork_b
        else:
            # 4. Tie-breaker: choose fork with more recent timestamp
            latest = fork_a if fork_a.timestamp > fork_b.timestamp else fork_b
            self._log_fork_resolution(latest, "timestamp_tiebreaker")
            return latest
    
    def _get_hub_weight(self, hub_id: str) -> float:
        """Hub weight based on historical accuracy and stake"""
        base_weight = 1.0
        
        # Bonus for hubs with good consensus history
        accuracy = self._get_consensus_accuracy(hub_id)
        accuracy_bonus = 0.5 * accuracy
        
        # Bonus for hubs with verified agents
        agent_quality = self._get_average_agent_quality(hub_id)
        agent_bonus = 0.3 * agent_quality
        
        # Penalty for recent Byzantine behavior
        byzantine_penalty = self._get_byzantine_penalty(hub_id)
        
        return max(0.1, base_weight + accuracy_bonus + agent_bonus - byzantine_penalty)
```

#### 3.4 Capability Consensus

Specific consensus for capability attestations:

```python
class CapabilityConsensus:
    """Consensus specifically for capability attestation decisions"""
    
    async def vote_on_attestation(self, attestation: PeerAttestation) -> AttestationVote:
        """Vote whether to accept a capability attestation"""
        
        capability = attestation.capability
        attestor = attestation.attestor_id
        
        # 1. Does attestor have credibility for this capability?
        attestor_credibility = self._compute_attestor_credibility(attestor, capability)
        if attestor_credibility < 0.3:
            return AttestationVote.REJECT("low_credibility")
        
        # 2. Is the quality score reasonable given evidence?
        if not self._validate_quality_score(attestation):
            return AttestationVote.REJECT("invalid_score")
        
        # 3. Does this conflict with existing strong attestations?
        if self._conflicts_with_consensus(attestation):
            return AttestationVote.REJECT("consensus_conflict")
        
        return AttestationVote.ACCEPT(weight=attestor_credibility)
    
    def finalize_capability_status(self, capability: str, agent_id: str) -> CapabilityStatus:
        """Determine final capability status from all attestations"""
        attestations = self._get_attestations(capability, agent_id)
        
        total_weight = 0.0
        weighted_score = 0.0
        
        for att in attestations:
            weight = self._get_attestor_weight(att.attestor_id, capability)
            total_weight += weight
            weighted_score += att.quality_score * weight
        
        if total_weight < self.MIN_ATTESTATION_WEIGHT:
            return CapabilityStatus.INSUFFICIENT_ATTESTATION
        
        final_score = weighted_score / total_weight
        
        if final_score >= 0.8:
            return CapabilityStatus.VERIFIED
        elif final_score >= 0.6:
            return CapabilityStatus.PROVISIONAL
        else:
            return CapabilityStatus.DISPUTED
```

### Layer 4: Anti-Sybil Mechanisms

**Problem**: Without barriers to entry, an adversary can create thousands of fake agents to overwhelm the mesh consensus or reputation system.

**Solution**: Multi-layered Sybil resistance using computational cost, stake requirements, and social verification.

#### 4.1 Proof-of-Work Agent Registration

New agents must solve a computational puzzle to join:

```python
class AgentRegistrationPoW:
    """Proof-of-Work for agent registration"""
    
    def generate_registration_challenge(self, public_key: str) -> RegistrationChallenge:
        """Generate PoW challenge for new agent"""
        difficulty = self._compute_adaptive_difficulty()
        
        return RegistrationChallenge(
            public_key=public_key,
            difficulty=difficulty,
            challenge_data={
                "target_prefix": "0" * difficulty,  # hash must start with N zeros
                "mesh_state_hash": self._get_current_mesh_hash(),
                "timestamp_window": (
                    int(time.time()) - 300,     # Valid for 5 minutes
                    int(time.time()) + 300
                ),
                "nonce_space": "full"  # Agent finds nonce to satisfy target
            }
        )
    
    def verify_registration_proof(self, challenge: RegistrationChallenge, proof: RegistrationProof) -> bool:
        """Verify agent solved PoW correctly"""
        # 1. Reconstruct challenge hash
        challenge_data = canonical_json({
            "public_key": challenge.public_key,
            "mesh_state_hash": challenge.challenge_data["mesh_state_hash"],
            "timestamp": proof.timestamp,
            "nonce": proof.nonce
        })
        
        # 2. Verify hash meets difficulty target
        result_hash = hashlib.sha256(challenge_data.encode()).hexdigest()
        required_prefix = "0" * challenge.difficulty
        
        if not result_hash.startswith(required_prefix):
            return False
        
        # 3. Verify timestamp is within window  
        ts = proof.timestamp
        window = challenge.challenge_data["timestamp_window"]
        if not (window[0] <= ts <= window[1]):
            return False
            
        return True
    
    def _compute_adaptive_difficulty(self) -> int:
        """Adjust PoW difficulty based on recent registration rate"""
        recent_registrations = self._count_recent_registrations(hours=24)
        baseline_difficulty = 4  # 4 leading zeros baseline
        
        if recent_registrations > 100:
            # High registration rate - increase difficulty
            return baseline_difficulty + 2
        elif recent_registrations < 10:
            # Low registration rate - decrease difficulty  
            return max(2, baseline_difficulty - 1)
        else:
            return baseline_difficulty
```

#### 4.2 Progressive Stake Requirements

Agents must stake increasing amounts to gain reputation and voting power:

```python
class ProgressiveStaking:
    """Stake requirements that scale with desired influence"""
    
    STAKE_TIERS = {
        "observer": 0,          # Can view mesh, limited interactions
        "participant": 10,       # Can claim capabilities, requires attestation
        "attester": 50,         # Can attest others' capabilities  
        "consensus": 200,       # Can participate in consensus voting
        "hub_operator": 1000    # Can operate federation hub
    }
    
    def get_required_stake(self, desired_tier: str) -> float:
        """Minimum stake required for participation tier"""
        return self.STAKE_TIERS.get(desired_tier, 0)
    
    def verify_stake_commitment(self, agent_id: str, tier: str) -> bool:
        """Verify agent has staked required amount"""
        required = self.get_required_stake(tier)
        committed = self._get_committed_stake(agent_id)
        
        return committed >= required
    
    def slash_stake(self, agent_id: str, reason: str, amount: float):
        """Slash stake for Byzantine behavior"""
        current_stake = self._get_committed_stake(agent_id)
        slashed_amount = min(amount, current_stake)
        
        self._record_slash({
            "agent_id": agent_id,
            "reason": reason,
            "amount_slashed": slashed_amount,
            "remaining_stake": current_stake - slashed_amount,
            "timestamp": int(time.time())
        })
        
        # Reduce agent's tier if stake falls below requirement
        self._demote_if_insufficient_stake(agent_id)
```

#### 4.3 Social Verification Network

Existing trusted agents vouch for new agents they have verified out-of-band:

```python
class SocialVerification:
    """Out-of-band social verification for Sybil resistance"""
    
    def create_social_voucher(self, voucher_id: str, new_agent_id: str, verification_method: str) -> SocialVoucher:
        """Trusted agent vouches for new agent"""
        return SocialVoucher(
            voucher_id=voucher_id,
            new_agent_id=new_agent_id,
            verification_method=verification_method,  # "video_call", "pgp_key", "physical_meeting"
            verification_evidence="",  # Optional evidence hash
            confidence_level=0.9,     # Voucher's confidence in identity
            stake_backing=0.0,        # Optional: stake to back voucher
            timestamp=int(time.time()),
            signature=""              # Voucher's signature
        )
    
    def compute_social_score(self, agent_id: str) -> float:
        """Compute social verification score from voucher network"""
        vouchers = self._get_vouchers_for_agent(agent_id)
        
        if not vouchers:
            return 0.0
        
        total_weight = 0.0
        weighted_confidence = 0.0
        
        for voucher in vouchers:
            # Weight by voucher's own reputation
            voucher_weight = self._get_agent_reputation(voucher.voucher_id)
            
            # Apply confidence level
            confidence = voucher.confidence_level
            
            # Time decay for old vouchers
            age_days = (time.time() - voucher.timestamp) / 86400
            time_decay = max(0.1, 1.0 - (age_days / 365))  # Decay over 1 year
            
            final_weight = voucher_weight * confidence * time_decay
            total_weight += final_weight
            weighted_confidence += final_weight
        
        # Normalize to [0, 1]
        return min(1.0, weighted_confidence / len(vouchers))
    
    def detect_voucher_rings(self) -> List[SybilRing]:
        """Detect groups of agents vouching for each other (Sybil rings)"""
        graph = self._build_voucher_graph()
        rings = []
        
        # Find strongly connected components where all agents vouch for each other
        sccs = self._find_strongly_connected_components(graph)
        
        for scc in sccs:
            if len(scc) >= 3:  # Potential Sybil ring
                ring_score = self._analyze_ring_legitimacy(scc)
                if ring_score < 0.3:  # Low legitimacy
                    rings.append(SybilRing(
                        members=scc,
                        legitimacy_score=ring_score,
                        detected_at=int(time.time())
                    ))
        
        return rings
```

#### 4.4 Reputation-Based Participation Weights

Agents with higher reputation have more influence in attestation and consensus:

```python
class ReputationWeighting:
    """Reputation-based participation weighting"""
    
    def compute_agent_reputation(self, agent_id: str) -> float:
        """Comprehensive reputation score [0, 1]"""
        
        # 1. Historical attestation accuracy (40% weight)
        attestation_score = self._compute_attestation_accuracy(agent_id)
        
        # 2. Social verification score (25% weight)  
        social_score = self._social_verifier.compute_social_score(agent_id)
        
        # 3. Stake commitment (20% weight)
        stake_score = min(1.0, self._get_committed_stake(agent_id) / 1000)
        
        # 4. Age and activity (10% weight)
        age_score = self._compute_age_and_activity_score(agent_id)
        
        # 5. Consensus participation (5% weight)
        consensus_score = self._compute_consensus_score(agent_id)
        
        reputation = (
            0.40 * attestation_score +
            0.25 * social_score +  
            0.20 * stake_score +
            0.10 * age_score +
            0.05 * consensus_score
        )
        
        # Apply penalty for any slashing history
        slashing_penalty = self._compute_slashing_penalty(agent_id)
        
        return max(0.0, reputation - slashing_penalty)
    
    def get_voting_weight(self, agent_id: str, vote_type: str) -> float:
        """Get agent's voting weight for different types of decisions"""
        base_reputation = self.compute_agent_reputation(agent_id)
        
        # Different vote types have different weight calculations
        if vote_type == "capability_attestation":
            # Capability attestation weighted by domain expertise
            domain_bonus = self._get_domain_expertise_bonus(agent_id)
            return min(1.0, base_reputation + 0.2 * domain_bonus)
        
        elif vote_type == "consensus_vote":
            # Consensus voting weighted by stake and history
            stake_factor = min(1.0, self._get_committed_stake(agent_id) / 500)
            consensus_history = self._get_consensus_history_bonus(agent_id)
            return base_reputation * (0.7 + 0.3 * stake_factor + consensus_history)
        
        else:
            return base_reputation
```

### Layer 5: Mesh Partitioning

**Problem**: Single trust domain prevents different security requirements. Corporate agents need private capabilities; research agents need open collaboration; high-security agents need isolated enclaves.

**Solution**: Hierarchical trust zones with controlled bridging and graduated trust propagation.

#### 5.1 Trust Zone Architecture

```python
class TrustZone:
    """Isolated trust domain with specific security policies"""
    
    def __init__(self, zone_id: str, security_level: SecurityLevel):
        self.zone_id = zone_id
        self.security_level = security_level
        self.admission_policy = self._create_admission_policy(security_level)
        self.propagation_rules = self._create_propagation_rules(security_level)
        self.member_agents: Set[str] = set()
        self.bridge_agents: Set[str] = set()
        
    def _create_admission_policy(self, level: SecurityLevel) -> AdmissionPolicy:
        """Define who can join this trust zone"""
        if level == SecurityLevel.PUBLIC:
            return AdmissionPolicy(
                min_reputation=0.0,
                min_stake=0,
                attestation_required=False,
                social_vouchers_required=0
            )
        elif level == SecurityLevel.VERIFIED:
            return AdmissionPolicy(
                min_reputation=0.6,
                min_stake=50,
                attestation_required=True,
                social_vouchers_required=1
            )
        elif level == SecurityLevel.PRIVATE:
            return AdmissionPolicy(
                min_reputation=0.8,
                min_stake=200,
                attestation_required=True,
                social_vouchers_required=2,
                invitation_required=True
            )
        elif level == SecurityLevel.CLASSIFIED:
            return AdmissionPolicy(
                min_reputation=0.95,
                min_stake=1000,
                attestation_required=True,
                social_vouchers_required=3,
                invitation_required=True,
                background_check_required=True
            )

TRUST_ZONES = {
    "public": TrustZone("public", SecurityLevel.PUBLIC),
    "research": TrustZone("research", SecurityLevel.VERIFIED), 
    "enterprise": TrustZone("enterprise", SecurityLevel.PRIVATE),
    "government": TrustZone("government", SecurityLevel.CLASSIFIED)
}
```

#### 5.2 Zone Admission Control

```python
class ZoneAdmissionController:
    """Control agent admission to trust zones"""
    
    async def request_zone_admission(self, agent_id: str, zone_id: str, credentials: dict) -> AdmissionResult:
        """Agent requests to join trust zone"""
        zone = TRUST_ZONES.get(zone_id)
        if not zone:
            return AdmissionResult.ZONE_NOT_FOUND
        
        policy = zone.admission_policy
        
        # 1. Check reputation requirement
        agent_reputation = self._get_agent_reputation(agent_id)
        if agent_reputation < policy.min_reputation:
            return AdmissionResult.INSUFFICIENT_REPUTATION
        
        # 2. Check stake requirement  
        agent_stake = self._get_committed_stake(agent_id)
        if agent_stake < policy.min_stake:
            return AdmissionResult.INSUFFICIENT_STAKE
        
        # 3. Check attestation requirement
        if policy.attestation_required:
            attestations = self._get_verified_attestations(agent_id)
            if len(attestations) == 0:
                return AdmissionResult.NO_ATTESTATIONS
        
        # 4. Check social voucher requirement
        social_vouchers = self._get_valid_social_vouchers(agent_id)
        if len(social_vouchers) < policy.social_vouchers_required:
            return AdmissionResult.INSUFFICIENT_VOUCHERS
        
        # 5. Check invitation requirement (for private zones)
        if policy.invitation_required:
            invitation = credentials.get("invitation")
            if not self._verify_zone_invitation(invitation, zone_id, agent_id):
                return AdmissionResult.NO_INVITATION
        
        # 6. Background check (for classified zones)
        if policy.background_check_required:
            bg_check = credentials.get("background_check") 
            if not self._verify_background_check(bg_check, agent_id):
                return AdmissionResult.BACKGROUND_CHECK_FAILED
        
        # All requirements met
        zone.member_agents.add(agent_id)
        self._log_zone_admission(agent_id, zone_id)
        return AdmissionResult.APPROVED
```

#### 5.3 Cross-Zone Trust Propagation

Information flows between zones through designated bridge agents:

```python
class TrustBridge:
    """Bridge agent that can relay information between trust zones"""
    
    def __init__(self, agent_id: str, source_zone: str, target_zone: str):
        self.agent_id = agent_id
        self.source_zone = source_zone
        self.target_zone = target_zone
        self.trust_attenuation = self._compute_attenuation(source_zone, target_zone)
        
    def _compute_attenuation(self, source: str, target: str) -> float:
        """How much to attenuate trust when bridging between zones"""
        source_level = TRUST_ZONES[source].security_level
        target_level = TRUST_ZONES[target].security_level
        
        # Trust flows more freely from high to low security zones
        if source_level.value >= target_level.value:
            return 0.9  # Minimal attenuation
        else:
            # Trust flows less freely from low to high security zones
            level_diff = target_level.value - source_level.value
            return max(0.3, 0.9 - 0.2 * level_diff)  # More attenuation
    
    def relay_attestation(self, attestation: PeerAttestation) -> PeerAttestation:
        """Relay attestation across zones with trust attenuation"""
        return PeerAttestation(
            challenge_hash=attestation.challenge_hash,
            attestor_id=self.agent_id,  # Bridge becomes the attestor
            quality_score=attestation.quality_score * self.trust_attenuation,
            confidence=attestation.confidence * self.trust_attenuation,
            timestamp=int(time.time()),
            signature=""  # Bridge signs with its own key
        )
    
    def relay_capability_claim(self, claim: dict) -> dict:
        """Relay capability claim across zones"""
        return {
            **claim,
            "bridged_from": self.source_zone,
            "bridge_agent": self.agent_id,
            "trust_attenuation": self.trust_attenuation,
            "original_zone_confidence": claim.get("confidence", 1.0),
            "bridged_confidence": claim.get("confidence", 1.0) * self.trust_attenuation
        }
```

#### 5.4 Zone-Specific Consensus

Each zone runs its own consensus with zone-specific rules:

```python
class ZoneConsensus:
    """Consensus mechanism that operates within a trust zone"""
    
    def __init__(self, zone: TrustZone):
        self.zone = zone
        self.consensus_threshold = self._compute_threshold(zone.security_level)
        
    def _compute_threshold(self, level: SecurityLevel) -> float:
        """Higher security zones require higher consensus thresholds"""
        if level == SecurityLevel.PUBLIC:
            return 0.51  # Simple majority
        elif level == SecurityLevel.VERIFIED:
            return 0.67  # 2/3 majority
        elif level == SecurityLevel.PRIVATE:
            return 0.75  # 3/4 majority  
        elif level == SecurityLevel.CLASSIFIED:
            return 0.90  # Near unanimity
    
    async def propose_zone_change(self, proposal: ZoneProposal) -> ConsensusResult:
        """Propose change that affects this zone"""
        
        # Only zone members can vote
        eligible_voters = [
            agent_id for agent_id in self.zone.member_agents
            if self._is_agent_active(agent_id)
        ]
        
        votes = {}
        for voter_id in eligible_voters:
            vote_weight = self._get_zone_voting_weight(voter_id)
            vote = await self._request_vote(voter_id, proposal)
            votes[voter_id] = (vote, vote_weight)
        
        # Calculate weighted consensus
        total_weight = sum(weight for _, weight in votes.values())
        accept_weight = sum(
            weight for vote, weight in votes.values() 
            if vote == Vote.ACCEPT
        )
        
        consensus_ratio = accept_weight / total_weight
        
        if consensus_ratio >= self.consensus_threshold:
            return ConsensusResult.ACCEPTED
        else:
            return ConsensusResult.REJECTED
    
    def _get_zone_voting_weight(self, agent_id: str) -> float:
        """Voting weight for agent within this zone"""
        base_reputation = self._get_agent_reputation(agent_id)
        
        # Zone-specific bonuses
        zone_tenure = self._get_zone_tenure(agent_id, self.zone.zone_id)
        zone_contributions = self._get_zone_contributions(agent_id, self.zone.zone_id)
        
        return base_reputation * (1.0 + 0.1 * zone_tenure + 0.1 * zone_contributions)
```

## Threat Model

### Primary Threats

1. **Sybil Attack**: Adversary creates many fake identities to overwhelm consensus
   - *Mitigation*: PoW registration + progressive staking + social verification

2. **Capability Fraud**: Agent claims capabilities it doesn't have
   - *Mitigation*: Multi-peer attestation + challenge-response proofs

3. **Eclipse Attack**: Adversary isolates target agents from honest network
   - *Mitigation*: Gossip-based peer discovery + reputation-weighted routing

4. **Consensus Manipulation**: Adversary corrupts mesh state through Byzantine behavior
   - *Mitigation*: PBFT consensus + stake slashing + weighted voting

5. **Trust Zone Breach**: Agent gains unauthorized access to higher security zones  
   - *Mitigation*: Graduated admission requirements + background checks + bridge monitoring

6. **Reputation Manipulation**: Adversary artificially inflates reputation scores
   - *Mitigation*: Time-weighted grading + referral chain analysis + Sybil detection

7. **Mesh Partitioning**: Network splits prevent global consensus
   - *Mitigation*: Fork resolution protocol + hub reputation weighting + automated healing

### Attack Scenarios

**Scenario 1: Industrial Espionage**
- Corp A infiltrates Corp B's private trust zone to steal proprietary capabilities
- *Defense*: Multi-factor admission (stake + attestation + social vouchers + invitation)

**Scenario 2: False Expertise Attack**  
- Agent claims critical capability (e.g., "nuclear-safety") without actual expertise
- *Defense*: Domain-expert attestation with high-stakes challenges and peer review

**Scenario 3: Consensus Poisoning**
- Adversary creates 100 fake agents to manipulate capability attestation votes
- *Defense*: PoW registration cost + progressive stake requirements + reputation weighting

**Scenario 4: Trust Bridge Compromise**
- Adversary compromises bridge agent to inject false information between zones
- *Defense*: Multi-bridge verification + bridge agent monitoring + trust attenuation limits

## Migration Path from Tailscale

### Phase 1: Identity Layer (Months 1-2)

**Objective**: Add cryptographic identity while maintaining backward compatibility

```python
# Add identity support to existing Agent class
class Agent:
    def __init__(self, name: str, keypath: str = None, legacy_mode: bool = True):
        # Legacy mode supports name-only agents during transition
        if legacy_mode and not keypath:
            self._identity = None
            self._legacy_name = name
        else:
            self._identity = self._load_or_generate_identity(name, keypath)
```

**Tasks**:
1. Implement Ed25519 identity generation and storage
2. Update federation protocol to support both name and cryptographic identity
3. Add identity verification to capability announcements  
4. Create migration tooling: `manifold-agent-upgrade --generate-identity`

**Success Criteria**:
- New agents automatically get cryptographic identity
- Existing agents can upgrade without data loss
- Federation handles mixed identity types gracefully

### Phase 2: Attestation System (Months 3-4)

**Objective**: Implement capability attestation while maintaining trust ledger compatibility

```python
# Extend existing trust system with attestation
class TrustLedger:
    def __init__(self):
        # Existing fields remain
        self._records: dict[str, dict[str, _AgentRecord]] = {}
        
        # Add attestation tracking
        self._attestation_engine = AttestationEngine()
        self._capability_challenges = {}
```

**Tasks**:
1. Build challenge generation framework with domain-specific generators
2. Implement peer attestation protocol and verification
3. Integrate attestation results with existing `TrustLedger.rank()` method
4. Create attestation UI for human-readable capability proofs

**Success Criteria**:
- Capability claims optionally backed by attestations
- Existing stake-based selection works alongside attestation-based selection
- Domain experts can create and verify challenges for their capabilities

### Phase 3: Consensus Layer (Months 5-7)

**Objective**: Replace "last writer wins" with proper Byzantine consensus

```python
# Add consensus to existing MeshSync
class MeshSync:
    def __init__(self, hub: str, intervalMs: number):
        # Existing fields remain
        self._hub = hub
        self._intervalMs = intervalMs
        
        # Add consensus engine
        self._consensus_engine = ConsensusEngine(hub)
```

**Tasks**:
1. Implement state transition validation and voting
2. Add fork detection and resolution algorithms
3. Integrate consensus with existing `capability_index` updates
4. Build consensus monitoring and debugging tools

**Success Criteria**:
- Hub conflicts resolved through weighted voting instead of arbitrary winner
- Mesh state remains consistent during network partitions
- Byzantine behavior detection and mitigation works

### Phase 4: Anti-Sybil (Months 8-9)

**Objective**: Add registration costs and reputation weighting

**Tasks**:
1. Implement PoW challenge generation with adaptive difficulty
2. Build progressive staking system with tier upgrades
3. Create social verification framework with voucher management
4. Add reputation-based voting weights to consensus system

**Success Criteria**:
- Creating fake agents requires computational cost
- Voting power correlates with demonstrated reputation
- Social verification prevents automated Sybil creation

### Phase 5: Trust Zones (Months 10-12)

**Objective**: Enable private enclaves and enterprise deployment

**Tasks**:
1. Implement zone admission control with graduated requirements
2. Build trust bridge system for cross-zone information flow  
3. Create zone-specific consensus with security-level thresholds
4. Add enterprise management tools for private zone administration

**Success Criteria**:
- Enterprises can deploy private Manifold instances
- Research groups can collaborate in verified-only zones
- Public mesh continues to operate with lower security requirements

## Implementation Priorities

### Critical Path Dependencies

1. **Identity → Everything**: All other layers require cryptographic identity
2. **Attestation → Consensus**: Consensus needs capability verification to work
3. **Consensus → Anti-Sybil**: Voting weights require consensus mechanisms
4. **Anti-Sybil → Trust Zones**: Zone admission needs reputation system

### Resource Allocation

**Total Estimated Effort**: 12-18 months with 2-3 engineers

**Phase 1 (Identity)**: 1 engineer, 2 months - High ROI, low risk
**Phase 2 (Attestation)**: 2 engineers, 2 months - Medium ROI, medium risk  
**Phase 3 (Consensus)**: 2 engineers, 3 months - High ROI, high risk
**Phase 4 (Anti-Sybil)**: 1 engineer, 2 months - Medium ROI, low risk
**Phase 5 (Trust Zones)**: 2 engineers, 3 months - High ROI for enterprise, medium risk

## Comparison with Existing Systems

### Bitcoin
- **Similarity**: PoW for Sybil resistance, longest chain consensus
- **Difference**: Capability-based consensus instead of transaction-based

### libp2p/IPFS  
- **Similarity**: Content-addressed networking, DHT routing
- **Difference**: Trust-weighted routing instead of proximity-based

### Matrix Federation
- **Similarity**: Federated servers with cryptographic identity  
- **Difference**: Peer attestation instead of server authority

### Ethereum 2.0
- **Similarity**: Proof-of-stake with slashing for Byzantine behavior
- **Difference**: Capability consensus instead of smart contract execution

## Conclusion

This five-layer security architecture enables Manifold to evolve from a Tailscale-dependent federation to a fully trustless, globally-scalable cognitive mesh. The migration path provides a practical roadmap for implementation while maintaining backward compatibility.

The architecture directly addresses the core challenges of a decentralized AI agent network:

- **Identity**: Cryptographic identity prevents impersonation and enables accountability
- **Attestation**: Peer verification ensures agents actually possess claimed capabilities  
- **Consensus**: Byzantine fault tolerance maintains mesh integrity under adversarial conditions
- **Anti-Sybil**: Multi-layered resistance prevents adversaries from overwhelming the network
- **Partitioning**: Trust zones enable different security requirements within one global mesh

By implementing these layers incrementally, Manifold can become the "Bitcoin for AI agents" - a truly decentralized cognitive mesh that scales to planetary deployment while maintaining security and trustworthiness.

---

*This document is a living specification. As implementation proceeds, the security model will be refined based on real-world deployment experience and emerging threats.*