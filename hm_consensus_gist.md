# Hive Mind Cross-Agent Consensus Resolution Module

**Module ID:** `HM-CONSENSUS-001`  
**Spec ref:** `HMSPEC-L1-001` (`l1-envelope-v1.0`)  
**Published:** March 2026  
**Python:** 3.8+  ·  **Dependencies:** zero (pure stdlib)  
**Tests:** 8 cases  ·  **Last run:** 8/8 PASS (100%)

---

## Overview

Takes an array of Hive Mind board-agent extraction outputs for the same domain topic and resolves conflicting constraint interpretations into a single canonical output with a transparent resolution audit trail.

### Resolution Strategies

| Strategy | Trigger | Fields |
|---|---|---|
| `MAJORITY_VOTE` | Categorical fields with clear plurality | `constraint_type`, `technology_substitution_permitted`, `captive_vendor_required`, `sourcing_type` |
| `CONFIDENCE_WEIGHTED` | Numeric/ordinal fields with agent variance | `threshold_value`, `opacity` |
| `ESCALATE` | Tie on categorical field OR dissent ratio > threshold | Any field where agents cannot reach plurality |

**Confidence** is resolved separately via conservative merge (lowest declared confidence wins), preventing a HIGH-confidence agent from elevating a LOW-confidence extraction and avoiding spurious escalation on expected sourcing variance.

---

## Quick Start

```bash
# Run all 8 built-in tests
python hm_consensus.py --test

# JSON output
python hm_consensus.py --test --json

# Single test
python hm_consensus.py --test --id TC-04

# Resolve from file (array of agent extraction dicts)
python hm_consensus.py --file agents.json --topic JP-PHYS-NATL-001

# Custom escalation threshold
python hm_consensus.py --test --threshold 0.3 --tie-break CONSERVATIVE
```

---

## Input / Output Contract

### Input

An array of agent extraction dicts. Each element is either:
- A **full L1 envelope** (per `HMSPEC-L1-001`) — the module extracts `payload.constraints[0]`
- A **bare constraint dict** — used directly (agent must include `agent_id` field)

```json
[
  {
    "agent_id": "AGENT-1",
    "constraint_type": "PHYSICAL_PRESENCE",
    "confidence": "HIGH",
    "opacity": 1,
    "threshold_value": 10,
    "threshold_unit": "minutes",
    ...
  },
  {
    "agent_id": "AGENT-2",
    "constraint_type": "PHYSICAL_PRESENCE",
    "confidence": "MEDIUM",
    "opacity": 2,
    "threshold_value": 15,
    ...
  }
]
```

### Output — `ConsensusResult`

```json
{
  "consensus_id":       "HM-CONS-20260319T133158Z-AB7XK2",
  "topic_id":           "JP-PHYS-NATL-001",
  "strategy_used":      "CONFIDENCE_WEIGHTED",
  "resolution_status":  "RESOLVED",
  "consensus_score":    0.67,
  "canonical": {
    "constraint_type":  "PHYSICAL_PRESENCE",
    "confidence":       "MEDIUM",
    "threshold_value":  12,
    "opacity":          1,
    ...
  },
  "dissent_log": [
    {
      "agent_id":        "AGENT-1",
      "field_name":      "threshold_value",
      "agent_value":     10,
      "canonical_value": 12,
      "delta":           2.0,
      "severity":        "MODERATE"
    }
  ],
  "agent_votes": [...],
  "resolved_at":       "2026-03-19T13:31:58Z",
  "resolution_notes":  [...]
}
```

### `ConsensusConfig` Parameters

```python
@dataclass
class ConsensusConfig:
    escalation_threshold:  float = 0.5    # dissent ratio above which → ESCALATE
    min_agents:            int   = 2      # fewer valid agents → ESCALATE immediately
    tie_break:             str   = "ESCALATE"  # "ESCALATE" | "CONSERVATIVE" | "FIRST"
    weight_by_confidence:  bool  = True   # use CONF_WEIGHT for numeric merges
```

