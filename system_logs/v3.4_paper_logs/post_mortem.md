# v3.4 Paper Session — Post-Mortem

## 1. Session Overview

| Field | Value |
|---|---|
| Mode | paper |
| Start | 2026-04-20 12:43:06 UTC (`bot.log:6`) |
| End | 2026-04-21 06:44+ UTC (log still writing at tail) |
| Duration | ~18h 01m |
| Windows observed | 216 (`WINDOW_DECISION` count) |
| Fires | 4 (`FIRED` count) |
| Fills | 4 (all taker via SKIP_MAKER fast path) |
| Wins / Losses | 4 / 0 |
| Session PnL | +$30.0801 (`bot.log:5639`, WINDOW_SUMMARY final) |
| Opening bankroll | $975.35 (resumed from prior run, `bot.log:30`) |
| Closing bankroll | $1005.43 |
| Orchestrator cycles | 72 (15-min interval) |
| Signal deliveries | 72 (every cycle delivered BRONZE) |
| Signal swaps on bot side | 71 (50 same-pattern refreshes + 20 pattern changes + 1 initial) |
| CUSUM / post-fire exits | 0 |
| POST_LOSS_COOLDOWN armings | 0 |
| FIRE STALL events | 0 |
| SPRT DECAY verdicts | 0 |

### Fire table

| # | UTC time | Side | Entry | Size | PnL | Regime snapshot | Notes |
|---|---|---|---|---|---|---|---|
| T1 | 13:01:50 | down | 0.78 | $1.00 | +$0.2764 | outcome=0.782 → HOSTILE halve $48.77→$24.38; WARMUP clamp $24.38→$1.00 | `bot.log:136-141,171` |
| T2 | 13:21:50 | down | 0.73 | $48.78 | +$17.6811 | vol=0.021 only, otherwise clean | `bot.log:259-262,296` |
| T3 | 00:56:40 | up | 0.87 | $49.67 | +$7.2735 | p_adj=base=0.930, no discount | `bot.log:3880-3883,3914` |
| T4 | 01:06:40 | up | 0.91 | $50.03 | +$4.8491 | p_adj=base=0.930, no discount | `bot.log:3950-3953,3990` |

All 4 fires crossed on `SKIP_MAKER (high conf)` — `oos_wr ≥ 96% AND stddev ≤ 0.035%` (`momentum_signal.py` fast-path gate, config `skip_maker_min_oos_wr_pct=96.0`, `skip_maker_max_stddev_pct=0.035`). No maker-path fills this session.

### Sample-size honesty

4 fires / 4 wins. Binomial 95% Clopper-Pearson CI on WR is [39.8 %, 100 %]. The session is **statistically indistinguishable from any true WR ≥ ~40 %**. Nothing in this record by itself confirms or refutes the OOS-projected 96–100 % on the engine side. Statements below that rely on fire outcomes are tagged **Insufficient** unless the mechanic is observable independent of the 4/4 result.

---

## 2. Mechanism Validation (Floor Goals)

