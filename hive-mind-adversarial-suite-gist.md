# Hive Mind L1 — Adversarial Test Suite

**Suite ID:** `HM-ADVERSARIAL-001`  
**Spec:** `HMSPEC-L1-001` (`l1-envelope-v1.0`)  
**Published:** March 2026  
**Vectors:** 16 (15 adversarial + 1 positive control)  
**Last run result:** 16/16 PASS (100%)

---

## README

### What this is

A standalone Python adversarial test suite that validates the Hive Mind → Post Fiat L1 integration pipeline defined in `HMSPEC-L1-001`. It implements the pipeline's four stages locally and fires 16 test vectors — each targeting a distinct error-handling branch in the spec — asserting that every malformed, adversarial, or boundary-value input produces the exact outcome mandated by the specification.

### Dependencies

None. Pure Python 3.8+ stdlib only (`json`, `re`, `datetime`, `hashlib`, `copy`, `sys`, `argparse`).

### Running

```bash
# Run all 16 vectors — print table + write JSON log to /tmp/hm_adversarial_run.json
python adversarial_suite.py

# JSON output only (pipe-friendly)
python adversarial_suite.py --json

# Single vector
python adversarial_suite.py --vector AV-007

# By category
python adversarial_suite.py --category adversarial_logic
python adversarial_suite.py --category replay_attack
```

Exit code 0 = all tests passed. Exit code 1 = one or more failures.

### Adding New Vectors

1. Define `build_AVNNN() -> dict` — construct and return the adversarial payload.
2. Add a `TestVector(...)` entry to the `VECTORS` list with:
   - `id`: `AV-NNN` format
   - `category`: one of `malformed_json | schema_violation | injection | boundary_value | adversarial_logic | replay_attack | positive_control`
   - `expected_outcome`: `REJECT | QUEUE_REVIEW | PARSE_ERROR | INGEST`
   - `expected_error_code`: from the spec's error taxonomy, or `None`
   - `spec_ref`: section reference in `HMSPEC-L1-001`
3. Run the suite. A new failure indicates either a bug in the pipeline implementation or an incorrect expected_outcome in the vector.

---

## Test Vector Summary

| ID | Name | Category | Expected Outcome | Expected Error | Spec Ref |
|---|---|---|---|---|---|
| AV-001 | Truncated JSON string | malformed_json | PARSE_ERROR | PARSE_ERROR | §3.3 row 1 |
| AV-002 | Missing required field (pipeline_id) | schema_violation | REJECT | SCHEMA_VIOLATION | §3.3 row 2 |
| AV-003 | Malformed pipeline_id format | malformed_json | REJECT | SCHEMA_VIOLATION | §2.1 pipeline_id.pattern |
| AV-004 | Unknown constraint_type not in taxonomy | schema_violation | QUEUE_REVIEW | FIELD_ASSERTION_FAIL | §3.3 enum |
| AV-005 | INDETERMINATE constraint | schema_violation | REJECT | INDETERMINATE_CONSTRAINT | §2.2 row 5, §3.3 row 3 |
| AV-006 | Self-declared INGEST with confidence=LOW | adversarial_logic | QUEUE_REVIEW | — | §3.2, §3.4 vector 1 |
| AV-007 | Fabricated HIGH confidence with opacity=5 | adversarial_logic | QUEUE_REVIEW | — | §3.4 vector 2, §2.2 opacity>=4 |
| AV-008 | Invalid capital_mult (0.75) | schema_violation | QUEUE_REVIEW | FIELD_ASSERTION_FAIL | §3.3 row 7 |
| AV-009 | threshold_value present, threshold_unit null | boundary_value | QUEUE_REVIEW | FIELD_ASSERTION_FAIL | §3.3 row 6 |
| AV-010 | Oversized raw_text_excerpt (350 > 300 chars) | boundary_value | QUEUE_REVIEW | FIELD_ASSERTION_FAIL | §2.1 maxLength |
| AV-011 | Prompt injection in rule_description | injection | INGEST | — | §3.4 vector 4 |
| AV-012 | Stale envelope (created 6H ago, limit 4H) | replay_attack | REJECT | ENVELOPE_STALE | §6.2 |
| AV-013 | Replay attack — duplicate pipeline_id | replay_attack | REJECT | ALREADY_INGESTED | §6.3, §7 |
| AV-014 | Wrong stage (ROUTING, not L1_READY) | schema_violation | REJECT | ROUTING_ACTION_NOT_INGEST | §3.2 rule 5, §7 |
| AV-015 | Unknown source_module value | schema_violation | REJECT | SCHEMA_VIOLATION | §2.1 source_module.enum |
| AV-POSITIVE | Canonical good payload (positive control) | positive_control | INGEST | — | §5.5 |

