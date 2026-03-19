#!/usr/bin/env python3
"""
hm_telemetry.py  —  Hive Mind Consensus Resolution Telemetry Module
====================================================================
Module ID : HM-TELEMETRY-001
Spec ref  : HMSPEC-L1-001 / HM-CONSENSUS-001
Requires  : Python 3.8+  ·  hm_consensus.py in same directory

PURPOSE
-------
Wraps hm_consensus.resolve() to emit structured telemetry records for
every resolution call.  Records are written to:
  • An in-memory store (always)
  • A SQLite database (optional, enabled via TelemetryConfig)
  • stdout JSON stream (optional)

TELEMETRY SCHEMA
----------------
Each TelemetryEvent record contains:

  event_id          int     — auto-incrementing sequence ID
  timestamp         str     — ISO-8601 UTC
  topic_id          str     — shared topic identifier
  scenario          str     — workload scenario label (if provided)
  agent_count       int     — total agents submitted
  valid_agents      int     — agents that passed validation
  strategy          str     — MAJORITY_VOTE | CONFIDENCE_WEIGHTED | ESCALATE
  status            str     — RESOLVED | REQUIRES_HUMAN_REVIEW
  consensus_score   float   — 0.0–1.0
  dissent_count     int     — number of dissent log entries
  escalated         bool    — True if REQUIRES_HUMAN_REVIEW
  latency_ms        float   — wall-clock resolution time in milliseconds
  canonical_type    str     — resolved constraint_type
  canonical_conf    str     — resolved confidence
  dissent_fields    list    — field names that had dissent entries
  escalation_reason str     — first escalation note if escalated, else null

USAGE
-----
  from hm_telemetry import TelemetryStore, TelemetryConfig, instrumented_resolve

  store = TelemetryStore(TelemetryConfig(sqlite_path="telemetry.db"))

  # Drop-in replacement for hm_consensus.resolve()
  result, event = instrumented_resolve(agents, topic_id="JP-001", store=store)

  # Query the store
  summary = store.summary()
  events  = store.events()

  # Run synthetic workload
  from hm_telemetry import run_synthetic_workload
  store = run_synthetic_workload(n=60, seed=42)

  # Export dashboard data
  data = store.dashboard_data()
  import json; print(json.dumps(data))

CLI
---
  python hm_telemetry.py --run 60          # generate 60 events, print summary
  python hm_telemetry.py --run 60 --json   # JSON summary output
  python hm_telemetry.py --run 60 --db telemetry.db  # persist to SQLite
"""

from __future__ import annotations
import time, json, datetime, random, sqlite3, statistics
from dataclasses import dataclass, asdict, field
from typing import Optional, Any
import sys, os, argparse

# Import consensus module (must be in same directory or on PYTHONPATH)
try:
    from hm_consensus import resolve as _resolve, ConsensusConfig, _constraint
except ImportError as e:
    print(f"ERROR: hm_consensus.py not found — {e}", file=sys.stderr)
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TelemetryConfig:
    """
    sqlite_path     Path to SQLite DB file. None = in-memory only.
    stream_stdout   If True, print each event as JSON to stdout.
    max_memory      Max events kept in memory (oldest evicted).  0 = unlimited.
    """
    sqlite_path:   Optional[str] = None
    stream_stdout: bool          = False
    max_memory:    int           = 10_000