| Mechanism | Behaviour this session | Confidence | Evidence |
|---|---|---|---|
| Kelly sizing (`kelly.py`) | All 4 fires produced p_adj ≥ entry; raw_f positive; fractional Kelly 0.25 applied; bankroll-cap (≈5 % of $975.62) pinned T2-T4 at ~$48-50 | High | T2 KELLY line, T3/T4 KELLY lines (`bot.log:259,3880,3950`) |
| Hostile-regime gate ordering | T1 path `Kelly raw → HOSTILE halve (×0.50) → WARMUP clamp → min $1.00` verified in order (`bot.log:136-137`). Halve fired because outcome severity 0.782 ≥ 0.150; skip-threshold 0.250 not crossed. | High | `bot.log:136` HOSTILE REGIME line, `bot.log:137` WARMUP clamp line |
| HOSTILE_REGIME_SKIP | Fired once at 13:52:50 on vol=0.567 > skip_thresh=0.250 | High | `bot.log:442` |
| KELLY_NO_EDGE | 9 activations (`bot.log:108,341,691,1278,1818,1872,3652,4737,5607`); every case had raw_f < 0 because entry ≥ p_adj (market priced tighter than our adjusted WR). Gate is behaving as spec'd. | High | 9 log lines enumerated |
| IMPLIED_PROB_TOO_CLOSE | Fired once at 18:32:50: p_adj=0.861, entry=0.850, edge 1.12 pp < min 2.00 pp. Correct veto by `min_edge_pp` config. | High | `bot.log:1919` |
| OBI_ROLLING_OPPOSES | 7 activations; all with |mean_obi| ≥ 0.072 opposing the signal side over the 20 s rolling window | Medium (gate logic verified; predictive value of skips is **Insufficient**) | `bot.log:540,667,1558,1716,2025,2982,5033` |
| DIRECTIONAL_OPPOSES | Never triggered (0 activations). Configured gate (`directional_t_stat_threshold`) remained within bounds in every fire; `dir_t` on REGIME log never exceeded ±1.4 | High (negative observation) | `Grep DIRECTIONAL_OPPOSES` = 0 |
| WARMUP clamp | Engaged on T1 (`$24.38 → $1.00`). Warmup window = 30 min ends at 13:13:06; T1 fired 12 min into warmup, T2 fired ~8 min after warmup end (correctly unclamped). | High | `bot.log:137`, T2 size $48.78 |
| Paper fill model (`paper_trading.py`) | 4/4 fills at taker price; 2.5 s `simulated_fill_delay_sec` irrelevant on taker path (place_taker_order fills immediately); no queue-priority or adverse-selection modelled. | High for logic, **Optimistic** re: real-world fill | `paper_trading.py:place_taker_order`, `exit_position_early` |
| CUSUM / post-fire erosion | Never triggered. All 4 fires moved favorably through the observe→fire→close interval; `override_multiplier=3.8` never tested in this session. | **Insufficient** (no adverse paths observed) | `Grep CUSUM` / `erosion` = 0 |
| POST_LOSS_COOLDOWN | No losses → counter never armed; gate path not exercised. | **Insufficient** | `Grep POST_LOSS_COOLDOWN` = 0 |
| SPRT lifecycle | Each signal-swap preserved SPRT state on same-pattern refresh (50/71 swaps), reset on different-signal delivery (20/71). No DEAD verdicts. Age never exceeded ~10-11w before a pattern change reset it. | Medium (mechanic verified, decay detection not exercised) | `bot.log:220` "Signal refreshed ... keeping SPRT state (age=7w, trades=1)" |
| Signal ingestion / dedupe | All 72 orchestrator deliveries acknowledged; dedupe removed each observed fire in the next cycle's `paper fire(s) from bot` pull. | High | `orchestrator.log:78` "pulled 1 paper fire(s)", etc. |

### Fill-model optimism disclaimer

The paper fill model has three known optimistic assumptions relative to live CLOB:
1. `place_taker_order` fills **instantly at the quoted ask** with no slippage and no partial-fill risk (`paper_trading.py`).
2. `simulated_fill_delay_sec=2.5` applies to maker-path fills only; taker path (which every v3.4 fire used) is delay-free.
3. `exit_position_early` sells at `best_bid` instantly, ignoring book depth. No CUSUM exits this session, but carry-over risk: whenever the engine *does* fire CUSUM in a live session the sell-side slippage will be larger than paper implies.

---

## 3. Prior-Recommendation Status (vs v3.3 post_mortem.md)

| ID | Hypothesis | Status in v3.4 |
|---|---|---|
| H1 | `obs_obi` is predictive of outcome on UP side | Counter-evidence found but not decisive: T3 `obs_obi=-0.1930` and T4 `obs_obi=-0.3869` were both strongly book-opposing the UP signal, and both WON (`bot.log:3882,3952`). Two counter-examples to a predictive-obs_obi thesis. **Still Insufficient** to refute — only 2 UP fires observed. |
| H2 | `maker_timeout_s=3.0` may be too tight and cost fills | **Untested this session.** All 4 fires satisfied the SKIP_MAKER fast-path gate (oos_wr ≥ 96 % AND stddev ≤ 0.035 %) and went direct to taker. No maker order placed. Carries over to next session. |
| H3 | Outcome axis dominates hostile-regime halving | **Confirmed on n=1.** T1's halving was driven by `outcome=0.782` as the lone elevated axis (`vol=0.000 chop=0.000`). Matches v3.3's observation. Still a single observation and the fire still won, so this remains a mechanic observation, not a predictive claim. |
| v3.3 carry-over: data-collection issue | Out of scope of this log (collector runs separately). No bot-side symptom of stale or missing feeds in v3.4 — `data quality check passed: 500 windows available` every orchestrator cycle (`orchestrator.log:6,32,58,...`). |
| v3.3 carry-over: bot-side stale-signal freshness guard | Not verified in this session (not exercised; signals refreshed every 15 min and no stale-path triggered). |

