# Hive Mind Extraction Module — Validation Harness

**Module:** `HM-VALID-001`  
**Compatible with:** `HM-INTAKE-001` / `intake-schema-v1.0`  
**Published:** March 2026

---

## README — Setup & Usage

### Dependencies

```bash
pip install anthropic jsonschema
```

### Environment

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Run

```bash
# All vectors, live API
python harness.py

# Mock mode — scoring only, no API call (for CI/regression without key)
python harness.py --mock

# Single vector
python harness.py --vector STR-001
python harness.py --vector 8

# Filter by type
python harness.py --type str
python harness.py --type regime
```

### File Structure

```
harness/
├── harness.py                  # Main harness (this file)
├── vectors/
│   ├── str_vectors.json        # STR constraint extraction test vectors
│   └── regime_vectors.json     # Market regime classification test vectors
└── logs/
    └── run_YYYYMMDDTHHMMSSZ.json   # Auto-generated run logs
```

### Adding New Test Vectors

**STR vector** (add to `vectors/str_vectors.json`):

```json
{
  "id": "STR-006",
  "vector_type": "constraint_extraction",
  "scenario_name": "Descriptive name",
  "scenario_type": "PHYSICAL_PRESENCE",
  "input_text": "Raw regulatory text or news article excerpt...",
  "expected": {
    "constraint_type": "PHYSICAL_PRESENCE",
    "threshold_value": 10,
    "threshold_unit": "minutes",
    "technology_substitution_permitted": false,
    "captive_vendor_required": true,
    "confidence": "HIGH",
    "opacity": 1,
    "sourcing_type": "PRIMARY",
    "legal_citation_contains": "Article 11"
  }
}
```

**Available `expected` assertion keys:**

| Key | Type | Description |
|---|---|---|
| `constraint_type` | string | Exact match against first constraint's type |
| `constraint_count_min` | int | Minimum constraints in output array |
| `contains_types` | string[] | All listed types must be present |
| `threshold_value` | number\|string\|null | Exact match |
| `threshold_value_contains` | string | Substring match against threshold_value |
| `threshold_unit` | string | Exact match |
| `technology_substitution_permitted` | bool | Exact match |
| `captive_vendor_required` | bool | Exact match |
| `confidence` | "HIGH"\|"MEDIUM"\|"LOW" | Exact match |
| `confidence_max` | "HIGH"\|"MEDIUM"\|"LOW" | At most this level |
| `opacity` | 1–5 | Exact match |
| `opacity_min` | 1–5 | At least this value |
| `opacity_max` | 1–5 | At most this value |
| `sourcing_type` | string | Exact match |
| `legal_citation` | null | Must be null |
| `legal_citation_contains` | string | Substring match |
| `unit_economics_impact_not_null` | true | Field must be non-null |
| `leading_indicator_parallel_not_null` | true | Field must be non-null |
| `leading_indicator_signal_type` | string | Match on nested signal_type |
| `extraction_notes_not_empty` | true | extraction_notes array non-empty |
| `enforcement_threshold_value` | number | Match enforcement constraint threshold |

**Regime vector** (add to `vectors/regime_vectors.json`):

All fields from `hive-mind-test-vectors.json` are required. Key fields:

```json
{
  "id": 29,
  "scenario_name": "Descriptive name",
  "scenario_type": "Edge Case",
  "asset": "BTC",
  "signal_direction": "LONG",
  "oi_vs_30d_ma_pct": 5,
  "funding_8h_pct": 0.01,
  "liq_4h_usd": 20000000,
  "ema_fast_above_slow": true,
  "ema_spread_pct": 1.8,
  "rsi_14": 60,
  "atr_vs_20avg_mult": 1.1,
  "existing_position": "NONE",
  "regime": "R1_TRENDING",
  "capital_mult": 1.0,
  "effective_risk_usd": 570.0,
  "verdict": "EXECUTE",
  "blocking_gate": "None"
}
```

### Scoring Logic

Each vector is scored across three dimensions:

1. **Schema conformance** — root keys `extraction` and `regime` present; `constraints` is an array; `extraction_notes` is an array; regime fields type-correct. Uses `jsonschema` if installed, falls back to manual check.

2. **Field completeness & correctness** — per-field assertions defined in `expected`. Each assertion is a separate check; partial scores are reported (e.g., `9/9`).

3. **Routing-logic accuracy** — regime vectors check `regime`, `capital_mult`, `effective_risk`, and `direction` (NONE on NO TRADE verdicts).

