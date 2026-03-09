# Hive Mind Risk Routing Logic Specification
### Version 1.0 — March 2026
**Author:** Marcus | **Status:** Draft — Pending Tier 1 Implementation Review  
**Applies to:** BTC-PERP, SOL-PERP, 4H timeframe  
**Derived from:** [Liquidation Cascade Impact Analysis (March 2026)]

---

## §1 — System Constants

All constants must be configurable via environment variable or config file. Hardcoding is a breaking violation.

| Constant | Value |
|---|---|
| `BASE_RISK_UNIT` | $570 |
| `BASELINE_EXPECTANCY_R` | +1.09 |
| `TIMEFRAME` | 4H |
| `EMA_FAST_PERIOD` | 21 |
| `EMA_SLOW_PERIOD` | 55 |
| `RSI_PERIOD` | 14 |
| `RSI_LONG_THRESHOLD` | 52–68 |
| `RSI_SHORT_THRESHOLD` | 32–48 |
| `RSI_OVERBOUGHT_BLOCK` | > 75 |
| `RSI_OVERSOLD_BLOCK` | < 25 |
| `OI_ELEVATION_THRESHOLD` | +15% vs 30-day MA |
| `FUNDING_RATE_HOT` | > 0.05% per 8H |
| `LIQ_BLOCK_THRESHOLD` | $150M per 4H candle |
| `LIQ_REDUCE_THRESHOLD` | $75M per 4H candle |
| `LIQ_CLEAR_THRESHOLD` | < $50M for 2 consecutive 4H candles |
| `ASSETS_IN_SCOPE` | BTC, SOL |

---

## §2 — Regime State Definitions

The agent classifies the current market into exactly one of five regime states at the open of each 4H candle. **Precedence (highest severity wins): R3 > R4 > R2 > R1 > R0.**

| State | Name | Capital Multiplier | Classification Criteria |
|---|---|---|---|
| `R0` | NEUTRAL | **1.0×** | OI within 15% of 30d MA. Funding -0.03% to +0.03% per 8H. Prior 4H liq < $50M. EMA spread within ±0.8% of price. Default operating state. |
| `R1` | TRENDING | **1.0×** | EMA_fast above/below EMA_slow by ≥ 1.2% of price. RSI in signal band for ≥ 2 consecutive 4H candles. OI below elevation threshold. Funding below 0.03%. |
| `R2` | OVERHEATED | **0.5× (longs) / 1.0× (shorts)** | EITHER: OI elevated ≥ 15% above 30d MA. OR: Funding ≥ 0.05% per 8H. OR: RSI > 73 on long candidate. One condition sufficient. |
| `R3` | CASCADE-RISK | **0.0×** | BOTH OI elevated AND funding hot concurrent (Filter A). OR: Prior 4H liq ≥ $150M (Filter B). All new long entries halted. Clears after 2 consecutive 4H candles below threshold. |
| `R4` | VOLATILE | **0.25×** | Prior 4H liq $75M–$149M. OR: ATR(14,4H) ≥ 3× its 20-period average. OR: EMA cross within prior 2 candles followed immediately by opposing RSI signal. |

---

## §3 — Regime Classifier Pseudocode

Evaluate at each 4H candle open before any signal processing.

