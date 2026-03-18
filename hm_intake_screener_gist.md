# Hive Mind Automated Intake Screening Module

**Module ID:** `HM-SCREEN-001`  
**Spec ref:** `HMSPEC-L1-001` (`l1-envelope-v1.0`)  
**Published:** March 2026  
**Python:** 3.8+  ·  **Dependencies:** zero (pure stdlib)  
**Tests:** 15 cases  ·  **Last run:** 15/15 PASS (100%)

---

## Overview

Screens raw constraint payload JSON through five sequential gates before
any payload enters the L1 pipeline.  Each gate either passes the payload
to the next or terminates with a structured `IntakeDecision`:

```
Gate 1  PARSE       JSON well-formedness · UTF-8 · 512 KB size cap
Gate 2  SCHEMA      Required fields · types · enum membership
Gate 3  DEDUP       Exact hash match · near-duplicate similarity (SequenceMatcher)
Gate 4  ADVERSARIAL Injection pattern scan across all text fields
Gate 5  CONFIDENCE  Opacity threshold · INDETERMINATE guard · confidence filter
```

**Output decisions:**

| Decision | Meaning |
|---|---|
| `ACCEPT` | Cleared for L1 pipeline ingestion |
| `REJECT` | Hard block — payload must be corrected and resubmitted |
| `FLAG`   | Routed to human review queue — no auto-ingest |

---

## Quick Start

```bash
# Run built-in test suite (15 cases)
python hm_intake_screener.py --test

# JSON report (pipe-friendly)
python hm_intake_screener.py --test --json

# Single test
python hm_intake_screener.py --test --id TC-07

# Screen a file
python hm_intake_screener.py --file payload.json

# Screen stdin
cat payload.json | python hm_intake_screener.py --stdin

# Adjust thresholds
python hm_intake_screener.py --test --conf-threshold HIGH --sim-threshold 0.85
```

Exit code 0 = all tests passed (or file/stdin screened as ACCEPT).  
Exit code 1 = one or more failures (or REJECT/FLAG result).

---

## Configuration

```python
@dataclass
class ScreenerConfig:
    conf_threshold:  str   = "MEDIUM"   # "HIGH" | "MEDIUM" | "LOW"
    sim_threshold:   float = 0.90       # near-dup threshold (0.0–1.0)
    hash_algo:       str   = "sha256"   # "sha256" | "sha3_256" | "md5"
    max_opacity:     int   = 3          # opacity > this → FLAG
    allow_injection: bool  = False      # True → FLAG instead of REJECT
```

---

## Module Interface

```python
from hm_intake_screener import screen, ScreenerConfig, HashRegistry

# Default config, isolated registry (no dedup memory)
decision = screen(raw_json_string)

# Shared registry across calls (persistent dedup for a session)
session_registry = HashRegistry()
cfg = ScreenerConfig(conf_threshold="HIGH", sim_threshold=0.85)

d1 = screen(payload_a, cfg=cfg, reg=session_registry)
d2 = screen(payload_b, cfg=cfg, reg=session_registry)

print(d1.decision)       # ACCEPT | REJECT | FLAG
print(d1.decision_code)  # ACCEPTED | SCHEMA_VIOLATION | EXACT_DUPLICATE | ...
print(d1.reasoning)      # one-line English explanation
print(d1.content_hash)   # sha256:<hex>
print(d1.similarity)     # float or None
```

### `IntakeDecision` fields

| Field | Type | Description |
|---|---|---|
| `decision` | str | `ACCEPT` \| `REJECT` \| `FLAG` |
| `decision_code` | str | from error taxonomy |
| `reasoning` | str | one-line explanation |
| `details` | list[str] | supporting violation / match details |
| `content_hash` | str? | `sha256:<hex>` of canonical payload |
| `similarity` | float? | 0.0–1.0 vs most-similar prior |
| `confidence` | str? | extracted from envelope |
| `opacity` | int? | extracted from envelope |
| `payload_bytes` | int | raw input size |
| `screened_at` | str | ISO-8601 UTC timestamp |

---

## Decision Code Taxonomy

| Code | Gate | Decision | Meaning |
|---|---|---|---|
| `ACCEPTED` | 5 | ACCEPT | All gates passed |
| `PARSE_ERROR` | 1 | REJECT | JSON malformed or UTF-8 invalid |
| `PAYLOAD_TOO_LARGE` | 1 | REJECT | > 512 KB |
| `SCHEMA_VIOLATION` | 2 | REJECT | Required field missing, type wrong, enum invalid |
| `EXACT_DUPLICATE` | 3 | REJECT | SHA-256 matches prior submission |
| `NEAR_DUPLICATE` | 3 | FLAG | Similarity ≥ `sim_threshold` |
| `INJECTION_DETECTED` | 4 | REJECT | Injection pattern found (`allow_injection=False`) |
| `INJECTION_FLAGGED` | 4 | FLAG | Injection pattern found (`allow_injection=True`) |
| `INDETERMINATE_CONSTRAINT` | 5 | REJECT | `constraint_type=INDETERMINATE` |
| `HIGH_OPACITY` | 5 | FLAG | `opacity > max_opacity` |
| `LOW_CONFIDENCE` | 5 | FLAG | `confidence` below `conf_threshold` |
| `INDETERMINATE_CONFIDENCE` | 5 | REJECT | Envelope `confidence=INDETERMINATE` |

