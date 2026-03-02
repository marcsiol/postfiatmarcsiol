"""
generate_and_analyse.py
Generates 15 months of realistic 8H funding rate and 4H price data for
BTC and ETH (Jan 2024 – Mar 2025), grounded in documented market events:

  - Jan 2024: ETF approval euphoria → sustained high positive funding
  - Mar 2024: ATH breakout → extreme positive funding, flash correction
  - Aug 2024: Yen carry-trade unwind → negative funding spike
  - Sep 2024: Choppy recovery → volatile/flipping regime
  - Nov-Dec 2024: Post-election rally → hot positive funding, Dec cascade
  - Jan-Mar 2025: Consolidation → neutral to warm positive regime

Then classifies 5 funding rate regimes and overlays EMA/RSI backtest trades
to compute per-regime win rate, avg R, max drawdown, and expectancy.
"""

import numpy as np
import json
from datetime import datetime, timezone

np.random.seed(2024)

# ══════════════════════════════════════════════════════════════════════════════
# 1.  DEFINE MARKET REGIME PHASES (documented real events)
# ══════════════════════════════════════════════════════════════════════════════
# Each phase: (label, duration_8h_periods, funding_mean_%,  funding_std_%,
#              price_drift_per_4h, price_vol_per_4h, regime_label)
# Funding in % per 8H period.  Drift and vol are for 4H price candles.

PHASES_BTC = [
    # Jan 2024 – ETF launch anticipation/approval: steadily positive funding
    ("Jan24_ETF_Hype",      90,  0.020, 0.008,  0.0006, 0.016, "warm_pos"),
    # Feb 2024 – sustained rally, funding heating up
    ("Feb24_Rally",         84,  0.032, 0.010,  0.0007, 0.018, "hot_pos"),
    # Mar 2024 – ATH breakout to $73k, extreme funding, correction spike
    ("Mar24_ATH",          100,  0.055, 0.020,  0.0004, 0.024, "hot_pos"),
    # Apr 2024 – Halving consolidation, funding cooling
    ("Apr24_Halving",       90,  0.015, 0.010, -0.0001, 0.014, "warm_pos"),
    # May-Jun 2024 – sideways chop, neutral funding
    ("MayJun24_Chop",      180,  0.008, 0.012, -0.0002, 0.013, "neutral"),
    # Jul 2024 – mild recovery, warm positive
    ("Jul24_Recovery",      84,  0.018, 0.009,  0.0004, 0.015, "warm_pos"),
    # Aug 2024 – Yen carry unwind: sharp negative funding spike
    ("Aug24_YenUnwind",     90, -0.045, 0.025, -0.0012, 0.028, "hot_neg"),
    # Sep 2024 – volatile recovery, funding flipping
    ("Sep24_Volatile",      90,  0.002, 0.030,  0.0002, 0.020, "volatile"),
    # Oct 2024 – renewed optimism, warming
    ("Oct24_Warmup",        90,  0.025, 0.012,  0.0006, 0.016, "warm_pos"),
    # Nov-Dec 2024 – post-election rally to $103k, extreme positive funding
    ("NovDec24_Rally",     180,  0.068, 0.022,  0.0009, 0.018, "hot_pos"),
    # Dec 2024 – flash crash to $92k on liquidation cascade
    ("Dec24_Cascade",       15, -0.020, 0.040, -0.0035, 0.040, "hot_neg"),
    # Late Dec 2024 – rebound
    ("LateDec24_Rebound",   45,  0.030, 0.015,  0.0005, 0.016, "warm_pos"),
    # Jan 2025 – consolidation, neutral
    ("Jan25_Consol",       100,  0.010, 0.012,  0.0001, 0.014, "neutral"),
    # Feb-Mar 2025 – gradual recovery
    ("FebMar25_Recovery",  120,  0.022, 0.010,  0.0004, 0.015, "warm_pos"),
]

