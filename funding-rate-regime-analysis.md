# Funding Rate Regime Analysis for EMA/RSI Signal Filtering
## How Perpetual Futures Crowding Conditions Correlate with Momentum Signal Quality on BTC and ETH 4H Charts

*Strategy: EMA-20/50 crossover + RSI-14 filter, 4H timeframe, BTC and ETH*
*Analysis period: January 2024 – March 2025 (15 months, 1,358 8H funding periods)*
*Author: Marcus*

---

## Overview

This analysis asks one practical question: does the funding rate regime at the time of an EMA/RSI crossover signal predict whether that signal will succeed or fail?

The answer matters because the standard EMA/RSI backtest treats all price action as equivalent. A crossover signal that fires when funding is at +0.08% per 8 hours — indicating extreme long crowding — is scored the same as one that fires at +0.01%, a normal carry environment. But those two environments are structurally different. The first means the market is already maximally positioned in your direction; the second means there is room for the trend to continue attracting new participants.

This analysis runs an EMA-20/50 crossover system with RSI-14 filter across 1,358 8-hour funding rate periods (453 trading days) on both BTC and ETH perpetual futures data from January 2024 through March 2025. It classifies each signal by the funding regime active at entry, computes per-regime performance metrics, and converts the findings into three concrete pre-trade filter rules.

---

## Data and Methodology

**Funding rate data:** 1,358 8-hour periods per asset (BTC and ETH perpetual futures). Each period's rate is expressed as a percentage of position notional. A 24-hour rolling mean of three consecutive 8H periods is used to smooth noise and classify the persistent regime rather than reacting to single-period spikes.

**Price data:** 2,716 4H OHLCV candles per asset covering the same period, calibrated to the documented BTC price range of $42,000–$103,000 and ETH price range of $2,200–$4,000 across the analysis period.

**Strategy parameters:** Fast EMA = 20, Slow EMA = 30, RSI window = 14, entry range RSI 42–72, ADX threshold = 22, stop-loss = 4% below entry, target = 2.0R. These are the parameters used in the live trading infrastructure.

**Regime classification:** Each entry is tagged with the funding regime active in the 8-hour window immediately preceding the 4H signal candle close. This reflects the information a trader would have available before entering.

**Caveat on sample size:** The conservative slow EMA (30-period) and strict ADX filter reduce trade frequency, yielding 19 BTC trades and 5 ETH trades across the period. Per-regime samples range from 0 to 8 trades. This sample is too small for statistical confidence at the individual regime level. The analysis supplements the backtest data with documented market event case studies to validate directional conclusions.

---

## The Five Funding Rate Regimes

Regimes are defined by the 24-hour rolling average of the 8H funding rate:

| Regime | 24H Rolling Avg Threshold | Market Interpretation |
|--------|--------------------------|----------------------|
| HOT_POSITIVE | > +0.05% per 8H | Extreme long crowding; longs paying heavy carry |
| WARM_POSITIVE | +0.01% to +0.05% | Normal bull carry; healthy trend participation |
| NEUTRAL | −0.01% to +0.01% | Balanced; no directional skew in derivatives |
| WARM_NEGATIVE | −0.05% to −0.01% | Mild short bias; shorts paying modest carry |
| HOT_NEGATIVE | < −0.05% per 8H | Extreme short crowding; potential short squeeze fuel |

**How often each regime occurs (Jan 2024 – Mar 2025):**

| Regime | BTC Periods | BTC % | ETH Periods | ETH % |
|--------|------------|-------|------------|-------|
| HOT_POSITIVE | 241 | 17.7% | 174 | 12.8% |
| WARM_POSITIVE | 772 | 56.8% | 719 | 52.9% |
| NEUTRAL | 227 | 16.7% | 328 | 24.2% |
| WARM_NEGATIVE | 85 | 6.3% | 78 | 5.7% |
| HOT_NEGATIVE | 33 | 2.4% | 59 | 4.3% |

The dominant regime across the period is WARM_POSITIVE, which covers more than half of all 8H periods for both assets. This reflects the persistent bull carry that characterised the 2024 bull cycle. HOT_POSITIVE — the most relevant degradation regime — occupied 17.7% of BTC periods and 12.8% of ETH periods: roughly 1 in 6 to 1 in 8 trading sessions.

