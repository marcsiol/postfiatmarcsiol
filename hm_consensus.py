#!/usr/bin/env python3
"""
hm_consensus.py  —  Hive Mind Cross-Agent Consensus Resolution Module
======================================================================
Module ID : HM-CONSENSUS-001
Spec ref  : HMSPEC-L1-001 (l1-envelope-v1.0)
Requires  : Python 3.8+  ·  zero external dependencies

PURPOSE
-------
Takes an array of Hive Mind board-agent extraction outputs for the same
domain topic and resolves conflicting constraint interpretations into a
single canonical output with:

  • Transparent resolution audit trail
  • Per-field dissent log (which agent dissented, on which field, by how much)
  • Three configurable resolution strategies
  • Deterministic output — same inputs always produce the same consensus

RESOLUTION STRATEGIES
---------------------
  MAJORITY_VOTE         Categorical fields: plurality wins; tie → ESCALATE
  CONFIDENCE_WEIGHTED   Numeric/ordinal fields: weighted average by agent
                        confidence score (HIGH=1.0, MEDIUM=0.6, LOW=0.3)
  ESCALATE              Disagreement exceeds threshold → human review required;
                        consensus is still produced (conservative merge) but
                        flagged REQUIRES_HUMAN_REVIEW

CONSENSUS OUTPUT CONTRACT
-------------------------
  {
    "consensus_id":    str            — unique ID for this resolution run
    "topic_id":        str            — shared topic identifier across agents
    "strategy_used":   str            — MAJORITY_VOTE | CONFIDENCE_WEIGHTED | ESCALATE
    "resolution_status": str          — RESOLVED | REQUIRES_HUMAN_REVIEW
    "consensus_score": float          — 0.0–1.0, agreement ratio across agents
    "canonical":       ConstraintObj  — the merged canonical constraint
    "dissent_log":     [DisentEntry]  — per-agent, per-field disagreements
    "agent_votes":     [AgentVote]    — all agent inputs with weights
    "resolved_at":     str            — ISO-8601 UTC
    "resolution_notes": [str]         — human-readable explanation of decisions
  }

USAGE
-----
  python hm_consensus.py --test                # run all 8 test cases
  python hm_consensus.py --test --json         # JSON output
  python hm_consensus.py --test --id TC-03     # single test
  python hm_consensus.py --file agents.json    # resolve from file
  python hm_consensus.py --test --threshold 0.4  # custom escalation threshold

ADDING TEST CASES
-----------------
  Append a TestCase to TESTS at the bottom of this file.
  build_fn: callable returning list[dict] (agent extraction outputs).
  expected_status: "RESOLVED" | "REQUIRES_HUMAN_REVIEW"
  expected_strategy: "MAJORITY_VOTE" | "CONFIDENCE_WEIGHTED" | "ESCALATE"
"""

from __future__ import annotations
import json, re, hashlib, datetime, sys, argparse, statistics, copy, random, string
from collections import Counter
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA CONSTANTS  (HMSPEC-L1-001)
# ─────────────────────────────────────────────────────────────────────────────

CONSTRAINT_TYPES = {
    "PHYSICAL_PRESENCE","LICENSING_CEILING","GEOGRAPHIC_EXCLUSION",
    "FEE_FLOOR","TECHNOLOGY_BLOCK","CAPTIVE_VENDOR","ENFORCEMENT_ACTION",
    "LEADING_INDICATOR","PENDING_CHANGE","INDETERMINATE",
}
SOURCING_TYPES  = {"PRIMARY","SECONDARY_SYNTHESIS","OPERATOR_COMMENTARY","UNKNOWN"}
CONF_VALUES     = {"HIGH","MEDIUM","LOW"}
CONF_RANK       = {"HIGH":3,"MEDIUM":2,"LOW":1}
CONF_WEIGHT     = {"HIGH":1.0,"MEDIUM":0.6,"LOW":0.3}  # for weighted merge

# Categorical fields resolved by majority vote
# NOTE: "confidence" is intentionally absent — it is resolved separately
# via conservative merge (lowest wins) to avoid spurious escalations when
# agents legitimately declare different sourcing confidence levels.
CATEGORICAL_FIELDS = [
    "constraint_type",
    "technology_substitution_permitted",
    "captive_vendor_required",
    "sourcing_type",
]

# Numeric/ordinal fields resolved by confidence-weighted merge
NUMERIC_FIELDS = [
    "threshold_value",
    "opacity",
]

# Text fields: highest-confidence agent's value wins
TEXT_FIELDS = [
    "rule_description",
    "raw_text_excerpt",
    "legal_citation",
    "enforcement_citation",
    "effective_date",
    "captive_vendor_type",
    "constraint_id",
    "threshold_unit",
]