```
// ─── Input snapshot ─────────────────────────────────────────────────────
INPUT:
  oi_current        // aggregate perpetual OI, USD notional, cross-exchange
  oi_30d_ma         // 30-day rolling mean of oi_current
  funding_8h        // latest 8H funding rate, cross-exchange aggregate
  liq_4h_vol        // prior 4H liquidation volume, asset-specific
  ema_fast          // EMA(21, 4H close)
  ema_slow          // EMA(55, 4H close)
  rsi               // RSI(14, 4H close)
  atr_current       // ATR(14, 4H)
  atr_20_avg        // 20-period average of ATR(14, 4H)
  price             // 4H candle open price

// ─── Derived conditions ──────────────────────────────────────────────────
oi_elevated    = (oi_current > oi_30d_ma * 1.15)
funding_hot    = (funding_8h > 0.0005)                  // 0.05% per 8H
liq_cascade    = (liq_4h_vol >= 150_000_000)            // $150M threshold
liq_elevated   = (liq_4h_vol >= 75_000_000)             // $75M threshold
ema_spread_pct = ABS(ema_fast - ema_slow) / price * 100
ema_trending   = (ema_spread_pct >= 1.2)
rsi_long_band  = (rsi >= 52 AND rsi <= 68)
rsi_short_band = (rsi >= 32 AND rsi <= 48)
rsi_overbought = (rsi > 75)
atr_volatile   = (atr_current >= atr_20_avg * 3.0)

// ─── Classification (precedence: highest severity first) ─────────────────
IF (oi_elevated AND funding_hot) OR liq_cascade:
    regime = "R3_CASCADE_RISK"
    capital_mult = 0.0

ELSE IF liq_elevated OR atr_volatile:
    regime = "R4_VOLATILE"
    capital_mult = 0.25

ELSE IF oi_elevated OR funding_hot OR rsi_overbought:
    regime = "R2_OVERHEATED"
    capital_mult = 0.5    // long entries only; shorts at 1.0×

ELSE IF ema_trending AND (rsi_long_band OR rsi_short_band):
    regime = "R1_TRENDING"
    capital_mult = 1.0

ELSE:
    regime = "R0_NEUTRAL"
    capital_mult = 1.0

RETURN { regime, capital_mult }
```

---

## §4 — Capital Weighting Matrix

Multipliers apply to `BASE_RISK_UNIT` ($570) to compute effective risk per trade.

| Regime | Direction | Multiplier | Effective Risk |
|---|---|---|---|
| R0 NEUTRAL | Long / Short | 1.0× | $570 |
| R1 TRENDING | Long / Short | 1.0× | $570 |
| R2 OVERHEATED | **Long** | **0.5×** | **$285** |
| R2 OVERHEATED | Short | 1.0× | $570 |
| R3 CASCADE-RISK | Long / Short | 0.0× | No entry |
| R4 VOLATILE | Long / Short | 0.25× | $142 |

> **Asymmetric Rule:** In R2, the capital reduction applies to long entries only. Elevated OI and positive funding represent crowded long positioning, which is directionally favorable for short momentum signals. This asymmetry does not apply in R3 or R4.

---

## §5 — Logic Gate Specification

### Gate Set A — Pre-Signal (Regime Gates)
Evaluated before signal computation. A Gate A failure skips signal computation entirely.

```
// Gate A1 — CASCADE HALT
IF regime == "R3_CASCADE_RISK":
    HALT_ALL_ENTRIES()
    LOG("Gate A1 FAIL: CASCADE_RISK regime active", {oi_elevated, funding_hot, liq_4h_vol})
    RETURN FALSE

// Gate A2 — OVERHEATED SIZING (long entries)
IF direction == "LONG" AND oi_elevated:
    capital_mult = 0.5
    LOG("Gate A2: OI elevated, long capital reduced to 0.5×")

IF direction == "LONG" AND funding_hot:
    capital_mult = MIN(capital_mult, 0.5)
    LOG("Gate A2: Funding hot, long capital reduced to 0.5×")

// Gate A3 — PRIOR LIQUIDATION VOLUME CHECK
IF liq_4h_vol >= 150_000_000:
    HALT_ALL_ENTRIES()
    LOG("Gate A3 FAIL: Active cascade detected", {liq_4h_vol})
    RETURN FALSE

ELSE IF liq_4h_vol >= 75_000_000:
    capital_mult = MIN(capital_mult, 0.25)
    LOG("Gate A3: Elevated liquidation, capital reduced to 0.25×")
```

### Gate Set B — Signal Quality (Momentum Gates)

```
// Gate B1 — EMA TREND ALIGNMENT
IF direction == "LONG":
    required = (ema_fast > ema_slow) AND (ema_spread_pct >= 0.4)
ELSE IF direction == "SHORT":
    required = (ema_fast < ema_slow) AND (ema_spread_pct >= 0.4)

IF NOT required:
    LOG("Gate B1 FAIL: EMA not aligned", {ema_fast, ema_slow, ema_spread_pct})
    RETURN FALSE

// Gate B2 — RSI BAND CONFIRMATION
IF direction == "LONG":
    IF NOT rsi_long_band:           // RSI must be 52–68
        LOG("Gate B2 FAIL: RSI not in long band", {rsi})
        RETURN FALSE
    IF rsi_overbought:               // Hard block: RSI > 75
        LOG("Gate B2 FAIL: RSI overbought hard block", {rsi})
        RETURN FALSE

IF direction == "SHORT":
    IF NOT rsi_short_band:           // RSI must be 32–48
        LOG("Gate B2 FAIL: RSI not in short band", {rsi})
        RETURN FALSE
    IF rsi < 25:                     // Hard block: RSI < 25
        LOG("Gate B2 FAIL: RSI oversold hard block", {rsi})
        RETURN FALSE
```