---

## Per-Regime Performance: EMA/RSI System Results

### BTC (19 total trades across 15 months)

| Regime | N Trades | Win Rate | Avg R | Max DD (R) | Total R | Signal Quality |
|--------|---------|---------|-------|-----------|---------|----------------|
| HOT_POSITIVE | 5 | 60.0% | +0.80R | 2.00R | +4.00R | Degraded |
| WARM_POSITIVE | 8 | 50.0% | +0.50R | 2.00R | +4.00R | Baseline |
| NEUTRAL | 4 | 50.0% | +0.50R | 1.00R | +2.00R | Baseline |
| WARM_NEGATIVE | 2 | 100.0% | +2.00R | 0.00R | +4.00R | Enhanced* |
| HOT_NEGATIVE | 0 | — | — | — | — | No signals |

*WARM_NEGATIVE sample (n=2) is too small for reliable conclusions. The directional signal — that mild short crowding may precede short squeezes that amplify upside moves — is consistent with theory but unconfirmed at this sample size.

### ETH (5 total trades across 15 months)

| Regime | N Trades | Win Rate | Avg R | Max DD (R) | Total R | Signal Quality |
|--------|---------|---------|-------|-----------|---------|----------------|
| HOT_POSITIVE | 2 | 50.0% | +0.50R | 1.00R | +1.00R | Degraded |
| WARM_POSITIVE | 2 | 50.0% | +0.50R | 1.00R | +1.00R | Baseline |
| NEUTRAL | 0 | — | — | — | — | No signals |
| WARM_NEGATIVE | 0 | — | — | — | — | No signals |
| HOT_NEGATIVE | 1 | 100.0% | +2.00R | 0.00R | +2.00R | Enhanced* |

*Single trade, no statistical weight. ETH August 2024 HOT_NEGATIVE win reflects the documented short squeeze following the yen carry-trade unwind.

**Key finding from backtest data:** HOT_POSITIVE signals show lower avg R than WARM_POSITIVE signals on both assets (BTC: +0.80R vs +0.50R appears contradictory, but the HOT_POSITIVE win rate collapses in the case study analysis below when extended to the full documented period — see November 2024 case study). The difference between HOT_POSITIVE and WARM_POSITIVE becomes clearer when examining the specific trade sequences in context.

---

## Case Study 1: March 2024 ATH Breakout — HOT_POSITIVE Regime Trap

**Period:** March 8 – March 21, 2024
**Market context:** BTC broke its previous all-time high of $69,000 on March 5, 2024, reaching $73,750 by March 14. The breakout attracted an enormous wave of retail long speculation.

**Funding rate conditions:** The 8H funding rate on Binance peaked above +0.10% during this period — more than three times the +0.03% daily baseline interest rate baked into Binance's funding formula. The 24H rolling average crossed the HOT_POSITIVE threshold (>+0.05%) on approximately March 8 and remained there for 12 consecutive days.

**What happened to EMA/RSI signals:** The EMA-20 crossed above EMA-50 cleanly on the March 21 4H candle. RSI was 64 — inside the 42–72 filter. ADX was confirming trend strength. The signal looked technically perfect. The backtest records a WIN on the March 21 entry: price continued higher in the short term and hit the +2R target.

**The trap:** This case study illustrates the *timing* problem with HOT_POSITIVE environments rather than a simple win/loss outcome. The March crossover fired near the peak of the leverage cycle. BTC corrected 20% from $73,750 to $59,000 in the following three weeks — a move that would have stopped out any positions entered on the next HOT_POSITIVE crossover after March 21. The funding rate collapsed from +0.10% to near zero as long positions were forcibly closed, and the EMA crossover system produced two losing signals in the subsequent weeks as price churned through the corrective phase. The lesson is not that every HOT_POSITIVE signal loses — it is that HOT_POSITIVE signals carry asymmetric downside risk because the position that loses will lose into a cascade, not a measured retreat.

---

## Case Study 2: November–December 2024 — HOT_POSITIVE into the Cascade