PHASES_ETH = [
    ("Jan24_ETF_Hype",      90,  0.018, 0.010,  0.0005, 0.018, "warm_pos"),
    ("Feb24_Rally",         84,  0.028, 0.012,  0.0006, 0.020, "warm_pos"),
    ("Mar24_ATH",          100,  0.048, 0.022,  0.0003, 0.026, "hot_pos"),
    ("Apr24_Halving",       90,  0.012, 0.012, -0.0002, 0.016, "neutral"),
    ("MayJun24_Chop",      180,  0.005, 0.015, -0.0003, 0.015, "neutral"),
    ("Jul24_Recovery",      84,  0.014, 0.010,  0.0003, 0.017, "warm_pos"),
    ("Aug24_YenUnwind",     90, -0.055, 0.028, -0.0015, 0.032, "hot_neg"),
    ("Sep24_Volatile",      90, -0.005, 0.035,  0.0001, 0.022, "volatile"),
    ("Oct24_Warmup",        90,  0.020, 0.014,  0.0005, 0.018, "warm_pos"),
    ("NovDec24_Rally",     180,  0.058, 0.025,  0.0008, 0.020, "hot_pos"),
    ("Dec24_Cascade",       15, -0.030, 0.045, -0.0040, 0.045, "hot_neg"),
    ("LateDec24_Rebound",   45,  0.025, 0.018,  0.0004, 0.018, "warm_pos"),
    ("Jan25_Consol",       100,  0.008, 0.014,  0.0000, 0.016, "neutral"),
    ("FebMar25_Recovery",  120,  0.018, 0.012,  0.0003, 0.017, "warm_pos"),
]

def generate_data(phases, start_price, start_ts_ms):
    """Generate aligned 8H funding and 4H price time series."""
    funding_records = []   # [{ts, rate, regime, phase}]
    kline_records   = []   # [{ts, close}]

    current_ts_8h = start_ts_ms
    current_ts_4h = start_ts_ms
    price = start_price

    for phase in phases:
        name, n_8h, f_mean, f_std, drift, vol, regime = phase
        n_4h = n_8h * 2   # two 4H candles per 8H period

        # Generate funding rates for this phase
        for _ in range(n_8h):
            rate = np.random.normal(f_mean / 100, f_std / 100)
            funding_records.append({
                "ts": current_ts_8h,
                "rate_pct": round(rate * 100, 5),
                "regime": regime,
                "phase": name,
            })
            current_ts_8h += 8 * 3600 * 1000

        # Generate 4H prices for this phase
        for _ in range(n_4h):
            shock = np.random.normal(drift, vol)
            price = max(price * (1 + shock), 1.0)
            kline_records.append({
                "ts": current_ts_4h,
                "close": round(price, 2),
            })
            current_ts_4h += 4 * 3600 * 1000

    return funding_records, kline_records

# Generate
BTC_START = 42000
ETH_START = 2200
START_MS  = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

btc_funding, btc_klines = generate_data(PHASES_BTC, BTC_START, START_MS)
eth_funding, eth_klines = generate_data(PHASES_ETH, ETH_START, START_MS)

print(f"BTC: {len(btc_funding)} 8H funding periods, {len(btc_klines)} 4H candles")
print(f"ETH: {len(eth_funding)} 8H funding periods, {len(eth_klines)} 4H candles")

# ══════════════════════════════════════════════════════════════════════════════
# 2.  CLASSIFY 5 FUNDING REGIMES
# ══════════════════════════════════════════════════════════════════════════════
# Based on 3-period (24H) rolling mean of funding rate to smooth noise

def rolling_mean(arr, n=3):
    result = []
    for i in range(len(arr)):
        window = arr[max(0,i-n+1):i+1]
        result.append(np.mean(window))
    return result

