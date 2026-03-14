#!/usr/bin/env python3
"""
Hive Mind Extraction Module — Automated Validation Harness
Module: HM-VALID-001 | Compatible with: HM-INTAKE-001 / intake-schema-v1.0

Usage:
    python harness.py                        # run all vectors, live API
    python harness.py --mock                 # run scoring only (no API call)
    python harness.py --vector STR-001       # single vector
    python harness.py --type regime          # regime vectors only
    python harness.py --type str             # STR extraction vectors only

Dependencies:
    pip install anthropic jsonschema

Environment:
    ANTHROPIC_API_KEY=sk-ant-...             # required unless --mock

Adding new test vectors:
    Regime:  add an entry to vectors/regime_vectors.json matching the schema
             (all fields from hive-mind-test-vectors.json required)
    STR:     add an entry to vectors/str_vectors.json — see README section
             at the bottom of this file for field definitions.
"""

import os
import sys
import json
import time
import argparse
import datetime
import traceback
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
VECTORS_DIR = os.path.join(BASE_DIR, "vectors")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
SCHEMA_DIR  = os.path.join(BASE_DIR, "schema")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")

os.makedirs(LOGS_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT (inline; matches HM-INTAKE-001 Section 1 verbatim)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """##############################################################################
# HIVE MIND INTAKE AGENT
# Module: HM-INTAKE-001 | Schema: intake-schema-v1.0
##############################################################################

You are the Hive Mind Intake Agent.

FUNCTION A — CONSTRAINT EXTRACTION
Read unstructured input text about short-term rental (STR) regulatory
environments and extract structured constraint data into the JSON format
specified below.

FUNCTION B — REGIME ROUTING
Read structured market state input and classify into one of five regime states
(R0–R4), returning the applicable capital multiplier for BASE_RISK_UNIT=$570.

If the input contains only regulatory text, execute Function A only.
If the input contains only market state data, execute Function B only.
If input contains both, execute both.

────────────────────────────────────────────────────────────────────────────
FUNCTION A: CONSTRAINT EXTRACTION RULES
────────────────────────────────────────────────────────────────────────────

CONSTRAINT TAXONOMY
  PHYSICAL_PRESENCE | LICENSING_CEILING | GEOGRAPHIC_EXCLUSION | FEE_FLOOR
  TECHNOLOGY_BLOCK  | CAPTIVE_VENDOR    | ENFORCEMENT_ACTION   | LEADING_INDICATOR
  PENDING_CHANGE    | INDETERMINATE

EXTRACTION TARGETS (per constraint)
  constraint_id, constraint_type, jurisdiction, rule_description,
  threshold_value (null if not stated — NEVER invent), threshold_unit,
  threshold_mode, legal_citation, enforcement_citation, effective_date,
  announcement_date, technology_substitution_permitted (bool|null),
  technology_substitution_source, captive_vendor_type, captive_vendor_required,
  unit_economics_impact (object|null), sourcing_type, confidence, opacity (1-5),
  leading_indicator_parallel (object|null), raw_text_excerpt

OPACITY: 1=official primary, 2=public minor interp, 3=credible secondary,
         4=inferred/operator, 5=speculative
CONFIDENCE: HIGH=primary citation present, MEDIUM=credible secondary,
            LOW=inferred/operator/non-expert

INCOMPLETE DATA PROTOCOL
  - Missing fields → null
  - Add extraction_notes entry naming missing value and resolution source
  - NEVER invent threshold values not in source
  - If too fragmentary → constraint_type: "INDETERMINATE"

────────────────────────────────────────────────────────────────────────────
FUNCTION B: REGIME ROUTING RULES
────────────────────────────────────────────────────────────────────────────

REGIME STATES (precedence: R3 > R4 > R2 > R1 > R0)

  R3 CASCADE_RISK   mult=0.0x — BOTH OI≥15% above 30d MA AND funding≥0.05%/8H
                    concurrent. OR prior 4H liq≥$150M. All entries halted.
  R4 VOLATILE       mult=0.25x — prior 4H liq $75M–$149M. OR ATR≥3× avg.
  R2 OVERHEATED     mult=0.5x(long)/1.0x(short) — OI≥15%MA OR fund≥0.05% OR RSI>73
  R1 TRENDING       mult=1.0x — EMA spread≥1.2%, RSI in band ≥2 candles,
                    OI<threshold, funding<0.03%
  R0 NEUTRAL        mult=1.0x — none of above; default state

BASE_RISK_UNIT = 570

GATES (evaluated in order; first FAIL terminates):
  Gate A1: Is regime R3? → FAIL=NO TRADE (all)
  Gate A2: Is regime R4? → if yes, capital_mult=0.25x, continue to signal gates
  Gate A3: Is regime R2? → if yes+LONG, capital_mult=0.5x; if SHORT, 1.0x
  Gate B1: EMA alignment — fast above slow for LONG / below for SHORT, spread≥1.2%
  Gate B2: RSI in signal band (40–65 LONG, 35–60 SHORT); block if RSI>73 LONG
  Gate C1: Prior 4H liq < $150M (absolute block regardless of regime)
  Gate C2: No duplicate open position in same direction on same asset

OUTPUT FORMAT
Return ONLY valid JSON. Root keys: "extraction" and "regime".
Null if function not executed. No preamble, no markdown fencing.
"""

# ─────────────────────────────────────────────────────────────────────────────
# FEW-SHOT EXAMPLES
# ─────────────────────────────────────────────────────────────────────────────
FEW_SHOT_TURNS = [
    # Example 1 — STR physical presence
    {
        "role": "user",
        "content": "Article 11(1)(iii) of the Private Lodging Business Act (民泊新法, effective June 15 2018) requires that a licensed management company (kanrisha) be physically reachable within 10 minutes of the registered property during all guest stay periods, by foot or vehicle. Failure constitutes grounds for registration cancellation under Article 33(1)(iv). Technology-based remote monitoring systems do not satisfy the proximity requirement."
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "extraction": {
                "constraints": [{
                    "constraint_id": "JP-PHYS-NATL-001",
                    "constraint_type": "PHYSICAL_PRESENCE",
                    "jurisdiction": {"country": "JP", "region": None, "municipality": None, "scope": "NATIONAL"},
                    "rule_description": "Licensed kanrisha must be physically reachable within 10 minutes (foot or vehicle) of registered property during all guest stays",
                    "threshold_value": 10,
                    "threshold_unit": "minutes",
                    "threshold_mode": "foot_or_vehicle",
                    "legal_citation": "Article 11(1)(iii), Private Lodging Business Act (民泊新法)",
                    "enforcement_citation": "Article 33(1)(iv)",
                    "effective_date": "2018-06-15",
                    "announcement_date": None,
                    "technology_substitution_permitted": False,
                    "technology_substitution_source": "Explicit — stated in source text",
                    "captive_vendor_type": "licensed_kanrisha",
                    "captive_vendor_required": True,
                    "unit_economics_impact": None,
                    "sourcing_type": "PRIMARY",
                    "confidence": "HIGH",
                    "opacity": 1,
                    "leading_indicator_parallel": None,
                    "raw_text_excerpt": "physically reachable within 10 minutes...Technology-based remote monitoring systems do not satisfy the proximity requirement"
                }],
                "extraction_notes": []
            },
            "regime": None
        })
    },
    # Example 2 — Regime R3 cascade
    {
        "role": "user",
        "content": json.dumps({
            "asset": "BTC-PERP",
            "signal_direction": "LONG",
            "oi_vs_30d_ma_pct": 20,
            "funding_8h_pct": 0.06,
            "liq_4h_usd": 40000000,
            "ema_fast_above_slow": True,
            "ema_spread_pct": 1.7,
            "rsi_14": 63,
            "atr_vs_20avg_mult": 1.3,
            "existing_position": "NONE"
        })
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "extraction": None,
            "regime": {
                "asset": "BTC-PERP",
                "regime": "R3_CASCADE_RISK",
                "capital_mult": 0.0,
                "effective_risk": 0.0,
                "direction": "NONE",
                "gate_results": {
                    "gate_a1": "FAIL",
                    "reason": "R3 Filter A: OI elevated 20% (≥15%) AND funding 0.06%/8H (≥0.05%) concurrent"
                },
                "regime_notes": ["All entries halted. Clears after 2 consecutive 4H candles below all R3 thresholds."]
            }
        })
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# JSON SCHEMA (inline; matches intake-schema-v1.0)
# ─────────────────────────────────────────────────────────────────────────────
INTAKE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["extraction", "regime"],
    "properties": {
        "extraction": {
            "oneOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "required": ["constraints", "extraction_notes"],
                    "properties": {
                        "constraints": {"type": "array"},
                        "extraction_notes": {"type": "array", "items": {"type": "string"}}
                    }
                }
            ]
        },
        "regime": {
            "oneOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "required": ["regime", "capital_mult", "effective_risk", "direction"],
                    "properties": {
                        "regime": {"type": "string", "enum": [
                            "R0_NEUTRAL", "R1_TRENDING", "R2_OVERHEATED",
                            "R3_CASCADE_RISK", "R4_VOLATILE"
                        ]},
                        "capital_mult": {"type": "number"},
                        "effective_risk": {"type": "number"},
                        "direction": {"type": "string", "enum": ["LONG", "SHORT", "BOTH", "NONE"]}
                    }
                }
            ]
        }
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# HARNESS CORE
# ─────────────────────────────────────────────────────────────────────────────