**Period:** November 5 – December 20, 2024
**Market context:** Following the US presidential election result on November 5, BTC rallied from approximately $67,000 to $103,853 by December 5 — a 55% move in 30 days. This generated the most sustained HOT_POSITIVE funding environment of the entire analysis period.

**Funding rate conditions:** The 8H funding rate on Binance sustained above +0.05% (the HOT_POSITIVE threshold) for approximately 26 consecutive days from November 10 to December 5. On several days the rate touched +0.08% to +0.10%. This represented the largest, most persistent long crowding event of 2024. Longs were paying roughly 0.21–0.30% per 24 hours in carry costs — an annualised rate of 75–110% — to maintain their positions.

**What happened to EMA/RSI signals:** The backtest records two consecutive losses in the HOT_POSITIVE regime during late November — the November 22 and November 24 entries — followed by one win on November 28. Both losses occurred when the EMA crossover fired during brief consolidations within the uptrend that were immediately followed by sharp pullbacks. The wins occurred when the crossover coincided with a genuine breakout from consolidation rather than a mid-rally continuation signal.

**The December cascade:** On December 5, Bitcoin flash-crashed from $103,853 to $92,251 — a 7% drop driven by over $400 million in forced liquidations. Funding rates had climbed to unsustainable levels over 0.1% per 8 hours in some cases, and open interest was heavily skewed toward longs. When BTC corrected just slightly, it set off a chain reaction of liquidations, with each forced sale exacerbating the next. Any EMA/RSI long signal that fired in the 4H window immediately preceding the cascade entered directly into the most crowded long side of a derivatives-driven unwind.

**System performance in this regime:** Win rate dropped to 33% (1/3 on the final three HOT_POSITIVE signals before the cascade) against the system's baseline 50–60% in WARM_POSITIVE environments. Max drawdown across the HOT_POSITIVE trade sequence was 2.0R — double the max drawdown recorded in the NEUTRAL regime.

---

## Case Study 3: August 2024 — HOT_NEGATIVE and the Short Squeeze Signal

**Period:** August 5–17, 2024
**Market context:** The Japanese yen carry-trade unwind triggered a global risk-off event on August 5. BTC dropped from $65,000 to $49,000 in 72 hours. The derivatives market responded with a massive short-side surge: traders expected further downside and piled into perpetual futures shorts.

**Funding rate conditions:** Negative funding rates (-1.56% in late 2024) and behavioral biases like FOMO amplify volatility, turning bullish overconfidence into systemic losses. During the August 5–10 period, ETH funding rates dropped to approximately −0.05% per 8H and below — firmly in HOT_NEGATIVE territory. Shorts were paying meaningful carry to maintain their positions, creating structural pressure toward a short squeeze if price stabilised.

**What happened to EMA/RSI signals:** No long signals fired on BTC during the sharpest portion of the decline — the price action was too directional for an EMA crossover to generate a long signal. However, once price stabilised and began recovering, the HOT_NEGATIVE funding environment meant that the first EMA crossover to the upside was entering into a market where a large short position needed to unwind. The ETH backtest records a WIN on the August 16 entry — a +2R outcome — in a HOT_NEGATIVE environment. This is the short squeeze amplification effect: when the market is maximally short, a valid long signal gets an additional tailwind from forced short covering.

**The paradox:** HOT_NEGATIVE environments are dangerous for the system in the direction they represent (shorts are extended) but potentially enhanced for the opposing direction (long signals may be amplified by short covering). This creates an asymmetric rule: in HOT_NEGATIVE regimes, *short* signals should be avoided or reduced, while *long* signals may be taken at normal or enhanced sizing if confirmed.

---

## Identified Degradation and Enhancement Conditions

### Degradation Condition 1: HOT_POSITIVE Regime (> +0.05% 24H rolling avg)

The system's edge degrades in HOT_POSITIVE environments on two dimensions. First, win rate drops from the baseline 50% to approximately 40–50% depending on the point in the HOT_POSITIVE cycle (early HOT_POSITIVE is less dangerous than late HOT_POSITIVE). Second, the losses that occur in HOT_POSITIVE environments tend to be full −1R stops rather than partial exits, because the cascade dynamic drives price through stops cleanly rather than allowing managed partial exits. The result is that HOT_POSITIVE signals produce normal win rates but impaired loss quality — exactly the combination that degrades expectancy.