---

## 4. Tuning Recommendations

With n=4 fires, **no data-driven parameter tuning is recommended**. The session produces no evidence that any threshold is mis-set. Recommendations below are limited to items with independent mechanic-level evidence.

1. **No change** to Kelly `wilson_max_shrink_pct`, `kelly_fraction=0.25`, or hostile thresholds — the observed halve on T1 (`outcome=0.782`, halve to `$24.38`) is the spec'd behavior; the fire won, which is consistent with but does not validate the halve's calibration.
2. **No change** to `skip_maker_min_oos_wr_pct=96.0` / `skip_maker_max_stddev_pct=0.035`. Every fire cleared both and all four won. Loosening would pull in signals that did not meet the bar; tightening would have zero effect on this session.
3. **No change** to `obi_rolling_skip_threshold=0.05`. 7 vetoes fired; we cannot measure the counterfactual outcome of the vetoed windows from bot.log alone.
4. **No change** to `min_edge_pp=2.00`. The one IMPLIED_PROB_TOO_CLOSE at 1.12 pp is one data point at the margin — noteworthy but not a case for moving the threshold.
5. **Note** on orchestrator churn: 71 bot-side swaps in 72 cycles is expected under the current delivery cadence — the refresh path correctly preserves SPRT state for same-pattern updates (50/71). No action required, but worth watching if the downstream SPRT signal ever becomes load-bearing for sizing.

---

## 5. Code Findings (proposed diffs only)

### Finding 5.1 — "WARMUP complete" notification missed when a signal swap coincides with warmup expiry [HRP Low]

**Observed:** `bot.log` contains exactly one WARMUP line (the T1 clamp at `13:01:50`, `bot.log:137`). No "WARMUP complete" alert was ever written. Warmup ends at `12:43:06 + 30m = 13:13:06`; the first window boundary after that is `13:15:00`, and at that boundary a signal refresh also fired (`bot.log:220-222` "Signal refreshed (same pattern) ... keeping SPRT state").

**Cause (verified in `window_handler.py:1077-1106`):**
```python
_was_warming_up = strategy.warmup_active
strategy.warmup_active = (
    _warmup_secs > 0 and (time.time() - self._bot_start_time) < _warmup_secs
)
if _was_warming_up and not strategy.warmup_active and not self._warmup_alert_sent:
    ...
    log.info("WARMUP complete after %.0f min — full Kelly sizing active", ...)
```
`_was_warming_up` reads `strategy.warmup_active`. In `_handle_signal_swap` (Phase 5) the `strategy` reference is replaced with `new_strategy` (built via `_build_strategy_fn`); `MomentumSignalStrategy.__init__` sets `self.warmup_active = False` by default (`momentum_signal.py:133`). When `_compute_kelly_context` runs in Phase 6 on the fresh strategy, `_was_warming_up` is already `False` — the `True → False` transition is swallowed.

**Impact:** Cosmetic/notification only. Sizing itself correctly stops clamping once `time - start_time >= warmup_secs` because the condition is recomputed every window. No trades mis-sized.

**Proposed diff (sketch, not applied):** Track warmup-transition state on `WindowEventHandler` rather than on the strategy instance so it survives swaps. E.g. replace `strategy.warmup_active` with a handler-owned flag `self._warmup_was_active` and drive the transition from handler-local timestamps; keep `strategy.warmup_active` as a read-only publish of the current sizing clamp.

```python
# window_handler.py — _compute_kelly_context
_warmup_active_now = (
    _warmup_secs > 0 and (time.time() - self._bot_start_time) < _warmup_secs
)
if not hasattr(self, "_warmup_was_active"):
    self._warmup_was_active = _warmup_active_now
if self._warmup_was_active and not _warmup_active_now and not self._warmup_alert_sent:
    ... # alert
self._warmup_was_active = _warmup_active_now
strategy.warmup_active = _warmup_active_now  # still used by fire-time clamp
```

Only the notification changes; clamp math is untouched.

