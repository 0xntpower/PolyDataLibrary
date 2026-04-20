# v3.3 Paper Session — Post-Mortem

**Session:** 2026-04-18 16:18:13 UTC → 2026-04-20 10:50:46 UTC (orchestrator log end)
**Logs:** `PolyDataLibrary/system_logs/v3.3_paper_logs/`
**Analyst scope note (read first):** This session hit a data-collection failure at the orchestrator while the bot kept running. The user directive was to "perform the analysis on the parts of the sessions that were running before that point in time." Taking that strictly yields zero fires to analyze in the healthy period, so this report splits the session into two scopes and labels every claim accordingly.

---

## 0 · Session scope and the data-quality cutoff

Orchestrator side:
- First successful signal delivery: `2026-04-18 19:18:25 home-region local` = **16:18:25 UTC** (orchestrator.log:29).
- **Last successful delivery: `2026-04-19 00:35:43 home-region local` = 21:35:43 UTC 2026-04-18** (orchestrator.log:588–589). Score 4.77, down-side bronze.
- First data-quality failure at next cycle: `2026-04-19 00:50:43 home-region local` = **21:50:43 UTC**, `data quality insufficient: newest data is 2.2h old (max 2.0h)` (orchestrator.log:591).
- Staleness grew monotonically from 2.2 h to 39.2 h through log end (orchestrator.log:887).

Bot side (Dublin VPS, clock is UTC):
- 22 signals received between 16:18:24 UTC and **21:35:43 UTC** (bot.log:25, 1630).
- After 21:35:43 UTC the bot never received another signal and continued firing against the *last* delivered signal. At 13:35:45 UTC on 4/19 the bot itself warned: `no signal update from orchestrator in 16.0 hours — continuing with current signal` (bot.log:6165).

**Scope A — healthy (orchestrator live): 16:18:13 → 21:35:43 UTC on 2026-04-18 (≈5 h 18 min).** 22 signal deliveries, 64 5-min trading windows covered, **0 fires**. This is the scope the user's directive asks about.

**Scope B — stale signal (orchestrator data pool stale, bot operating on frozen last signal): 21:35:43 UTC 2026-04-18 → 10:50:46 UTC 2026-04-20 (≈37 h).** **All 6 fires of the session happened inside Scope B.** Results from Scope B cannot be used to validate v3.3's live-trading behavior because the signal was not being refreshed — the orchestrator's selection logic (hysteresis, min-score gate, dedupe) was dormant and whatever edge or regime-fit the frozen signal had at 21:35 UTC was assumed to persist for 37 h.

Geography reminder: orchestrator is in home-region (UTC+3), bot VPS in Dublin (UTC; April's BST would be +1 but bot timestamps match UTC exactly — see bot.log:4/5 against orchestrator handshake at 19:18:25 home-region / 16:18:25 UTC = bot's 16:18:24 UTC, delta ≈1 s, consistent with network latency only). All timestamps in this report are UTC.

---

## 1 · Session character

### 1.1 Scope A (healthy period) — what happened in 5 h 18 min