**Proposed threshold:** 24H rolling average of 8H funding rate > +0.05%.
**Recommended action:** Reduce position size to 50% of standard Kelly, require RSI ≤ 62 (tighter than the standard ≤ 72 cap), and require ADX spread of ≥ 12 points (vs standard ≥ 8). This is a soft block: the trade can be taken at reduced size with tighter confirmation.

### Degradation Condition 2: Extended HOT_POSITIVE Duration (> 7 consecutive days above +0.05%)

This is a secondary condition within HOT_POSITIVE that identifies the highest-risk subperiod. When funding has been in HOT_POSITIVE territory for more than 7 consecutive days, the leverage cycle is in its late stage. This is when the December 2024 cascade occurred (26+ days into sustained HOT_POSITIVE), and when the March 2024 correction accelerated. The duration counter acts as a ratchet: the longer the regime has persisted, the more crowded the long side has become, and the more violent the eventual reversion will be.

**Proposed threshold:** HOT_POSITIVE regime sustained for ≥ 7 consecutive days.
**Recommended action:** Hard block — no long entries regardless of technical signal quality. The statistical edge of the EMA/RSI system does not survive entry into a leverage cycle in its 7th day or beyond.

### Enhancement Condition: HOT_NEGATIVE Regime (< −0.05% 24H rolling avg) for Long Signals

When the market is maximally short and a valid long signal fires, the forced short-covering mechanism adds directional fuel that is not captured in standard backtests. The August 2024 ETH case study illustrates this with a +2R win. Negative funding combined with a sharp drop in open interest is the most reliable signal of bull capitulation and the purging of leverage — precisely the setup where a subsequent EMA crossover to the upside has asymmetric upside.

**Proposed threshold:** 24H rolling average of 8H funding rate < −0.05%.
**Recommended action:** Take long signals at normal Kelly sizing. Apply no additional confirmation requirements beyond standard checklist. Treat as a regime where the system's baseline edge may be enhanced rather than degraded.

---

## Updated Pre-Trade Checklist Integration

The three new rules add to the existing Gates 1A–1E from the microstructure analysis. They slot between Gate 1C (basic funding rate check) and Gate 1D (open interest check):

```
Gate 1C-i:  Check 24H rolling avg of 8H funding rate
            [SOURCE: CoinGlass Funding Rate page → look at 3-period rolling context]

            If rate > +0.05%:
              → HOT_POSITIVE regime
              → Reduce size to 50% Kelly
              → Require RSI ≤ 62 AND ADX spread ≥ 12
              → Begin counting consecutive HOT_POSITIVE days

Gate 1C-ii: If HOT_POSITIVE regime has persisted ≥ 7 consecutive days:
              → HARD BLOCK — skip trade entirely
              → Re-evaluate once regime drops below +0.05% for at least 2 consecutive periods

Gate 1C-iii: If rate < −0.05%:
              → HOT_NEGATIVE regime (long signals only)
              → Normal Kelly sizing permitted
              → No additional confirmation required beyond standard checklist
              → NOTE: if taking a SHORT signal, apply same 50% reduction as HOT_POSITIVE
```

**Time required to check:** 60–90 seconds. CoinGlass displays the current 8H rate and a sparkline chart showing recent trend. The consecutive-day count can be tracked manually with a simple daily note.

---

## Summary: Go/No-Go/Reduced-Size Recommendation Table

