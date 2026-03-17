# Hive Mind → Post Fiat L1 Integration Specification

**Document ID:** `HMSPEC-L1-001`  
**Schema Version:** `l1-envelope-v1.0`  
**Compatible Modules:** HM-EXT-STR-001 · HM-INTAKE-001 · HMRRS-v1.0 · HM-VALID-001  
**Published:** March 2026  
**Status:** DRAFT — For integration review

---

## Table of Contents

1. [Module Inventory & As-Built Contracts](#1-module-inventory--as-built-contracts)
2. [Unified L1 Data Contract Schema](#2-unified-l1-data-contract-schema)
3. [Pipeline Sequencing & Error Handling](#3-pipeline-sequencing--error-handling)
4. [Module-to-Role Mapping](#4-module-to-role-mapping)
5. [Worked Example: Japan STR Test Vectors End-to-End](#5-worked-example-japan-str-test-vectors-end-to-end)
6. [L1 Ingestion Endpoint Contract](#6-l1-ingestion-endpoint-contract)
7. [Error Taxonomy & Rejection Codes](#7-error-taxonomy--rejection-codes)
8. [Versioning & Upgrade Path](#8-versioning--upgrade-path)

---

## 1. Module Inventory & As-Built Contracts

The following modules have been shipped and are referenced throughout this specification. Each entry documents the module's identifier, function, input surface, and output contract as implemented.

### 1.1 HM-EXT-STR-001 — STR Constraint Extraction Module

| Property | Value |
|---|---|
| Module ID | `HM-EXT-STR-001` |
| Schema | `constraint-schema-v1.0` |
| Input | Unstructured text (regulatory documents, news, operator commentary) |
| Output | `{ "extraction": { "constraints": [...], "extraction_notes": [...] }, "regime": null }` |
| Published | `hive-mind-str-extraction-module.html` |

**Output contract summary:** Each element of `constraints[]` contains `constraint_id`, `constraint_type` (one of 10 taxonomy values), `jurisdiction` object, `rule_description`, `threshold_value`, `threshold_unit`, `legal_citation`, `effective_date`, `technology_substitution_permitted` (bool|null), `captive_vendor_type`, `unit_economics_impact` (object|null), `sourcing_type`, `confidence` (HIGH/MEDIUM/LOW), `opacity` (1–5), `leading_indicator_parallel` (object|null), `raw_text_excerpt`. Missing fields set to `null`; never invented.

---

### 1.2 HM-INTAKE-001 — Unified Intake Agent

| Property | Value |
|---|---|
| Module ID | `HM-INTAKE-001` |
| Schema | `intake-schema-v1.0` |
| Input | Unstructured text (Function A) OR structured market state JSON (Function B) OR both |
| Output | `{ "extraction": <extraction_object\|null>, "regime": <regime_object\|null> }` |
| Published | `hive-mind-intake-prompt-architecture.md` |

**Output contract summary — Function A (extraction):** Identical to HM-EXT-STR-001.

**Output contract summary — Function B (regime):** Contains `asset`, `regime` (one of `R0_NEUTRAL | R1_TRENDING | R2_OVERHEATED | R3_CASCADE_RISK | R4_VOLATILE`), `capital_mult` (one of `0.0 | 0.25 | 0.5 | 1.0`), `effective_risk` (float, USD), `direction` (one of `LONG | SHORT | BOTH | NONE`), `gate_results` (object), `regime_notes` (string[]).

---

### 1.3 HMRRS-v1.0 — Risk Routing Specification

| Property | Value |
|---|---|
| Module ID | `HMRRS-v1.0` |
| Input | Six market state fields: `oi_vs_30d_ma_pct`, `funding_8h_pct`, `liq_4h_usd`, `ema_fast_above_slow`, `ema_spread_pct`, `rsi_14` |
| Output | `regime`, `capital_mult`, `effective_risk`, `verdict` (EXECUTE \| NO TRADE) |
| `BASE_RISK_UNIT` | `$570` |
| Published | `hive-mind-risk-routing-spec.md` |

**Regime precedence:** R3 > R4 > R2 > R1 > R0. R3 halts all entries. R2 applies 0.5× to longs only (asymmetric rule). R4 applies 0.25× to all.

---

### 1.4 HM-VALID-001 — Validation Harness

| Property | Value |
|---|---|
| Module ID | `HM-VALID-001` |
| Input | Test vector set (`str_vectors.json`, `regime_vectors.json`) |
| Output | Structured run log: `{ run_id, module, schema, summary: { total, passed, failed, errors, pass_rate_pct }, results: [...] }` |
| Published | `hive-mind-validation-harness.py`, `hive-mind-validation-harness-gist.md` |

**Scoring dimensions:** Schema conformance, field completeness/correctness, routing-logic accuracy. Each vector produces `{ id, name, type, status (PASS|FAIL|ERROR), schema_valid, score_passed, score_total, field_issues[], latency_ms }`.

---

### 1.5 Test Vector Sets

| Set | File | Vectors | Types |
|---|---|---|---|
| STR constraint extraction | `hive-mind-str-test-vectors.json` | 5 | PHYSICAL_PRESENCE, FEE_FLOOR, GEOGRAPHIC_EXCLUSION, LEADING_INDICATOR, INDETERMINATE |
| Regime routing | `hive-mind-test-vectors.json` | 28 | R0–R4 across Normal, Edge Case, R3 Cascade, Signal Gate Fail |
| Regime (selected 5) | `hive-mind-regime-vectors-selected.json` | 5 | R1 clean, R2 asymmetric, R3 Filter A, R4, OI boundary |

---

## 2. Unified L1 Data Contract Schema

The L1 ingestion endpoint expects every Hive Mind payload to be wrapped in a standard envelope. The envelope adds provenance, versioning, pipeline traceability, and integrity metadata around the inner `payload` produced by one of the modules above.

### 2.1 Envelope Schema (JSON Schema Draft-07)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://postfiat.org/schemas/hm-l1-envelope-v1.0.json",
  "title": "HiveMindL1Envelope",
  "description": "Standard envelope wrapping any Hive Mind module output for L1 ingestion.",
  "type": "object",
  "required": [
    "envelope_version",
    "pipeline_id",
    "stage",
    "source_module",
    "schema_version",
    "created_at",
    "payload_type",
    "confidence",
    "routing_action",
    "payload"
  ],
  "properties": {

    "envelope_version": {
      "type": "string",
      "const": "l1-envelope-v1.0",
      "description": "Envelope schema version. Bump to v1.1+ on any breaking change."
    },

    "pipeline_id": {
      "type": "string",
      "pattern": "^HM-RUN-[0-9]{8}T[0-9]{6}Z-[A-Z0-9]{6}$",
      "description": "Unique run identifier for this pipeline execution. Format: HM-RUN-{ISO8601_compact}-{random6}. Used to correlate all stages of a single ingestion run."
    },

    "stage": {
      "type": "string",
      "enum": ["EXTRACTION", "ROUTING", "VALIDATION", "L1_READY"],
      "description": "Current pipeline stage. L1 only ingests L1_READY envelopes."
    },

    "source_module": {
      "type": "string",
      "enum": ["HM-EXT-STR-001", "HM-INTAKE-001", "HMRRS-v1.0", "HM-VALID-001"],
      "description": "The module that produced this envelope's payload."
    },

    "schema_version": {
      "type": "string",
      "description": "Inner payload schema version. E.g. constraint-schema-v1.0, intake-schema-v1.0, l1-routing-v1.0."
    },

    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 UTC timestamp of envelope creation."
    },

    "payload_type": {
      "type": "string",
      "enum": ["CONSTRAINT_EXTRACTION", "REGIME_ROUTING", "VALIDATION_RESULT", "COMPOSITE"],
      "description": "Discriminator for payload structure. COMPOSITE when both extraction and regime are present."
    },

    "confidence": {
      "type": "string",
      "enum": ["HIGH", "MEDIUM", "LOW", "INDETERMINATE"],
      "description": "Aggregate confidence for the payload. For multi-constraint payloads: lowest confidence across all constraints. For regime payloads: HIGH if all gates pass with margin, MEDIUM if boundary conditions present."
    },

    "opacity": {
      "type": ["integer", "null"],
      "minimum": 1,
      "maximum": 5,
      "description": "Highest opacity score across all constraints in payload. Null for regime-only payloads."
    },

    "routing_action": {
      "type": "string",
      "enum": ["INGEST", "QUEUE_REVIEW", "REJECT"],
      "description": "Pre-computed routing decision based on confidence + opacity thresholds (see §3.3). L1 enforces this independently; field is advisory."
    },

    "routing_reason": {
      "type": ["string", "null"],
      "description": "Human-readable reason for QUEUE_REVIEW or REJECT. Null for INGEST."
    },

    "validator_attestation": {
      "type": ["object", "null"],
      "description": "Optional. When present, attests that a validator node has reviewed this payload.",
      "properties": {
        "validator_id": { "type": "string" },
        "attested_at":  { "type": "string", "format": "date-time" },
        "signature":    { "type": "string", "description": "Ed25519 signature over canonical payload hash." }
      },
      "required": ["validator_id", "attested_at", "signature"]
    },

    "prior_stage_id": {
      "type": ["string", "null"],
      "description": "pipeline_id of the immediately preceding stage envelope. Enables chain-of-custody tracing."
    },

    "error": {
      "type": ["object", "null"],
      "description": "Populated only if this envelope represents a pipeline error rather than a valid payload.",
      "properties": {
        "code":    { "type": "string" },
        "message": { "type": "string" },
        "stage_failed": { "type": "string" }
      }
    },

    "payload": {
      "description": "The inner module output. Structure determined by payload_type.",
      "oneOf": [
        { "$ref": "#/$defs/ConstraintExtractionPayload" },
        { "$ref": "#/$defs/RegimeRoutingPayload" },
        { "$ref": "#/$defs/ValidationResultPayload" },
        { "$ref": "#/$defs/CompositePayload" }
      ]
    }

  },

  "$defs": {

    "ConstraintExtractionPayload": {
      "type": "object",
      "required": ["constraints", "extraction_notes"],
      "properties": {
        "constraints":       { "type": "array" },
        "extraction_notes":  { "type": "array", "items": { "type": "string" } }
      }
    },

    "RegimeRoutingPayload": {
      "type": "object",
      "required": ["asset", "regime", "capital_mult", "effective_risk", "direction", "gate_results"],
      "properties": {
        "asset":          { "type": "string" },
        "regime":         { "type": "string", "enum": ["R0_NEUTRAL","R1_TRENDING","R2_OVERHEATED","R3_CASCADE_RISK","R4_VOLATILE"] },
        "capital_mult":   { "type": "number", "enum": [0.0, 0.25, 0.5, 1.0] },
        "effective_risk": { "type": "number", "minimum": 0 },
        "direction":      { "type": "string", "enum": ["LONG","SHORT","BOTH","NONE"] },
        "gate_results":   { "type": "object" },
        "regime_notes":   { "type": "array", "items": { "type": "string" } }
      }
    },

    "ValidationResultPayload": {
      "type": "object",
      "required": ["run_id", "summary", "results"],
      "properties": {
        "run_id":   { "type": "string" },
        "summary":  { "type": "object" },
        "results":  { "type": "array" }
      }
    },

    "CompositePayload": {
      "type": "object",
      "required": ["extraction", "regime"],
      "properties": {
        "extraction": { "oneOf": [{"type":"null"}, {"$ref":"#/$defs/ConstraintExtractionPayload"}] },
        "regime":     { "oneOf": [{"type":"null"}, {"$ref":"#/$defs/RegimeRoutingPayload"}] }
      }
    }

  }
}
```

### 2.2 Routing Thresholds (Pre-computed `routing_action`)

| Confidence | Opacity | `routing_action` |
|---|---|---|
| HIGH | 1–2 | INGEST |
| MEDIUM | 1–3 | INGEST |
| HIGH | 3 | INGEST |
| MEDIUM | 4–5 | QUEUE_REVIEW |
| LOW | any | QUEUE_REVIEW |
| INDETERMINATE | any | REJECT |
| any | — | REJECT if `constraint_type == "INDETERMINATE"` |
| any | — | REJECT if `payload` fails schema validation |

---

## 3. Pipeline Sequencing & Error Handling

### 3.1 Pipeline Stages

The pipeline has four named stages. Each stage consumes the output of the prior stage and wraps it in a new envelope before passing downstream. The `pipeline_id` is minted at Stage 1 and carried unchanged through all subsequent stages; `prior_stage_id` at each stage holds the envelope ID of the immediately preceding output.

```
RAW INPUT
    │
    ▼
┌─────────────────────────────────────┐
│  STAGE 1: EXTRACTION                │  Module: HM-INTAKE-001 (or HM-EXT-STR-001)
│  Input:  raw text | market state    │  schema: intake-schema-v1.0
│  Output: extraction + regime JSON   │  stage: "EXTRACTION"
└─────────────────┬───────────────────┘
                  │  envelope_v1 (stage=EXTRACTION)
                  ▼
┌─────────────────────────────────────┐
│  STAGE 2: ROUTING GATE              │  Reads confidence + opacity + constraint_type
│  Applies routing_action thresholds  │  Adds routing_action + routing_reason
│  Branches: INGEST | QUEUE | REJECT  │  stage: "ROUTING"
└──────┬──────────────┬───────────────┘
       │ INGEST        │ QUEUE_REVIEW / REJECT
       ▼               ▼
┌──────────────┐  ┌───────────────────────────────┐
│  STAGE 3:    │  │  REVIEW QUEUE / DEAD LETTER    │
│  VALIDATION  │  │  Human or secondary validator  │
│  HM-VALID-001│  │  reviews payload before retry  │
└──────┬───────┘  └───────────────────────────────┘
       │  validation score + pass/fail per field
       ▼
┌─────────────────────────────────────┐
│  STAGE 4: L1_READY                  │  Final envelope, stage="L1_READY"
│  Validator attestation (optional)   │  routing_action confirmed INGEST
│  Submitted to L1 ingestion endpoint │
└─────────────────────────────────────┘
```

### 3.2 Sequencing Rules

1. **Stage 1 always fires first.** A `pipeline_id` is minted as `HM-RUN-{YYYYMMDDTHHmmssZ}-{RANDOM6}` at Stage 1. All downstream stages carry this ID unchanged.

2. **Stage 2 is synchronous and blocking.** The routing gate must resolve before Stage 3 is invoked. A REJECT at Stage 2 terminates the pipeline for this payload; no Stage 3 or Stage 4 envelope is produced.

3. **Stage 3 (validation) is required for INGEST path.** A payload that passed Stage 2 routing gate must pass HM-VALID-001 schema conformance before advancing to Stage 4. A validation failure (score < 100%) produces a `routing_action: QUEUE_REVIEW` correction on the Stage 3 envelope and routes to the review queue.

4. **Parallel execution is permitted for multi-asset inputs.** When a single raw input produces both BTC and ETH regime payloads (as in HM-INTAKE-001 COMPOSITE mode), the two asset pipelines execute in parallel from Stage 2 onward. Each produces an independent L1_READY envelope with the same `pipeline_id` and asset-specific suffixes on `constraint_id` / `asset` fields.

5. **Stage 4 requires `routing_action: INGEST`.** The L1 ingestion endpoint rejects any envelope where `stage != "L1_READY"` or `routing_action != "INGEST"`.

### 3.3 Error Handling: Malformed Payloads

| Error Condition | Detection Point | Handling |
|---|---|---|
| JSON parse failure | Stage 1 output | Wrap in error envelope with `error.code: "PARSE_ERROR"`, route to dead-letter queue |
| Missing required envelope field | Stage 2 gate | `routing_action: REJECT`, `error.code: "SCHEMA_VIOLATION"` |
| `constraint_type: INDETERMINATE` | Stage 2 gate | `routing_action: REJECT`, `error.code: "INDETERMINATE_CONSTRAINT"` |
| `confidence: LOW` on any constraint | Stage 2 gate | `routing_action: QUEUE_REVIEW`, `error.code: null` (not an error; requires review) |
| `opacity >= 4` | Stage 2 gate | `routing_action: QUEUE_REVIEW` regardless of confidence |
| `threshold_value` present but `threshold_unit` null | Stage 3 validation | Field-level FAIL, `score_passed < score_total`, routes to QUEUE_REVIEW |
| `regime.capital_mult` not in `[0.0, 0.25, 0.5, 1.0]` | Stage 3 validation | Hard schema violation, `routing_action: REJECT` |
| `constraint_id` pattern mismatch (`^[A-Z]{2}-[A-Z]+-[A-Z]+-[0-9]{3}$`) | Stage 3 validation | Field-level FAIL |
| Duplicate `pipeline_id` on L1 | Stage 4 (L1 side) | L1 returns `409 CONFLICT`, pipeline records as `ALREADY_INGESTED` |

### 3.4 Adversarial Payload Handling

The pipeline is designed to be conservative: unknown constraint types, injected field values outside the defined enum sets, and oversized string fields are all handled by schema validation at Stage 3 before any payload reaches L1.

Specific adversarial vectors and mitigations:

- **Injected `routing_action: INGEST` in Stage 1 payload:** The routing gate at Stage 2 recomputes `routing_action` independently from the inner payload's confidence and opacity fields. A payload cannot self-declare its routing action.
- **Fabricated `confidence: HIGH` with `opacity: 5`:** The opacity-threshold matrix (§2.2) overrides confidence. `opacity >= 4` always produces `QUEUE_REVIEW` regardless of declared confidence.
- **`constraint_type` value not in taxonomy:** Schema validation at Stage 3 rejects via enum constraint. The `enum` array in the schema is the canonical list; no additions are accepted without a schema version bump.
- **Oversized `raw_text_excerpt` (>300 chars):** `maxLength: 300` enforced at Stage 3. Field truncation is not permitted; the constraint must be re-extracted with a compliant excerpt.
- **`leading_indicator_parallel.trigger_condition` containing executable code strings:** The L1 ingestion endpoint treats all string fields as data, never executes them. No sanitisation layer is required, but the spec documents this explicitly for validator awareness.

---

## 4. Module-to-Role Mapping

| Module | Pipeline Role | Stage | L1 Relevance |
|---|---|---|---|
| **HM-EXT-STR-001** | Constraint extraction for STR-specific inputs | Stage 1 (extraction-only) | Produces constraint objects that become on-chain regulatory signals |
| **HM-INTAKE-001** | Unified extraction + regime classification | Stage 1 (composite or single-function) | Primary intake point for production; routes both STR constraint and market regime data in one call |
| **HMRRS-v1.0** | Regime classification logic (embedded in HM-INTAKE-001 Function B) | Stage 1 / Stage 2 gate | Produces `capital_mult` and `effective_risk` that L1 validator nodes read for position-sizing decisions |
| **HM-VALID-001** | Structural conformance + routing-logic accuracy testing | Stage 3 | QA gate before L1 ingestion; outputs `score_passed/score_total` per field; failures trigger QUEUE_REVIEW |
| **Test vectors (STR + regime)** | Ground truth for Stage 3 validation scoring | Stage 3 reference data | Validators can re-run HM-VALID-001 against a new payload set to confirm classification correctness before on-chain acceptance |

### 4.1 On-Chain Signal Mapping

L1 validator nodes consume the `L1_READY` envelope and read the following fields for signal state:

| Envelope Field | L1 Validator Reads As |
|---|---|
| `payload.regime` | Current market regime state for the named asset |
| `payload.capital_mult` | Position sizing multiplier applied to `BASE_RISK_UNIT` ($570) |
| `payload.direction` | Permitted trade direction (`NONE` = all entries halted) |
| `payload.constraints[].constraint_type` | Regulatory constraint category for signal weighting |
| `payload.constraints[].confidence` | Signal confidence tier |
| `payload.constraints[].opacity` | Signal opacity score (1 = most reliable) |
| `envelope.routing_action` | Final ingest decision (validators reject non-INGEST envelopes) |
| `envelope.created_at` | Timestamp for staleness checks (validators reject envelopes > 4H old) |
| `envelope.pipeline_id` | Deduplication key |

---

## 5. Worked Example: Japan STR Test Vectors End-to-End

This section traces test vector **STR-001** (10-minute proximity rule, primary legal text) through all four pipeline stages, showing the exact JSON at each handoff point.

### 5.1 Input: Raw Text (Stage 1 Entry)

```
Article 11(1)(iii) of the Private Lodging Business Act (民泊新法, effective
June 15 2018) requires that a licensed management company (kanrisha) be
physically reachable within 10 minutes of the registered property during all
guest stay periods, by foot or vehicle. Failure constitutes grounds for
registration cancellation under Article 33(1)(iv). Technology-based remote
monitoring systems do not satisfy the proximity requirement.
```

---

### 5.2 Stage 1 Output: HM-INTAKE-001 Extraction (Function A)

*This is the raw module output before the envelope is applied.*

```json
{
  "extraction": {
    "constraints": [
      {
        "constraint_id": "JP-PHYS-NATL-001",
        "constraint_type": "PHYSICAL_PRESENCE",
        "jurisdiction": {
          "country": "JP",
          "region": null,
          "municipality": null,
          "scope": "NATIONAL"
        },
        "rule_description": "Licensed kanrisha must be physically reachable within 10 minutes (foot or vehicle) of registered property during all guest stays",
        "threshold_value": 10,
        "threshold_unit": "minutes",
        "threshold_mode": "foot_or_vehicle",
        "legal_citation": "Article 11(1)(iii), Private Lodging Business Act (民泊新法)",
        "enforcement_citation": "Article 33(1)(iv)",
        "effective_date": "2018-06-15",
        "announcement_date": null,
        "technology_substitution_permitted": false,
        "technology_substitution_source": "Explicit — stated in source text",
        "captive_vendor_type": "licensed_kanrisha",
        "captive_vendor_required": true,
        "unit_economics_impact": null,
        "sourcing_type": "PRIMARY",
        "confidence": "HIGH",
        "opacity": 1,
        "leading_indicator_parallel": null,
        "raw_text_excerpt": "physically reachable within 10 minutes...Technology-based remote monitoring systems do not satisfy the proximity requirement"
      }
    ],
    "extraction_notes": []
  },
  "regime": null
}
```

**Stage 1 Envelope:**

```json
{
  "envelope_version": "l1-envelope-v1.0",
  "pipeline_id": "HM-RUN-20260317T091500Z-JP001A",
  "stage": "EXTRACTION",
  "source_module": "HM-INTAKE-001",
  "schema_version": "intake-schema-v1.0",
  "created_at": "2026-03-17T09:15:00Z",
  "payload_type": "CONSTRAINT_EXTRACTION",
  "confidence": "HIGH",
  "opacity": 1,
  "routing_action": null,
  "routing_reason": null,
  "validator_attestation": null,
  "prior_stage_id": null,
  "error": null,
  "payload": {
    "constraints": [ /* as above */ ],
    "extraction_notes": []
  }
}
```

---

### 5.3 Stage 2 Output: Routing Gate Applied

The routing gate reads `confidence: HIGH` and `opacity: 1`. Per §2.2 threshold matrix: HIGH + opacity 1–2 → `INGEST`. No review required.

```json
{
  "envelope_version": "l1-envelope-v1.0",
  "pipeline_id": "HM-RUN-20260317T091500Z-JP001A",
  "stage": "ROUTING",
  "source_module": "HM-INTAKE-001",
  "schema_version": "intake-schema-v1.0",
  "created_at": "2026-03-17T09:15:02Z",
  "payload_type": "CONSTRAINT_EXTRACTION",
  "confidence": "HIGH",
  "opacity": 1,
  "routing_action": "INGEST",
  "routing_reason": null,
  "validator_attestation": null,
  "prior_stage_id": "HM-RUN-20260317T091500Z-JP001A",
  "error": null,
  "payload": {
    "constraints": [
      {
        "constraint_id": "JP-PHYS-NATL-001",
        "constraint_type": "PHYSICAL_PRESENCE",
        "jurisdiction": { "country": "JP", "region": null, "municipality": null, "scope": "NATIONAL" },
        "rule_description": "Licensed kanrisha must be physically reachable within 10 minutes (foot or vehicle) of registered property during all guest stays",
        "threshold_value": 10,
        "threshold_unit": "minutes",
        "threshold_mode": "foot_or_vehicle",
        "legal_citation": "Article 11(1)(iii), Private Lodging Business Act (民泊新法)",
        "enforcement_citation": "Article 33(1)(iv)",
        "effective_date": "2018-06-15",
        "announcement_date": null,
        "technology_substitution_permitted": false,
        "technology_substitution_source": "Explicit — stated in source text",
        "captive_vendor_type": "licensed_kanrisha",
        "captive_vendor_required": true,
        "unit_economics_impact": null,
        "sourcing_type": "PRIMARY",
        "confidence": "HIGH",
        "opacity": 1,
        "leading_indicator_parallel": null,
        "raw_text_excerpt": "physically reachable within 10 minutes...Technology-based remote monitoring systems do not satisfy the proximity requirement"
      }
    ],
    "extraction_notes": []
  }
}
```

---

### 5.4 Stage 3 Output: HM-VALID-001 Validation

HM-VALID-001 runs the STR-001 vector assertions against the payload. Expected assertions and results:

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| `constraint_type` | PHYSICAL_PRESENCE | PHYSICAL_PRESENCE | ✓ |
| `threshold_value` | 10 | 10 | ✓ |
| `threshold_unit` | minutes | minutes | ✓ |
| `technology_substitution_permitted` | false | false | ✓ |
| `captive_vendor_required` | true | true | ✓ |
| `confidence` | HIGH | HIGH | ✓ |
| `opacity` | 1 | 1 | ✓ |
| `sourcing_type` | PRIMARY | PRIMARY | ✓ |
| `legal_citation_contains` | "Article 11" | "Article 11(1)(iii)…" | ✓ |

Score: **9/9**. Schema valid. No field issues.

```json
{
  "envelope_version": "l1-envelope-v1.0",
  "pipeline_id": "HM-RUN-20260317T091500Z-JP001A",
  "stage": "VALIDATION",
  "source_module": "HM-VALID-001",
  "schema_version": "l1-routing-v1.0",
  "created_at": "2026-03-17T09:15:04Z",
  "payload_type": "VALIDATION_RESULT",
  "confidence": "HIGH",
  "opacity": 1,
  "routing_action": "INGEST",
  "routing_reason": null,
  "validator_attestation": null,
  "prior_stage_id": "HM-RUN-20260317T091500Z-JP001A",
  "error": null,
  "payload": {
    "run_id": "20260317T091504Z",
    "summary": {
      "total": 1,
      "passed": 1,
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
      }
    ]
  }
}
```

---

### 5.5 Stage 4 Output: L1_READY Final Envelope

The VALIDATION stage passed 9/9. `routing_action` remains `INGEST`. The Stage 4 envelope packages the original constraint payload (not the validation result) with the final stage marker and optional validator attestation slot.

```json
{
  "envelope_version": "l1-envelope-v1.0",
  "pipeline_id": "HM-RUN-20260317T091500Z-JP001A",
  "stage": "L1_READY",
  "source_module": "HM-INTAKE-001",
  "schema_version": "intake-schema-v1.0",
  "created_at": "2026-03-17T09:15:06Z",
  "payload_type": "CONSTRAINT_EXTRACTION",
  "confidence": "HIGH",
  "opacity": 1,
  "routing_action": "INGEST",
  "routing_reason": null,
  "validator_attestation": {
    "validator_id": "VALIDATOR-NODE-001",
    "attested_at": "2026-03-17T09:15:05Z",
    "signature": "<ed25519_signature_over_canonical_payload_hash>"
  },
  "prior_stage_id": "HM-RUN-20260317T091500Z-JP001A",
  "error": null,
  "payload": {
    "constraints": [
      {
        "constraint_id": "JP-PHYS-NATL-001",
        "constraint_type": "PHYSICAL_PRESENCE",
        "jurisdiction": { "country": "JP", "region": null, "municipality": null, "scope": "NATIONAL" },
        "rule_description": "Licensed kanrisha must be physically reachable within 10 minutes (foot or vehicle) of registered property during all guest stays",
        "threshold_value": 10,
        "threshold_unit": "minutes",
        "threshold_mode": "foot_or_vehicle",
        "legal_citation": "Article 11(1)(iii), Private Lodging Business Act (民泊新法)",
        "enforcement_citation": "Article 33(1)(iv)",
        "effective_date": "2018-06-15",
        "announcement_date": null,
        "technology_substitution_permitted": false,
        "technology_substitution_source": "Explicit — stated in source text",
        "captive_vendor_type": "licensed_kanrisha",
        "captive_vendor_required": true,
        "unit_economics_impact": null,
        "sourcing_type": "PRIMARY",
        "confidence": "HIGH",
        "opacity": 1,
        "leading_indicator_parallel": null,
        "raw_text_excerpt": "physically reachable within 10 minutes...Technology-based remote monitoring systems do not satisfy the proximity requirement"
      }
    ],
    "extraction_notes": []
  }
}
```

**L1 ingestion endpoint receives this envelope and reads:**
- `payload.constraints[0].constraint_type` → `PHYSICAL_PRESENCE` — signal category for on-chain weighting
- `payload.constraints[0].confidence` → `HIGH` — tier 1 signal
- `payload.constraints[0].opacity` → `1` — maximum reliability
- `payload.constraints[0].threshold_value` + `threshold_unit` → `10 minutes` — quantified threshold for validator logic
- `envelope.routing_action` → `INGEST` — accepted

---

### 5.6 Contrast: STR-005 (Indeterminate) — Rejection Path

Test vector STR-005 (operator rumour, no official source) shows the rejection path:

**Stage 1 extraction output (key fields only):**
```json
{
  "constraint_type": "INDETERMINATE",
  "confidence": "LOW",
  "opacity": 5,
  "sourcing_type": "OPERATOR_COMMENTARY",
  "threshold_value": null,
  "legal_citation": null
}
```

**Stage 2 routing gate output:**
```json
{
  "routing_action": "REJECT",
  "routing_reason": "constraint_type INDETERMINATE — cannot ingest unclassified constraints. confidence LOW + opacity 5 both independently trigger REJECT.",
  "error": {
    "code": "INDETERMINATE_CONSTRAINT",
    "message": "Constraint type INDETERMINATE is not ingestible. Re-extract when primary source available.",
    "stage_failed": "ROUTING"
  }
}
```

Pipeline terminates at Stage 2. No Stage 3 or Stage 4 envelope is produced. The raw payload is routed to the dead-letter queue with the `pipeline_id` for human review and re-extraction once a primary source is located.

---

## 6. L1 Ingestion Endpoint Contract

### 6.1 Endpoint Specification

```
POST /v1/hive-mind/ingest
Content-Type: application/json
Authorization: Bearer <validator_jwt>

Body: <L1_READY envelope JSON>

Success: 201 Created
  { "ingested": true, "pipeline_id": "...", "l1_tx_id": "..." }

Already ingested: 409 Conflict
  { "ingested": false, "reason": "ALREADY_INGESTED", "pipeline_id": "..." }

Schema violation: 422 Unprocessable Entity
  { "ingested": false, "reason": "SCHEMA_VIOLATION", "field_errors": [...] }

Routing action not INGEST: 400 Bad Request
  { "ingested": false, "reason": "ROUTING_ACTION_NOT_INGEST", "routing_action": "..." }

Stale envelope (>4H): 400 Bad Request
  { "ingested": false, "reason": "ENVELOPE_STALE", "created_at": "..." }
```

### 6.2 Staleness Check

L1 rejects any envelope where `created_at` is more than 4 hours before the server's current time. This aligns with the 4H candle cadence in HMRRS-v1.0 — a regime signal older than one full classification period is considered expired.

### 6.3 Idempotency

`pipeline_id` is the deduplication key. A second POST with the same `pipeline_id` returns `409 CONFLICT` without re-ingesting. Clients must mint a new `pipeline_id` for retry submissions after error correction.

---

## 7. Error Taxonomy & Rejection Codes

| Code | Stage | Meaning | Resolution |
|---|---|---|---|
| `PARSE_ERROR` | Stage 1 | JSON parse failure on module output | Re-run extraction module; check for truncated API response |
| `SCHEMA_VIOLATION` | Stage 2–3 | Required field missing or type mismatch | Validate against `l1-envelope-v1.0` schema before submission |
| `INDETERMINATE_CONSTRAINT` | Stage 2 | `constraint_type: INDETERMINATE` present | Re-extract when primary source available |
| `LOW_CONFIDENCE_CONSTRAINT` | Stage 2 | `confidence: LOW` on one or more constraints | Route to QUEUE_REVIEW; do not auto-ingest |
| `HIGH_OPACITY` | Stage 2 | `opacity >= 4` on any constraint | Route to QUEUE_REVIEW; manual review required |
| `INVALID_REGIME` | Stage 3 | `regime` not in defined enum | Check HMRRS-v1.0 classifier output; schema bug in regime module |
| `INVALID_CAPITAL_MULT` | Stage 3 | `capital_mult` not in `[0.0, 0.25, 0.5, 1.0]` | Hard reject; classifier produced non-standard multiplier |
| `FIELD_ASSERTION_FAIL` | Stage 3 | One or more HM-VALID-001 assertions failed | Inspect `field_issues[]` array; re-extract or re-classify |
| `ENVELOPE_STALE` | Stage 4 (L1) | `created_at` > 4H ago | Re-run pipeline with fresh data |
| `ALREADY_INGESTED` | Stage 4 (L1) | Duplicate `pipeline_id` | Normal; do not retry unless content changed (mint new pipeline_id) |
| `ROUTING_ACTION_NOT_INGEST` | Stage 4 (L1) | `routing_action` is not `INGEST` | Pipeline routing gate failed to reject; do not reach L1 with QUEUE_REVIEW or REJECT envelopes |

---

## 8. Versioning & Upgrade Path

### 8.1 Version Fields

Every envelope carries two version identifiers:
- `envelope_version`: The envelope wrapper schema version (`l1-envelope-v1.0`). Bump to `v1.1` on any change to required envelope fields; bump to `v2.0` on breaking changes.
- `schema_version`: The inner payload schema version (e.g. `intake-schema-v1.0`). Each module maintains its own version independently.

### 8.2 Backward Compatibility Rules

- L1 accepts envelopes where `envelope_version` major version matches (`v1.x` accepts `v1.0`, `v1.1`, etc.).
- L1 rejects envelopes where `envelope_version` major version differs.
- Schema version changes in `schema_version` do not require L1 endpoint changes as long as the envelope wrapper schema is unchanged.

### 8.3 Module Upgrade Protocol

Any change to a module's output contract (new required field, enum value addition, type change) requires:
1. Module ID bump (e.g. `HM-EXT-STR-001` → `HM-EXT-STR-002`)
2. `schema_version` bump in the module's output
3. Update to HM-VALID-001 test vectors to cover new contract
4. Full regression run: 100% pass rate required before production deployment
5. Updated entry in this document's §1 module inventory

---

*HMSPEC-L1-001 · l1-envelope-v1.0 · March 2026*  
*Modules: HM-EXT-STR-001 · HM-INTAKE-001 · HMRRS-v1.0 · HM-VALID-001*  
*BASE_RISK_UNIT: $570 · 4H cadence · Ed25519 validator attestation*