---

## Sample Run Log

```
══════════════════════════════════════════════════════════════════════════════════════════
  HIVE MIND L1 ADVERSARIAL TEST SUITE  ·  HM-ADVERSARIAL-001  ·  2026-03-17T15:14:18Z
══════════════════════════════════════════════════════════════════════════════════════════
  ID             CATEGORY           STATUS     EXPECTED         ACTUAL           STAGE
  ──────────────────────────────────────────────────────────────────────────────────────
  AV-POSITIVE    positive_control   ✓ PASS     INGEST           INGEST           STAGE4
  AV-001         malformed_json     ✓ PASS     PARSE_ERROR      PARSE_ERROR      STAGE1
                                               detail: JSON parse failure: Unterminated string starting at: line 1 column 57
  AV-003         malformed_json     ✓ PASS     REJECT           REJECT           STAGE2
                                               detail: pipeline_id format invalid: 'NOTAVALIDID-20260317-ABCDEF'
  AV-002         schema_violation   ✓ PASS     REJECT           REJECT           STAGE2
                                               detail: Missing required field: 'pipeline_id'
  AV-004         schema_violation   ✓ PASS     QUEUE_REVIEW     QUEUE_REVIEW     STAGE3
                                               detail: constraints[0].constraint_type unknown: 'CUSTOM_HACK'
  AV-005         schema_violation   ✓ PASS     REJECT           REJECT           STAGE2
                                               detail: INDETERMINATE constraint present: JP-PHYS-NATL-001
  AV-008         schema_violation   ✓ PASS     QUEUE_REVIEW     QUEUE_REVIEW     STAGE3
                                               detail: INVALID_CAPITAL_MULT: 0.75 not in [0.0, 0.25, 0.5, 1.0]
  AV-014         schema_violation   ✓ PASS     REJECT           REJECT           STAGE4
                                               detail: stage is 'ROUTING', expected L1_READY
  AV-015         schema_violation   ✓ PASS     REJECT           REJECT           STAGE2
                                               detail: Unknown source_module: 'EXTERNAL-INJECTOR-v9'
  AV-011         injection          ✓ PASS     INGEST           INGEST           STAGE4
  AV-009         boundary_value     ✓ PASS     QUEUE_REVIEW     QUEUE_REVIEW     STAGE3
                                               detail: constraints[0]: threshold_value=10 present but threshold_unit is null/missing
  AV-010         boundary_value     ✓ PASS     QUEUE_REVIEW     QUEUE_REVIEW     STAGE3
                                               detail: constraints[0].raw_text_excerpt exceeds 300 chars (got 350)
  AV-006         adversarial_logic  ✓ PASS     QUEUE_REVIEW     QUEUE_REVIEW     STAGE2
                                               detail: confidence=LOW; routed to review queue
  AV-007         adversarial_logic  ✓ PASS     QUEUE_REVIEW     QUEUE_REVIEW     STAGE2
                                               detail: opacity=5 >= 4; routed to manual review regardless of confidence
  AV-012         replay_attack      ✓ PASS     REJECT           REJECT           STAGE4
                                               detail: Envelope age 6.0H exceeds 4H limit
  AV-013         replay_attack      ✓ PASS     REJECT           REJECT           STAGE4
                                               detail: Duplicate pipeline_id: HM-RUN-20260317T130000Z-REPLA1
  ──────────────────────────────────────────────────────────────────────────────────────
  RESULT: 16/16 passed (100.0%)
══════════════════════════════════════════════════════════════════════════════════════════

  CATEGORY BREAKDOWN:
  ✓ positive_control       1/1  █
  ✓ malformed_json         2/2  ██
  ✓ schema_violation       6/6  ██████
  ✓ injection              1/1  █
  ✓ boundary_value         2/2  ██
  ✓ adversarial_logic      2/2  ██
  ✓ replay_attack          2/2  ██
```