---

## Dissent Log Entry Fields

| Field | Type | Description |
|---|---|---|
| `agent_id` | str | Which agent dissented |
| `field_name` | str | Which field disagreed |
| `agent_value` | Any | What the agent submitted |
| `canonical_value` | Any | What the consensus chose |
| `delta` | Any | Numeric diff, or `"CATEGORICAL_CONFLICT"` / `"CONSERVATIVE_MERGE"` |
| `severity` | str | `CRITICAL` (constraint_type) · `MODERATE` · `MINOR` |

---

## L1 Pipeline Integration

The `ConsensusResult.canonical` dict conforms to `constraint-schema-v1.0` and can be wrapped in an L1 envelope for downstream ingestion via `HM-SCREEN-001` and the L1 routing gate:

```python
from hm_consensus import resolve, ConsensusConfig
from hm_intake_screener import screen, ScreenerConfig

# Step 1: resolve agent disagreements
result = resolve(agent_outputs, topic_id="JP-PHYS-NATL-001")

if result.resolution_status == "RESOLVED":
    # Step 2: wrap canonical in envelope and screen for L1
    envelope = build_l1_envelope(result.canonical)  # your envelope wrapper
    decision = screen(envelope, cfg=ScreenerConfig())
    # Step 3: ingest if ACCEPT
    if decision.decision == "ACCEPT":
        l1_ingest(envelope)
else:
    # Route to human review queue with full dissent log
    review_queue.push(result.to_dict())
```

---

## Test Case Summary

| ID | Name | Agents | Expected Status | Expected Strategy | Key Dissent Field |
|---|---|---|---|---|---|
| TC-01 | Two agents fully agree | 2 | RESOLVED | MAJORITY_VOTE | — |
| TC-02 | Two agents disagree on numeric severity | 2 | RESOLVED | CONFIDENCE_WEIGHTED | threshold_value |
| TC-03 | Three agents, split categorical vote (2v1) | 3 | RESOLVED | MAJORITY_VOTE | constraint_type |
| TC-04 | Two agents tie on constraint_type | 2 | REQUIRES_HUMAN_REVIEW | ESCALATE | constraint_type |
| TC-05 | One malformed agent, below min_agents | 2 | REQUIRES_HUMAN_REVIEW | ESCALATE | — |
| TC-06 | Equal confidence weights, different numerics | 2 | RESOLVED | CONFIDENCE_WEIGHTED | threshold_value |
| TC-07 | Three agents, unanimous type, split opacity | 3 | RESOLVED | CONFIDENCE_WEIGHTED | opacity |
| TC-08 | Dissent ratio > configured threshold | 3 | REQUIRES_HUMAN_REVIEW | ESCALATE | technology_substitution_permitted |

---

## Sample Run Log