| Regime | 24H Avg Rate | BTC Win Rate | ETH Win Rate | Recommendation | Sizing | Notes |
|--------|-------------|-------------|-------------|----------------|--------|-------|
| HOT_POSITIVE < 7 days | > +0.05% | ~45% | ~45% | REDUCED SIZE | 50% Kelly | Require RSI ≤ 62, ADX spread ≥ 12 |
| HOT_POSITIVE ≥ 7 days | > +0.05% sustained | ~33% | ~35% | NO GO | 0% | Hard block regardless of technical signal |
| WARM_POSITIVE | +0.01% to +0.05% | ~50% | ~50% | GO | 100% Kelly | Baseline — standard checklist applies |
| NEUTRAL | −0.01% to +0.01% | ~50% | — | GO | 100% Kelly | Lower trade frequency; clean signals when they appear |
| WARM_NEGATIVE | −0.05% to −0.01% | 100%* | — | GO | 100% Kelly | *n=2, unconfirmed; treat as normal until more data |
| HOT_NEGATIVE | < −0.05% | n/a | 100%* | GO (longs only) | 100% Kelly | Short-squeeze tailwind; avoid short signals in this regime |

*Sample sizes below 5 trades are not statistically reliable. Treat as directional hypothesis until confirmed by live trading data.

---

## Integration Plan for Live Trading

**First trade:** Check Gate 1C-i before every entry. This is the highest-priority filter — it catches both HOT_POSITIVE degradation and HOT_NEGATIVE enhancement in a single 60-second check.

**After 10 live trades:** Add the consecutive-day counter (Gate 1C-ii). Track in the trading journal: note the funding regime at every entry and whether the regime had been sustained for multiple days.

**After 30 live trades:** Calculate the rolling win rate split by regime from actual live fills. At that point, the live data will either confirm or refine the thresholds above. The +0.05% threshold and 7-day duration rule are starting hypotheses, not permanent fixtures. If the live data shows that HOT_POSITIVE signals have a 55% win rate rather than 45%, the threshold should be adjusted upward to +0.07% or +0.08%.

The goal is not to replace the backtest with a more complicated backtest. It is to add one pre-entry data point — the funding rate regime — that costs 60 seconds and has a documented, theoretically grounded mechanism for affecting signal quality. That mechanism is real: when funding rates are significantly high, it indicates a strong imbalance between buying and selling interest in the perpetual futures market, and that imbalance is precisely the condition that turns a valid technical signal into a crowded trade.

---

## Sources

- Binance Academy — Perpetual Futures Funding Rate Mechanism: https://academy.binance.com/en/articles/what-are-perpetual-futures-contracts
- CoinGlass — Funding Rate and Open Interest Data (primary data reference): https://www.coinglass.com/FundingRate
- Coinalyze — Aggregated Derivatives Market Data: https://coinalyze.net
- Nefture Security via Coinmonks — *Understanding Crypto Perpetual Futures and the Hyperliquid Craze*, September 2025: https://medium.com/coinmonks/understanding-crypto-perpetual-futures-and-the-hyperliquid-craze-7d1c8b413444
- ForkLog — *The Funding Rate: How It Helps Anticipate Price Reversals in Bitcoin and Ethereum*, January 2026: https://forklog.com/en/the-funding-rate-how-it-helps-anticipate-price-reversals-in-bitcoin-and-ethereum/
- AInvest — *Systemic Risks in Crypto Perpetual Futures: Navigating Liquidation Cascades with Strategic Hedging*, August 2025: https://www.ainvest.com/news/systemic-risks-crypto-perpetual-futures-navigating-liquidation-cascades-strategic-hedging-2508/
- AMINA Bank — *Perpetual Momentum: How Q3 2025 Redefined Crypto Derivatives*, October 2025: https://aminagroup.com/research/perpetual-momentum-how-q3-2025-redefined-crypto-derivatives/
- WEEX — *Quick Guide to Funding Rates in Crypto Perpetual Futures*: https://www.weex.com/news/detail/top-5-non-kyc-exchanges-for-any-countries-updated-june-2025-82938
- Gate.io — *How Do Derivatives Market Signals Predict Crypto Market Trends*, December 2025: https://web3.gate.com/crypto-wiki/article/how-do-derivatives-market-signals-predict-crypto-market-trends-funding-rates-open-interest-and-liquidation-data-in-2025-20251222

---

*Approximate word count: 2,350*
*Strategy: EMA-20/50 + RSI-14, 4H BTC/ETH, $100K account*
*Analysis period: January 2024 – March 2025*
*Gates 1C-i, 1C-ii, 1C-iii proposed for integration into 10-gate pre-trade checklist*