### Gate Set C — Execution Guards

```
// Gate C1 — CAPITAL FLOOR GUARD
effective_risk = BASE_RISK_UNIT * capital_mult

IF effective_risk < 50:
    LOG("Gate C1 FAIL: Effective risk below $50 floor, skip trade")
    RETURN FALSE

// Gate C2 — OPEN POSITION GUARD
IF open_positions[asset] > 0 AND direction == current_position_direction:
    LOG("Gate C2 FAIL: Duplicate directional entry blocked")
    RETURN FALSE

IF open_positions[asset] > 0 AND direction != current_position_direction:
    LOG("Gate C2 WARN: Opposite direction signal — evaluate exit first")
    TRIGGER_EXIT_REVIEW(asset)
    RETURN FALSE
    // Do not flip positions automatically. Human review required.
```

---

## §6 — Entry Gate Sequence (Ordered)

| Step | Gate | Condition | On Fail |
|---|---|---|---|
| 1 | A1 | Is regime R3? | Halt all entries. Return. |
| 2 | A2 | Is OI elevated OR funding hot (long entries)? | Reduce capital_mult to 0.5×. Continue. |
| 3 | A3 | Is prior 4H liq ≥ $150M? $75M–$149M? | ≥$150M: halt. $75–149M: reduce to 0.25×. |
| 4 | B1 | Is EMA_fast aligned (≥ 0.4% spread) in signal direction? | Block entry. Return. |
| 5 | B2 | Is RSI in valid band? Outside hard-block zones? | Block entry. Return. |
| 6 | C1 | Is effective_risk ≥ $50? | Skip trade. |
| 7 | C2 | Is there an existing open position in same asset? | Block (same direction). Exit review (opposite direction). |
| ✓ | — | All gates pass | Submit order at `BASE_RISK_UNIT × capital_mult`. Log all state. |

---

## §7 — Exit & Override Rules

```
// Mid-Position Regime Escalation to R3
IF regime escalates to "R3_CASCADE_RISK" AND position.direction == "LONG":
    ALERT_HUMAN("URGENT: R3 regime while long position open. Review stop.")
    TIGHTEN_STOP(position, trail_offset=0.005)   // 0.5% trail from current price

IF regime escalates to "R3_CASCADE_RISK" AND position.direction == "SHORT":
    LOG("R3 while short: cascade may accelerate in favorable direction. Hold.")
    MONITOR(position, interval="1H")

// Extreme cascade override ($500M+ threshold)
IF liq_4h_vol >= 500_000_000:
    ALERT_HUMAN("CRITICAL: Extreme cascade event. Manual override required.")
    PAUSE_AGENT()
    // Automated systems pause. Human must explicitly resume.

// R3 Clearance Condition
r3_clear_condition = (
    liq_4h_vol < 50_000_000
    AND NOT (oi_elevated AND funding_hot)
)

IF r3_clear_condition FOR consecutive_candles >= 2:
    regime = RECLASSIFY()   // re-run full classifier
    LOG("R3 cleared. New regime:", regime)
```

---

## §8 — Regime State Transition Table

| From | Trigger | To | Capital Effect | Action |
|---|---|---|---|---|
| R0 | OI elevated OR funding hot (single factor) | R2 | 1.0× → 0.5× long | Resize pending long entries. |
| R0 | OI elevated AND funding hot concurrent | R3 | → 0.0× | Halt entries. Alert human. |
| R0 | Prior 4H liq ≥ $75M | R4 | → 0.25× | Reduce size on new entries. |
| R2 | OI elevated AND funding hot concurrent | R3 | 0.5× → 0.0× | Halt entries. Alert human. |
| R2 | Prior 4H liq ≥ $150M | R3 | 0.5× → 0.0× | Halt entries. Alert human. |
| R2 | OI returns < 1.15× MA AND funding < 0.03% | R0/R1 | 0.5× → 1.0× | Restore full sizing on next signal. |
| R3 | liq < $50M AND NOT(OI+funding concurrent) × 2 candles | Reclassify | 0.0× → per new regime | Re-run classifier. Log clearance time. |
| R4 | Prior 4H liq < $50M AND ATR < 3× average | R0/R1 | 0.25× → 1.0× | Restore standard sizing. |