---

## Test Case Summary

| ID | Name | Category | Expected | Expected Code |
|---|---|---|---|---|
| TC-01 | Clean high-confidence payload | accept | ACCEPT | ACCEPTED |
| TC-02 | Missing required field 'pipeline_id' | schema_reject | REJECT | SCHEMA_VIOLATION |
| TC-03 | Unknown source_module value | schema_reject | REJECT | SCHEMA_VIOLATION |
| TC-04 | Exact duplicate — same content hash | dedup | REJECT | EXACT_DUPLICATE |
| TC-05 | Near-duplicate — single-word variation | dedup | FLAG | NEAR_DUPLICATE |
| TC-06 | LOW confidence below MEDIUM threshold | confidence | FLAG | LOW_CONFIDENCE |
| TC-07 | Prompt injection in rule_description | injection | REJECT | INJECTION_DETECTED |
| TC-08 | INDETERMINATE constraint type | schema_reject | REJECT | INDETERMINATE_CONSTRAINT |
| TC-09 | High opacity (5) with HIGH confidence | confidence | FLAG | HIGH_OPACITY |
| TC-10 | Empty constraints array | boundary | ACCEPT | ACCEPTED |
| TC-11 | Truncated JSON (parse failure) | parse_error | REJECT | PARSE_ERROR |
| TC-12 | Oversized raw_text_excerpt (350 > 300 chars) | boundary | REJECT | SCHEMA_VIOLATION |
| TC-13 | threshold_value present, threshold_unit null | boundary | REJECT | SCHEMA_VIOLATION |
| TC-14 | MEDIUM confidence at MEDIUM threshold (inclusive) | confidence | ACCEPT | ACCEPTED |
| TC-15 | Regime payload with invalid capital_mult=0.75 | schema_reject | REJECT | SCHEMA_VIOLATION |

---

## Adding New Test Cases

```python
# Append to TESTS list in hm_intake_screener.py

_tc("TC-16", "Custom test name", "category",
    lambda: good_envelope(**{"confidence": "HIGH"}),  # build_fn
    "ACCEPT",    # expected_decision
    "ACCEPTED",  # expected_code
    "Description of what this test validates.",
    cfg=ScreenerConfig(conf_threshold="HIGH"),  # optional custom config
)
```

Each test always receives a **fresh isolated `HashRegistry`** — no cross-test dedup contamination.  For dedup tests, use the `_EXACT_DUP` or `_NEAR_DUP` sentinels (see TC-04/TC-05 in source).

---

## Sample Run Log

```
══════════════════════════════════════════════════════════════════════════════════════════════════════
  HIVE MIND INTAKE SCREENER  ·  HM-SCREEN-001  ·  2026-03-18T12:11:41Z
══════════════════════════════════════════════════════════════════════════════════════════════════════
  ID      CATEGORY         GATE  EXP      ACT       CODE                         REASONING
  ────────────────────────────────────────────────────────────────────────────────────────────────────
  ── accept ────────────────────────────────────────────────────────────────────────────────────────
  TC-01   accept           PASS  ACCEPT   ✓ ACCEPT  ACCEPTED                     Payload cleared — all gates passed
  ── schema_reject ─────────────────────────────────────────────────────────────────────────────────
  TC-02   schema_reject    PASS  REJECT   ✗ REJECT  SCHEMA_VIOLATION             Schema invalid: 1 violation(s)
  TC-03   schema_reject    PASS  REJECT   ✗ REJECT  SCHEMA_VIOLATION             Schema invalid: 1 violation(s)
  TC-08   schema_reject    PASS  REJECT   ✗ REJECT  INDETERMINATE_CONSTRAINT     INDETERMINATE constraint — unclassified
  TC-15   schema_reject    PASS  REJECT   ✗ REJECT  SCHEMA_VIOLATION             Schema invalid: 1 violation(s)
  ── dedup ─────────────────────────────────────────────────────────────────────────────────────────
  TC-04   dedup            PASS  REJECT   ✗ REJECT  EXACT_DUPLICATE              Exact duplicate — content hash matches
  TC-05   dedup            PASS  FLAG     ⚑ FLAG    NEAR_DUPLICATE               Near-duplicate — similarity 95.8% ≥ 90%
  ── confidence ────────────────────────────────────────────────────────────────────────────────────
  TC-06   confidence       PASS  FLAG     ⚑ FLAG    LOW_CONFIDENCE               confidence='LOW' below threshold='MEDIUM'
  TC-09   confidence       PASS  FLAG     ⚑ FLAG    HIGH_OPACITY                 opacity=5 > max_opacity=3 — review required
  TC-14   confidence       PASS  ACCEPT   ✓ ACCEPT  ACCEPTED                     Payload cleared — all gates passed
  ── injection ─────────────────────────────────────────────────────────────────────────────────────
  TC-07   injection        PASS  REJECT   ✗ REJECT  INJECTION_DETECTED           Adversarial payload: 2 injection pattern(s)
  ── boundary ──────────────────────────────────────────────────────────────────────────────────────
  TC-10   boundary         PASS  ACCEPT   ✓ ACCEPT  ACCEPTED                     Payload cleared — all gates passed
  TC-12   boundary         PASS  REJECT   ✗ REJECT  SCHEMA_VIOLATION             Schema invalid: 1 violation(s)
  TC-13   boundary         PASS  REJECT   ✗ REJECT  SCHEMA_VIOLATION             Schema invalid: 1 violation(s)
  ── parse_error ───────────────────────────────────────────────────────────────────────────────────
  TC-11   parse_error      PASS  REJECT   ✗ REJECT  PARSE_ERROR                  JSON parse failure: Unterminated string
  ────────────────────────────────────────────────────────────────────────────────────────────────────
  RESULT: 15/15 passed (100.0%)
══════════════════════════════════════════════════════════════════════════════════════════════════════

  CATEGORY BREAKDOWN:
  ✓ accept               1/1  █
  ✓ schema_reject        4/4  ████
  ✓ dedup                2/2  ██
  ✓ confidence           3/3  ███
  ✓ injection            1/1  █
  ✓ boundary             3/3  ███
  ✓ parse_error          1/1  █
```

