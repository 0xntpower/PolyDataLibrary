# PolySignalLab v1.5 Paper Trading Analysis

## Session Summary

| Metric | Value |
|--------|-------|
| Duration | ~22h 41m (Apr 3 16:01 → Apr 4 14:42) |
| Windows observed | 272 |
| Trades taken | 3 (1.1% fire rate) |
| Win rate | 3/3 = 100% |
| Total PnL | **+$18.75** (+2.06% on $910.79 starting balance) |
| Best trade | +$15.73 (DOWN @ $0.60 entry) |
| Worst trade | +$0.41 (UP @ $0.97 entry) |
| BTC range | $66,587 → $67,160 (+0.67%) |
| Market outcomes | 136 Up / 136 Down (perfect 50/50) |

## The Core Problem: Extreme Selectivity

The system is **very accurate but barely trades**. 3 trades in 23 hours means ~1 trade per 7.6 hours. The signal pipeline has multiple conservative gates stacked on top of each other:

1. **Orchestrator**: Only 58 of 91 engine cycles (64%) produced a deliverable signal. After 05:00 Apr 4, **zero signals** were delivered for 10+ hours straight (all top signals were OVERFIT_DANGER tier).

2. **Delta threshold** (`minDeltaPct = 0.10%`): 254 of 272 windows (93.4%) skipped because BTC didn't move 0.10% within the observation window. This is the **single biggest filter**.

3. **Kelly no-edge**: 13 windows passed the delta filter but entry prices were too expensive (0.72–0.99) for Kelly to find positive EV. The market had already priced in the move.

4. **Chop discount**: Active in 56% of windows, reducing adjusted win rate by up to 7.5%, making the Kelly edge harder to clear.

**Net result**: Only 3 of 272 windows (1.1%) cleared all gates.

## Trade Breakdown

| Trade | Signal | Side | Entry | Kelly Bet | SPRT | Final Size | PnL | Issue |
|-------|--------|------|-------|-----------|------|-----------|-----|-------|
| 1 | rank=1 | UP | $0.90 | $24.00 | 1.00 | $24.00 | +$2.61 | Decent entry, but still expensive |
| 2 | rank=1 | UP | $0.97 | $24.06 | 0.56 | $13.53 | +$0.41 | Terrible entry — market already priced in |
| 3 | rank=10 | DOWN | $0.60 | $24.07 | 1.00 | $24.07 | +$15.73 | Great entry — cheap price = huge payoff |

**Key insight**: Trade 3 produced **38x more profit** than Trade 2 with similar capital deployed. Entry price is the dominant factor in profitability, not signal rank.

## Signal Quality Timeline

The orchestrator showed a clear three-phase pattern:

| Phase | Period | Signal Quality | Trades |
|-------|--------|---------------|--------|
| Strong | 16:01–20:18 | GOLDEN signals (scores 39–50) | 1 |
| Decay | 20:18–04:52 | Declining SILVER (scores 10–28) | 1 |
| Drought | 05:07–14:42 | All OVERFIT_DANGER, scores 3–8 | 1 |

11 GOLDEN signals appeared in a ~5.5h cluster (18:17–23:35), all UP direction. This episodic clustering suggests the system should **size up during golden streaks**.

## Infrastructure Health

Flawless. Zero errors, zero data quality issues. 4 WebSocket disconnects all recovered in <1.3s. IPC latency consistently 7–32ms. Engine execution steady at ~6.8s per cycle. This is not where improvement is needed.

---

# Tuning Recommendations (Ordered by Impact)

## 1. CRITICAL: Lower the Delta Threshold — `minDeltaPct`

**Current**: 0.10% | **Suggested**: 0.06–0.08%

This is the #1 bottleneck. 93.4% of windows are rejected here. The engine already discovered signals with various delta thresholds — the orchestrator should deliver signals with lower deltas. Trade 3 actually fired at delta = -0.0501% (a rank=10 signal with a different effective threshold), and it was the session's most profitable trade.

**Risk**: Lower delta = noisier signal = lower win rate. But with OOS win rates of 79–100% on the delivered signals, there's significant margin to absorb some accuracy loss while still trading profitably.

**Where to change**: This is a property of each signal from the engine (`SignalConfig.minDeltaPct` in `shared/models.py:35`). The orchestrator selects signals that already have this baked in. To get more low-delta signals, the **PolySignalEngine** parameter space needs to include lower deltas. Alternatively, the orchestrator could prioritize signals with lower minDeltaPct when multiple candidates exist.

## 2. HIGH: Prioritize Cheap Entry Prices Over Signal Rank

**Current behavior**: The system picks the top-ranked signal by `smart_score`, regardless of typical entry price.

Trade 2 (entry $0.97) made $0.41. Trade 3 (entry $0.60) made $15.73. The `evPerTrade` field from the engine already captures this, but `smart_score` weighs it alongside consistency, folds, confidence, and sample depth.

**Suggestion**: Add an **entry price favorability** weight to `calculate_smart_score()` in `shared/signal_ranking.py:12`. Something like:

```python
entry_edge = max(0, 1.0 - avg_entry_price) ** 0.5  # favor cheaper entries
score = EV * consistency**1.5 * min_fold_WR * confidence * sample_depth * entry_edge * 100
```

