# Skip tuner report
_generated 2026-04-18T12:14:05+00:00_

- input: `C:\Users\user\ll_projects\tradingprojects\PolySignalLab\PolyDataLibrary\system_logs\data.txt`
- config: per_trade_cost=0.01  min_n=30  train_frac=0.6  k_folds=5  bootstrap=10000  permutations=2000  seed=0

## VERDICT: FAIL — none

no stratum showed a net-positive best cell that could survive scrutiny (best stratum ALL: net +321.50, perm p=1.000, test PnL=+81.76)

### How to read this
- *Credible* requires bootstrap lower CI > 0, Bonferroni-corrected permutation p < 0.05, positive walk-forward test PnL, ≥50% fold stability, and majority of sessions positive. All five together rule out the common failure modes.
- *Suggestive* means some but not all gates passed — might be real, worth more data.
- *No credible edge* is the honest answer when the data can't distinguish the result from noise.

## Stratum: ALL

- trades: **862**  (wins: 407 / losses: 455)
- base win-rate: **47.22%**
- avg entry ask: **0.4982**  (break-even win-rate: **49.82%**)
- naive net if all skips were taken: **+69.10** USD

### Single-knob best (each swept with others permissive)

| knob | best value | n | W | L | avg ask | $won | $lost | net | ROI |
|------|-----------:|--:|--:|--:|--------:|-----:|------:|----:|----:|
| mom_offset | +0.1200 | 543 | 323 | 220 | 0.6152 | +480.30 | +225.43 | **+254.87** | +46.94% |
| var_offset | +0.0000 | 783 | 384 | 399 | 0.5184 | +507.80 | +406.83 | **+100.97** | +12.90% |
| ask_cap | +0.7000 | 396 | 19 | 377 | 0.0449 | +503.97 | +380.96 | **+123.01** | +31.06% |
| min_abs_pct | +0.0100 | 690 | 344 | 346 | 0.5227 | +504.83 | +352.90 | **+151.93** | +22.02% |

### Top combinations — train / test split (60/40 chronological)

Cells are ranked by **train** net PnL. The test column is out-of-sample. A large train > test gap is the overfit tell.

| # | mom_off | var_off | ask_cap | min_abs | train n | tr W | tr L | train $ | test n | te W | te L | test $ |
|--:|--------:|--------:|--------:|--------:|--------:|-----:|-----:|--------:|-------:|-----:|-----:|-------:|
| 1 | +0.120 | -0.020 | 0.85 | 0.010 | 100 | 13 | 87 | **+238.01** | 74 | 6 | 68 | **+81.76** |
| 2 | +0.120 | -0.020 | 0.90 | 0.010 | 100 | 13 | 87 | **+238.01** | 75 | 7 | 68 | **+81.89** |
| 3 | +0.120 | -0.020 | 0.80 | 0.010 | 98 | 11 | 87 | **+237.61** | 72 | 5 | 67 | **+82.59** |
| 4 | +0.120 | -0.020 | 0.75 | 0.010 | 98 | 11 | 87 | **+237.61** | 72 | 5 | 67 | **+82.59** |
| 5 | +0.120 | -0.020 | 0.65 | 0.010 | 97 | 10 | 87 | **+237.21** | 69 | 4 | 65 | **+84.29** |
| 6 | +0.120 | -0.020 | 0.70 | 0.010 | 97 | 10 | 87 | **+237.21** | 69 | 4 | 65 | **+84.29** |
| 7 | +0.120 | -0.020 | 0.95 | 0.010 | 103 | 15 | 88 | **+237.16** | 79 | 11 | 68 | **+82.06** |
| 8 | +0.120 | -0.020 | 0.60 | 0.010 | 95 | 8 | 87 | **+236.00** | 69 | 4 | 65 | **+84.29** |
| 9 | +0.120 | -0.020 | 0.55 | 0.010 | 95 | 8 | 87 | **+236.00** | 68 | 3 | 65 | **+83.54** |
| 10 | +0.120 | -0.020 | 0.50 | 0.010 | 94 | 7 | 87 | **+235.20** | 68 | 3 | 65 | **+83.54** |

### Best cell (by full-data net PnL) — deep dive