### JSON Summary

```json
{
  "module": "HM-SCREEN-001",
  "spec_ref": "HMSPEC-L1-001",
  "summary": {
    "total": 15,
    "passed": 15,
    "failed": 0,
    "pass_rate_pct": 100.0
  },
  "results": [
    { "id": "TC-01", "category": "accept",        "pass": true,  "actual_decision": "ACCEPT", "actual_code": "ACCEPTED",                  "similarity": null  },
    { "id": "TC-02", "category": "schema_reject", "pass": true,  "actual_decision": "REJECT", "actual_code": "SCHEMA_VIOLATION",           "similarity": null  },
    { "id": "TC-03", "category": "schema_reject", "pass": true,  "actual_decision": "REJECT", "actual_code": "SCHEMA_VIOLATION",           "similarity": null  },
    { "id": "TC-04", "category": "dedup",         "pass": true,  "actual_decision": "REJECT", "actual_code": "EXACT_DUPLICATE",            "similarity": 1.0   },
    { "id": "TC-05", "category": "dedup",         "pass": true,  "actual_decision": "FLAG",   "actual_code": "NEAR_DUPLICATE",             "similarity": 0.9583},
    { "id": "TC-06", "category": "confidence",    "pass": true,  "actual_decision": "FLAG",   "actual_code": "LOW_CONFIDENCE",             "similarity": null  },
    { "id": "TC-07", "category": "injection",     "pass": true,  "actual_decision": "REJECT", "actual_code": "INJECTION_DETECTED",         "similarity": null  },
    { "id": "TC-08", "category": "schema_reject", "pass": true,  "actual_decision": "REJECT", "actual_code": "INDETERMINATE_CONSTRAINT",   "similarity": null  },
    { "id": "TC-09", "category": "confidence",    "pass": true,  "actual_decision": "FLAG",   "actual_code": "HIGH_OPACITY",               "similarity": null  },
    { "id": "TC-10", "category": "boundary",      "pass": true,  "actual_decision": "ACCEPT", "actual_code": "ACCEPTED",                  "similarity": null  },
    { "id": "TC-11", "category": "parse_error",   "pass": true,  "actual_decision": "REJECT", "actual_code": "PARSE_ERROR",               "similarity": null  },
    { "id": "TC-12", "category": "boundary",      "pass": true,  "actual_decision": "REJECT", "actual_code": "SCHEMA_VIOLATION",           "similarity": null  },
    { "id": "TC-13", "category": "boundary",      "pass": true,  "actual_decision": "REJECT", "actual_code": "SCHEMA_VIOLATION",           "similarity": null  },
    { "id": "TC-14", "category": "confidence",    "pass": true,  "actual_decision": "ACCEPT", "actual_code": "ACCEPTED",                  "similarity": null  },
    { "id": "TC-15", "category": "schema_reject", "pass": true,  "actual_decision": "REJECT", "actual_code": "SCHEMA_VIOLATION",           "similarity": null  }
  ]
}
```

---

*HM-SCREEN-001 · HMSPEC-L1-001 · l1-envelope-v1.0 · March 2026*  
*Pure stdlib Python 3.8+ · Zero external dependencies · Exit 0 = all pass*