Alternatively, when ranking, prefer signals where `avg_entry_price < 0.80` — these have the highest payoff-to-risk ratio.

## 3. HIGH: Reduce Kelly Conservatism for Proven Signals

**Current**: Quarter-Kelly (`kelly_fraction = 0.25`) with `kelly_max_bet_pct = 2.5%`.

At $960 bankroll, max bet is $24. With a 100% realized win rate and 79–100% OOS win rates, this is extremely conservative. The system is leaving significant expected growth on the table.

**Suggestion**:
- Increase `kelly_fraction` from 0.25 to **0.35** (third-Kelly). This is still well within safe territory for binary outcomes with 80%+ win rates.
- Increase `kelly_max_bet_pct` from 2.5% to **4.0%** ($40 at $1000 bankroll).
- Consider a **tiered approach**: use 0.35 for GOLDEN-tier signals, 0.25 for SILVER.

**Config**: `config.yml` lines 100-102

## 4. MEDIUM: Relax the Chop Discount

**Current**: Chop discount reaches max at 5.0 flips (`chop_elevated_flips`), and chop was detected in 56% of windows, applying up to 7.5% win rate reduction.

Given the 100% realized win rate, this is over-penalizing. The chop detector is flagging normal market microstructure as problematic.

**Suggestion**:
- Raise `chop_elevated_flips` from 5.0 to **6.5** (shrinks the penalty band)
- Or reduce `kelly_max_discount` from 0.15 to **0.10** (caps the combined vol+chop penalty)

**Config**: `config.yml` lines 95-96, 103

## 5. MEDIUM: Earlier Observation Window / Earlier Entry

13 windows had `KELLY_NO_EDGE` because the market had already priced in the move by the time the observation window closed. Entry prices of 0.94–0.99 leave no edge.

**Suggestion**: The orchestrator should favor signals with **earlier observation windows** (higher `observeFromS` / `observeToS`). Entering earlier means cheaper prices before the Polymarket orderbook reacts to the BTC move. The highest-scoring signals already used [280s→110s] — encourage more of these.

**Where**: Signal ranking in `shared/signal_ranking.py` could include an earliness bonus. Also in engine configuration — generate more signals with higher `observeToS` (more time remaining = earlier entry).

## 6. MEDIUM: Scale Up During Golden Streaks

GOLDEN signals clustered in a 5.5-hour window. The bot should recognize when it's receiving GOLDEN-tier signals and increase sizing.

**Implementation**: The IPC payload already includes tier info. In `momentum_signal.py`, apply a multiplier when the current signal has GOLDEN tier:

```python
tier_multiplier = 1.5 if signal.tier == "GOLDEN" else 1.0
size_usd = kelly_bet * sprt_factor * tier_multiplier
```

## 7. LOW: Reduce Fire Stall Sensitivity in Low-Vol Periods

**Current**: `fire_stall_windows = 50` (~4 hours). During the overnight low-vol period (vol_stddev=0.024%), the delta threshold is rarely met, so fire stall triggers even though the signal is still valid — the market is just quiet.

**Suggestion**: Make fire stall **vol-aware**. During low-vol regimes (below `vol_baseline_stddev_pct`), extend the stall threshold by 1.5–2x. This prevents prematurely killing signals during quiet hours.

**Where**: `main.py:1242` — add a condition checking the current volatility regime.

## 8. LOW: Use Viable Signal Count as Early Warning

The orchestrator's viable signal count dropped from 40+ to the low 20s before the full drought began. Monitoring this metric could trigger proactive signal rotation or alert the operator.

**Where**: `SignalOrchestrator/main.py` — log/alert when viable signals drop below 25.

---

# Priority Matrix

| # | Recommendation | Effort | Expected Impact | Risk |
|---|---------------|--------|-----------------|------|
| 1 | Lower delta threshold | Low (engine config) | **Very High** — could 3–5x trade frequency | Medium — lower accuracy |
| 2 | Favor cheap entries in ranking | Medium (scoring formula) | **High** — dramatically better PnL per trade | Low |
| 3 | Increase Kelly fraction to 0.35 | Trivial (config) | **High** — ~40% larger bets | Low at these win rates |
| 4 | Relax chop discount | Trivial (config) | **Medium** — fewer KELLY_NO_EDGE rejections | Low |
| 5 | Favor earlier observation windows | Medium (ranking + engine) | **Medium** — cheaper entries | Low |
| 6 | Golden streak scaling | Low (code change) | **Medium** — larger bets during best signals | Low |
| 7 | Vol-aware fire stall | Low (code change) | **Low** — prevents premature signal kills overnight | Very Low |
| 8 | Viable signal count alerting | Trivial (logging) | **Low** — operational awareness | None |

The biggest lever is **trading more often** (#1 + #2 + #4 + #5 combined). The system has strong signal quality (100% WR, 79–100% OOS rates) but fires so rarely that it can't compound gains. Even a modest increase from 3 trades/day to 10–15 trades/day at a slightly lower win rate (say 85%) would substantially increase daily PnL — from ~$19/day to potentially $50–80/day at current sizing, more with recommendation #3.