- strategy: `mom_offset=+0.1200  var_offset=-0.0200  ask_cap=0.65  min_abs_pct=0.0100`
- full data: n=166  wins=14  losses=152  avg_ask=0.0507
- cashflow: $won=**+$475.16**  $lost=**-$153.66**  net=**+321.50**
- walk-forward: train net **+238.01** (13W/87L on 100)  → test net **+81.76** (6W/68L on 74)
- 5-fold stability: **4/5** folds positive (score=0.80)  [f0: +80.23  f1: +73.74  f2: +83.24  f3: -42.22  f4: +126.50]
- bootstrap 10k resamples of captured trades: mean +322.49  95% CI [**-35.30, +755.33**]  P(net>0)=0.957
- permutation null (2000 shuffles): p=**1.0000**  (Bonferroni across strata: 1.0000)

#### Per-session breakdown on best cell
| session | n | W | L | net $ |
|---------|--:|--:|--:|------:|
| v3.0_paper_logs | 46 | 3 | 43 | **+75.18** |
| v3.1_paper_logs | 95 | 8 | 87 | **+119.81** |
| v3.2_paper_logs | 25 | 3 | 22 | **+126.50** |

#### Per-signal_id breakdown on best cell (top 10 by n)
| signal_id | n | W | L | net $ |
|-----------|--:|--:|--:|------:|
| up_230_200_0.06_0.05 | 28 | 2 | 26 | **+91.72** |
| down_220_190_0.14_0.1 | 14 | 1 | 13 | **+35.86** |
| down_250_220_0.11_0.1 | 14 | 4 | 10 | **+95.54** |
| down_270_240_0.08_0.15 | 13 | 0 | 13 | **-13.13** |
| up_230_200_0.08_0.1 | 13 | 1 | 12 | **-10.91** |
| down_210_180_0.15_0.1 | 11 | 2 | 9 | **+90.64** |
| up_230_170_0.06_0.05 | 9 | 0 | 9 | **-9.09** |
| down_270_160_0.13_0.05 | 8 | 0 | 8 | **-8.08** |
| down_240_210_0.12_0.1 | 7 | 0 | 7 | **-7.07** |
| down_270_240_0.07_0.15 | 6 | 0 | 6 | **-6.06** |


## Stratum: UP

- trades: **271**  (wins: 131 / losses: 140)
- base win-rate: **48.34%**
- avg entry ask: **0.4895**  (break-even win-rate: **48.95%**)
- naive net if all skips were taken: **+27.01** USD

### Single-knob best (each swept with others permissive)

| knob | best value | n | W | L | avg ask | $won | $lost | net | ROI |
|------|-----------:|--:|--:|--:|--------:|-----:|------:|----:|----:|
| mom_offset | +0.0900 | 120 | 83 | 37 | 0.7102 | +101.08 | +38.20 | **+62.88** | +52.40% |
| var_offset | +0.0000 | 239 | 120 | 119 | 0.5122 | +145.72 | +121.39 | **+24.33** | +10.18% |
| ask_cap | +0.8500 | 127 | 10 | 117 | 0.0694 | +145.44 | +118.27 | **+27.17** | +21.40% |
| min_abs_pct | +0.0200 | 183 | 81 | 102 | 0.4566 | +143.66 | +103.83 | **+39.83** | +21.76% |

### Top combinations — train / test split (60/40 chronological)

Cells are ranked by **train** net PnL. The test column is out-of-sample. A large train > test gap is the overfit tell.

| # | mom_off | var_off | ask_cap | min_abs | train n | tr W | tr L | train $ | test n | te W | te L | test $ |
|--:|--------:|--------:|--------:|--------:|--------:|-----:|-----:|--------:|-------:|-----:|-----:|-------:|
| 1 | +0.110 | +0.010 | 0.75 | 0.020 | 30 | 3 | 27 | **+91.34** | 14 | 1 | 13 | **-12.81** |
| 2 | +0.110 | +0.010 | 0.65 | 0.020 | 30 | 3 | 27 | **+91.34** | 13 | 0 | 13 | **-13.13** |
| 3 | +0.110 | -0.010 | 0.85 | 0.020 | 30 | 3 | 27 | **+91.34** | 13 | 1 | 12 | **-11.80** |
| 4 | +0.110 | +0.010 | 0.90 | 0.020 | 30 | 3 | 27 | **+91.34** | 14 | 1 | 13 | **-12.81** |
| 5 | +0.110 | +0.010 | 0.80 | 0.020 | 30 | 3 | 27 | **+91.34** | 14 | 1 | 13 | **-12.81** |
| 6 | +0.110 | +0.010 | 0.70 | 0.020 | 30 | 3 | 27 | **+91.34** | 13 | 0 | 13 | **-13.13** |
| 7 | +0.110 | +0.000 | 0.90 | 0.020 | 30 | 3 | 27 | **+91.34** | 13 | 1 | 12 | **-11.80** |
| 8 | +0.110 | +0.010 | 0.85 | 0.020 | 30 | 3 | 27 | **+91.34** | 14 | 1 | 13 | **-12.81** |
| 9 | +0.110 | -0.010 | 0.75 | 0.020 | 30 | 3 | 27 | **+91.34** | 13 | 1 | 12 | **-11.80** |
| 10 | +0.110 | -0.010 | 0.70 | 0.020 | 30 | 3 | 27 | **+91.34** | 12 | 0 | 12 | **-12.12** |