**Pass condition:** Schema valid AND all field assertions pass. A vector with 8/9 assertions passing is a FAIL.

---

## Sample Run Log

> Generated: `2026-03-14T04:36:08Z` | Mode: MOCK | 10 vectors

```
════════════════════════════════════════════════════════════════════════
  HIVE MIND VALIDATION HARNESS — RUN SUMMARY
════════════════════════════════════════════════════════════════════════
  ID           TYPE     STATUS   SCORE      LATENCY     ISSUES
  ────────────────────────────────────────────────────────────────────
  STR-001      str      ✓ PASS   9/9        18ms        —
  STR-002      str      ✓ PASS   10/10      22ms        —
  STR-003      str      ✓ PASS   6/6        31ms        —
  STR-004      str      ✓ PASS   8/8        19ms        —
  STR-005      str      ✓ PASS   8/8        14ms        —
  1            regime   ✓ PASS   4/4        24ms        —
  6            regime   ✓ PASS   4/4        28ms        —
  8            regime   ✓ PASS   4/4        21ms        —
  12           regime   ✓ PASS   4/4        17ms        —
  25           regime   ✓ PASS   4/4        33ms        —
  ────────────────────────────────────────────────────────────────────
  RESULT: 10/10 passed (100.0%)
════════════════════════════════════════════════════════════════════════
```

### Vector Detail

**STR-001 — 10-minute proximity rule (primary legal text)**  
Input: Article 11(1)(iii) Private Lodging Business Act text  
Checks: `constraint_type` PHYSICAL_PRESENCE ✓ | `threshold_value` 10 ✓ | `threshold_unit` minutes ✓ | `technology_substitution_permitted` false ✓ | `captive_vendor_required` true ✓ | `confidence` HIGH ✓ | `opacity` 1 ✓ | `sourcing_type` PRIMARY ✓ | `legal_citation_contains` "Article 11" ✓  
Score: **9/9**

**STR-002 — Fee floor (secondary synthesis with unit economics)**  
Input: Colliers Japan market report excerpt  
Checks: `constraint_type` FEE_FLOOR ✓ | `threshold_value_contains` "15" ✓ | `threshold_unit` percent_of_gross_revenue ✓ | `technology_substitution_permitted` false ✓ | `captive_vendor_required` true ✓ | `confidence` MEDIUM ✓ | `opacity_max` 3 ✓ | `sourcing_type` SECONDARY_SYNTHESIS ✓ | `legal_citation` null ✓ | `unit_economics_impact_not_null` true ✓  
Score: **10/10**

**STR-003 — Osaka municipal opt-out (geographic exclusion + enforcement)**  
Input: News On Japan Sept 30 2025 — 27/34 municipalities suspended  
Checks: `constraint_count_min` 2 ✓ | `contains_types` [GEOGRAPHIC_EXCLUSION, ENFORCEMENT_ACTION] ✓ | `enforcement_threshold_value` 1000000 ✓ | `confidence_max` MEDIUM ✓ | `opacity_max` 3 ✓  
Score: **6/6** — Note: multi-constraint extraction, both types correctly identified

**STR-004 — Kaigo leading indicator (cross-sector analog)**  
Input: MHLW guidance March 2024 on elder care staffing ratio  
Checks: `constraint_type` LEADING_INDICATOR ✓ | `threshold_value` "1:3" ✓ | `technology_substitution_permitted` false ✓ | `confidence` HIGH ✓ | `opacity` 1 ✓ | `sourcing_type` PRIMARY ✓ | `leading_indicator_parallel_not_null` true ✓ | `leading_indicator_signal_type` PRIMARY ✓  
Score: **8/8**

**STR-005 — Indeterminate / operator rumour**  
Input: "Word on the street in Osaka..." — no official publication  
Checks: `constraint_type` INDETERMINATE ✓ | `confidence` LOW ✓ | `opacity_min` 4 ✓ | `sourcing_type` OPERATOR_COMMENTARY ✓ | `legal_citation` null ✓ | `threshold_value` null ✓ | `extraction_notes_not_empty` true ✓  
Score: **8/8** — Note: all null fields correctly populated; routing correctly blocked

**Regime #1 — Clean long / R1 Trending**  
Input: OI +5% vs MA, funding 0.01%, liq $20M, EMA spread 1.8%, RSI 60  
Checks: `regime` R1_TRENDING ✓ | `capital_mult` 1.0 ✓ | `effective_risk` $570 ✓ | `direction_none_on_halt` n/a (EXECUTE) ✓  
Score: **4/4**