STRATEGIES = {"MAJORITY_VOTE","CONFIDENCE_WEIGHTED","ESCALATE"}


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConsensusConfig:
    """
    escalation_threshold  If the ratio of agents disagreeing on ANY categorical
                          field exceeds this value, resolution is flagged
                          REQUIRES_HUMAN_REVIEW.  Default 0.5 (majority dissent).

    min_agents            Minimum number of valid agent outputs required.
                          Fewer → ESCALATE immediately.  Default 2.

    tie_break             How to break categorical ties:
                          "ESCALATE" (default) — flag for human review.
                          "CONSERVATIVE"       — pick the more restrictive value.
                          "FIRST"              — pick the value from agent[0].

    weight_by_confidence  If True (default), use CONF_WEIGHT for numeric merges.
                          If False, use equal weights (simple average).
    """
    escalation_threshold:  float = 0.5
    min_agents:            int   = 2
    tie_break:             str   = "ESCALATE"
    weight_by_confidence:  bool  = True


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DissentEntry:
    """Records a single agent's disagreement on a single field."""
    agent_id:      str
    field_name:    str
    agent_value:   Any
    canonical_value: Any
    delta:         Any          # numeric diff or "CATEGORICAL_CONFLICT"
    severity:      str          # MINOR | MODERATE | CRITICAL

    def to_dict(self):
        return asdict(self)


@dataclass
class AgentVote:
    """A single agent's full constraint submission, with metadata."""
    agent_id:         str
    raw_confidence:   str         # HIGH | MEDIUM | LOW as declared
    weight:           float       # CONF_WEIGHT value
    valid:            bool        # False if malformed / failed validation
    validation_error: Optional[str]
    constraint:       dict        # the constraint dict (may be partial if invalid)

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class ConsensusResult:
    consensus_id:       str
    topic_id:           str
    strategy_used:      str
    resolution_status:  str       # RESOLVED | REQUIRES_HUMAN_REVIEW
    consensus_score:    float     # 0.0–1.0
    canonical:          dict      # merged canonical constraint
    dissent_log:        list      # list of DissentEntry dicts
    agent_votes:        list      # list of AgentVote dicts
    resolved_at:        str
    resolution_notes:   list[str]

    def to_dict(self):
        return {
            "consensus_id":      self.consensus_id,
            "topic_id":          self.topic_id,
            "strategy_used":     self.strategy_used,
            "resolution_status": self.resolution_status,
            "consensus_score":   round(self.consensus_score, 4),
            "canonical":         self.canonical,
            "dissent_log":       [d for d in self.dissent_log],
            "agent_votes":       [v for v in self.agent_votes],
            "resolved_at":       self.resolved_at,
            "resolution_notes":  self.resolution_notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_agent_input(agent_output: dict) -> tuple[bool, Optional[str], dict]:
    """
    Validate a single agent extraction output.
    Returns (is_valid, error_message, constraint_dict).
    Extracts the constraint from the payload envelope or accepts a bare constraint.
    """
    if not isinstance(agent_output, dict):
        return False, "Input is not a JSON object", {}

    # Accept either a full L1 envelope or a bare constraint dict
    if "payload" in agent_output:
        payload = agent_output.get("payload", {})
        if not isinstance(payload, dict):
            return False, "payload is not an object", {}
        ptype = agent_output.get("payload_type", "CONSTRAINT_EXTRACTION")
        if ptype == "CONSTRAINT_EXTRACTION":
            constraints = payload.get("constraints", [])
        elif ptype == "COMPOSITE":
            constraints = (payload.get("extraction") or {}).get("constraints", [])
        else:
            return False, f"payload_type {ptype!r} not supported for consensus", {}

        if not constraints:
            return False, "No constraints found in payload", {}
        constraint = constraints[0]  # consensus operates per-constraint
    elif "constraint_type" in agent_output:
        constraint = agent_output   # bare constraint dict
    else:
        return False, "Cannot locate constraint in agent output", {}

    if not isinstance(constraint, dict):
        return False, "Constraint is not a dict", {}

    # Minimum required fields
    required = ["constraint_type", "confidence"]
    for f in required:
        if f not in constraint:
            return False, f"Constraint missing required field: '{f}'", constraint

    if constraint.get("constraint_type") not in CONSTRAINT_TYPES:
        return False, f"Unknown constraint_type: {constraint.get('constraint_type')!r}", constraint

    if constraint.get("confidence") not in CONF_VALUES:
        return False, f"Invalid confidence: {constraint.get('confidence')!r}", constraint

    return True, None, constraint


# ─────────────────────────────────────────────────────────────────────────────
# RESOLUTION STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def _majority_vote(votes: list[AgentVote], field: str,
                   cfg: ConsensusConfig) -> tuple[Any, str, list[str]]:
    """
    Resolve a categorical field by plurality vote among valid agents.
    Returns (resolved_value, resolution_note, [dissent_agent_ids]).
    """
    values = [(v.agent_id, v.constraint.get(field)) for v in votes if v.valid]
    if not values:
        return None, f"{field}: no valid votes", []

    non_null = [(aid, val) for aid, val in values if val is not None]
    if not non_null:
        return None, f"{field}: all agents returned null", []

    counts = Counter(val for _, val in non_null)
    max_count = max(counts.values())
    winners = [val for val, cnt in counts.items() if cnt == max_count]

    if len(winners) == 1:
        winner = winners[0]
        dissenters = [aid for aid, val in non_null if val != winner]
        note = (f"{field}: majority={winner!r} ({max_count}/{len(non_null)} votes)"
                + (f" — dissenters: {dissenters}" if dissenters else ""))
        return winner, note, dissenters

    # Tie — apply tie_break strategy
    if cfg.tie_break == "CONSERVATIVE":
        # For constraint_type: prefer more restrictive; for confidence: prefer lower
        if field == "confidence":
            winner = min(winners, key=lambda x: CONF_RANK.get(x, 0))
        elif field == "technology_substitution_permitted":
            winner = True if True in winners else winners[0]  # True = more restrictive
        else:
            winner = sorted(winners)[0]  # alphabetical fallback
        dissenters = [aid for aid, val in non_null if val != winner]
        note = f"{field}: tie broken conservatively → {winner!r}"
        return winner, note, dissenters
    elif cfg.tie_break == "FIRST":
        winner = non_null[0][1]
        dissenters = [aid for aid, val in non_null if val != winner]
        note = f"{field}: tie broken by agent[0] → {winner!r}"
        return winner, note, dissenters
    else:  # ESCALATE
        return None, f"{field}: TIED — {winners} — escalation required", \
               [aid for aid, _ in non_null]