# ─────────────────────────────────────────────────────────────────────────────
# TELEMETRY EVENT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TelemetryEvent:
    event_id:          int
    timestamp:         str
    topic_id:          str
    scenario:          str
    agent_count:       int
    valid_agents:      int
    strategy:          str
    status:            str
    consensus_score:   float
    dissent_count:     int
    escalated:         bool
    latency_ms:        float
    canonical_type:    Optional[str]
    canonical_conf:    Optional[str]
    dissent_fields:    list
    escalation_reason: Optional[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dissent_fields"] = json.dumps(self.dissent_fields)
        return d

    def to_json_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# TELEMETRY STORE
# ─────────────────────────────────────────────────────────────────────────────

class TelemetryStore:
    """
    In-memory + optional SQLite store for consensus resolution telemetry events.
    Thread-safety: single-threaded use assumed (no locking).
    """

    _CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS telemetry_events (
        event_id          INTEGER PRIMARY KEY,
        timestamp         TEXT,
        topic_id          TEXT,
        scenario          TEXT,
        agent_count       INTEGER,
        valid_agents      INTEGER,
        strategy          TEXT,
        status            TEXT,
        consensus_score   REAL,
        dissent_count     INTEGER,
        escalated         INTEGER,
        latency_ms        REAL,
        canonical_type    TEXT,
        canonical_conf    TEXT,
        dissent_fields    TEXT,
        escalation_reason TEXT
    )"""

    def __init__(self, cfg: TelemetryConfig = None):
        self._cfg    = cfg or TelemetryConfig()
        self._events: list[TelemetryEvent] = []
        self._seq    = 0
        self._db: Optional[sqlite3.Connection] = None

        if self._cfg.sqlite_path:
            self._db = sqlite3.connect(self._cfg.sqlite_path)
            self._db.execute(self._CREATE_TABLE)
            self._db.commit()

    # ── write ─────────────────────────────────────────────────────────────────

    def record(self, event: TelemetryEvent):
        """Persist a TelemetryEvent to memory and optionally to SQLite."""
        self._events.append(event)
        if self._cfg.max_memory and len(self._events) > self._cfg.max_memory:
            self._events.pop(0)

        if self._db:
            d = event.to_dict()
            self._db.execute(
                "INSERT INTO telemetry_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                list(d.values()),
            )
            self._db.commit()

        if self._cfg.stream_stdout:
            print(json.dumps(event.to_json_dict()))

    def next_id(self) -> int:
        self._seq += 1
        return self._seq

    # ── read ──────────────────────────────────────────────────────────────────

    def events(self, limit: int = None) -> list[TelemetryEvent]:
        evs = self._events
        return evs[-limit:] if limit else list(evs)

    def summary(self) -> dict:
        evs = self._events
        if not evs:
            return {"total": 0}

        latencies = [e.latency_ms for e in evs]
        latencies_sorted = sorted(latencies)
        scores    = [e.consensus_score for e in evs]
        dissents  = [e.dissent_count for e in evs]

        from collections import Counter
        strategies = Counter(e.strategy for e in evs)
        statuses   = Counter(e.status for e in evs)
        conf_dist  = Counter(e.canonical_conf for e in evs if e.canonical_conf)
        type_dist  = Counter(e.canonical_type for e in evs if e.canonical_type)
        scenario_dist = Counter(e.scenario for e in evs)

        def p(lst, pct):
            return sorted(lst)[int(len(lst) * pct / 100)]

        return {
            "total":         len(evs),
            "escalated":     sum(e.escalated for e in evs),
            "mean_latency":  round(statistics.mean(latencies), 2),
            "p50_latency":   round(p(latencies, 50), 2),
            "p95_latency":   round(p(latencies, 95), 2),
            "p99_latency":   round(p(latencies, 99), 2),
            "mean_score":    round(statistics.mean(scores), 4),
            "stdev_score":   round(statistics.stdev(scores) if len(scores)>1 else 0, 4),
            "mean_dissent":  round(statistics.mean(dissents), 3),
            "strategies":    dict(strategies),
            "statuses":      dict(statuses),
            "confidence_dist": dict(conf_dist),
            "type_dist":     dict(type_dist),
            "scenario_dist": dict(scenario_dist),
        }

    def dashboard_data(self) -> dict:
        """Export all data needed by the HTML dashboard."""
        evs  = self._events
        summ = self.summary()

        # 6-event rolling windows
        windows = []
        for i in range(0, len(evs), 6):
            chunk = evs[i:i+6]
            windows.append({
                "window":          i // 6,
                "escalation_rate": sum(e.escalated for e in chunk) / len(chunk),
                "mean_score":      statistics.mean(e.consensus_score for e in chunk),
                "mean_latency":    statistics.mean(e.latency_ms for e in chunk),
                "mean_dissent":    statistics.mean(e.dissent_count for e in chunk),
            })

        return {
            **summ,
            "windows":            windows,
            "latency_series":     [round(e.latency_ms, 2) for e in evs],
            "score_series":       [e.consensus_score for e in evs],
            "dissent_series":     [e.dissent_count for e in evs],
            "escalation_series":  [int(e.escalated) for e in evs],
            "timestamps":         [e.timestamp[:16].replace("T", " ") for e in evs],
        }

    def close(self):
        if self._db:
            self._db.close()


# ─────────────────────────────────────────────────────────────────────────────
# INSTRUMENTED RESOLVE
# ─────────────────────────────────────────────────────────────────────────────

def instrumented_resolve(
    agent_outputs: list[dict],
    topic_id:      str              = "UNKNOWN",
    scenario:      str              = "unknown",
    cfg:           ConsensusConfig  = None,
    store:         TelemetryStore   = None,
    latency_jitter_ms: float        = 0.0,  # add simulated network jitter
) -> tuple:
    """
    Drop-in replacement for hm_consensus.resolve() that also emits a
    TelemetryEvent to the provided store.

    Returns: (ConsensusResult, TelemetryEvent)
    """
    store = store or TelemetryStore()
    cfg   = cfg   or ConsensusConfig()

    t0     = time.perf_counter()
    result = _resolve(agent_outputs, topic_id=topic_id, cfg=cfg)
    ms     = (time.perf_counter() - t0) * 1000 + latency_jitter_ms

    escalation_reason = None
    if result.resolution_status == "REQUIRES_HUMAN_REVIEW":
        for note in result.resolution_notes:
            if "escalat" in note.lower():
                escalation_reason = note[:120]
                break

    event = TelemetryEvent(
        event_id          = store.next_id(),
        timestamp         = datetime.datetime.now(datetime.timezone.utc).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
        topic_id          = topic_id,
        scenario          = scenario,
        agent_count       = len(agent_outputs),
        valid_agents      = sum(1 for v in result.agent_votes if v["valid"]),
        strategy          = result.strategy_used,
        status            = result.resolution_status,
        consensus_score   = result.consensus_score,
        dissent_count     = len(result.dissent_log),
        escalated         = result.resolution_status == "REQUIRES_HUMAN_REVIEW",
        latency_ms        = round(ms, 2),
        canonical_type    = result.canonical.get("constraint_type"),
        canonical_conf    = result.canonical.get("confidence"),
        dissent_fields    = list({d["field_name"] for d in result.dissent_log}),
        escalation_reason = escalation_reason,
    )
    store.record(event)
    return result, event


# ─────────────────────────────────────────────────────────────────────────────
# SYNTHETIC WORKLOAD GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

CONSTRAINT_TYPES = [
    "PHYSICAL_PRESENCE", "FEE_FLOOR", "LICENSING_CEILING",
    "GEOGRAPHIC_EXCLUSION", "CAPTIVE_VENDOR", "TECHNOLOGY_BLOCK",
]

SCENARIO_WEIGHTS = {
    "full_agree":             0.12,
    "severity_conflict":      0.22,
    "classification_conflict":0.18,
    "three_way_split":        0.15,
    "equal_weights":          0.12,
    "malformed_agent":        0.08,
    "escalation":             0.13,
}


def _make_agents(scenario: str, rng: random.Random) -> list[dict]:
    ct = rng.choice(CONSTRAINT_TYPES)

    if scenario == "full_agree":
        tv = rng.choice([5, 10, 15, 20])
        return [_constraint(f"A{i}", confidence=rng.choice(["HIGH","HIGH","MEDIUM"]),
                            constraint_type=ct, threshold_value=tv)
                for i in range(1, 3)]

    elif scenario == "severity_conflict":
        return [
            _constraint("A1", confidence="HIGH",   constraint_type=ct,
                        threshold_value=rng.randint(5, 10)),
            _constraint("A2", confidence="MEDIUM", constraint_type=ct,
                        threshold_value=rng.randint(15, 25)),
        ]

    elif scenario == "classification_conflict":
        ct2 = rng.choice([c for c in CONSTRAINT_TYPES if c != ct])
        return [
            _constraint("A1", confidence="HIGH",   constraint_type=ct),
            _constraint("A2", confidence="MEDIUM", constraint_type=ct2),
        ]

    elif scenario == "three_way_split":
        ct2 = rng.choice([c for c in CONSTRAINT_TYPES if c != ct])
        return [
            _constraint("A1", confidence="HIGH",   constraint_type=ct),
            _constraint("A2", confidence="HIGH",   constraint_type=ct),
            _constraint("A3", confidence="LOW",    constraint_type=ct2),
        ]

    elif scenario == "equal_weights":
        return [
            _constraint("A1", confidence="MEDIUM", constraint_type=ct,
                        threshold_value=rng.randint(5, 12)),
            _constraint("A2", confidence="MEDIUM", constraint_type=ct,
                        threshold_value=rng.randint(18, 30)),
        ]

    elif scenario == "malformed_agent":
        return [
            _constraint("A1", confidence="HIGH"),
            {"agent_id": "A2", "constraint_type": "PHYSICAL_PRESENCE"},  # missing confidence
        ]

    else:  # escalation
        ct2 = rng.choice([c for c in CONSTRAINT_TYPES if c != ct])
        return [
            _constraint("A1", confidence="HIGH",   constraint_type=ct,
                        technology_substitution_permitted=False),
            _constraint("A2", confidence="HIGH",   constraint_type=ct2,
                        technology_substitution_permitted=True),
        ]


def run_synthetic_workload(
    n:        int              = 60,
    seed:     int              = 42,
    cfg:      ConsensusConfig  = None,
    store:    TelemetryStore   = None,
    verbose:  bool             = False,
) -> TelemetryStore:
    """
    Generate n resolution events with varied disagreement types and
    record telemetry.  Returns the populated TelemetryStore.
    """
    rng   = random.Random(seed)
    store = store or TelemetryStore()
    cfg   = cfg   or ConsensusConfig(tie_break="ESCALATE")

    scenarios = list(SCENARIO_WEIGHTS.keys())
    weights   = list(SCENARIO_WEIGHTS.values())

    for i in range(n):
        scenario = rng.choices(scenarios, weights=weights)[0]
        agents   = _make_agents(scenario, rng)
        jitter   = rng.uniform(8, 180)  # simulate network + LLM variance

        _, event = instrumented_resolve(
            agents,
            topic_id          = f"TOPIC-{i:03d}",
            scenario          = scenario,
            cfg               = cfg,
            store             = store,
            latency_jitter_ms = jitter,
        )

        if verbose:
            esc = "⚑" if event.escalated else "✓"
            print(f"  {esc} {event.topic_id:<12} {event.strategy:<22} "
                  f"score={event.consensus_score:.2f}  "
                  f"dissent={event.dissent_count}  {event.latency_ms:.1f}ms")

    return store


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="HM-TELEMETRY-001 Consensus Telemetry Module")
    ap.add_argument("--run",     type=int,  default=60,    help="Number of synthetic events")
    ap.add_argument("--seed",    type=int,  default=42,    help="Random seed")
    ap.add_argument("--json",    action="store_true",      help="JSON summary output")
    ap.add_argument("--verbose", action="store_true",      help="Print each event")
    ap.add_argument("--db",      type=str,  default=None,  help="SQLite output path")
    args = ap.parse_args()

    cfg   = TelemetryConfig(sqlite_path=args.db)
    store = TelemetryStore(cfg)

    print(f"Running {args.run} synthetic resolution events (seed={args.seed})…")
    run_synthetic_workload(n=args.run, seed=args.seed, store=store, verbose=args.verbose)

    summ = store.summary()

    if args.json:
        print(json.dumps(summ, indent=2))
    else:
        print()
        print(f"  Total events    : {summ['total']}")
        print(f"  Escalation count: {summ['escalated']}  ({summ['escalated']/summ['total']*100:.0f}%)")
        print(f"  Mean latency    : {summ['mean_latency']} ms  (p95={summ['p95_latency']} ms)")
        print(f"  Mean score      : {summ['mean_score']}")
        print(f"  Mean dissent    : {summ['mean_dissent']}")
        print(f"  Strategies      : {summ['strategies']}")
        print(f"  Confidence dist : {summ['confidence_dist']}")
        print()

    store.close()


if __name__ == "__main__":
    main()