---

## §9 — Master Pseudocode: Agent Main Loop

```
ON CANDLE_OPEN(timeframe="4H", asset):

  // ── Step 1: Fetch market structure snapshot ──────────────────────────
  snapshot = FETCH_SNAPSHOT(asset)

  // ── Step 2: Regime classification ───────────────────────────────────
  { regime, capital_mult } = CLASSIFY_REGIME(snapshot)
  LOG_REGIME(regime, capital_mult, timestamp)

  // ── Step 3: Gate A — Regime gates ────────────────────────────────────
  IF NOT GATE_A1_CASCADE_HALT(regime):
      RETURN

  capital_mult = GATE_A2_OVERHEATED_SIZING(snapshot, direction, capital_mult)
  capital_mult = GATE_A3_LIQ_VOLUME(snapshot, capital_mult)

  IF capital_mult == 0.0:
      RETURN

  // ── Step 4: Signal computation ───────────────────────────────────────
  signal = COMPUTE_SIGNAL(snapshot.ema_fast, snapshot.ema_slow, snapshot.rsi)
  // signal = { direction: "LONG"|"SHORT"|"NONE" }

  IF signal.direction == "NONE":
      RETURN

  // ── Step 5: Gate B — Signal quality gates ────────────────────────────
  IF NOT GATE_B1_EMA_ALIGNMENT(snapshot, signal.direction):
      RETURN

  IF NOT GATE_B2_RSI_BAND(snapshot, signal.direction):
      RETURN

  // ── Step 6: Gate C — Execution guards ────────────────────────────────
  effective_risk = BASE_RISK_UNIT * capital_mult

  IF NOT GATE_C1_CAPITAL_FLOOR(effective_risk):
      RETURN

  IF NOT GATE_C2_OPEN_POSITION(asset, signal.direction):
      RETURN

  // ── Step 7: Execute ───────────────────────────────────────────────────
  order = BUILD_ORDER(asset, signal.direction, effective_risk)
  SUBMIT_ORDER(order)
  LOG_ENTRY(order, regime, capital_mult, signal)
```

---

## §10 — Data Source Map

| Variable | Primary Source | Fallback | Update Frequency | Notes |
|---|---|---|---|---|
| `oi_current` | CoinGlass OI (cross-exchange aggregate) | Coinalyze | Per 4H candle | Use USD notional |
| `oi_30d_ma` | Computed from CoinGlass 30d history | — | Per 4H candle | Rolling 30-day MA |
| `funding_8h` | CoinGlass funding dashboard | Coinalyze aggregated | Per 8H + predicted | Use predicted if settlement >4H away |
| `liq_4h_vol` | CoinGlass 4H liquidation chart, asset-filtered | Coinalyze 4H view | Per 4H candle close | Asset-specific, not cross-crypto total |
| `ema_fast/slow` | Computed from exchange OHLCV (Binance/Bybit) | TradingView | Real-time per candle | EMA(21) and EMA(55), 4H close |
| `rsi` | Computed from exchange OHLCV | TradingView | Real-time per candle | RSI(14), 4H close |
| `atr_current` | Computed from exchange OHLCV | TradingView | Per 4H candle | ATR(14, 4H) vs 20-period average |

> **Data Staleness Warning:** Any reading older than one 4H candle must be treated as missing data, not a clean signal. If both primary and fallback sources are stale, Gate A1 defaults to conservative behavior (block new entries) until fresh data is available. Log the data-unavailable condition explicitly.

---

## §11 — Changelog

| Version | Date | Author | Changes |
|---|---|---|---|
| v1.0 | March 2026 | Marcus | Initial specification. Five regime states (R0–R4), six logic gates (A1–A3, B1–B2, C1–C2), capital weighting matrix, state transition table, master pseudocode loop, data source map. Derived from Liquidation Cascade Impact Analysis (March 2026). |

---

*Post Fiat // Hive Mind Infrastructure // Marcus // March 2026*