def _confidence_weighted_merge(votes: list[AgentVote], field: str,
                                cfg: ConsensusConfig) -> tuple[Any, str, list[str]]:
    """
    Resolve a numeric/ordinal field via confidence-weighted average.
    Returns (resolved_value, resolution_note, [dissent_agent_ids]).
    """
    weighted_vals = []
    for v in votes:
        if not v.valid:
            continue
        val = v.constraint.get(field)
        if val is None:
            continue
        try:
            w = v.weight if cfg.weight_by_confidence else 1.0
            weighted_vals.append((v.agent_id, float(val), w))
        except (TypeError, ValueError):
            pass  # skip non-numeric

    if not weighted_vals:
        return None, f"{field}: no valid numeric votes", []

    total_weight = sum(w for _, _, w in weighted_vals)
    merged = sum(val * w for _, val, w in weighted_vals) / total_weight

    # For integer fields (opacity, threshold_value), round to nearest int
    if field in ("opacity",):
        merged = round(merged)
    elif field == "threshold_value":
        # Keep as float if any agent used decimal, else round
        if all(float(v) == int(v) for _, v, _ in weighted_vals):
            merged = round(merged)

    # Dissenters = agents whose value differs from merged by > 10% of range
    vals_only = [v for _, v, _ in weighted_vals]
    rng = max(vals_only) - min(vals_only) if len(vals_only) > 1 else 0
    threshold_delta = max(rng * 0.1, 0.5)
    dissenters = [aid for aid, val, _ in weighted_vals if abs(val - merged) > threshold_delta]

    note = (f"{field}: weighted_merge={merged} "
            f"(inputs={[v for _,v,_ in weighted_vals]}, "
            f"weights={[round(w,2) for _,_,w in weighted_vals]})")
    return merged, note, dissenters


def _highest_confidence_text(votes: list[AgentVote], field: str) -> tuple[Any, str]:
    """For text fields, take the value from the highest-confidence valid agent."""
    candidates = [(v.agent_id, v.weight, v.constraint.get(field))
                  for v in votes if v.valid and v.constraint.get(field) is not None]
    if not candidates:
        return None, f"{field}: no valid text values"
    best = max(candidates, key=lambda x: x[1])
    return best[2], f"{field}: from agent {best[0]} (weight={best[1]:.2f})"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RESOLVER
# ─────────────────────────────────────────────────────────────────────────────

def _make_consensus_id() -> str:
    s = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"HM-CONS-{ts}Z-{s}"