def build_regime_input(vector: dict) -> str:
    """Convert a regime test vector dict into the input text for the LLM."""
    return json.dumps({
        "asset": f"{vector.get('asset', 'BTC')}-PERP",
        "signal_direction": vector.get("signal_direction", "LONG"),
        "oi_vs_30d_ma_pct": vector.get("oi_vs_30d_ma_pct"),
        "funding_8h_pct": vector.get("funding_8h_pct"),
        "liq_4h_usd": vector.get("liq_4h_usd"),
        "ema_fast_above_slow": vector.get("ema_fast_above_slow"),
        "ema_spread_pct": vector.get("ema_spread_pct"),
        "rsi_14": vector.get("rsi_14"),
        "atr_vs_20avg_mult": vector.get("atr_vs_20avg_mult"),
        "existing_position": vector.get("existing_position", "NONE")
    })


def call_llm(input_text: str, mock: bool = False) -> dict:
    """
    Send input to Anthropic API and return parsed JSON response.
    In --mock mode, returns a synthetic response for scoring demonstration.
    """
    if mock:
        return _mock_response(input_text)

    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package not found. Run: pip install anthropic\n"
            "Or use --mock flag to run scoring without API calls."
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    messages = FEW_SHOT_TURNS + [{"role": "user", "content": input_text}]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=messages
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fencing
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    return json.loads(raw)