def classify_regime(rate_pct_24h_avg):
    """Classify based on 24H rolling average funding rate (in %)."""
    r = rate_pct_24h_avg
    if r > 0.05:    return "HOT_POSITIVE"    # >0.05%/8H avg → extreme long crowd
    if r > 0.01:    return "WARM_POSITIVE"   # 0.01–0.05%    → healthy bull carry
    if r > -0.01:   return "NEUTRAL"         # ±0.01%        → balanced
    if r > -0.05:   return "WARM_NEGATIVE"   # -0.05 to -0.01 → mild bear bias
    return              "HOT_NEGATIVE"       # < -0.05%      → extreme short crowd

def label_funding(funding_records):
    rates = [r["rate_pct"] for r in funding_records]
    roll  = rolling_mean(rates, 3)
    for i, rec in enumerate(funding_records):
        rec["regime_classified"] = classify_regime(roll[i])
        rec["roll24_pct"]        = round(roll[i], 5)
    return funding_records

btc_funding = label_funding(btc_funding)
eth_funding = label_funding(eth_funding)

def regime_distribution(funding_records, symbol):
    from collections import Counter
    counts = Counter(r["regime_classified"] for r in funding_records)
    total  = len(funding_records)
    rates  = [r["rate_pct"] for r in funding_records]
    print(f"\n{symbol} Funding Rate Statistics:")
    print(f"  Periods: {total} (8H each, {total/3:.0f} trading days)")
    print(f"  Mean: {np.mean(rates):+.4f}%  Std: {np.std(rates):.4f}%  "
          f"Min: {np.min(rates):+.4f}%  Max: {np.max(rates):+.4f}%")
    print(f"  Regime distribution:")
    for reg in ["HOT_POSITIVE","WARM_POSITIVE","NEUTRAL","WARM_NEGATIVE","HOT_NEGATIVE"]:
        n = counts.get(reg, 0)
        print(f"    {reg:18s}: {n:4d} periods ({n/total*100:5.1f}%)")

regime_distribution(btc_funding, "BTC")
regime_distribution(eth_funding, "ETH")

# ══════════════════════════════════════════════════════════════════════════════
# 3.  EMA/RSI BACKTEST WITH FUNDING REGIME TAGGING
# ══════════════════════════════════════════════════════════════════════════════

def ema(prices, n):
    e = np.zeros(len(prices)); k = 2/(n+1)
    e[:n] = np.mean(prices[:n])
    for i in range(n, len(prices)):
        e[i] = prices[i]*k + e[i-1]*(1-k)
    return e

def rsi(prices, n=14):
    deltas = np.diff(prices)
    ag = np.zeros(len(prices))
    al = np.zeros(len(prices))
    if n <= len(deltas):
        ag[n] = np.mean(np.where(deltas[:n]>0, deltas[:n], 0))
        al[n] = np.mean(np.where(deltas[:n]<0,-deltas[:n], 0))
    for i in range(n+1, len(prices)):
        ag[i] = (ag[i-1]*(n-1) + max(deltas[i-1],0))/n
        al[i] = (al[i-1]*(n-1) + max(-deltas[i-1],0))/n
    rs = np.where(al>0, ag/al, 100.0)
    return 100 - 100/(1+rs)

def adx_simple(prices, n=14):
    adx = np.zeros(len(prices))
    for i in range(n, len(prices)):
        w = prices[max(0,i-n):i+1]
        tr = (w.max()-w.min())/max(w.mean(),0.01)*100
        adx[i] = adx[i-1]*(1-2/(n+1))+tr*2/(n+1) if i>n else tr
    arr = adx[n:]
    mn, mx = arr.min(), arr.max()
    if mx > mn:
        adx[n:] = 15 + (arr-mn)/(mx-mn)*30
    return adx

def build_funding_ts_map(funding_records):
    """Map 8H timestamps → classified regime."""
    fm = {}
    for rec in funding_records:
        fm[rec["ts"]] = rec["regime_classified"]
    return fm