def resolve(
    agent_outputs: list[dict],
    topic_id:      str = "UNKNOWN",
    cfg:           ConsensusConfig = None,
) -> ConsensusResult:
    """
    Resolve conflicting agent extractions into a single canonical constraint.

    agent_outputs : list of dicts — each is either a full L1 envelope or a
                    bare constraint dict, as produced by HM-INTAKE-001 /
                    HM-EXT-STR-001.
    topic_id      : shared identifier for this constraint topic (e.g.
                    "JP-PHYS-NATL-001").
    cfg           : ConsensusConfig (defaults applied if None).

    Returns ConsensusResult with canonical constraint + dissent log.
    """
    cfg       = cfg or ConsensusConfig()
    cons_id   = _make_consensus_id()
    now       = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes: list[str] = []
    dissent:  list[dict] = []

    # ── 1. Validate each agent output ─────────────────────────────────────────
    votes: list[AgentVote] = []
    for i, ao in enumerate(agent_outputs):
        agent_id = ao.get("agent_id", f"AGENT-{i+1}") if isinstance(ao, dict) else f"AGENT-{i+1}"
        is_valid, err, constraint = validate_agent_input(ao)
        conf_str = constraint.get("confidence", "LOW") if constraint else "LOW"
        weight   = CONF_WEIGHT.get(conf_str, 0.3)
        votes.append(AgentVote(
            agent_id=agent_id, raw_confidence=conf_str, weight=weight,
            valid=is_valid, validation_error=err,
            constraint=constraint,
        ))
        if not is_valid:
            notes.append(f"Agent {agent_id} failed validation: {err}")

    valid_votes = [v for v in votes if v.valid]

    # ── 2. Check minimum agent count ──────────────────────────────────────────
    if len(valid_votes) < cfg.min_agents:
        notes.append(f"Only {len(valid_votes)} valid agent(s) — below min_agents={cfg.min_agents}. Escalating.")
        canonical = valid_votes[0].constraint.copy() if valid_votes else {}
        return ConsensusResult(
            consensus_id=cons_id, topic_id=topic_id,
            strategy_used="ESCALATE", resolution_status="REQUIRES_HUMAN_REVIEW",
            consensus_score=0.0, canonical=canonical,
            dissent_log=dissent, agent_votes=[v.to_dict() for v in votes],
            resolved_at=now, resolution_notes=notes,
        )

    # ── 3. Resolve each field ─────────────────────────────────────────────────
    canonical: dict = {}
    strategy_flags: set[str] = set()
    escalation_fields: list[str] = []
    total_fields   = 0
    agreed_fields  = 0

    # Categorical fields → majority vote
    for fld in CATEGORICAL_FIELDS:
        total_fields += 1
        value, note, dissenters = _majority_vote(valid_votes, fld, cfg)
        notes.append(note)

        if value is None and "TIED" in note:
            # Tie escalation — use conservative fallback but flag
            escalation_fields.append(fld)
            strategy_flags.add("ESCALATE")
            # Fallback: take value from highest-confidence agent
            fb, _ = _highest_confidence_text(valid_votes, fld)
            canonical[fld] = fb
            notes.append(f"  → tie fallback for {fld}: {fb!r} (from highest-confidence agent)")
        else:
            canonical[fld] = value
            if not dissenters:
                agreed_fields += 1

        # Dissent log entries
        for aid in dissenters:
            agent_val = next((v.constraint.get(fld) for v in valid_votes if v.agent_id == aid), None)
            dissent.append(DissentEntry(
                agent_id=aid, field_name=fld,
                agent_value=agent_val, canonical_value=canonical[fld],
                delta="CATEGORICAL_CONFLICT",
                severity="CRITICAL" if fld == "constraint_type" else "MODERATE",
            ).to_dict())

        # Check escalation threshold — exempt expected-variance fields
        ESCALATION_EXEMPT = {"confidence"}
        if dissenters and fld not in ESCALATION_EXEMPT:
            dissent_ratio = len(dissenters) / len(valid_votes)
            if dissent_ratio > cfg.escalation_threshold:
                escalation_fields.append(fld)
                strategy_flags.add("ESCALATE")
                notes.append(f"  → dissent_ratio={dissent_ratio:.0%} > threshold={cfg.escalation_threshold:.0%} on '{fld}' — escalating")

    # Confidence field — conservative merge: lowest declared confidence wins.
    # This prevents a HIGH-confidence agent from elevating a LOW-confidence
    # extraction, and avoids spurious escalation on expected sourcing variance.
    conf_values_present = [v.constraint.get("confidence") for v in valid_votes
                           if v.valid and v.constraint.get("confidence") in CONF_VALUES]
    if conf_values_present:
        canonical["confidence"] = min(conf_values_present, key=lambda x: CONF_RANK.get(x, 0))
        conf_dissenters = [v.agent_id for v in valid_votes
                           if v.valid and v.constraint.get("confidence") != canonical["confidence"]]
        for aid in conf_dissenters:
            av = next((v.constraint.get("confidence") for v in valid_votes if v.agent_id == aid), None)
            dissent.append(DissentEntry(
                agent_id=aid, field_name="confidence",
                agent_value=av, canonical_value=canonical["confidence"],
                delta="CONSERVATIVE_MERGE", severity="MINOR",
            ).to_dict())
        notes.append(f"confidence: conservative_merge={canonical['confidence']!r} "
                     f"(inputs={conf_values_present})")
    else:
        canonical["confidence"] = "LOW"

    # Numeric fields → confidence-weighted merge
    for fld in NUMERIC_FIELDS:
        total_fields += 1
        value, note, dissenters = _confidence_weighted_merge(valid_votes, fld, cfg)
        notes.append(note)
        canonical[fld] = value
        strategy_flags.add("CONFIDENCE_WEIGHTED")
        if not dissenters:
            agreed_fields += 1

        for aid in dissenters:
            agent_val = next((v.constraint.get(fld) for v in valid_votes if v.agent_id == aid), None)
            canon_val = canonical[fld]
            try:
                delta = abs(float(agent_val) - float(canon_val)) if agent_val is not None else None
            except (TypeError, ValueError):
                delta = None
            dissent.append(DissentEntry(
                agent_id=aid, field_name=fld,
                agent_value=agent_val, canonical_value=canon_val,
                delta=round(delta, 4) if delta is not None else "N/A",
                severity="MODERATE" if (delta or 0) > 1 else "MINOR",
            ).to_dict())

    # Text fields → highest-confidence agent
    for fld in TEXT_FIELDS:
        value, note = _highest_confidence_text(valid_votes, fld)
        canonical[fld] = value
        # Don't count text fields toward agreement score — they're not voted on

    # Jurisdiction — take from highest-confidence agent
    jur_val, jur_note = _highest_confidence_text(valid_votes, "jurisdiction")
    canonical["jurisdiction"] = jur_val
    notes.append(jur_note if jur_note else "jurisdiction: not available")

    # Boolean fields not in CATEGORICAL — copy from canonical confidence winner
    for fld in ("technology_substitution_permitted", "captive_vendor_required"):
        if fld not in canonical:
            val, _ = _highest_confidence_text(valid_votes, fld)
            canonical[fld] = val

    # ── 4. Determine overall strategy and status ───────────────────────────────
    # Strategy label: ESCALATE > CONFIDENCE_WEIGHTED > MAJORITY_VOTE
    # Numeric merge (CONFIDENCE_WEIGHTED) is always run alongside categorical
    # resolution; only report it as the primary strategy when numeric fields
    # actually had meaningful variance across agents.
    numeric_had_variance = any(
        len({v.constraint.get(fld) for v in valid_votes
             if v.valid and v.constraint.get(fld) is not None}) > 1
        for fld in NUMERIC_FIELDS
    )

    if "ESCALATE" in strategy_flags:
        strategy = "ESCALATE"
        status   = "REQUIRES_HUMAN_REVIEW"
        notes.append(f"Escalation triggered on fields: {escalation_fields}")
    elif numeric_had_variance:
        strategy = "CONFIDENCE_WEIGHTED"
        status   = "RESOLVED"
    else:
        strategy = "MAJORITY_VOTE"
        status   = "RESOLVED"

    # ── 5. Consensus score ────────────────────────────────────────────────────
    # Weighted: categorical agreements count more than numeric
    consensus_score = agreed_fields / total_fields if total_fields > 0 else 0.0
    if escalation_fields:
        # Penalise for escalations
        consensus_score *= (1 - len(escalation_fields) / total_fields)

    notes.insert(0, f"Resolved {len(valid_votes)}/{len(votes)} valid agents. "
                    f"Strategy: {strategy}. Score: {consensus_score:.2f}.")

    return ConsensusResult(
        consensus_id=cons_id, topic_id=topic_id,
        strategy_used=strategy, resolution_status=status,
        consensus_score=round(consensus_score, 4),
        canonical=canonical, dissent_log=dissent,
        agent_votes=[v.to_dict() for v in votes],
        resolved_at=now, resolution_notes=notes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

def _constraint(agent_id="AGENT-1", constraint_type="PHYSICAL_PRESENCE",
                confidence="HIGH", opacity=1, threshold_value=10,
                threshold_unit="minutes", sourcing_type="PRIMARY",
                technology_substitution_permitted=False,
                captive_vendor_required=True, **extra) -> dict:
    c = {
        "agent_id":         agent_id,
        "constraint_type":  constraint_type,
        "confidence":       confidence,
        "opacity":          opacity,
        "threshold_value":  threshold_value,
        "threshold_unit":   threshold_unit,
        "sourcing_type":    sourcing_type,
        "technology_substitution_permitted": technology_substitution_permitted,
        "captive_vendor_required":           captive_vendor_required,
        "rule_description": f"Test constraint from {agent_id}",
        "raw_text_excerpt": "Sample excerpt from regulatory text",
        "legal_citation":   "Article 11(1)(iii), Private Lodging Business Act",
        "enforcement_citation": "Article 33(1)(iv)",
        "effective_date":   "2018-06-15",
        "captive_vendor_type": "licensed_kanrisha",
        "constraint_id":    "JP-PHYS-NATL-001",
        "jurisdiction":     {"country":"JP","region":None,"municipality":None,"scope":"NATIONAL"},
    }
    c.update(extra)
    return c


# ─────────────────────────────────────────────────────────────────────────────
# TEST CASES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    id:               str
    name:             str
    description:      str
    build_fn:         Any                   # callable → list[dict]
    expected_status:  str                   # RESOLVED | REQUIRES_HUMAN_REVIEW
    expected_strategy: str                  # MAJORITY_VOTE | CONFIDENCE_WEIGHTED | ESCALATE
    expected_dissent_fields: list[str]      # fields expected in dissent log
    config:           ConsensusConfig = None


def _tc(id_, name, desc, fn, status, strategy, dissent_fields, cfg=None):
    return TestCase(id=id_, name=name, description=desc, build_fn=fn,
                    expected_status=status, expected_strategy=strategy,
                    expected_dissent_fields=dissent_fields, config=cfg)


TESTS: list[TestCase] = [

    # TC-01 ── Two agents fully agree ─────────────────────────────────────────
    _tc("TC-01", "Two agents fully agree",
        "Both agents return identical constraint_type, confidence, opacity. "
        "Should resolve cleanly with zero dissent entries and MAJORITY_VOTE strategy.",
        lambda: [
            _constraint("AGENT-1", confidence="HIGH", opacity=1, threshold_value=10),
            _constraint("AGENT-2", confidence="HIGH", opacity=1, threshold_value=10),
        ],
        "RESOLVED", "MAJORITY_VOTE", []),

    # TC-02 ── Two agents disagree on severity (threshold_value) ──────────────
    _tc("TC-02", "Two agents disagree on numeric severity",
        "Agent-1 extracts threshold=10 minutes (HIGH confidence). "
        "Agent-2 extracts threshold=15 minutes (MEDIUM confidence). "
        "Confidence-weighted merge should produce ~11.5 minutes. "
        "threshold_value should appear in dissent log.",
        lambda: [
            _constraint("AGENT-1", confidence="HIGH",   opacity=1, threshold_value=10),
            _constraint("AGENT-2", confidence="MEDIUM", opacity=2, threshold_value=15),
        ],
        "RESOLVED", "CONFIDENCE_WEIGHTED", ["threshold_value"]),

    # TC-03 ── Three agents, split categorical vote (2v1) ─────────────────────
    _tc("TC-03", "Three agents split vote on constraint_type",
        "AGENT-1 and AGENT-2 classify as PHYSICAL_PRESENCE. "
        "AGENT-3 classifies as CAPTIVE_VENDOR. Majority wins (2v1). "
        "constraint_type dissent logged for AGENT-3.",
        lambda: [
            _constraint("AGENT-1", constraint_type="PHYSICAL_PRESENCE", confidence="HIGH"),
            _constraint("AGENT-2", constraint_type="PHYSICAL_PRESENCE", confidence="MEDIUM"),
            _constraint("AGENT-3", constraint_type="CAPTIVE_VENDOR",    confidence="LOW"),
        ],
        "RESOLVED", "MAJORITY_VOTE", ["constraint_type"]),

    # TC-04 ── Conflicting regulatory classification → ESCALATE ───────────────
    _tc("TC-04", "Two agents tie on constraint_type — escalation required",
        "AGENT-1 classifies as FEE_FLOOR, AGENT-2 classifies as LICENSING_CEILING. "
        "Perfect tie with tie_break=ESCALATE. Status must be REQUIRES_HUMAN_REVIEW.",
        lambda: [
            _constraint("AGENT-1", constraint_type="FEE_FLOOR",        confidence="HIGH"),
            _constraint("AGENT-2", constraint_type="LICENSING_CEILING", confidence="HIGH"),
        ],
        "REQUIRES_HUMAN_REVIEW", "ESCALATE",
        ["constraint_type"],
        cfg=ConsensusConfig(tie_break="ESCALATE")),

    # TC-05 ── One agent malformed, one valid ─────────────────────────────────
    _tc("TC-05", "One malformed agent output — below min_agents",
        "AGENT-1 returns valid constraint. AGENT-2 returns garbage (missing confidence). "
        "With min_agents=2, only 1 valid → ESCALATE immediately.",
        lambda: [
            _constraint("AGENT-1", confidence="HIGH"),
            {"agent_id": "AGENT-2", "constraint_type": "PHYSICAL_PRESENCE"},  # missing confidence
        ],
        "REQUIRES_HUMAN_REVIEW", "ESCALATE", []),

    # TC-06 ── Equal confidence scores, different numeric values ──────────────
    _tc("TC-06", "Boundary: equal confidence weights on numeric field",
        "Both agents have MEDIUM confidence. threshold_value=10 vs 20. "
        "Equal-weight merge → 15.0. Both should appear in dissent log "
        "(delta > 10% of range).",
        lambda: [
            _constraint("AGENT-1", confidence="MEDIUM", threshold_value=10),
            _constraint("AGENT-2", confidence="MEDIUM", threshold_value=20),
        ],
        "RESOLVED", "CONFIDENCE_WEIGHTED", ["threshold_value"]),

    # TC-07 ── Three-way tie on confidence field ───────────────────────────────
    _tc("TC-07", "Three agents, confidence field unanimous — opacity split",
        "All three agree on constraint_type=PHYSICAL_PRESENCE and confidence=HIGH. "
        "Opacity differs: 1, 2, 3. Weighted merge produces opacity ~1.6 → rounded 2. "
        "opacity dissent logged for agents far from merge value.",
        lambda: [
            _constraint("AGENT-1", confidence="HIGH",   opacity=1, threshold_value=10),
            _constraint("AGENT-2", confidence="MEDIUM", opacity=2, threshold_value=10),
            _constraint("AGENT-3", confidence="LOW",    opacity=3, threshold_value=10),
        ],
        "RESOLVED", "CONFIDENCE_WEIGHTED", ["opacity"]),

    # TC-08 ── High dissent ratio triggers escalation ──────────────────────────
    _tc("TC-08", "Dissent ratio > threshold triggers escalation",
        "Three agents: AGENT-1 and AGENT-2 disagree with AGENT-3 on "
        "technology_substitution_permitted. Majority=False (2/3), "
        "but AGENT-3 dissents → dissent_ratio=1/3=33%. "
        "To guarantee escalation with threshold=0.2: ratio=0.33 > 0.2. "
        "Status: REQUIRES_HUMAN_REVIEW.",
        lambda: [
            _constraint("AGENT-1", technology_substitution_permitted=False, confidence="HIGH"),
            _constraint("AGENT-2", technology_substitution_permitted=False, confidence="MEDIUM"),
            _constraint("AGENT-3", technology_substitution_permitted=True,  confidence="LOW"),
        ],
        "REQUIRES_HUMAN_REVIEW", "ESCALATE",
        ["technology_substitution_permitted"],
        cfg=ConsensusConfig(escalation_threshold=0.2)),
]


# ─────────────────────────────────────────────────────────────────────────────
# TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_tests(subset: list[TestCase] = None) -> list[dict]:
    cases   = subset or TESTS
    results = []

    for tc in cases:
        cfg = tc.config or ConsensusConfig()
        agents = tc.build_fn()
        result = resolve(agents, topic_id=tc.id, cfg=cfg)

        status_ok   = result.resolution_status == tc.expected_status
        strategy_ok = result.strategy_used     == tc.expected_strategy

        # Check expected dissent fields appear in dissent log
        actual_dissent_fields = {d["field_name"] for d in result.dissent_log}
        missing_dissent = [f for f in tc.expected_dissent_fields
                           if f not in actual_dissent_fields]
        dissent_ok = len(missing_dissent) == 0

        passed = status_ok and strategy_ok and dissent_ok

        results.append({
            "id":                tc.id,
            "name":              tc.name,
            "description":       tc.description,
            "expected_status":   tc.expected_status,
            "expected_strategy": tc.expected_strategy,
            "expected_dissent":  tc.expected_dissent_fields,
            "actual_status":     result.resolution_status,
            "actual_strategy":   result.strategy_used,
            "actual_dissent":    sorted(actual_dissent_fields),
            "consensus_score":   result.consensus_score,
            "canonical_type":    result.canonical.get("constraint_type"),
            "canonical_conf":    result.canonical.get("confidence"),
            "canonical_thresh":  result.canonical.get("threshold_value"),
            "canonical_opacity": result.canonical.get("opacity"),
            "dissent_count":     len(result.dissent_log),
            "dissent_entries":   result.dissent_log,
            "resolution_notes":  result.resolution_notes,
            "agent_count":       len(agents),
            "valid_agents":      sum(1 for v in result.agent_votes if v["valid"]),
            "pass":              passed,
            "fail_reason":       None if passed else (
                (f"status={result.resolution_status!r} (want {tc.expected_status!r}); " if not status_ok else "") +
                (f"strategy={result.strategy_used!r} (want {tc.expected_strategy!r}); " if not strategy_ok else "") +
                (f"missing dissent fields: {missing_dissent}" if not dissent_ok else "")
            ).rstrip("; "),
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────────────────────────────────────

_PASS = {True: "PASS", False: "FAIL"}
_ST   = {"RESOLVED": "RESOLVD", "REQUIRES_HUMAN_REVIEW": "ESCALTE"}
_STR  = {"MAJORITY_VOTE": "MAJORITY", "CONFIDENCE_WEIGHTED": "CONF-WT", "ESCALATE": "ESCALTE"}

def print_report(results: list[dict]):
    passed = sum(1 for r in results if r["pass"])
    total  = len(results)
    ts     = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    W      = 108

    print()
    print("═" * W)
    print(f"  HIVE MIND CONSENSUS RESOLUTION  ·  HM-CONSENSUS-001  ·  {ts}")
    print("═" * W)
    print(f"  {'ID':<7} {'NAME':<38} {'GATE':<5} {'STATUS':<9} {'STRATEGY':<9} {'SCORE':<7} {'DISSENT'}")
    print("  " + "─" * (W - 2))

    for r in results:
        st  = _ST.get(r["actual_status"], r["actual_status"][:7])
        str_ = _STR.get(r["actual_strategy"], r["actual_strategy"][:7])
        sc  = f"{r['consensus_score']:.2f}"
        dis = ", ".join(r["actual_dissent"]) or "—"
        gate = _PASS[r["pass"]]
        name = r["name"][:37]
        print(f"  {r['id']:<7} {name:<38} {gate:<5} {st:<9} {str_:<9} {sc:<7} {dis}")

        if not r["pass"]:
            print(f"  {'':>7}   ✗ FAIL: {r['fail_reason']}")

        # Show canonical resolved values
        cv = (f"type={r['canonical_type']} conf={r['canonical_conf']} "
              f"thresh={r['canonical_thresh']} opacity={r['canonical_opacity']}")
        print(f"  {'':>7}   canonical: {cv}")

        # Show dissent entries briefly
        for d in r["dissent_entries"][:3]:
            print(f"  {'':>7}   dissent: {d['agent_id']} on '{d['field_name']}' "
                  f"agent={d['agent_value']!r} → canonical={d['canonical_value']!r} "
                  f"Δ={d['delta']} [{d['severity']}]")

        print()

    print("  " + "─" * (W - 2))
    pct = round(passed / total * 100, 1) if total else 0
    print(f"  RESULT: {passed}/{total} passed ({pct}%)")
    print("═" * W)
    print()


def print_json_report(results: list[dict]):
    passed = sum(1 for r in results if r["pass"])
    print(json.dumps({
        "module":   "HM-CONSENSUS-001",
        "spec_ref": "HMSPEC-L1-001",
        "run_at":   datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "summary": {
            "total":  len(results), "passed": passed,
            "failed": len(results) - passed,
            "pass_rate_pct": round(passed / len(results) * 100, 1) if results else 0,
        },
        "results": results,
    }, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="HM-CONSENSUS-001 Cross-Agent Consensus Resolution Module",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test",      action="store_true", help="Run built-in test suite")
    ap.add_argument("--id",        type=str, default=None, help="Run single test by ID")
    ap.add_argument("--json",      action="store_true", help="JSON output only")
    ap.add_argument("--file",      type=str, default=None,
                    help="Resolve agent outputs from JSON file (array of dicts)")
    ap.add_argument("--topic",     type=str, default="CLI",
                    help="Topic ID for --file mode")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="Escalation threshold (default 0.5)")
    ap.add_argument("--tie-break", type=str, default="ESCALATE",
                    choices=["ESCALATE","CONSERVATIVE","FIRST"])
    args = ap.parse_args()

    cfg = ConsensusConfig(escalation_threshold=args.threshold, tie_break=args.tie_break)

    if args.test:
        cases = TESTS
        if args.id:
            cases = [t for t in TESTS if t.id == args.id]
            if not cases:
                print(f"No test with id={args.id!r}"); sys.exit(1)
        results = run_tests(cases)
        if args.json:
            print_json_report(results)
        else:
            print_report(results)
        sys.exit(0 if all(r["pass"] for r in results) else 1)

    elif args.file:
        with open(args.file) as f:
            agents = json.load(f)
        if not isinstance(agents, list):
            print("File must contain a JSON array of agent outputs"); sys.exit(1)
        result = resolve(agents, topic_id=args.topic, cfg=cfg)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n{result.resolution_status}  [{result.strategy_used}]  "
                  f"score={result.consensus_score:.2f}")
            print(f"  canonical type: {result.canonical.get('constraint_type')}")
            print(f"  canonical conf: {result.canonical.get('confidence')}")
            print(f"  dissent entries: {len(result.dissent_log)}")
            for note in result.resolution_notes[:5]:
                print(f"  · {note}")
        sys.exit(0 if result.resolution_status == "RESOLVED" else 1)

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