### Best cell (by full-data net PnL) — deep dive

- strategy: `mom_offset=+0.1100  var_offset=-0.0200  ask_cap=0.75  min_abs_pct=0.0200`
- full data: n=40  wins=4  losses=36  avg_ask=0.0530
- cashflow: $won=**+$118.97**  $lost=**-$36.40**  net=**+82.57**
- walk-forward: train net **+91.34** (3W/27L on 30)  → test net **-9.09** (0W/9L on 9)
- 5-fold stability: **1/5** folds positive (score=0.20)  [f0: -9.09  f1: +109.52  f2: -9.09  f3: -8.77  f4: +0.00]
- bootstrap 10k resamples of captured trades: mean +81.65  95% CI [**-39.07, +302.27**]  P(net>0)=0.721
- permutation null (2000 shuffles): p=**1.0000**  (Bonferroni across strata: 1.0000)

#### Per-session breakdown on best cell
| session | n | W | L | net $ |
|---------|--:|--:|--:|------:|
| v3.0_paper_logs | 23 | 3 | 20 | **+98.41** |
| v3.1_paper_logs | 17 | 1 | 16 | **-15.84** |

#### Per-signal_id breakdown on best cell (top 10 by n)
| signal_id | n | W | L | net $ |
|-----------|--:|--:|--:|------:|
| up_230_200_0.06_0.05 | 22 | 2 | 20 | **+97.78** |
| up_230_200_0.08_0.1 | 10 | 1 | 9 | **-8.77** |
| up_230_170_0.06_0.05 | 7 | 0 | 7 | **-7.07** |
| up_270_150_0.06_0.05 | 1 | 1 | 0 | **+0.63** |


## Stratum: DOWN

- trades: **591**  (wins: 276 / losses: 315)
- base win-rate: **46.70%**
- avg entry ask: **0.5021**  (break-even win-rate: **50.21%**)
- naive net if all skips were taken: **+42.09** USD

### Single-knob best (each swept with others permissive)

| knob | best value | n | W | L | avg ask | $won | $lost | net | ROI |
|------|-----------:|--:|--:|--:|--------:|-----:|------:|----:|----:|
| mom_offset | +0.1200 | 366 | 214 | 152 | 0.6121 | +358.86 | +155.66 | **+203.20** | +55.52% |
| var_offset | -0.0200 | 513 | 246 | 267 | 0.5186 | +359.93 | +272.13 | **+87.80** | +17.11% |
| ask_cap | +0.6500 | 273 | 13 | 260 | 0.0442 | +359.65 | +262.73 | **+96.92** | +35.50% |
| min_abs_pct | +0.0100 | 478 | 241 | 237 | 0.5346 | +359.93 | +241.78 | **+118.15** | +24.72% |

### Top combinations — train / test split (60/40 chronological)

Cells are ranked by **train** net PnL. The test column is out-of-sample. A large train > test gap is the overfit tell.

| # | mom_off | var_off | ask_cap | min_abs | train n | tr W | tr L | train $ | test n | te W | te L | test $ |
|--:|--------:|--------:|--------:|--------:|--------:|-----:|-----:|--------:|-------:|-----:|-----:|-------:|
| 1 | +0.120 | -0.020 | 0.95 | 0.010 | 67 | 11 | 56 | **+150.64** | 58 | 7 | 51 | **+97.61** |
| 2 | +0.120 | -0.020 | 0.90 | 0.010 | 65 | 9 | 56 | **+150.49** | 56 | 5 | 51 | **+97.52** |
| 3 | +0.120 | -0.020 | 0.85 | 0.010 | 65 | 9 | 56 | **+150.49** | 55 | 4 | 51 | **+97.39** |
| 4 | +0.120 | -0.020 | 0.75 | 0.010 | 64 | 8 | 56 | **+150.31** | 53 | 3 | 50 | **+98.22** |
| 5 | +0.120 | -0.020 | 0.80 | 0.010 | 64 | 8 | 56 | **+150.31** | 53 | 3 | 50 | **+98.22** |
| 6 | +0.120 | -0.020 | 0.65 | 0.010 | 63 | 7 | 56 | **+149.91** | 51 | 3 | 48 | **+100.24** |
| 7 | +0.120 | -0.020 | 0.70 | 0.010 | 63 | 7 | 56 | **+149.91** | 51 | 3 | 48 | **+100.24** |
| 8 | +0.120 | -0.020 | 0.60 | 0.010 | 62 | 6 | 56 | **+149.33** | 51 | 3 | 48 | **+100.24** |
| 9 | +0.120 | -0.020 | 0.55 | 0.010 | 62 | 6 | 56 | **+149.33** | 50 | 2 | 48 | **+99.50** |
| 10 | +0.120 | -0.020 | 0.50 | 0.010 | 61 | 5 | 56 | **+148.53** | 50 | 2 | 48 | **+99.50** |