def snap_8h(ts_ms):
    """Snap ms timestamp to nearest 8H boundary."""
    dt = datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc)
    h8 = (dt.hour // 8) * 8
    snapped = dt.replace(hour=h8, minute=0, second=0, microsecond=0)
    return int(snapped.timestamp() * 1000)

def get_regime(ts_ms, fm):
    for delta in [0, 8, 16, 24, -8]:
        key = snap_8h(ts_ms) + delta*3600*1000
        if key in fm:
            return fm[key]
    return "NEUTRAL"

def backtest_with_regimes(kline_list, funding_map,
                          fast=20, slow=30, rsi_n=14,
                          sl_pct=4.0, target_r=2.0, adx_thresh=22):
    if len(kline_list) < slow + 10:
        return []
    prices = np.array([k["close"] for k in kline_list])
    ts_arr = np.array([k["ts"]    for k in kline_list])

    fe = ema(prices, fast)
    se = ema(prices, slow)
    rs = rsi(prices, rsi_n)
    ad = adx_simple(prices)

    start  = max(slow, rsi_n) + 2
    trades = []
    in_t   = False
    ep = sp = tp = entry_ts = 0

    for i in range(start, len(prices)-1):
        if in_t:
            if prices[i] <= sp:
                regime = get_regime(entry_ts, funding_map)
                trades.append({"r": -1.0, "entry_ts": int(entry_ts),
                                "exit_ts":  int(ts_arr[i]),
                                "outcome": "LOSS", "regime": regime})
                in_t = False
            elif prices[i] >= tp:
                regime = get_regime(entry_ts, funding_map)
                trades.append({"r": target_r, "entry_ts": int(entry_ts),
                                "exit_ts":  int(ts_arr[i]),
                                "outcome": "WIN",  "regime": regime})
                in_t = False
        else:
            cross = (fe[i] > se[i]) and (fe[i-1] <= se[i-1])
            if cross and 42 <= rs[i] <= 72 and ad[i] >= adx_thresh:
                ep       = prices[i]
                sp       = ep*(1-sl_pct/100)
                tp       = ep + (ep-sp)*target_r
                entry_ts = int(ts_arr[i])
                in_t     = True
    return trades

def per_regime_stats(trades):
    from collections import defaultdict
    buckets = defaultdict(list)
    for t in trades:
        buckets[t["regime"]].append(t["r"])

    ORDER = ["HOT_POSITIVE","WARM_POSITIVE","NEUTRAL","WARM_NEGATIVE","HOT_NEGATIVE"]
    stats = {}
    for reg in ORDER:
        rs_list = buckets.get(reg, [])
        if not rs_list:
            stats[reg] = {"n": 0, "win_rate": 0, "avg_r": 0,
                          "max_dd_r": 0, "total_r": 0}
            continue
        arr  = np.array(rs_list)
        wins = arr[arr > 0]
        eq   = np.cumsum(arr)
        pk   = np.maximum.accumulate(eq)
        dd   = float((pk-eq).max()) if len(arr)>1 else 0.0
        stats[reg] = {
            "n":          len(arr),
            "win_rate":   round(float(len(wins)/len(arr)*100), 1),
            "avg_r":      round(float(arr.mean()), 3),
            "max_dd_r":   round(dd, 2),
            "total_r":    round(float(eq[-1]), 2),
        }
    return stats

print("\nRunning backtests...")
btc_fm = build_funding_ts_map(btc_funding)
eth_fm = build_funding_ts_map(eth_funding)

btc_trades = backtest_with_regimes(btc_klines, btc_fm)
eth_trades = backtest_with_regimes(eth_klines, eth_fm)

btc_stats = per_regime_stats(btc_trades)
eth_stats = per_regime_stats(eth_trades)

ORDER = ["HOT_POSITIVE","WARM_POSITIVE","NEUTRAL","WARM_NEGATIVE","HOT_NEGATIVE"]

print(f"\nBTC: {len(btc_trades)} total trades")
print(f"{'Regime':<20} {'N':>4} {'WR%':>6} {'Avg R':>7} {'Max DD':>8} {'Total R':>9}")
print("-"*60)
for reg in ORDER:
    s = btc_stats[reg]
    print(f"{reg:<20} {s['n']:>4} {s['win_rate']:>6.1f} {s['avg_r']:>+7.3f} "
          f"{s['max_dd_r']:>8.2f} {s['total_r']:>+9.2f}")

print(f"\nETH: {len(eth_trades)} total trades")
print(f"{'Regime':<20} {'N':>4} {'WR%':>6} {'Avg R':>7} {'Max DD':>8} {'Total R':>9}")
print("-"*60)
for reg in ORDER:
    s = eth_stats[reg]
    print(f"{reg:<20} {s['n']:>4} {s['win_rate']:>6.1f} {s['avg_r']:>+7.3f} "
          f"{s['max_dd_r']:>8.2f} {s['total_r']:>+9.2f}")

# ══════════════════════════════════════════════════════════════════════════════
# 4.  CASE STUDY: Extract notable trade sequences around documented events
# ══════════════════════════════════════════════════════════════════════════════
# March 2024 ATH breakout (hot positive, then correction)
# August 2024 yen-carry unwind (hot negative)
# November-December 2024 rally + cascade

def ts_to_date(ts_ms):
    return datetime.fromtimestamp(ts_ms/1000, tz=timezone.utc).strftime("%Y-%m-%d")

print("\n\nCASE STUDY TRADES:")
for asset, trades, label in [("BTC", btc_trades, "BTC"), ("ETH", eth_trades, "ETH")]:
    hot_pos = [t for t in trades if t["regime"] == "HOT_POSITIVE"]
    hot_neg = [t for t in trades if t["regime"] == "HOT_NEGATIVE"]
    neutral = [t for t in trades if t["regime"] == "NEUTRAL"]
    warm_pos = [t for t in trades if t["regime"] == "WARM_POSITIVE"]
    print(f"\n  {label} HOT_POSITIVE trades:")
    for t in hot_pos[:4]:
        print(f"    {ts_to_date(t['entry_ts'])} → {ts_to_date(t['exit_ts'])}: "
              f"{t['outcome']} {t['r']:+.1f}R")
    print(f"  {label} HOT_NEGATIVE trades:")
    for t in hot_neg[:4]:
        print(f"    {ts_to_date(t['entry_ts'])} → {ts_to_date(t['exit_ts'])}: "
              f"{t['outcome']} {t['r']:+.1f}R")
    print(f"  {label} NEUTRAL trades:")
    for t in neutral[:4]:
        print(f"    {ts_to_date(t['entry_ts'])} → {ts_to_date(t['exit_ts'])}: "
              f"{t['outcome']} {t['r']:+.1f}R")

# ══════════════════════════════════════════════════════════════════════════════
# 5.  SAVE FULL RESULTS
# ══════════════════════════════════════════════════════════════════════════════
output = {
    "btc": {"trades": btc_trades, "regime_stats": btc_stats,
            "total_trades": len(btc_trades)},
    "eth": {"trades": eth_trades, "regime_stats": eth_stats,
            "total_trades": len(eth_trades)},
    "funding_summary": {
        "btc": {
            "mean_pct": round(float(np.mean([r["rate_pct"] for r in btc_funding])),4),
            "std_pct":  round(float(np.std( [r["rate_pct"] for r in btc_funding])),4),
            "n_periods": len(btc_funding),
            "regime_counts": {
                reg: sum(1 for r in btc_funding if r["regime_classified"]==reg)
                for reg in ORDER
            }
        },
        "eth": {
            "mean_pct": round(float(np.mean([r["rate_pct"] for r in eth_funding])),4),
            "std_pct":  round(float(np.std( [r["rate_pct"] for r in eth_funding])),4),
            "n_periods": len(eth_funding),
            "regime_counts": {
                reg: sum(1 for r in eth_funding if r["regime_classified"]==reg)
                for reg in ORDER
            }
        },
    }
}
with open("/home/claude/analysis_results.json","w") as f:
    json.dump(output, f, indent=2)
print("\nSaved → /home/claude/analysis_results.json")
print("Done.")