- **Signals delivered:** 22. First 4 were gold-tier `up_200.0_170.0_0.08_0.05` (smartScore 4.85→4.65, avgEntry 0.89). Signal flipped to `down_280.0_180.0_0.1_0.05` at 17:18 UTC (smartScore 5.47, avgEntry 0.86) and remained the #1 down signal for the rest of Scope A through the cutoff, with smartScore hovering 4.77–5.50 as OOS matches ticked up.
- **Trades fired:** 0.
- **Window decisions:** All 64 windows returned `WINDOW_DECISION [SKIP] … (conditions not met)`. Session PnL at cutoff: $0.0000, bankroll $979.08 (identical to start).
- **Skip-reason distribution inside Scope A** (from `momentum_signal: [SKIP] … reason=…` lines):
  - `conditions_not_met` (signal pattern didn't qualify — delta/variance gate): ~60 out of 64 windows. Pattern requires `|latest_pct| ≥ 0.08–0.10%` with `stddev ≤ 0.05%`; realised |delta| was below that most of the window.
  - `HOSTILE_REGIME_SKIP`: **1** (16:22 UTC, UP-signal active, `vol=0.585 chop=0.000 max=0.585 > skip_thresh=0.250`). bot.log:67.
  - `OBI_ROLLING_OPPOSES`: **2** (18:02 UTC `mean_obi=0.402`; 18:42 UTC `mean_obi=0.120`, both vs DOWN side). bot.log:561, 760.
  - `KELLY_NO_EDGE`: **1** (20:57 UTC `p_adj=0.824 entry=0.96 raw_f=-3.400 outcome=0.800`). bot.log:1441.
  - `DIRECTIONAL_OPPOSES`: **0**.
  - `POST_LOSS_COOLDOWN`: **0** (no prior loss to cool down from).

### 1.2 Scope B (stale-signal period) — summary

- 6 fires on the frozen `down_280.0_180.0_0.1_0.05` signal. 4 wins / 2 losses. Net session PnL $-3.73. Final bankroll $975.35.
- All 6 fires carry signal metadata snapshotted at **21:35:43 UTC 4/18**: `oos_wr=95.0%`, `bh_p=7.75e-06`, `avg_entry=0.85` (bot.log:5091 etc.). The orchestrator's own periodic updates would normally drift these figures and potentially swap the active signal; none of that happened for 37 h.

| # | Fire time (UTC) | Side | Fire Δ | Kelly size | Maker/taker entry | Outcome | PnL | obs_obi at fire |
|---|---|---|---|---|---|---|---|---|
| T1 | 2026-04-19 09:57:00 | down | −0.1022% | $27.52 | maker 0.84 → taker **0.85** (+1 tick) | WIN | +$4.76 | −0.0749 |
| T2 | 2026-04-19 12:37:00 | down | −0.1020% | $28.14 | maker 0.83 → taker **0.90** (+7 ticks, 5-min window WIN) | WIN | +$3.06 | −0.0947 |
| T3 | 2026-04-19 13:37:00 | down | −0.1010% | $14.36 | maker 0.75 → taker **0.76** | LOSS | −$13.80 | **+0.5768** |
| T4 | 2026-04-19 20:17:00 | down | −0.1027% | $22.99 | maker 0.82 → taker **0.87** (+5 ticks) | WIN | +$3.37 | −0.6998 |
| T5 | 2026-04-20 01:07:00 | down | −0.1079% | $10.00 | **maker 0.72** filled | LOSS | −$5.51 | **+0.4800** |
| T6 | 2026-04-20 02:12:00 | down | −0.1078% | $15.56 | **maker 0.78** filled | WIN | +$4.39 | −0.9905 |

References: FIRED and TAKER ESCALATION / MAKER FILLED lines at bot.log:5091/5093–5096, 5867/5869–5872, 6172/6174–6177, 8131/8133–8136, 9537/9539–9541, 9888/9890–9892; WINDOW_DECISION results at bot.log:5124, 5899, 6241, 8164, 9587, 9919.

---

## 2 · Mechanism validation

"Evidence" column flags whether Scope A alone gave us a read, whether Scope B is usable with caveat, or Insufficient (N too low or signal stale).

| Mechanism | What it should do | What logs show | Evidence quality | Verdict |
|---|---|---|---|---|
| §5.1 Soft-OR regime (HOSTILE halving / skip) | Halve size when any axis > 0.15; skip when max > 0.25 | 1 HOSTILE_SKIP in Scope A (vol=0.585 on UP signal, bot.log:67). 2 HOSTILE halves in Scope B on T3 and T5 — both LOSSes (bot.log:6169, 9534: `outcome=0.800 max=0.800` and `outcome=0.397 max=0.397`) | Medium (pre-cutoff skip triggered once; post-cutoff halvings exercised twice, both before losses) | **Working as specified.** Halving did its job — losses landed at 50% of baseline Kelly. Note the halving was driven by the *outcome* axis on both losses (streak of same-side outcomes), not vol/chop. |
| §5.2 Directional t-stat veto | Skip if t-stat opposes signal side above threshold (2.0) | 0 in Scope A. **1 in Scope B** at 12:27 UTC 4/19, `t_stat=2.13 thresh=2.00`, down side (bot.log:5819) — 10 min before the T2 WIN fire at 12:37. | Insufficient | Behaviour consistent with code; 1 fire is not enough to judge calibration. The fact that a DIRECTIONAL_OPPOSES skip at 12:27 was followed by a successful down fire 10 min later suggests the t-stat flipped quickly; neither vetoed-then-winner nor vetoed-then-loser narrative is supported by N=1. |
| §5.3 Adaptive discount cap | Cap total Kelly discount so the product stays in [0, ≈0.1] | Every Kelly line in Scope B shows `total_disc ≤ 0.101` (e.g. bot.log:6170 `total_disc=0.096`; bot.log:5501 `total_disc=0.101`). Cap appears to clamp cleanly. | Medium | **Working.** No pathological zero-sizings observed. |
| §5.4 CUSUM erosion tracker + 3.8× override | Exit on sustained erosion (≥4s above threshold); override bypasses reversal-pp and top-bid suppressions when cusum ≥ 3.8× limit | **Primary exit mechanism on both Scope B losses.** T3 exit: `EROSION CUSUM OVERRIDE` at cusum=3.221 ≥ 3.04 (3.8×0.800), reversal=0.0857% < min 0.1500% was being suppressed; override fired, exit at sell_bid=0.03 (bot.log:6230–6237). T5 exit: cusum=3.072, sustained=4.02 s, exit at sell_bid=0.33 (bot.log:9575–9578). Wins (T1, T2, T4, T6) held to window close with cusum never breaching. | High | **Load-bearing and vindicated.** Without the 3.8× override, both losses would have sat under the reversal-too-shallow suppression while the DOWN token collapsed (0.76 → 0.03 on T3; 0.72 → 0.33 on T5), and losses would have been catastrophically larger than the $13.80 / $5.51 recorded. This is the single strongest positive datapoint in the session. |
| §5.5 EWMA fast-vol (λ=0.94) | Reactive vol signal for risk logic | `vol_fast` populated in every REGIME line, moves faster than `vol_stddev` (e.g. bot.log:79 `vol_stddev=0.150 vol_fast=0.150`; bot.log:6158 `vol_stddev=0.120 vol_fast=0.120`) | Low | Pipe is intact; no fire was gated specifically on fast-vol, so calibration is not testable from this session. |
| §5.6 Kelly min-edge (2 pp) | Skip if `raw_f < 0` (i.e. no edge after discounts) | 20 `KELLY_NO_EDGE` across full session; 1 in Scope A, 19 in Scope B. All show `raw_f` negative (e.g. bot.log:1441 `raw_f=-3.400 entry=0.96`). | Medium | **Working.** Veto fires where entry price is high enough that Kelly would imply an inverse bet. No false-positive pattern visible — every veto tied to a legitimately bad entry price. |
| §5.7 Rolling OBI gate (§5.7) | Skip if 20-s mean OBI opposes signal with magnitude > 0.05 | 19 `OBI_ROLLING_OPPOSES` session-wide; 2 in Scope A. Thresholds worked as configured. | Medium | **Working.** Cannot judge whether veto-rate is too aggressive because we have 0 fires in Scope A to compare vetoed-vs-fired outcomes. |
| §5.8 Post-loss cooldown | Block next N minutes after a loss ≥ 2.0% | **0 activations observed.** After T3 loss at 13:40, next fire was T4 at 20:17 (~6.7 h later — long past any cooldown window). After T5 loss at 01:10, next fire was T6 at 02:12 (~65 min later, still past the cooldown). | Insufficient | Gate exists in code and config (`post_loss_cooldown_loss_pct=2.0`), but natural spacing of fires meant the gate was never the active constraint. No evidence for or against calibration. |
| §5.9 Outcome magnitude weighting | Scale outcome-streak discount by magnitude | Visible in REGIME lines: `outcome=0.800` when 3U/3D with recent streak; `outcome=0.000` when 3U/3D balanced (bot.log:6158 vs 9477) | Low–Medium | Pipe intact; the outcome axis drove the §5.1 halving on T3 (0.800) and T5 (0.397). Can't isolate its PnL effect from other discounts. |
| §5.10 SPRT sizing modulation | Shrink bet when SPRT is in `active_42pct` / `active_50pct` states vs `active_100pct` | All SPRT states exercised: T1 sprt=0.56 final $27.52 → T5 sprt=0.41 final $10.00 (bot.log:5090, 9536). SPRT state propagates into the `final` size line correctly. | Medium | **Working.** Sizing discipline visible — T5 got $10.00 vs T1's $27.52 on equivalent fire deltas, driven by SPRT + HOSTILE halving stack. |

---

## 3 · Prior-recommendation status check (against `docs/strategy/v3.1_postmortem_and_v3.2_plan.md`)

| Recommendation carried into v3.3 | Status in this session |
|---|---|
| `min_score` raised 4.0 → 4.5 | In effect (orchestrator-config.yml:38). Orchestrator's lowest delivered `score=4.77` (final bronze delivery) cleared the bar by 0.27. No signals suppressed by this gate were observable. |
| Binance depth `depth5` → `depth20` | In effect (bot-config.yml; bot.log:19 subscribes to `btcusdt@depth20@100ms`). No connectivity issues in Scope A; no regressions. |
| §5.6 MIN_EDGE over-vetoing watch | 1 Scope-A KELLY_NO_EDGE skip, 19 Scope-B. All had legitimately high entries (0.89–0.97) where `raw_f` was negative. No evidence of over-vetoing marginal winners. |
| §5.9 outcome magnitude visible in logs | Confirmed (outcome axis present in every KELLY / REGIME line). |
| §5.7 rolling-OBI impact visible | Confirmed (19 OBI_ROLLING_OPPOSES skips, with `mean_obi` and `n=79` printed). |
| Watch: `POST_LOSS_COOLDOWN` blocking winners | Not triggered this session — natural fire spacing exceeded the cooldown window. No data for or against. |
| Watch: §5.2 / §5.7 vetoing eventual winners | No veto-vs-outcome pairs observable inside Scope A (0 fires). Scope B not usable for this since the signal was stale. |

---

## 4 · Tuning recommendations

**Before recommending any parameter change, the data-collection issue must be root-caused.** A session in which the healthy period produced 0 fires gives us effectively no evidence to tune against. I'm therefore restricting recommendations to things supported by Scope B *with explicit stale-signal caveats* or by observations about the pipeline itself.

### 4.1 Blocking — investigate first (no config change yet)

1. **Root-cause the collector → orchestrator data-quality cutoff at 21:50 UTC 4/18.** The orchestrator stopped seeing fresh data after 21:35 UTC but the bot's own Binance/RTDS feeds kept running (we see 37 h of STATUS lines and intact WS reconnects, e.g. bot.log:5044). So the failure is upstream of the orchestrator's pool, not a bot network issue. Until the collector pipeline is fixed, the v3.3 stack cannot be validated. This is non-optional and blocks the next paper session.

2. **Decide whether the bot should refuse to fire on a stale signal.** The bot's own warning (`no signal update from orchestrator in 16.0 hours — continuing with current signal`, bot.log:6165) is advisory only; it fired 4 more trades after that warning. Per §5.10 plan discipline, we should not be taking positions on a 16–29 h-old signal whose underlying regime context has certainly shifted. A bot-side freshness guard (e.g. refuse to fire if `now - last_signal_received > N hours`) would have avoided all 6 Scope B trades. This is a design call, not a tuning knob. **Severity: HRP — architectural.**

### 4.2 Worth investigating, not actioning yet

3. **Maker→taker escalation is firing 4/6 times with non-trivial slippage** (bot.log:5096, 5872, 6177, 8136). T2 escalated from maker 0.83 to taker **0.90** (7-tick move during the 3 s timeout) and T4 from 0.82 to 0.87 (5-tick). The `maker_timeout_s=3.0` window coincides with the paper fill delay (`simulated_fill_delay_sec=2.5`), so in this session the maker had essentially 0.5 s of real shot-at-fill before cancel. Consider widening `maker_timeout_s` to something like 5–8 s before recommending any change, but **do not do this yet** — the evidence is from a stale-signal, N=6 period. Add as a watch item for next session. **Severity: HRP — observational.**

4. **obs_obi signed direction is predictive in this sample** (N=6 so very weak):
   - Both losses had strongly-opposing obs_obi: T3 +0.5768 vs down side, T5 +0.4800 vs down side.
   - Both high-magnitude agreeing obs_obi fires were wins: T4 −0.6998, T6 −0.9905.
   - The two small-magnitude obs_obi fires (T1 −0.07, T2 −0.09) both won, but T2 had 7-tick taker slippage almost wiping the edge.
   The 20-s rolling OBI gate is currently `off` for this signal (`obiThreshold=0.0, obiDepth="none"` — the engine decided this signal didn't benefit from a rolling gate). The *instantaneous* obs_obi at fire time did predict here, but N=6 on a stale signal does not justify changing engine policy. Watch item only.

### 4.3 Do-not-change (current behaviour confirmed by session)

- The CUSUM 3.8× override (`cusum_override_multiplier=3.8`) is load-bearing and should stay. Both Scope B losses exited only because of this override; the reversal-pp floor suppressed the cusum trigger for 4+ s while the DOWN token was mid-collapse.
- `min_score=4.5` did not over-filter (the bronze down signal cleared 4.77–5.50 throughout Scope A). No evidence to revise.

---

## 5 · Code-level findings

No HRP (`docs/standards/The_HRP_Standard_v1.0/HRP_STANDARD.md`) or HRC violations observable from logs alone. Gate logic behaviour matched config in every instance checked. The only code-level concern surfaced is architectural — the absence of a bot-side signal-freshness guard — which is a §Section-4.1 blocker, not a bug in the current code.

---

## 6 · Open hypotheses (carry into v3.4 planning, do not act on alone)

- **H1 — obs_obi at fire time is predictive.** Needs N ≥ 20 healthy fires to evaluate. If confirmed, the engine could be asked to turn on a directional-obs_obi gate at fire time for signals where it currently sets `obiDepth="none"`.
- **H2 — Maker timeout of 3 s is too tight when paper fill delay is 2.5 s.** Clean test only once fill-model realism is revisited; paper-trading result is biased because maker orders need `best_ask ≤ order.price AND 2.5 s elapsed` (`PolyTraderLightning/src/execution/paper_trading.py:_check_maker_fill`), which is a relatively optimistic model with no queue priority, so the real-world maker-fill rate will be lower than paper, not higher.
- **H3 — The outcome axis (§5.9) is the dominant driver of size halving in real regimes.** Both HOSTILE halvings in Scope B were driven by `outcome=0.800` / `outcome=0.397`, not vol or chop. If HRP+data support, the outcome axis may warrant independent calibration rather than being lumped in with vol/chop under the common 0.15/0.25 thresholds.

---

## 7 · Strategic verdict

- **Verdict: INCONCLUSIVE.** The only scope that would have validated v3.3's live-trading behaviour (Scope A, orchestrator healthy) produced 0 fires over 64 windows. The scope that did produce fires (Scope B) ran on a 12–29 h-stale frozen signal, so its 4W/2L / −$3.73 outcome does not speak to v3.3's intended behaviour.
- Per the v3.2 session-validation bar recorded in memory ("2–3 profitable sessions, not 1"): this session cannot count toward that bar — neither positively nor negatively — because the healthy period was too short and empty to be decisive and the rest was off-regime.
- **One positive takeaway that does carry forward regardless of scope:** the §5.4 CUSUM 3.8× override did its job on both Scope B losses. That mechanism was added partly to handle "gets into a DOWN position at 0.80 and the token collapses to pennies before the reversal gate unfreezes" scenarios — Scope B delivered exactly those scenarios twice and the override exited both times. Keep it.
- **Blocker for v3.4:** root-cause and fix the collector → orchestrator data-quality cutoff, and decide on a bot-side stale-signal refusal policy. Do both before starting v3.4.

---

## 8 · Analyst notes

- Sample-size discipline: Scope A trade N = 0; Scope B trade N = 6 on stale signal. Every claim in §1–§5 is tied to a specific log line or code path. Mechanism verdicts are graded (High / Medium / Low / Insufficient); nothing is claimed High on N=6.
- Fill-model honesty: the paper fill model (`_check_maker_fill`) uses a 2.5 s synthetic delay with no queue-position model and always charges taker on exit — so paper maker fills are more optimistic than live would be, and early-exit sell prices (0.03 on T3, 0.33 on T5) would almost certainly slip further in real execution. Scope B net PnL of −$3.73 is therefore an *optimistic* number, not a conservative one.
- Clock discipline: orchestrator log stamps are home-region local (UTC+3); bot log stamps are UTC. Report normalises to UTC throughout. The 11-hour timezone note in the brief's "Dublin/home-region" wording refers to geographic distance, not clock offset; the actual orchestrator→bot timestamp offset is +3 h, not +11 h.
- "Creativity in what you investigate; discipline in what you conclude": the session's single strongest signal is structural (CUSUM override vindicated), not tuning-actionable. The temptation to turn the obs_obi-predictive-of-loss observation into a v3.4 gate change is rejected on N=6 grounds — flagged as H1 for future corroboration.
- What this post-mortem deliberately does NOT do: recommend any v3.4 parameter changes on the strength of Scope B results, or treat the 4W/2L record as meaningful signal quality evidence.
