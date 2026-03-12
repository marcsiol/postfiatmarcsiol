# Hive Mind Intake Agent — Prompt Architecture v1.0

**Module ID:** `HM-INTAKE-001`  
**Schema version:** `intake-schema-v1.0`  
**Compatible with:** Hive Mind Risk Routing Spec v1.0 · STR Constraint Extraction Module HM-EXT-STR-001  
**Published:** March 2026  
**Format:** GitHub Gist — deploy verbatim, do not summarise or reformat for production use

---

## Contents

1. [System Prompt — Intake Agent](#1-system-prompt)
2. [Few-Shot Examples (5)](#2-few-shot-examples)
3. [JSON Output Schema](#3-json-output-schema)
4. [Routing Logic Reference](#4-routing-logic-reference)
5. [Integration Notes](#5-integration-notes)

---

## 1. System Prompt

> Paste this block verbatim as the `system` parameter in every API call. Do not abbreviate.

```
##############################################################################
# HIVE MIND INTAKE AGENT
# Module: HM-INTAKE-001 | Schema: intake-schema-v1.0
# Covers: (A) STR regulatory constraint extraction
#         (B) Market regime classification routing
# Do not modify without bumping the module ID.
##############################################################################

You are the Hive Mind Intake Agent.

You serve two functions in a single pass:

FUNCTION A — CONSTRAINT EXTRACTION
Read unstructured input text about short-term rental (STR) regulatory
environments and extract structured constraint data into the JSON format
specified below. Input may be laws, ordinances, enforcement orders, market
reports, legal memos, news articles, or operator commentary.

FUNCTION B — REGIME ROUTING
Read structured or semi-structured market state input (OI levels, funding
rates, liquidation volumes, EMA spread, RSI values) and classify the current
market into exactly one of five regime states (R0–R4), returning the
applicable capital multiplier for the BASE_RISK_UNIT of $570.

If the input contains only regulatory text, execute Function A only.
If the input contains only market state data, execute Function B only.
If the input contains both, execute both and return a unified JSON object
with both "extraction" and "regime" keys populated.

────────────────────────────────────────────────────────────────────────────
FUNCTION A: CONSTRAINT EXTRACTION RULES
────────────────────────────────────────────────────────────────────────────

CONSTRAINT TAXONOMY
Classify every extracted constraint into exactly one of these types:
  PHYSICAL_PRESENCE    — mandated human presence at or near a property
  LICENSING_CEILING    — limit on operating days, units, or rooms
  GEOGRAPHIC_EXCLUSION — zone or ward-level prohibition or restriction
  FEE_FLOOR            — mandated minimum cost structure
  TECHNOLOGY_BLOCK     — explicit prohibition on tech substituting for human requirement
  CAPTIVE_VENDOR       — mandatory use of a specific licensed third party
  ENFORCEMENT_ACTION   — fine, revocation, or operational suspension event
  LEADING_INDICATOR    — upstream signal in another sector predicting STR rule change
  PENDING_CHANGE       — proposed, announced, or consulted regulatory modification
  INDETERMINATE        — input too fragmentary to classify

EXTRACTION TARGETS (for each constraint found)
  1. constraint_type (from taxonomy)
  2. rule_description (plain English, ≤400 chars)
  3. threshold_value (exact numeric value as stated; null if not stated)
  4. threshold_unit (minutes, percent_of_gross_revenue, JPY, etc.)
  5. legal_citation (article, act name; null if absent)
  6. effective_date (ISO 8601 or partial; null if unknown)
  7. jurisdiction (country, region, municipality, scope)
  8. technology_substitution_permitted (boolean; null if not addressed)
  9. captive_vendor_type (string; null if not applicable)
  10. unit_economics_impact (object with quantified cost/margin data; null if none)
  11. sourcing_type: "PRIMARY" | "SECONDARY_SYNTHESIS" | "OPERATOR_COMMENTARY" | "UNKNOWN"
  12. confidence: "HIGH" | "MEDIUM" | "LOW"
  13. opacity: integer 1–5
  14. leading_indicator_parallel (object; null if not applicable)
  15. raw_text_excerpt (verbatim ≤300 chars supporting the extraction)

OPACITY SCORING
  1 = Official government source, unambiguous primary text
  2 = Public source, minor interpretation required
  3 = Credible secondary report (law firm, survey, REIT disclosure)
  4 = Inferred from market behaviour or operator commentary
  5 = Speculative / unverified / rumour-level

CONFIDENCE RULES
  HIGH   — legal citation or official primary text present in input
  MEDIUM — credible secondary report without primary citation
  LOW    — inferred, operator-reported, or non-expert media without citation

INCOMPLETE DATA PROTOCOL
  - Set missing required fields to null
  - Add extraction_notes entry: name the missing value type and the primary
    source that would resolve it
  - NEVER invent threshold values, distances, ratios, or fees not stated in source
  - If input is too fragmentary for any extraction: return constraint_type
    "INDETERMINATE", populate only raw_text_excerpt and extraction_notes
  - NEVER produce prose outside JSON fields

────────────────────────────────────────────────────────────────────────────
FUNCTION B: REGIME ROUTING RULES
────────────────────────────────────────────────────────────────────────────

REGIME STATES (evaluate in precedence order: R3 > R4 > R2 > R1 > R0)

  R3  CASCADE_RISK   — capital_mult: 0.0×
      Trigger: BOTH OI elevated (≥15% above 30d MA) AND funding hot
      (≥0.05%/8H) concurrent. OR: prior 4H liquidation volume ≥ $150M.
      All new long AND short entries halted.
      Clears after 2 consecutive 4H candles below all R3 thresholds.

  R4  VOLATILE       — capital_mult: 0.25×
      Trigger: Prior 4H liq $75M–$149M. OR: ATR(14,4H) ≥ 3× its
      20-period average. OR: EMA cross within prior 2 candles followed
      immediately by opposing RSI signal.

  R2  OVERHEATED     — capital_mult: 0.5× (longs) / 1.0× (shorts)
      Trigger (one condition sufficient): OI ≥ 15% above 30d MA. OR:
      funding ≥ 0.05%/8H. OR: RSI > 73 on long candidate.
      Asymmetric rule: long reduction applies only; shorts at full size.

  R1  TRENDING       — capital_mult: 1.0×
      Trigger: EMA_fast above/below EMA_slow by ≥1.2% of price. AND:
      RSI in signal band for ≥2 consecutive 4H candles. AND: OI below
      elevation threshold. AND: funding below 0.03%/8H.

  R0  NEUTRAL        — capital_mult: 1.0×
      Default: none of the above conditions met. OI within 15% of 30d MA.
      Funding -0.03% to +0.03%/8H. Prior 4H liq < $50M.

REGIME INPUT FIELDS
  oi_current        // aggregate perpetual OI, USD notional
  oi_30d_ma         // 30-day moving average of OI
  funding_8h        // latest 8H funding rate, decimal (0.0005 = 0.05%)
  liq_4h            // prior 4H liquidation volume, USD notional
  ema_fast          // fast EMA value
  ema_slow          // slow EMA value
  price             // current price
  rsi_4h            // 4H RSI, 0–100
  atr_14            // ATR(14,4H) current value
  atr_20_avg        // 20-period average of ATR(14,4H)

REGIME OUTPUT FIELDS
  regime            // string: R0_NEUTRAL | R1_TRENDING | R2_OVERHEATED |
                    //         R3_CASCADE_RISK | R4_VOLATILE
  capital_mult      // float: effective multiplier for BASE_RISK_UNIT
  effective_risk    // float: BASE_RISK_UNIT ($570) × capital_mult
  direction         // "LONG" | "SHORT" | "BOTH" | "NONE"
  gate_results      // object: each gate's pass/fail with reason
  regime_notes      // array of strings: boundary conditions, warnings

BASE_RISK_UNIT = 570  // USD

────────────────────────────────────────────────────────────────────────────
OUTPUT FORMAT
────────────────────────────────────────────────────────────────────────────

Return ONLY valid JSON. No preamble. No trailing commentary. No markdown
fencing. The root object must contain:
  "extraction" key if Function A was executed (may be null if B-only)
  "regime"     key if Function B was executed (may be null if A-only)

If no STR constraints are found: "extraction": {"constraints": [], "extraction_notes": ["No STR-relevant constraints identified."]}
If regime input is absent or incomplete: "regime": null, add note to extraction_notes

##############################################################################
# END SYSTEM PROMPT
##############################################################################
```

---

## 2. Few-Shot Examples

> Pass these as alternating `user` / `assistant` turns immediately after the system prompt, before the live input.

---

### Example 1 — Physical Presence Constraint (Primary Legal Text)

**USER:**
```
Article 11(1)(iii) of the Private Lodging Business Act (民泊新法, effective
June 15 2018) requires that a licensed management company (kanrisha) be
physically reachable within 10 minutes of the registered property during all
guest stay periods, by foot or vehicle. Failure constitutes grounds for
registration cancellation under Article 33(1)(iv). Technology-based remote
monitoring systems do not satisfy the proximity requirement.
```

**ASSISTANT:**
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

---

### Example 2 — Fee Floor (Secondary Synthesis, Quantified Unit Economics)

**USER:**
```
Colliers International Japan (September 2024): management fees for licensed
STR kanrisha in Tokyo have remained stable at 15–20% of gross revenue since
2018 despite IoT adoption. Fee stability is attributed to irreducible legal
liability, not labour costs. Platform fees (primarily Airbnb) average ~14%
of gross, creating a combined compliance-plus-platform cost floor of ~31.5%
of gross before operating expenses. Individual operators with 1–3 properties
cannot internalise the kanrisha function; institutional operators above ~20
central Tokyo units can break even on an in-house licensed kanrisha hire at
¥4.5–5.5M annual cost.
```

**ASSISTANT:**
```json
{
  "extraction": {
    "constraints": [
      {
        "constraint_id": "JP-FEE-TKY-001",
        "constraint_type": "FEE_FLOOR",
        "jurisdiction": {
          "country": "JP",
          "region": "Tokyo",
          "municipality": null,
          "scope": "REGIONAL"
        },
        "rule_description": "Kanrisha management fees stable at 15–20% of gross since 2018 despite technology cost reduction; floor driven by legal liability not labour",
        "threshold_value": "15–20",
        "threshold_unit": "percent_of_gross_revenue",
        "threshold_mode": "market_observed_range",
        "legal_citation": null,
        "enforcement_citation": null,
        "effective_date": "2018-06-15",
        "announcement_date": null,
        "technology_substitution_permitted": false,
        "technology_substitution_source": "Inferred — IoT adoption has not reduced fees per source",
        "captive_vendor_type": "licensed_kanrisha",
        "captive_vendor_required": true,
        "unit_economics_impact": {
          "combined_compliance_platform_floor_pct": 31.5,
          "platform_fee_component_pct": 14,
          "kanrisha_fee_midpoint_pct": 17.5,
          "institutional_breakeven_units": 20,
          "institutional_kanrisha_hire_cost_jpy_annual": "4500000–5500000"
        },
        "sourcing_type": "SECONDARY_SYNTHESIS",
        "confidence": "MEDIUM",
        "opacity": 3,
        "leading_indicator_parallel": null,
        "raw_text_excerpt": "management fees...remained stable at 15–20%...combined compliance and platform cost floor of approximately 31.5%"
      }
    ],
    "extraction_notes": [
      "No legal citation — fee floor is market-observed, not legally mandated. Mandate for kanrisha engagement derives from Article 11(1)(iii). Primary source to confirm fee levels: Japan Tourism Agency annual operator survey."
    ]
  },
  "regime": null
}
```

---

### Example 3 — Leading Indicator (Cross-Sector Analog: Kaigo Elder Care)

**USER:**
```
MHLW guidance, March 2024: robotic care systems approved for use in
long-term care facilities under the Long-Term Care Insurance Act but the
1:3 carer-to-resident staffing ratio under Article 14 remains unchanged.
Robots assist present carers; they do not substitute for the legal presence
requirement. Industry groups representing 4,000+ facilities have petitioned
for ratio relaxation citing a 300,000-worker projected shortfall. MHLW
review pending, no timeline.
```

**ASSISTANT:**
```json
{
  "extraction": {
    "constraints": [
      {
        "constraint_id": "JP-LI-KAIGO-001",
        "constraint_type": "LEADING_INDICATOR",
        "jurisdiction": {
          "country": "JP",
          "region": null,
          "municipality": null,
          "scope": "NATIONAL"
        },
        "rule_description": "MHLW 1:3 carer-to-resident staffing ratio unchanged despite robotic adoption; technology permitted as task assistance only, not legal presence substitution",
        "threshold_value": "1:3",
        "threshold_unit": "carer_to_resident_ratio",
        "threshold_mode": "staffing_floor",
        "legal_citation": "Article 14, Long-Term Care Insurance Act (介護保険法)",
        "enforcement_citation": null,
        "effective_date": null,
        "announcement_date": "2024-03",
        "technology_substitution_permitted": false,
        "technology_substitution_source": "Explicit — MHLW guidance March 2024",
        "captive_vendor_type": null,
        "captive_vendor_required": false,
        "unit_economics_impact": null,
        "sourcing_type": "PRIMARY",
        "confidence": "HIGH",
        "opacity": 1,
        "leading_indicator_parallel": {
          "target_sector": "short_term_rental",
          "analog_sector": "elder_care_kaigo",
          "signal_type": "PRIMARY",
          "signal_logic": "MHLW kaigo staffing ratio is closest policy analog to MLIT STR 10-minute proximity rule — both are physical presence mandates resistant to technology substitution. Ratio relaxation in kaigo would establish first Japanese precedent for a presence mandate yielding to technology capability, materially raising STR rule-change probability.",
          "trigger_condition": "MHLW announces kaigo ratio relaxation OR pilot permitting technology substitution at legal compliance threshold (not task assistance)",
          "current_status": "Review pending, no timeline. Petition filed by 4,000+ facility coalition."
        },
        "raw_text_excerpt": "robots assist present carers; they do not substitute for the legal presence requirement...review pending with no timeline announced"
      }
    ],
    "extraction_notes": [
      "No MHLW review timeline in source. Monitor MHLW press releases and Diet Health Committee proceedings."
    ]
  },
  "regime": null
}
```

---

### Example 4 — Market Regime Classification (Function B Only)

**USER:**
```json
{
  "asset": "BTC-PERP",
  "timestamp": "2026-03-10T08:00:00Z",
  "oi_current": 18700000000,
  "oi_30d_ma": 15200000000,
  "funding_8h": 0.00062,
  "liq_4h": 42000000,
  "ema_fast": 61840,
  "ema_slow": 60210,
  "price": 61950,
  "rsi_4h": 71.4,
  "atr_14": 1820,
  "atr_20_avg": 1340,
  "direction_candidate": "LONG"
}
```

**ASSISTANT:**
```json
{
  "extraction": null,
  "regime": {
    "asset": "BTC-PERP",
    "timestamp": "2026-03-10T08:00:00Z",
    "regime": "R2_OVERHEATED",
    "capital_mult": 0.5,
    "effective_risk": 285.0,
    "direction": "LONG",
    "gate_results": {
      "R3_check": {
        "pass": false,
        "oi_elevated": true,
        "funding_hot": true,
        "note": "Both OI elevated and funding hot — would trigger R3, but liq_4h $42M is below $150M standalone trigger. Concurrent condition: BOTH required for R3 via Filter A. OI elevated = true (18.7B vs 15.2B MA = +23% > 15% threshold). Funding hot = true (0.062%/8H > 0.05% threshold). R3 Filter A TRIGGERED."
      },
      "override": "R3_CASCADE_RISK triggered by Filter A (concurrent OI + funding). Downgrade to R3.",
      "final_regime": "R3_CASCADE_RISK",
      "capital_mult_corrected": 0.0,
      "effective_risk_corrected": 0.0
    },
    "regime": "R3_CASCADE_RISK",
    "capital_mult": 0.0,
    "effective_risk": 0.0,
    "direction": "NONE",
    "regime_notes": [
      "Initial read was R2 (OI + funding each individually satisfy R2). However R3 Filter A requires BOTH OI elevated AND funding hot concurrently — both conditions met. R3 takes precedence per cascade rule R3 > R2.",
      "All new entries halted. Clears after 2 consecutive 4H candles where EITHER OI drops below 15% elevation OR funding drops below 0.05%/8H.",
      "RSI 71.4 is below R2 long-side RSI trigger of >73 — RSI alone would not have triggered R2, but OI and funding both independently meet R2 threshold."
    ]
  }
}
```

---

### Example 5 — Incomplete Input (Edge Case: Indeterminate Constraint + Incomplete Regime Data)

**USER:**
```
Word on the street in Osaka is that some wards near Dotonbori are cracking
down harder on unlicensed rentals. Nothing official yet. Also BTC funding is
running hot but I don't have the exact number.
```

**ASSISTANT:**
```json
{
  "extraction": {
    "constraints": [
      {
        "constraint_id": "JP-INDET-OSK-001",
        "constraint_type": "INDETERMINATE",
        "jurisdiction": {
          "country": "JP",
          "region": "Osaka",
          "municipality": "Dotonbori-area wards, unspecified",
          "scope": "WARD"
        },
        "rule_description": "Unverified reports of increased enforcement against unlicensed STR near Dotonbori; no official publication confirmed",
        "threshold_value": null,
        "threshold_unit": null,
        "threshold_mode": null,
        "legal_citation": null,
        "enforcement_citation": null,
        "effective_date": null,
        "announcement_date": null,
        "technology_substitution_permitted": null,
        "technology_substitution_source": null,
        "captive_vendor_type": null,
        "captive_vendor_required": null,
        "unit_economics_impact": null,
        "sourcing_type": "OPERATOR_COMMENTARY",
        "confidence": "LOW",
        "opacity": 5,
        "leading_indicator_parallel": null,
        "raw_text_excerpt": "wards near Dotonbori are cracking down harder on unlicensed rentals. Nothing official yet."
      }
    ],
    "extraction_notes": [
      "Input is unverified operator commentary. Constraint classified INDETERMINATE — insufficient data for type, threshold, or legal basis. Do not route to Hive Mind risk model until confidence >= MEDIUM.",
      "Resolution sources: (1) Osaka City ward office official gazettes; (2) Japan Tourism Agency operator registration portal; (3) Naniwa-ku or Chuo-ku ward office enforcement announcements.",
      "Re-extract when primary or credible secondary source available."
    ]
  },
  "regime": null,
  "regime_notes": [
    "Regime classification not possible: funding_8h value described qualitatively ('running hot') but no numeric value provided. Required fields absent: oi_current, oi_30d_ma, funding_8h (exact), liq_4h, ema_fast, ema_slow, price, rsi_4h, atr_14, atr_20_avg.",
    "Provide structured market state input per the regime input field specification to enable classification."
  ]
}
```

---

## 3. JSON Output Schema

> Validate every LLM response against this schema before routing to the Hive Mind intake API.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "HiveMindIntakeOutput",
  "description": "Root output schema for HM-INTAKE-001. Both keys present on every call; null if function not executed.",
  "type": "object",
  "required": ["extraction", "regime"],
  "properties": {

    "extraction": {
      "oneOf": [
        { "type": "null" },
        {
          "type": "object",
          "required": ["constraints", "extraction_notes"],
          "properties": {

            "constraints": {
              "type": "array",
              "items": {
                "type": "object",
                "required": [
                  "constraint_id", "constraint_type", "jurisdiction",
                  "rule_description", "confidence", "opacity",
                  "sourcing_type", "raw_text_excerpt"
                ],
                "properties": {
                  "constraint_id":    { "type": "string", "pattern": "^[A-Z]{2}-[A-Z]+-[A-Z]+-[0-9]{3}$" },
                  "constraint_type":  {
                    "type": "string",
                    "enum": [
                      "PHYSICAL_PRESENCE", "LICENSING_CEILING", "GEOGRAPHIC_EXCLUSION",
                      "FEE_FLOOR", "TECHNOLOGY_BLOCK", "CAPTIVE_VENDOR",
                      "ENFORCEMENT_ACTION", "LEADING_INDICATOR", "PENDING_CHANGE",
                      "INDETERMINATE"
                    ]
                  },
                  "jurisdiction": {
                    "type": "object",
                    "required": ["country", "scope"],
                    "properties": {
                      "country":      { "type": "string" },
                      "region":       { "type": ["string", "null"] },
                      "municipality": { "type": ["string", "null"] },
                      "scope":        { "type": "string", "enum": ["NATIONAL", "REGIONAL", "MUNICIPAL", "WARD"] }
                    }
                  },
                  "rule_description":               { "type": "string", "maxLength": 400 },
                  "threshold_value":                { "type": ["number", "string", "null"] },
                  "threshold_unit":                 { "type": ["string", "null"] },
                  "threshold_mode":                 { "type": ["string", "null"] },
                  "legal_citation":                 { "type": ["string", "null"] },
                  "enforcement_citation":           { "type": ["string", "null"] },
                  "effective_date":                 { "type": ["string", "null"] },
                  "announcement_date":              { "type": ["string", "null"] },
                  "technology_substitution_permitted": { "type": ["boolean", "null"] },
                  "technology_substitution_source": { "type": ["string", "null"] },
                  "captive_vendor_type":            { "type": ["string", "null"] },
                  "captive_vendor_required":        { "type": ["boolean", "null"] },
                  "unit_economics_impact":          { "type": ["object", "null"] },
                  "sourcing_type": {
                    "type": "string",
                    "enum": ["PRIMARY", "SECONDARY_SYNTHESIS", "OPERATOR_COMMENTARY", "UNKNOWN"]
                  },
                  "confidence": { "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"] },
                  "opacity":    { "type": "integer", "minimum": 1, "maximum": 5 },
                  "leading_indicator_parallel": {
                    "oneOf": [
                      { "type": "null" },
                      {
                        "type": "object",
                        "properties": {
                          "target_sector":    { "type": "string" },
                          "analog_sector":    { "type": "string" },
                          "signal_type":      { "type": "string", "enum": ["PRIMARY", "SECONDARY", "TERTIARY"] },
                          "signal_logic":     { "type": "string" },
                          "trigger_condition":{ "type": "string" },
                          "current_status":   { "type": "string" }
                        }
                      }
                    ]
                  },
                  "raw_text_excerpt": { "type": "string", "maxLength": 300 }
                }
              }
            },

            "extraction_notes": {
              "type": "array",
              "items": { "type": "string" }
            }

          }
        }
      ]
    },

    "regime": {
      "oneOf": [
        { "type": "null" },
        {
          "type": "object",
          "required": ["asset", "regime", "capital_mult", "effective_risk", "direction", "gate_results"],
          "properties": {
            "asset":          { "type": "string" },
            "timestamp":      { "type": ["string", "null"] },
            "regime": {
              "type": "string",
              "enum": ["R0_NEUTRAL", "R1_TRENDING", "R2_OVERHEATED", "R3_CASCADE_RISK", "R4_VOLATILE"]
            },
            "capital_mult":   { "type": "number", "enum": [0.0, 0.25, 0.5, 1.0] },
            "effective_risk": { "type": "number", "minimum": 0 },
            "direction": {
              "type": "string",
              "enum": ["LONG", "SHORT", "BOTH", "NONE"]
            },
            "gate_results":   { "type": "object" },
            "regime_notes":   { "type": "array", "items": { "type": "string" } }
          }
        }
      ]
    },

    "regime_notes": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Top-level regime notes when regime key is null but partial regime input was provided."
    }

  }
}
```

---

## 4. Routing Logic Reference

> This section is informational for the development team. Not injected into the LLM prompt.

### Capital Multiplier Table

| Regime | Direction | Multiplier | Effective Risk (BASE=$570) |
|---|---|---|---|
| R0 NEUTRAL | Long / Short | 1.0× | $570 |
| R1 TRENDING | Long / Short | 1.0× | $570 |
| R2 OVERHEATED | **Long** | **0.5×** | **$285** |
| R2 OVERHEATED | Short | 1.0× | $570 |
| R3 CASCADE_RISK | Long / Short | 0.0× | $0 — no entry |
| R4 VOLATILE | Long / Short | 0.25× | $142.50 |

### Regime Precedence (highest severity wins)

```
R3 > R4 > R2 > R1 > R0
```

### Constraint Routing Thresholds

| Confidence | Opacity | Action |
|---|---|---|
| HIGH | 1–2 | Direct ingest, no review required |
| MEDIUM | 1–3 | Ingest with periodic review flag |
| LOW | any | Pending queue — manual review required |
| any | 4–5 | Hold for manual review regardless of confidence |
| INDETERMINATE | any | Do not ingest — log for re-extraction |
| PENDING_CHANGE + LOW | any | Pending queue until effective_date confirmed |

---

## 5. Integration Notes

### API Call Structure

```python
import anthropic
import json
import jsonschema

client = anthropic.Anthropic()

# Build message list: few-shot turns + live input
messages = [
    # Example 1
    {"role": "user",      "content": "... (Example 1 USER text) ..."},
    {"role": "assistant", "content": "... (Example 1 ASSISTANT JSON) ..."},
    # Examples 2–5 follow same pattern
    # ...
    # Live input — final user turn
    {"role": "user", "content": live_input_text}
]

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=SYSTEM_PROMPT,   # Section 1 verbatim
    messages=messages
)

raw = response.content[0].text.strip()

# Strip accidental markdown fencing
if raw.startswith("```"):
    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

parsed = json.loads(raw)
jsonschema.validate(instance=parsed, schema=SCHEMA)  # Section 3

# Route
for constraint in (parsed.get("extraction") or {}).get("constraints", []):
    if constraint["constraint_type"] == "INDETERMINATE":
        log_pending(constraint)
        continue
    if constraint["confidence"] == "LOW":
        log_pending(constraint)
        continue
    hive_mind_intake_api(constraint)

if parsed.get("regime"):
    regime_routing_api(parsed["regime"])
```

### Model Selection

Use `claude-sonnet-4-20250514`. Do not downgrade to Haiku for production — structured output reliability on multi-constraint documents requires Sonnet-class capability.

### Version Discipline

Any change to system prompt text, constraint taxonomy enum values, schema field names, or few-shot example content requires a module version bump (`HM-INTAKE-002`, etc.) and re-validation of all downstream routing logic. Do not edit a deployed version in-place.

### Relationship to HM-EXT-STR-001

`HM-INTAKE-001` is a superset of `HM-EXT-STR-001`. It adds Function B (regime routing) and unifies both functions into a single API call and output schema. The STR extraction logic is identical. Use `HM-INTAKE-001` for all new intake integrations; `HM-EXT-STR-001` remains valid as a constraint-extraction-only module where regime routing is not needed.

---

*HM-INTAKE-001 · intake-schema-v1.0 · March 2026*  
*Not legal advice. Validate primary sources before operational use.*  
*BASE_RISK_UNIT: $570 · Assets: BTC-PERP / ETH-PERP*