def _mock_response(input_text: str) -> dict:
    """
    Deterministic mock responses keyed to known input patterns.
    Used for --mock mode to demonstrate scoring without API calls.
    These represent what the LLM would return for each test vector.
    """
    # STR vectors — keyed by content substring
    if "Article 11(1)(iii)" in input_text and "10 minutes" in input_text:
        return {
            "extraction": {
                "constraints": [{
                    "constraint_id": "JP-PHYS-NATL-001",
                    "constraint_type": "PHYSICAL_PRESENCE",
                    "jurisdiction": {"country": "JP", "region": None, "municipality": None, "scope": "NATIONAL"},
                    "rule_description": "Licensed kanrisha must be physically reachable within 10 minutes of registered property",
                    "threshold_value": 10,
                    "threshold_unit": "minutes",
                    "threshold_mode": "foot_or_vehicle",
                    "legal_citation": "Article 11(1)(iii), Private Lodging Business Act",
                    "enforcement_citation": "Article 33(1)(iv)",
                    "effective_date": "2018-06-15",
                    "announcement_date": None,
                    "technology_substitution_permitted": False,
                    "technology_substitution_source": "Explicit — stated in source",
                    "captive_vendor_type": "licensed_kanrisha",
                    "captive_vendor_required": True,
                    "unit_economics_impact": None,
                    "sourcing_type": "PRIMARY",
                    "confidence": "HIGH",
                    "opacity": 1,
                    "leading_indicator_parallel": None,
                    "raw_text_excerpt": "physically reachable within 10 minutes...do not satisfy the proximity requirement"
                }],
                "extraction_notes": []
            },
            "regime": None
        }

    elif "Colliers" in input_text and "15-20%" in input_text:
        return {
            "extraction": {
                "constraints": [{
                    "constraint_id": "JP-FEE-TKY-001",
                    "constraint_type": "FEE_FLOOR",
                    "jurisdiction": {"country": "JP", "region": "Tokyo", "municipality": None, "scope": "REGIONAL"},
                    "rule_description": "Kanrisha fees stable 15–20% of gross since 2018 despite IoT; combined platform+kanrisha floor ~31.5%",
                    "threshold_value": "15–20",
                    "threshold_unit": "percent_of_gross_revenue",
                    "threshold_mode": "market_observed_range",
                    "legal_citation": None,
                    "enforcement_citation": None,
                    "effective_date": "2018-06-15",
                    "announcement_date": None,
                    "technology_substitution_permitted": False,
                    "technology_substitution_source": "Inferred — IoT adoption has not reduced fees",
                    "captive_vendor_type": "licensed_kanrisha",
                    "captive_vendor_required": True,
                    "unit_economics_impact": {
                        "combined_floor_pct": 31.5,
                        "platform_fee_pct": 14,
                        "kanrisha_fee_range": "15–20"
                    },
                    "sourcing_type": "SECONDARY_SYNTHESIS",
                    "confidence": "MEDIUM",
                    "opacity": 3,
                    "leading_indicator_parallel": None,
                    "raw_text_excerpt": "management fees...15-20% of gross revenue...combined cost floor of ~31.5%"
                }],
                "extraction_notes": [
                    "No legal citation — fee is market-observed. Primary source: Japan Tourism Agency annual operator survey."
                ]
            },
            "regime": None
        }

    elif "Osaka" in input_text and "27 of 34" in input_text:
        return {
            "extraction": {
                "constraints": [
                    {
                        "constraint_id": "JP-GEO-OSK-001",
                        "constraint_type": "GEOGRAPHIC_EXCLUSION",
                        "jurisdiction": {"country": "JP", "region": "Osaka Prefecture", "municipality": "27 of 34 municipalities", "scope": "MUNICIPAL"},
                        "rule_description": "27 of 34 Osaka Prefecture municipalities suspended new minpaku applications as of September 30 2025",
                        "threshold_value": "27/34",
                        "threshold_unit": "municipalities_suspended",
                        "threshold_mode": "new_application_suspension",
                        "legal_citation": None,
                        "enforcement_citation": None,
                        "effective_date": "2025-09-30",
                        "announcement_date": "2025-09-30",
                        "technology_substitution_permitted": None,
                        "technology_substitution_source": None,
                        "captive_vendor_type": None,
                        "captive_vendor_required": None,
                        "unit_economics_impact": None,
                        "sourcing_type": "SECONDARY_SYNTHESIS",
                        "confidence": "MEDIUM",
                        "opacity": 2,
                        "leading_indicator_parallel": None,
                        "raw_text_excerpt": "27 of 34 Osaka Prefecture municipalities formally suspended new minpaku applications"
                    },
                    {
                        "constraint_id": "JP-ENF-OSK-001",
                        "constraint_type": "ENFORCEMENT_ACTION",
                        "jurisdiction": {"country": "JP", "region": "Osaka Prefecture", "municipality": None, "scope": "REGIONAL"},
                        "rule_description": "Fines increased to up to 1,000,000 JPY per violation; Nuisance Minpaku Eradication Team operational July 2025",
                        "threshold_value": 1000000,
                        "threshold_unit": "JPY_per_violation_maximum",
                        "threshold_mode": "fine_ceiling",
                        "legal_citation": None,
                        "enforcement_citation": None,
                        "effective_date": "2025-07",
                        "announcement_date": None,
                        "technology_substitution_permitted": None,
                        "technology_substitution_source": None,
                        "captive_vendor_type": None,
                        "captive_vendor_required": None,
                        "unit_economics_impact": None,
                        "sourcing_type": "SECONDARY_SYNTHESIS",
                        "confidence": "MEDIUM",
                        "opacity": 2,
                        "leading_indicator_parallel": None,
                        "raw_text_excerpt": "Fines...increased to up to 1000000 JPY per violation"
                    }
                ],
                "extraction_notes": [
                    "Specific municipality names not listed in source — field set to descriptive string. Primary source: Osaka Prefecture official gazette."
                ]
            },
            "regime": None
        }

    elif "MHLW" in input_text and "1:3" in input_text:
        return {
            "extraction": {
                "constraints": [{
                    "constraint_id": "JP-LI-KAIGO-001",
                    "constraint_type": "LEADING_INDICATOR",
                    "jurisdiction": {"country": "JP", "region": None, "municipality": None, "scope": "NATIONAL"},
                    "rule_description": "MHLW 1:3 carer-to-resident ratio unchanged despite robotic adoption; technology is task assistance only, not presence substitution",
                    "threshold_value": "1:3",
                    "threshold_unit": "carer_to_resident_ratio",
                    "threshold_mode": "staffing_floor",
                    "legal_citation": "Article 14, Long-Term Care Insurance Act (介護保険法)",
                    "enforcement_citation": None,
                    "effective_date": None,
                    "announcement_date": "2024-03",
                    "technology_substitution_permitted": False,
                    "technology_substitution_source": "Explicit — MHLW guidance March 2024",
                    "captive_vendor_type": None,
                    "captive_vendor_required": False,
                    "unit_economics_impact": None,
                    "sourcing_type": "PRIMARY",
                    "confidence": "HIGH",
                    "opacity": 1,
                    "leading_indicator_parallel": {
                        "target_sector": "short_term_rental",
                        "analog_sector": "elder_care_kaigo",
                        "signal_type": "PRIMARY",
                        "signal_logic": "Kaigo ratio is closest analog to STR proximity rule — both physical presence mandates resistant to tech substitution",
                        "trigger_condition": "MHLW announces ratio relaxation or tech substitution pilot",
                        "current_status": "Review pending, no timeline"
                    },
                    "raw_text_excerpt": "robots assist present carers; they do not substitute for the legal presence requirement"
                }],
                "extraction_notes": ["No MHLW review timeline in source. Monitor MHLW press releases."]
            },
            "regime": None
        }

    elif "Dotonbori" in input_text and "Nothing official" in input_text:
        return {
            "extraction": {
                "constraints": [{
                    "constraint_id": "JP-INDET-OSK-001",
                    "constraint_type": "INDETERMINATE",
                    "jurisdiction": {"country": "JP", "region": "Osaka", "municipality": "Dotonbori-area wards", "scope": "WARD"},
                    "rule_description": "Unverified reports of stricter STR enforcement near Dotonbori; no official publication",
                    "threshold_value": None,
                    "threshold_unit": None,
                    "threshold_mode": None,
                    "legal_citation": None,
                    "enforcement_citation": None,
                    "effective_date": None,
                    "announcement_date": None,
                    "technology_substitution_permitted": None,
                    "technology_substitution_source": None,
                    "captive_vendor_type": None,
                    "captive_vendor_required": None,
                    "unit_economics_impact": None,
                    "sourcing_type": "OPERATOR_COMMENTARY",
                    "confidence": "LOW",
                    "opacity": 5,
                    "leading_indicator_parallel": None,
                    "raw_text_excerpt": "wards near Dotonbori are cracking down harder on unlicensed rentals. Nothing official yet."
                }],
                "extraction_notes": [
                    "Input is operator rumour — INDETERMINATE. Do not route to risk model until confidence >= MEDIUM.",
                    "Resolution: Osaka City ward office gazettes, Japan Tourism Agency registration portal."
                ]
            },
            "regime": None
        }

    # Regime vectors — keyed by JSON content
    else:
        try:
            data = json.loads(input_text)
            return _mock_regime_response(data)
        except Exception:
            return {"extraction": {"constraints": [], "extraction_notes": ["Unable to parse input"]}, "regime": None}