```
════════════════════════════════════════════════════════════════════════════════════════════════════════════
  HIVE MIND CONSENSUS RESOLUTION  ·  HM-CONSENSUS-001  ·  2026-03-19T13:31:58Z
════════════════════════════════════════════════════════════════════════════════════════════════════════════
  ID      NAME                                   GATE  STATUS    STRATEGY  SCORE   DISSENT
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────
  TC-01   Two agents fully agree                 PASS  RESOLVD   MAJORITY  1.00    —
            canonical: type=PHYSICAL_PRESENCE conf=HIGH thresh=10 opacity=1

  TC-02   Two agents disagree on numeric severi  PASS  RESOLVD   CONF-WT   0.67    confidence, opacity, threshold_value
            canonical: type=PHYSICAL_PRESENCE conf=MEDIUM thresh=12 opacity=1
            dissent: AGENT-1 on 'confidence' agent='HIGH' → canonical='MEDIUM' Δ=CONSERVATIVE_MERGE [MINOR]
            dissent: AGENT-1 on 'threshold_value' agent=10 → canonical=12 Δ=2.0 [MODERATE]
            dissent: AGENT-2 on 'threshold_value' agent=15 → canonical=12 Δ=3.0 [MODERATE]

  TC-03   Three agents split vote on constraint  PASS  RESOLVD   MAJORITY  0.83    confidence, constraint_type
            canonical: type=PHYSICAL_PRESENCE conf=LOW thresh=10 opacity=1
            dissent: AGENT-3 on 'constraint_type' agent='CAPTIVE_VENDOR' → canonical='PHYSICAL_PRESENCE' Δ=CATEGORICAL_CONFLICT [CRITICAL]
            dissent: AGENT-1 on 'confidence' agent='HIGH' → canonical='LOW' Δ=CONSERVATIVE_MERGE [MINOR]
            dissent: AGENT-2 on 'confidence' agent='MEDIUM' → canonical='LOW' Δ=CONSERVATIVE_MERGE [MINOR]

  TC-04   Two agents tie on constraint_type — e  PASS  ESCALTE   ESCALTE   0.56    constraint_type
            canonical: type=FEE_FLOOR conf=HIGH thresh=10 opacity=1
            dissent: AGENT-1 on 'constraint_type' agent='FEE_FLOOR' → canonical='FEE_FLOOR' Δ=CATEGORICAL_CONFLICT [CRITICAL]
            dissent: AGENT-2 on 'constraint_type' agent='LICENSING_CEILING' → canonical='FEE_FLOOR' Δ=CATEGORICAL_CONFLICT [CRITICAL]

  TC-05   One malformed agent output — below mi  PASS  ESCALTE   ESCALTE   0.00    —
            canonical: type=PHYSICAL_PRESENCE conf=HIGH thresh=10 opacity=1

  TC-06   Boundary: equal confidence weights on  PASS  RESOLVD   CONF-WT   0.83    threshold_value
            canonical: type=PHYSICAL_PRESENCE conf=MEDIUM thresh=15 opacity=1
            dissent: AGENT-1 on 'threshold_value' agent=10 → canonical=15 Δ=5.0 [MODERATE]
            dissent: AGENT-2 on 'threshold_value' agent=20 → canonical=15 Δ=5.0 [MODERATE]

  TC-07   Three agents, confidence field unanim  PASS  RESOLVD   CONF-WT   0.83    confidence, opacity
            canonical: type=PHYSICAL_PRESENCE conf=LOW thresh=10 opacity=2
            dissent: AGENT-1 on 'confidence' agent='HIGH' → canonical='LOW' Δ=CONSERVATIVE_MERGE [MINOR]
            dissent: AGENT-2 on 'confidence' agent='MEDIUM' → canonical='LOW' Δ=CONSERVATIVE_MERGE [MINOR]
            dissent: AGENT-1 on 'opacity' agent=1 → canonical=2 Δ=1.0 [MINOR]

  TC-08   Dissent ratio > threshold triggers es  PASS  ESCALTE   ESCALTE   0.69    confidence, technology_substitution_permitted
            canonical: type=PHYSICAL_PRESENCE conf=LOW thresh=10 opacity=1
            dissent: AGENT-3 on 'technology_substitution_permitted' agent=True → canonical=False Δ=CATEGORICAL_CONFLICT [MODERATE]
            dissent: AGENT-1 on 'confidence' agent='HIGH' → canonical='LOW' Δ=CONSERVATIVE_MERGE [MINOR]
            dissent: AGENT-2 on 'confidence' agent='MEDIUM' → canonical='LOW' Δ=CONSERVATIVE_MERGE [MINOR]

  ──────────────────────────────────────────────────────────────────────────────────────────────────────────
  RESULT: 8/8 passed (100.0%)
════════════════════════════════════════════════════════════════════════════════════════════════════════════
```

---

*HM-CONSENSUS-001 · HMSPEC-L1-001 · l1-envelope-v1.0 · March 2026*  
*Pure stdlib Python 3.8+ · Zero external dependencies · Exit 0 = all pass*