### JSON Run Log

```json
{
  "suite_id": "HM-ADVERSARIAL-001",
  "spec_ref": "HMSPEC-L1-001",
  "run_at": "2026-03-17T15:14:18+00:00",
  "summary": {
    "total": 16,
    "passed": 16,
    "failed": 0,
    "pass_rate_pct": 100.0
  },
  "results": [
    { "id": "AV-001", "category": "malformed_json",    "pass": true, "actual_outcome": "PARSE_ERROR",   "actual_error": "PARSE_ERROR",               "actual_stage": "STAGE1" },
    { "id": "AV-002", "category": "schema_violation",  "pass": true, "actual_outcome": "REJECT",        "actual_error": "SCHEMA_VIOLATION",           "actual_stage": "STAGE2" },
    { "id": "AV-003", "category": "malformed_json",    "pass": true, "actual_outcome": "REJECT",        "actual_error": "SCHEMA_VIOLATION",           "actual_stage": "STAGE2" },
    { "id": "AV-004", "category": "schema_violation",  "pass": true, "actual_outcome": "QUEUE_REVIEW",  "actual_error": "FIELD_ASSERTION_FAIL",       "actual_stage": "STAGE3" },
    { "id": "AV-005", "category": "schema_violation",  "pass": true, "actual_outcome": "REJECT",        "actual_error": "INDETERMINATE_CONSTRAINT",   "actual_stage": "STAGE2" },
    { "id": "AV-006", "category": "adversarial_logic", "pass": true, "actual_outcome": "QUEUE_REVIEW",  "actual_error": null,                         "actual_stage": "STAGE2" },
    { "id": "AV-007", "category": "adversarial_logic", "pass": true, "actual_outcome": "QUEUE_REVIEW",  "actual_error": null,                         "actual_stage": "STAGE2" },
    { "id": "AV-008", "category": "schema_violation",  "pass": true, "actual_outcome": "QUEUE_REVIEW",  "actual_error": "FIELD_ASSERTION_FAIL",       "actual_stage": "STAGE3" },
    { "id": "AV-009", "category": "boundary_value",    "pass": true, "actual_outcome": "QUEUE_REVIEW",  "actual_error": "FIELD_ASSERTION_FAIL",       "actual_stage": "STAGE3" },
    { "id": "AV-010", "category": "boundary_value",    "pass": true, "actual_outcome": "QUEUE_REVIEW",  "actual_error": "FIELD_ASSERTION_FAIL",       "actual_stage": "STAGE3" },
    { "id": "AV-011", "category": "injection",         "pass": true, "actual_outcome": "INGEST",        "actual_error": null,                         "actual_stage": "STAGE4" },
    { "id": "AV-012", "category": "replay_attack",     "pass": true, "actual_outcome": "REJECT",        "actual_error": "ENVELOPE_STALE",             "actual_stage": "STAGE4" },
    { "id": "AV-013", "category": "replay_attack",     "pass": true, "actual_outcome": "REJECT",        "actual_error": "ALREADY_INGESTED",           "actual_stage": "STAGE4" },
    { "id": "AV-014", "category": "schema_violation",  "pass": true, "actual_outcome": "REJECT",        "actual_error": "ROUTING_ACTION_NOT_INGEST",  "actual_stage": "STAGE4" },
    { "id": "AV-015", "category": "schema_violation",  "pass": true, "actual_outcome": "REJECT",        "actual_error": "SCHEMA_VIOLATION",           "actual_stage": "STAGE2" },
    { "id": "AV-POSITIVE", "category": "positive_control", "pass": true, "actual_outcome": "INGEST",   "actual_error": null,                         "actual_stage": "STAGE4" }
  ]
}
```

---

*HM-ADVERSARIAL-001 · HMSPEC-L1-001 · l1-envelope-v1.0 · March 2026*  
*Pure stdlib Python 3.8+ · No external dependencies · Exit 0 = all pass*