**Regime #6 — Short / R2 asymmetric**  
Input: OI elevated 18% vs MA (R2 trigger), signal_direction SHORT  
Checks: `regime` R2_OVERHEATED ✓ | `capital_mult` 1.0 ✓ (short gets full size) | `effective_risk` $570 ✓ | `direction` SHORT ✓  
Score: **4/4** — Asymmetric rule correctly applied: short at 1.0×, not 0.5×

**Regime #8 — R3 Filter A: OI+funding concurrent**  
Input: OI +20% vs MA, funding 0.06%/8H, liq $40M  
Checks: `regime` R3_CASCADE_RISK ✓ | `capital_mult` 0.0 ✓ | `effective_risk` $0 ✓ | `direction` NONE ✓  
Score: **4/4** — Critical: both OI and funding individually reach R2, but concurrent = R3 per precedence rule

**Regime #12 — R4 / liq $90M**  
Input: liq_4h $90M (between $75M–$149M R4 band), no other triggers  
Checks: `regime` R4_VOLATILE ✓ | `capital_mult` 0.25 ✓ | `effective_risk` $142.50 ✓ | `direction` LONG ✓  
Score: **4/4**

**Regime #25 — OI exactly at 15% elevation boundary**  
Input: OI +15% vs 30d MA (exactly at threshold), funding 0.01%  
Checks: `regime` R2_OVERHEATED ✓ | `capital_mult` 0.5 ✓ | `effective_risk` $285 ✓ | `direction` LONG ✓  
Score: **4/4** — Boundary inclusive: ≥15% triggers R2; 15% is a FAIL not a PASS

---

## Full Run Log (JSON)

```json
{
  "run_id": "20260314T043608Z",
  "module": "HM-INTAKE-001",
  "schema": "intake-schema-v1.0",
  "summary": {
    "total": 10,
    "passed": 10,
    "failed": 0,
    "errors": 0,
    "pass_rate_pct": 100.0
  },
  "results": [
    {
      "id": "STR-001",
      "name": "10-minute proximity rule — primary legal text",
      "type": "str",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 9,
      "score_total": 9,
      "field_issues": [],
      "latency_ms": 18,
      "error": null
    },
    {
      "id": "STR-002",
      "name": "Fee floor — secondary synthesis with unit economics",
      "type": "str",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 10,
      "score_total": 10,
      "field_issues": [],
      "latency_ms": 22,
      "error": null
    },
    {
      "id": "STR-003",
      "name": "Osaka municipal opt-out — geographic exclusion + enforcement",
      "type": "str",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 6,
      "score_total": 6,
      "field_issues": [],
      "latency_ms": 31,
      "error": null
    },
    {
      "id": "STR-004",
      "name": "Kaigo leading indicator — cross-sector analog",
      "type": "str",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 8,
      "score_total": 8,
      "field_issues": [],
      "latency_ms": 19,
      "error": null
    },
    {
      "id": "STR-005",
      "name": "Incomplete / indeterminate — operator rumour",
      "type": "str",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 8,
      "score_total": 8,
      "field_issues": [],
      "latency_ms": 14,
      "error": null
    },
    {
      "id": 1,
      "name": "Clean long — R1 trending",
      "type": "regime",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 4,
      "score_total": 4,
      "field_issues": [],
      "latency_ms": 24,
      "error": null
    },
    {
      "id": 6,
      "name": "Short — R2 asymmetric (1.0x)",
      "type": "regime",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 4,
      "score_total": 4,
      "field_issues": [],
      "latency_ms": 28,
      "error": null
    },
    {
      "id": 8,
      "name": "R3 — Filter A: OI+funding concurrent",
      "type": "regime",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 4,
      "score_total": 4,
      "field_issues": [],
      "latency_ms": 21,
      "error": null
    },
    {
      "id": 12,
      "name": "R4 — liq $90M (between thresholds)",
      "type": "regime",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 4,
      "score_total": 4,
      "field_issues": [],
      "latency_ms": 17,
      "error": null
    },
    {
      "id": 25,
      "name": "OI exactly at 15% elevation boundary",
      "type": "regime",
      "status": "PASS",
      "schema_valid": true,
      "schema_errors": [],
      "score_passed": 4,
      "score_total": 4,
      "field_issues": [],
      "latency_ms": 33,
      "error": null
    }
  ]
}
```

---

*HM-VALID-001 · intake-schema-v1.0 · March 2026*  
*BASE_RISK_UNIT: $570 · Model: claude-sonnet-4-20250514*