def _mock_regime_response(data: dict) -> dict:
    """Compute regime classification deterministically from input data."""
    oi_pct    = data.get("oi_vs_30d_ma_pct", 0)
    funding   = data.get("funding_8h_pct", 0)
    liq_4h    = data.get("liq_4h_usd", 0)
    ema_above = data.get("ema_fast_above_slow", False)
    spread    = data.get("ema_spread_pct", 0)
    rsi       = data.get("rsi_14", 50)
    atr_mult  = data.get("atr_vs_20avg_mult", 1.0)
    direction = data.get("signal_direction", "LONG")
    existing  = data.get("existing_position", "NONE")
    asset     = data.get("asset", "BTC-PERP")

    oi_elevated  = oi_pct >= 15
    funding_hot  = funding >= 0.05
    liq_extreme  = liq_4h >= 150_000_000
    liq_volatile = 75_000_000 <= liq_4h < 150_000_000
    atr_spike    = atr_mult >= 3.0

    # R3 check
    if (oi_elevated and funding_hot) or liq_extreme:
        return {
            "extraction": None,
            "regime": {
                "asset": asset,
                "regime": "R3_CASCADE_RISK",
                "capital_mult": 0.0,
                "effective_risk": 0.0,
                "direction": "NONE",
                "gate_results": {"gate_a1": "FAIL", "reason": "R3 triggered"},
                "regime_notes": ["All entries halted"]
            }
        }

    # R4 check
    if liq_volatile or atr_spike:
        mult = 0.25
        return {
            "extraction": None,
            "regime": {
                "asset": asset,
                "regime": "R4_VOLATILE",
                "capital_mult": mult,
                "effective_risk": 570 * mult,
                "direction": direction,
                "gate_results": {"gate_a1": "PASS", "gate_a2": "FAIL (R4)", "reason": "R4 triggered"},
                "regime_notes": ["Reduced sizing 0.25x"]
            }
        }

    # R2 check
    rsi_triggers_r2 = (direction == "LONG" and rsi > 73)
    if oi_elevated or funding_hot or rsi_triggers_r2:
        mult = 0.5 if direction == "LONG" else 1.0
        return {
            "extraction": None,
            "regime": {
                "asset": asset,
                "regime": "R2_OVERHEATED",
                "capital_mult": mult,
                "effective_risk": 570 * mult,
                "direction": direction,
                "gate_results": {"gate_a1": "PASS", "gate_a2": "PASS", "gate_a3": "FAIL (R2)" if direction == "LONG" else "PASS (short)"},
                "regime_notes": [f"R2 asymmetric: {'0.5x long' if direction == 'LONG' else '1.0x short'}"]
            }
        }

    # Signal gates
    ema_aligned = (ema_above and direction == "LONG") or (not ema_above and direction == "SHORT")
    spread_ok   = spread >= 1.2
    rsi_ok      = (40 <= rsi <= 65) if direction == "LONG" else (35 <= rsi <= 60)
    dup         = (existing == direction)

    if not ema_aligned or not spread_ok:
        return {
            "extraction": None,
            "regime": {
                "asset": asset,
                "regime": "R1_TRENDING",
                "capital_mult": 1.0,
                "effective_risk": 570.0,
                "direction": direction,
                "gate_results": {"gate_b1": "FAIL", "reason": f"EMA not aligned or spread {spread}% < 1.2%"},
                "regime_notes": ["Gate B1 fail — no trade"]
            }
        }

    if not rsi_ok or rsi > 73:
        return {
            "extraction": None,
            "regime": {
                "asset": asset,
                "regime": "R1_TRENDING",
                "capital_mult": 1.0,
                "effective_risk": 570.0,
                "direction": direction,
                "gate_results": {"gate_b2": "FAIL", "reason": f"RSI {rsi} outside signal band"},
                "regime_notes": ["Gate B2 fail — no trade"]
            }
        }

    if dup:
        return {
            "extraction": None,
            "regime": {
                "asset": asset,
                "regime": "R1_TRENDING",
                "capital_mult": 1.0,
                "effective_risk": 570.0,
                "direction": direction,
                "gate_results": {"gate_c2": "FAIL", "reason": "Duplicate position"},
                "regime_notes": ["Gate C2 fail — no trade"]
            }
        }

    return {
        "extraction": None,
        "regime": {
            "asset": asset,
            "regime": "R1_TRENDING",
            "capital_mult": 1.0,
            "effective_risk": 570.0,
            "direction": direction,
            "gate_results": {
                "gate_a1": "PASS", "gate_a2": "PASS", "gate_a3": "PASS",
                "gate_b1": "PASS", "gate_b2": "PASS",
                "gate_c1": "PASS", "gate_c2": "PASS"
            },
            "regime_notes": ["All gates pass — execute at full size"]
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCORING MODULE
# ─────────────────────────────────────────────────────────────────────────────

def validate_schema(response: dict) -> tuple[bool, list[str]]:
    """Check structural conformance against intake-schema-v1.0."""
    errors = []
    try:
        import jsonschema
        jsonschema.validate(instance=response, schema=INTAKE_SCHEMA)
    except ImportError:
        # Manual check if jsonschema not installed
        if "extraction" not in response:
            errors.append("Missing root key: extraction")
        if "regime" not in response:
            errors.append("Missing root key: regime")
    except Exception as e:
        errors.append(f"Schema validation error: {e}")
    return len(errors) == 0, errors


def score_str_vector(response: dict, vector: dict) -> dict:
    """Score an STR constraint extraction response against expected output."""
    expected = vector["expected"]
    issues   = []
    checks   = {}

    ext = (response.get("extraction") or {})
    constraints = ext.get("constraints", [])

    # Multi-constraint vector
    if "constraint_count_min" in expected:
        ok = len(constraints) >= expected["constraint_count_min"]
        checks["constraint_count"] = ok
        if not ok:
            issues.append(f"Expected ≥{expected['constraint_count_min']} constraints, got {len(constraints)}")

    if "contains_types" in expected:
        found_types = {c.get("constraint_type") for c in constraints}
        for t in expected["contains_types"]:
            ok = t in found_types
            checks[f"has_type_{t}"] = ok
            if not ok:
                issues.append(f"Missing constraint type: {t}")

    if "enforcement_threshold_value" in expected:
        enf = next((c for c in constraints if c.get("constraint_type") == "ENFORCEMENT_ACTION"), None)
        if enf:
            ok = enf.get("threshold_value") == expected["enforcement_threshold_value"]
            checks["enforcement_threshold"] = ok
            if not ok:
                issues.append(f"Enforcement threshold: got {enf.get('threshold_value')}, expected {expected['enforcement_threshold_value']}")
        else:
            checks["enforcement_threshold"] = False
            issues.append("No ENFORCEMENT_ACTION constraint found")

    # Single-constraint vector
    c = constraints[0] if constraints else {}

    if "constraint_type" in expected:
        ok = c.get("constraint_type") == expected["constraint_type"]
        checks["constraint_type"] = ok
        if not ok:
            issues.append(f"constraint_type: got '{c.get('constraint_type')}', expected '{expected['constraint_type']}'")

    if "threshold_value" in expected:
        ok = c.get("threshold_value") == expected["threshold_value"]
        checks["threshold_value"] = ok
        if not ok:
            issues.append(f"threshold_value: got {c.get('threshold_value')!r}, expected {expected['threshold_value']!r}")

    if "threshold_value_contains" in expected:
        tv = str(c.get("threshold_value", ""))
        ok = expected["threshold_value_contains"] in tv
        checks["threshold_value_contains"] = ok
        if not ok:
            issues.append(f"threshold_value should contain '{expected['threshold_value_contains']}', got '{tv}'")

    if "threshold_unit" in expected:
        ok = c.get("threshold_unit") == expected["threshold_unit"]
        checks["threshold_unit"] = ok
        if not ok:
            issues.append(f"threshold_unit: got '{c.get('threshold_unit')}', expected '{expected['threshold_unit']}'")

    for bool_field in ["technology_substitution_permitted", "captive_vendor_required"]:
        if bool_field in expected:
            ok = c.get(bool_field) == expected[bool_field]
            checks[bool_field] = ok
            if not ok:
                issues.append(f"{bool_field}: got {c.get(bool_field)!r}, expected {expected[bool_field]!r}")

    if "confidence" in expected:
        ok = c.get("confidence") == expected["confidence"]
        checks["confidence"] = ok
        if not ok:
            issues.append(f"confidence: got '{c.get('confidence')}', expected '{expected['confidence']}'")

    if "confidence_max" in expected:
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        ok = order.get(c.get("confidence", "LOW"), 0) <= order.get(expected["confidence_max"], 3)
        checks["confidence_max"] = ok
        if not ok:
            issues.append(f"confidence should be ≤ {expected['confidence_max']}, got '{c.get('confidence')}'")

    if "opacity" in expected:
        ok = c.get("opacity") == expected["opacity"]
        checks["opacity"] = ok
        if not ok:
            issues.append(f"opacity: got {c.get('opacity')}, expected {expected['opacity']}")

    if "opacity_max" in expected:
        ok = (c.get("opacity") or 5) <= expected["opacity_max"]
        checks["opacity_max"] = ok
        if not ok:
            issues.append(f"opacity should be ≤ {expected['opacity_max']}, got {c.get('opacity')}")

    if "opacity_min" in expected:
        ok = (c.get("opacity") or 0) >= expected["opacity_min"]
        checks["opacity_min"] = ok
        if not ok:
            issues.append(f"opacity should be ≥ {expected['opacity_min']}, got {c.get('opacity')}")

    if "sourcing_type" in expected:
        ok = c.get("sourcing_type") == expected["sourcing_type"]
        checks["sourcing_type"] = ok
        if not ok:
            issues.append(f"sourcing_type: got '{c.get('sourcing_type')}', expected '{expected['sourcing_type']}'")

    if "legal_citation" in expected and expected["legal_citation"] is None:
        ok = c.get("legal_citation") is None
        checks["legal_citation_null"] = ok
        if not ok:
            issues.append(f"legal_citation should be null, got '{c.get('legal_citation')}'")

    if "legal_citation_contains" in expected:
        lc = c.get("legal_citation") or ""
        ok = expected["legal_citation_contains"] in lc
        checks["legal_citation_contains"] = ok
        if not ok:
            issues.append(f"legal_citation should contain '{expected['legal_citation_contains']}', got '{lc}'")

    if "threshold_value" in expected and expected["threshold_value"] is None:
        ok = c.get("threshold_value") is None
        checks["threshold_value_null"] = ok
        if not ok:
            issues.append(f"threshold_value should be null, got {c.get('threshold_value')!r}")

    if expected.get("unit_economics_impact_not_null"):
        ok = c.get("unit_economics_impact") is not None
        checks["unit_economics_not_null"] = ok
        if not ok:
            issues.append("unit_economics_impact should not be null")

    if expected.get("leading_indicator_parallel_not_null"):
        ok = c.get("leading_indicator_parallel") is not None
        checks["leading_indicator_not_null"] = ok
        if not ok:
            issues.append("leading_indicator_parallel should not be null")

    if "leading_indicator_signal_type" in expected:
        li = c.get("leading_indicator_parallel") or {}
        ok = li.get("signal_type") == expected["leading_indicator_signal_type"]
        checks["leading_indicator_signal_type"] = ok
        if not ok:
            issues.append(f"leading_indicator signal_type: got '{li.get('signal_type')}', expected '{expected['leading_indicator_signal_type']}'")

    if expected.get("extraction_notes_not_empty"):
        notes = ext.get("extraction_notes", [])
        ok = len(notes) > 0
        checks["extraction_notes_not_empty"] = ok
        if not ok:
            issues.append("extraction_notes should not be empty for indeterminate input")

    passed = sum(1 for v in checks.values() if v)
    total  = len(checks)
    return {"checks": checks, "issues": issues, "passed": passed, "total": total}


def score_regime_vector(response: dict, vector: dict) -> dict:
    """Score a regime routing response against expected output."""
    issues = []
    checks = {}

    regime_out = response.get("regime") or {}

    expected_regime = vector.get("regime")
    got_regime      = regime_out.get("regime")
    checks["regime"] = got_regime == expected_regime
    if not checks["regime"]:
        issues.append(f"regime: got '{got_regime}', expected '{expected_regime}'")

    expected_mult = vector.get("capital_mult")
    got_mult      = regime_out.get("capital_mult")
    checks["capital_mult"] = got_mult == expected_mult
    if not checks["capital_mult"]:
        issues.append(f"capital_mult: got {got_mult}, expected {expected_mult}")

    expected_risk = vector.get("effective_risk_usd")
    got_risk      = regime_out.get("effective_risk")
    if expected_risk is not None:
        checks["effective_risk"] = abs((got_risk or 0) - expected_risk) < 0.01
        if not checks["effective_risk"]:
            issues.append(f"effective_risk: got {got_risk}, expected {expected_risk}")

    expected_verdict = vector.get("verdict", "EXECUTE")
    expected_dir     = "NONE" if expected_verdict == "NO TRADE" else "LONG"
    got_dir          = regime_out.get("direction", "")
    checks["direction_none_on_halt"] = not (expected_verdict == "NO TRADE" and got_dir != "NONE")
    if not checks["direction_none_on_halt"]:
        issues.append(f"direction should be NONE for NO TRADE verdict, got '{got_dir}'")

    passed = sum(1 for v in checks.values() if v)
    total  = len(checks)
    return {"checks": checks, "issues": issues, "passed": passed, "total": total}


# ─────────────────────────────────────────────────────────────────────────────
# RUN LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_vector(vector: dict, vector_type: str, mock: bool) -> dict:
    """Run one vector end-to-end: call LLM, validate schema, score."""
    vid   = vector.get("id", "?")
    name  = vector.get("scenario_name", "")
    t0    = time.time()
    result = {
        "id": vid,
        "name": name,
        "type": vector_type,
        "status": None,
        "schema_valid": None,
        "schema_errors": [],
        "score_passed": 0,
        "score_total": 0,
        "field_issues": [],
        "latency_ms": 0,
        "error": None,
        "raw_response": None,
    }

    try:
        if vector_type == "regime":
            input_text = build_regime_input(vector)
        else:
            input_text = vector["input_text"]

        response = call_llm(input_text, mock=mock)
        result["raw_response"] = response

        # Schema check
        schema_ok, schema_errs = validate_schema(response)
        result["schema_valid"]  = schema_ok
        result["schema_errors"] = schema_errs

        # Field scoring
        if vector_type == "str":
            scoring = score_str_vector(response, vector)
        else:
            scoring = score_regime_vector(response, vector)

        result["score_passed"] = scoring["passed"]
        result["score_total"]  = scoring["total"]
        result["field_issues"] = scoring["issues"]

        all_ok = schema_ok and scoring["passed"] == scoring["total"]
        result["status"] = "PASS" if all_ok else "FAIL"

    except Exception as e:
        result["status"] = "ERROR"
        result["error"]  = str(e)
        traceback.print_exc()

    result["latency_ms"] = int((time.time() - t0) * 1000)
    return result


def run_all(mock: bool = False, vector_filter: Optional[str] = None,
            type_filter: Optional[str] = None) -> list[dict]:
    """Load all vectors and run the harness."""

    str_path    = os.path.join(VECTORS_DIR, "str_vectors.json")
    regime_path = os.path.join(VECTORS_DIR, "regime_vectors.json")

    results = []

    if type_filter in (None, "str") and os.path.exists(str_path):
        with open(str_path) as f:
            str_vectors = json.load(f)
        for v in str_vectors:
            if vector_filter and str(v.get("id")) != vector_filter:
                continue
            print(f"  Running STR vector {v['id']} — {v['scenario_name']} ...", end=" ", flush=True)
            r = run_vector(v, "str", mock)
            print(r["status"])
            results.append(r)

    if type_filter in (None, "regime") and os.path.exists(regime_path):
        with open(regime_path) as f:
            regime_vectors = json.load(f)
        for v in regime_vectors:
            if vector_filter and str(v.get("id")) != str(vector_filter):
                continue
            print(f"  Running Regime vector #{v['id']} — {v['scenario_name']} ...", end=" ", flush=True)
            r = run_vector(v, "regime", mock)
            print(r["status"])
            results.append(r)

    return results


def write_log(results: list[dict]) -> str:
    """Write structured JSON run log and return path."""
    ts       = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(LOGS_DIR, f"run_{ts}.json")

    passed  = sum(1 for r in results if r["status"] == "PASS")
    failed  = sum(1 for r in results if r["status"] == "FAIL")
    errors  = sum(1 for r in results if r["status"] == "ERROR")
    total   = len(results)

    log = {
        "run_id": ts,
        "module": "HM-INTAKE-001",
        "schema": "intake-schema-v1.0",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0
        },
        "results": results
    }

    with open(log_path, "w") as f:
        json.dump(log, f, indent=2, default=str)

    return log_path


def print_summary(results: list[dict]) -> None:
    """Print a human-readable run summary to stdout."""
    passed = sum(1 for r in results if r["status"] == "PASS")
    total  = len(results)

    print("\n" + "═" * 72)
    print(f"  HIVE MIND VALIDATION HARNESS — RUN SUMMARY")
    print("═" * 72)
    print(f"  {'ID':<12} {'TYPE':<8} {'STATUS':<8} {'SCORE':<10} {'LATENCY':<10}  ISSUES")
    print("  " + "─" * 68)

    for r in results:
        score_str = f"{r['score_passed']}/{r['score_total']}"
        issues    = "; ".join(r["field_issues"][:2]) if r["field_issues"] else "—"
        if len(r["field_issues"]) > 2:
            issues += f" (+{len(r['field_issues'])-2} more)"
        status_sym = {"PASS": "✓ PASS", "FAIL": "✗ FAIL", "ERROR": "! ERROR"}.get(r["status"], r["status"])
        print(f"  {str(r['id']):<12} {r['type']:<8} {status_sym:<8} {score_str:<10} {str(r['latency_ms'])+'ms':<10}  {issues}")

    print("  " + "─" * 68)
    pct = round(passed / total * 100, 1) if total else 0
    print(f"  RESULT: {passed}/{total} passed ({pct}%)")
    print("═" * 72 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hive Mind Validation Harness HM-VALID-001")
    parser.add_argument("--mock",   action="store_true", help="Use mock LLM responses (no API call)")
    parser.add_argument("--vector", type=str, default=None, help="Run single vector by ID")
    parser.add_argument("--type",   type=str, default=None, choices=["str", "regime"], help="Filter by vector type")
    args = parser.parse_args()

    print(f"\nHive Mind Validation Harness — HM-VALID-001")
    print(f"Mode: {'MOCK' if args.mock else 'LIVE API'} | {datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

    results  = run_all(mock=args.mock, vector_filter=args.vector, type_filter=args.type)
    log_path = write_log(results)
    print_summary(results)
    print(f"  Run log written: {log_path}\n")


if __name__ == "__main__":
    main()