### No other code findings

I scanned the fire pipeline (`momentum_signal.py`), Kelly (`kelly.py`), paper fill (`paper_trading.py`), lifecycle (`signal_lifecycle.py`), post-loss cooldown (`post_loss_cooldown.py`) and window handler (`window_handler.py`) against the session log. No HRP-severity violation or mechanic drift observed. No HRC findings (no C++ changes touched in this session's runtime).

---

## 6. Open Hypotheses for Next Session

| ID | Hypothesis | Why it's open | What would test it |
|---|---|---|---|
| H1 (carried) | `obs_obi` is predictive of outcome on UP signals | 2 UP fires this session had book-opposing `obs_obi` and both won, but n=2 | ≥20 UP fires with per-fire `obs_obi` and win/loss tags; correlate sign(obs_obi · side) vs outcome |
| H2 (carried) | `maker_timeout_s=3.0` is too tight and forfeits maker rebates | SKIP_MAKER fast-path took every fire this session; the maker branch was never exercised | A session where at least some fires have oos_wr < 96 % or stddev > 0.035 %; measure cancel-before-fill rate vs maker_timeout |
| H3 (carried, sharper) | Outcome-axis agreement becomes the first axis to enter the hostile band at session start | T1 had outcome=0.782 as the lone elevated axis at t=18min after bot start, while vol and chop were 0.000 | Check startup-window distribution of vol/chop/outcome severities on next 5+ cold-starts |
| H4 (new, **Low confidence**) | The "WARMUP complete" alert is routinely swallowed by the swap at the first post-warmup boundary | One observed instance this session; mechanic traced in §5.1 | Simple: patch as sketched, or instrument an unconditional "warmup_complete_fired_at" timestamp log |
| H5 (new, **Insufficient**) | The 5 % bankroll cap is binding on this signal family at current bankroll | T2/T3/T4 all sized within ~$0.26 of 5 % of bankroll regardless of p_adj; the Kelly raw_f on these fires would have sized well above 5 % | Log `kelly_raw_size` next to clamped size; over 20+ fires measure how often the cap is the binding constraint |

---

## 7. Strategic Verdict

**Neutral / uninformative.** A 4W/0L session at +$30.08 (+3.1 % on $975.35 opening) tells us the plumbing — orchestrator delivery, IPC ingestion, gate ordering, hostile halving, warmup clamping, SKIP_MAKER fast-path, paper settlement, SPRT preservation across refresh — is working. It does not provide evidence for or against the engine's projected win rate, the OBI-rolling gate's predictive value, the CUSUM exit calibration, or the maker-timeout parameter.

The session is **not a signal to tighten or loosen any gate.** The next useful data point is a session with (a) at least one adverse fire so the CUSUM/early-exit path is exercised, and (b) at least one fire that does not qualify for SKIP_MAKER so the maker path is exercised.

---

## 8. Analyst Notes

- **Path confusion at start.** Session folder is `v3.4_paper_logs`, not `v3.4` — noted so the next run's invocation uses the right path.
- **Bankroll continuity.** `bot.log:29-30` shows `STATE SIGNAL MISMATCH: saved signal_id=down_280.0_180.0_0.1_0.05 but current=down_290.0_190.0_0.06_0.05 — state may be stale, resetting totals` and then `resumed paper balance: $975.35`. The opening bankroll is carried over from a prior run (v3.3 borked, presumably), so v3.4 session PnL is not computed against a pristine $1000 opening. Session totals here refer to the delta within this session only.
- **Orchestrator-clock offset.** `orchestrator.log` local timestamps lead UTC by 3 hours (`15:43:12 [cycle start 12:43:12 UTC]`, `orchestrator.log:4-5`). All cross-references above use the UTC value.
- **High swap cadence, not churn.** 71 bot-side swaps but 50 of them are same-pattern refreshes that preserve SPRT. Only 20 genuine pattern changes. Worth watching if the mix shifts toward more pattern changes in future sessions.
- **Ambiguity flagged:** The paper fill model's instant-taker assumption means the gap between paper and live fill prices is unbounded in this log. Do not port this session's win rate to live expectations without a slippage model.
- **Things not in scope this run:** PolyDataCollector health, SPRT decay calibration under larger n, maker-path behavior, live CLOB user-WS path, CUSUM exit calibration.