### Best cell (by full-data net PnL) — deep dive

- strategy: `mom_offset=+0.1200  var_offset=-0.0200  ask_cap=0.65  min_abs_pct=0.0100`
- full data: n=114  wins=10  losses=104  avg_ask=0.0562
- cashflow: $won=**+$355.30**  $lost=**-$105.14**  net=**+250.16**
- walk-forward: train net **+150.64** (11W/56L on 67)  → test net **+97.61** (7W/51L on 58)
- 5-fold stability: **3/5** folds positive (score=0.60)  [f0: +79.80  f1: -20.20  f2: +90.31  f3: -28.28  f4: +128.52]
- bootstrap 10k resamples of captured trades: mean +250.67  95% CI [**-51.94, +646.53**]  P(net>0)=0.934
- permutation null (2000 shuffles): p=**1.0000**  (Bonferroni across strata: 1.0000)

#### Per-session breakdown on best cell
| session | n | W | L | net $ |
|---------|--:|--:|--:|------:|
| v3.0_paper_logs | 17 | 0 | 17 | **-17.17** |
| v3.1_paper_logs | 72 | 7 | 65 | **+140.82** |
| v3.2_paper_logs | 25 | 3 | 22 | **+126.50** |

#### Per-signal_id breakdown on best cell (top 10 by n)
| signal_id | n | W | L | net $ |
|-----------|--:|--:|--:|------:|
| down_220_190_0.14_0.1 | 14 | 1 | 13 | **+35.86** |
| down_250_220_0.11_0.1 | 14 | 4 | 10 | **+95.54** |
| down_270_240_0.08_0.15 | 13 | 0 | 13 | **-13.13** |
| down_210_180_0.15_0.1 | 11 | 2 | 9 | **+90.64** |
| down_270_160_0.13_0.05 | 8 | 0 | 8 | **-8.08** |
| down_240_210_0.12_0.1 | 7 | 0 | 7 | **-7.07** |
| down_270_240_0.07_0.15 | 6 | 0 | 6 | **-6.06** |
| down_290_250_0.07_0.05 | 5 | 0 | 5 | **-5.05** |
| down_270_170_0.13_0.05 | 4 | 0 | 4 | **-4.04** |
| down_290_150_0.1_0.05 | 4 | 0 | 4 | **-4.04** |


## Bot patch shape (informational — do NOT apply without positive verdict)

For stratum **ALL**:

```python
# in momentum_signal._conditions_met()
effective_d   = max(sc.min_delta_pct - 0.1200, 0.0)
effective_var = sc.max_variance_pct - 0.0200
if self._population_stddev() > effective_var: return False
if sc.side == Direction.UP   and self._latest_pct <  effective_d: return False
if sc.side == Direction.DOWN and self._latest_pct > -effective_d: return False
if abs(self._latest_pct) < 0.0100: return False
# paper_trading-side gate (needs ask available at decision time):
if entry_ask > 0.65: return False
```

## Known limitations

- **Selection bias:** every trade in this analysis is a bot **skip**. Conclusions only apply to the skip population — a rule tuned here might behave differently on trades the bot currently takes.
- **Costs assumed flat:** slippage, gas and order-book dynamics are folded into the single per-trade cost parameter. Real per-trade cost varies with ask depth and size.
- **Outcome trusted from paper_trading log:** we use the bot's recorded resolution; no independent cross-check against Polymarket.
- **Window parameters fixed:** observe_from_s / observe_to_s come from the active signal. We don't search over those because they aren't replayable from skip records.
- **Temporal structure beyond chronological split not modeled:** if markets cluster by regime, walk-forward with k=5 may under- or over-estimate stability.
