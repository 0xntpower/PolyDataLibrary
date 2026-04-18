"""Analysis orchestration and report writers.

run_analysis() is the one public entry: given a data.txt path and a
config, it stratifies by side, runs the full safeguard stack per stratum,
assembles a verdict, and writes report.md + report.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .collect import load_jsonl
from .model import Strategy, Trades, pnl_array, trades_from_records
from .schema import SkipRecord
from .stats import (
    BootstrapCI,
    GroupBreakdown,
    PermutationResult,
    StabilityResult,
    TrainTestResult,
    bootstrap_ci,
    group_breakdown_for_cell,
    k_fold_stability,
    permutation_null,
    pick_best,
    train_test_split,
)
from .sweep import CellMetrics, Grid, build_cell_masks, default_grid, evaluate_grid


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    per_trade_cost: float
    min_n: int
    train_frac: float
    k_folds: int
    n_bootstrap: int
    n_permutations: int
    random_seed: int


@dataclass(frozen=True, slots=True)
class KnobResult:
    knob: str
    best_value: float
    n: int
    wins: int
    losses: int
    avg_ask: float
    gross_won: float
    gross_lost: float
    net_pnl: float
    roi_pct: float


@dataclass(frozen=True, slots=True)
class CombinationRow:
    rank: int
    strategy: Strategy
    train_n: int
    train_wins: int
    train_losses: int
    train_net: float
    test_n: int
    test_wins: int
    test_losses: int
    test_net: float


@dataclass(frozen=True, slots=True)
class StratumReport:
    stratum: str
    n_trades: int
    n_wins: int
    base_winrate_pct: float
    avg_ask: float
    break_even_wr_pct: float
    naive_net_if_took_all: float
    single_knob: list[KnobResult]
    top_combinations: list[CombinationRow]
    best_strategy: Strategy
    best_cell_n: int
    best_cell_wins: int
    best_cell_losses: int
    best_cell_gross_won: float
    best_cell_gross_lost: float
    best_cell_net: float
    best_cell_avg_ask: float
    train_test: TrainTestResult
    stability: StabilityResult
    bootstrap: BootstrapCI
    permutation_p: float
    permutation_n: int
    permutation_bonferroni_p: float
    per_session: list[GroupBreakdown]
    per_signal: list[GroupBreakdown]


def _net_metrics_for_cell(
    metrics: CellMetrics, trades: Trades, masks_row: np.ndarray, per_trade_cost: float,
) -> tuple[float, float, float]:
    pnl = pnl_array(trades, per_trade_cost)
    sel = masks_row.astype(bool)
    won = trades.won[sel]
    ask = trades.entry_ask[sel]
    gross_won = float(((1.0 - ask[won]) / ask[won]).sum())
    losses = int((~won).sum())
    gross_lost = float(losses) + per_trade_cost * sel.sum()
    net = float(pnl[sel].sum())
    return gross_won, gross_lost, net


def _single_knob_best(
    trades: Trades,
    knob: str,
    offsets: np.ndarray,
    per_trade_cost: float,
    min_n: int,
    fixed_ask_cap: float,
    fixed_pct_floor: float,
) -> KnobResult:
    """Sweep one knob holding others at permissive defaults (ask_cap=1.0,
    pct_floor=0.0, and whichever of mom/var is not being swept fixed at
    the loosest value in the default grid)."""
    best: tuple[float, int, int, int, float, float, float, float] | None = None
    pnl_per_trade = pnl_array(trades, per_trade_cost)
    for val in offsets:
        if knob == "mom_offset":
            mask = (
                (trades.mom_gap <= val + 1e-12)
                & (trades.var_gap <= 0.05 + 1e-12)
                & (trades.entry_ask <= fixed_ask_cap + 1e-12)
                & (trades.abs_latest_pct >= fixed_pct_floor - 1e-12)
            )
        elif knob == "var_offset":
            mask = (
                (trades.mom_gap <= 0.20 + 1e-12)
                & (trades.var_gap <= val + 1e-12)
                & (trades.entry_ask <= fixed_ask_cap + 1e-12)
                & (trades.abs_latest_pct >= fixed_pct_floor - 1e-12)
            )
        elif knob == "ask_cap":
            mask = (
                (trades.mom_gap <= 0.20 + 1e-12)
                & (trades.var_gap <= 0.05 + 1e-12)
                & (trades.entry_ask <= val + 1e-12)
                & (trades.abs_latest_pct >= fixed_pct_floor - 1e-12)
            )
        elif knob == "min_abs_pct":
            mask = (
                (trades.mom_gap <= 0.20 + 1e-12)
                & (trades.var_gap <= 0.05 + 1e-12)
                & (trades.entry_ask <= fixed_ask_cap + 1e-12)
                & (trades.abs_latest_pct >= val - 1e-12)
            )
        else:
            raise ValueError(f"unknown knob {knob}")

        n = int(mask.sum())
        if n < min_n:
            continue
        wins = int(trades.won[mask].sum())
        losses = n - wins
        ask_sel = trades.entry_ask[mask]
        won_sel = trades.won[mask]
        gross_won = float(((1.0 - ask_sel[won_sel]) / ask_sel[won_sel]).sum())
        gross_lost = float(losses) + per_trade_cost * n
        net = float(pnl_per_trade[mask].sum())
        avg_ask = float(ask_sel.mean())
        row = (float(val), n, wins, losses, avg_ask, gross_won, gross_lost, net)
        if best is None or net > best[7]:
            best = row

    if best is None:
        return KnobResult(knob, 0.0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    val, n, wins, losses, avg_ask, gross_won, gross_lost, net = best
    roi = (net / n * 100.0) if n else 0.0
    return KnobResult(
        knob=knob,
        best_value=val,
        n=n,
        wins=wins,
        losses=losses,
        avg_ask=avg_ask,
        gross_won=gross_won,
        gross_lost=gross_lost,
        net_pnl=net,
        roi_pct=roi,
    )


def _top_combinations_with_holdout(
    trades: Trades,
    grid: Grid,
    masks: np.ndarray,
    metrics: CellMetrics,
    per_trade_cost: float,
    min_n: int,
    train_frac: float,
    top_k: int,
) -> list[CombinationRow]:
    """Rank cells by train-set PnL (with train-set min_n); compute test PnL
    for the same cells on the held-out tail. Exposes the train-vs-test gap
    directly in the report — the clearest single overfit signal.
    """
    n = trades.n
    cut = int(round(n * train_frac))
    cut = max(min_n, min(n - min_n, cut))

    pnl = pnl_array(trades, per_trade_cost)
    masks_f = masks.astype(np.float64)
    masks_i = masks.astype(np.int64)
    won_int = trades.won.astype(np.int64)

    train_counts = masks_i[:, :cut].sum(axis=1)
    train_wins = (masks_i[:, :cut] * won_int[None, :cut]).sum(axis=1)
    train_net = masks_f[:, :cut] @ pnl[:cut]
    test_counts = masks_i[:, cut:].sum(axis=1)
    test_wins = (masks_i[:, cut:] * won_int[None, cut:]).sum(axis=1)
    test_net = masks_f[:, cut:] @ pnl[cut:]

    eligible = train_counts >= min_n
    masked = np.where(eligible, train_net, -np.inf)
    order = np.argsort(-masked)

    rows: list[CombinationRow] = []
    for rank, idx in enumerate(order[:top_k], start=1):
        if not eligible[idx]:
            break
        strat = grid.strategy_at(int(idx))
        rows.append(
            CombinationRow(
                rank=rank,
                strategy=strat,
                train_n=int(train_counts[idx]),
                train_wins=int(train_wins[idx]),
                train_losses=int(train_counts[idx] - train_wins[idx]),
                train_net=float(train_net[idx]),
                test_n=int(test_counts[idx]),
                test_wins=int(test_wins[idx]),
                test_losses=int(test_counts[idx] - test_wins[idx]),
                test_net=float(test_net[idx]),
            )
        )
    return rows


def _stratum(label: str, trades: Trades) -> Trades:
    if label == "ALL":
        return trades
    mask = trades.side == label.lower()
    return trades.subset(mask)


def analyze_stratum(
    label: str,
    trades: Trades,
    grid: Grid,
    config: AnalysisConfig,
    n_strata_for_bonferroni: int,
) -> StratumReport | None:
    if trades.n < config.min_n * 2:
        return None

    masks = build_cell_masks(trades, grid)
    metrics = evaluate_grid(trades, masks, config.per_trade_cost)

    # Single-knob results (each knob swept with other knobs permissive).
    single = [
        _single_knob_best(trades, "mom_offset", grid.mom_offsets, config.per_trade_cost, config.min_n, 1.0, 0.0),
        _single_knob_best(trades, "var_offset", grid.var_offsets, config.per_trade_cost, config.min_n, 1.0, 0.0),
        _single_knob_best(trades, "ask_cap", grid.ask_caps, config.per_trade_cost, config.min_n, 1.0, 0.0),
        _single_knob_best(trades, "min_abs_pct", grid.pct_floors, config.per_trade_cost, config.min_n, 1.0, 0.0),
    ]

    top_combos = _top_combinations_with_holdout(
        trades=trades,
        grid=grid,
        masks=masks,
        metrics=metrics,
        per_trade_cost=config.per_trade_cost,
        min_n=config.min_n,
        train_frac=config.train_frac,
        top_k=10,
    )

    best_idx = pick_best(metrics, config.min_n)
    best_strat = grid.strategy_at(best_idx)
    best_n = int(metrics.counts[best_idx])
    best_wins = int(metrics.wins[best_idx])
    best_losses = best_n - best_wins
    best_net = float(metrics.net_pnl[best_idx])
    best_gross_won = float(metrics.gross_won[best_idx])
    best_avg_ask = float(metrics.avg_ask[best_idx])
    best_gross_lost = float(best_losses) + config.per_trade_cost * best_n

    rng = np.random.default_rng(config.random_seed)
    tt = train_test_split(
        trades, masks, config.per_trade_cost, config.train_frac, config.min_n
    )
    stability = k_fold_stability(
        trades, masks, best_idx, config.per_trade_cost, config.k_folds
    )
    boot = bootstrap_ci(
        trades, masks, best_idx, config.per_trade_cost, config.n_bootstrap, rng
    )
    perm = permutation_null(
        trades, masks, config.per_trade_cost, config.min_n, config.n_permutations, rng
    )
    bonf_p = min(1.0, perm.p_value * n_strata_for_bonferroni)

    per_session = group_breakdown_for_cell(
        trades, masks, best_idx, config.per_trade_cost, trades.session
    )
    per_signal = group_breakdown_for_cell(
        trades, masks, best_idx, config.per_trade_cost, trades.signal_id
    )

    base_wins = int(trades.won.sum())
    base_wr = base_wins / trades.n * 100.0 if trades.n else 0.0
    avg_ask_all = float(trades.entry_ask.mean())
    break_even_wr = avg_ask_all * 100.0
    naive_net = float(pnl_array(trades, config.per_trade_cost).sum())

    return StratumReport(
        stratum=label,
        n_trades=trades.n,
        n_wins=base_wins,
        base_winrate_pct=base_wr,
        avg_ask=avg_ask_all,
        break_even_wr_pct=break_even_wr,
        naive_net_if_took_all=naive_net,
        single_knob=single,
        top_combinations=top_combos,
        best_strategy=best_strat,
        best_cell_n=best_n,
        best_cell_wins=best_wins,
        best_cell_losses=best_losses,
        best_cell_gross_won=best_gross_won,
        best_cell_gross_lost=best_gross_lost,
        best_cell_net=best_net,
        best_cell_avg_ask=best_avg_ask,
        train_test=tt,
        stability=stability,
        bootstrap=boot,
        permutation_p=perm.p_value,
        permutation_n=perm.n_permutations,
        permutation_bonferroni_p=bonf_p,
        per_session=per_session,
        per_signal=per_signal,
    )


def _verdict(reports: list[StratumReport]) -> tuple[str, str]:
    """Return (tier, reason). Tiers: 'credible', 'suggestive', 'none'."""
    if not reports:
        return ("none", "no stratum had enough data")

    def passes_credible(r: StratumReport) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        ok = True
        if r.bootstrap.lower_95 <= 0:
            ok = False
            reasons.append(f"bootstrap 95% CI lower bound is {r.bootstrap.lower_95:+.2f} (not > 0)")
        if r.permutation_bonferroni_p >= 0.05:
            ok = False
            reasons.append(f"permutation p (Bonferroni) is {r.permutation_bonferroni_p:.3f} (not < 0.05)")
        if r.train_test.test_net <= 0:
            ok = False
            reasons.append(f"walk-forward test PnL is {r.train_test.test_net:+.2f} (not > 0)")
        if r.stability.stability_score < 0.5:
            ok = False
            reasons.append(
                f"stability score is {r.stability.stability_score:.2f} "
                f"({r.stability.positive_fold_count}/{r.stability.fold_count} folds positive, need ≥ 0.5)"
            )
        positive_sessions = sum(1 for g in r.per_session if g.net_pnl > 0)
        if positive_sessions < max(2, (len(r.per_session) + 1) // 2):
            ok = False
            reasons.append(
                f"only {positive_sessions}/{len(r.per_session)} sessions positive on best cell"
            )
        return ok, reasons

    def passes_suggestive(r: StratumReport) -> bool:
        # Softer: positive CI mean, at-or-near significant permutation p, positive test net.
        return (
            r.best_cell_net > 0
            and r.train_test.test_net > 0
            and r.permutation_p < 0.15
        )

    credible = [r for r in reports if passes_credible(r)[0]]
    if credible:
        winners = ", ".join(r.stratum for r in credible)
        return ("credible", f"strata passing all gates: {winners}")

    suggestive = [r for r in reports if passes_suggestive(r)]
    if suggestive:
        winners = ", ".join(r.stratum for r in suggestive)
        # Collect reasons why credible wasn't reached for the most profitable
        best = max(reports, key=lambda r: r.best_cell_net)
        _, reasons = passes_credible(best)
        return (
            "suggestive",
            f"strata showing promise: {winners}; gates missed by best stratum ({best.stratum}): " + "; ".join(reasons),
        )

    best = max(reports, key=lambda r: r.best_cell_net)
    return (
        "none",
        f"no stratum showed a net-positive best cell that could survive scrutiny "
        f"(best stratum {best.stratum}: net {best.best_cell_net:+.2f}, "
        f"perm p={best.permutation_p:.3f}, test PnL={best.train_test.test_net:+.2f})",
    )


def _fmt_strategy(s: Strategy) -> str:
    return (
        f"mom_offset={s.mom_offset:+.4f}  "
        f"var_offset={s.var_offset:+.4f}  "
        f"ask_cap={s.ask_cap:.2f}  "
        f"min_abs_pct={s.min_abs_pct:.4f}"
    )


def _md_stratum(r: StratumReport) -> str:
    lines: list[str] = []
    lines.append(f"## Stratum: {r.stratum}\n")
    lines.append(f"- trades: **{r.n_trades}**  (wins: {r.n_wins} / losses: {r.n_trades - r.n_wins})")
    lines.append(f"- base win-rate: **{r.base_winrate_pct:.2f}%**")
    lines.append(f"- avg entry ask: **{r.avg_ask:.4f}**  (break-even win-rate: **{r.break_even_wr_pct:.2f}%**)")
    lines.append(f"- naive net if all skips were taken: **{r.naive_net_if_took_all:+.2f}** USD\n")

    lines.append("### Single-knob best (each swept with others permissive)\n")
    lines.append("| knob | best value | n | W | L | avg ask | $won | $lost | net | ROI |")
    lines.append("|------|-----------:|--:|--:|--:|--------:|-----:|------:|----:|----:|")
    for k in r.single_knob:
        lines.append(
            f"| {k.knob} | {k.best_value:+.4f} | {k.n} | {k.wins} | {k.losses} | "
            f"{k.avg_ask:.4f} | {k.gross_won:+.2f} | {k.gross_lost:+.2f} | "
            f"**{k.net_pnl:+.2f}** | {k.roi_pct:+.2f}% |"
        )
    lines.append("")

    lines.append("### Top combinations — train / test split (60/40 chronological)\n")
    lines.append(
        "Cells are ranked by **train** net PnL. The test column is out-of-sample. A large "
        "train > test gap is the overfit tell.\n"
    )
    lines.append("| # | mom_off | var_off | ask_cap | min_abs | train n | tr W | tr L | train $ | test n | te W | te L | test $ |")
    lines.append("|--:|--------:|--------:|--------:|--------:|--------:|-----:|-----:|--------:|-------:|-----:|-----:|-------:|")
    for c in r.top_combinations:
        s = c.strategy
        lines.append(
            f"| {c.rank} | {s.mom_offset:+.3f} | {s.var_offset:+.3f} | {s.ask_cap:.2f} | {s.min_abs_pct:.3f} | "
            f"{c.train_n} | {c.train_wins} | {c.train_losses} | **{c.train_net:+.2f}** | "
            f"{c.test_n} | {c.test_wins} | {c.test_losses} | **{c.test_net:+.2f}** |"
        )
    lines.append("")

    lines.append("### Best cell (by full-data net PnL) — deep dive\n")
    lines.append(f"- strategy: `{_fmt_strategy(r.best_strategy)}`")
    lines.append(
        f"- full data: n={r.best_cell_n}  wins={r.best_cell_wins}  losses={r.best_cell_losses}  "
        f"avg_ask={r.best_cell_avg_ask:.4f}"
    )
    lines.append(
        f"- cashflow: $won=**+${r.best_cell_gross_won:.2f}**  $lost=**-${r.best_cell_gross_lost:.2f}**  "
        f"net=**{r.best_cell_net:+.2f}**"
    )
    lines.append(
        f"- walk-forward: train net **{r.train_test.train_net:+.2f}** "
        f"({r.train_test.train_wins}W/{r.train_test.train_losses}L on {r.train_test.train_n})  "
        f"→ test net **{r.train_test.test_net:+.2f}** "
        f"({r.train_test.test_wins}W/{r.train_test.test_losses}L on {r.train_test.test_n})"
    )
    folds_str = "  ".join(f"f{f.fold_idx}: {f.net_pnl:+.2f}" for f in r.stability.folds)
    lines.append(
        f"- 5-fold stability: **{r.stability.positive_fold_count}/{r.stability.fold_count}** folds positive "
        f"(score={r.stability.stability_score:.2f})  [{folds_str}]"
    )
    lines.append(
        f"- bootstrap 10k resamples of captured trades: mean {r.bootstrap.mean_net:+.2f}  "
        f"95% CI [**{r.bootstrap.lower_95:+.2f}, {r.bootstrap.upper_95:+.2f}**]  "
        f"P(net>0)={r.bootstrap.frac_positive:.3f}"
    )
    lines.append(
        f"- permutation null ({r.permutation_n} shuffles): p=**{r.permutation_p:.4f}**  "
        f"(Bonferroni across strata: {r.permutation_bonferroni_p:.4f})"
    )

    lines.append("\n#### Per-session breakdown on best cell")
    lines.append("| session | n | W | L | net $ |")
    lines.append("|---------|--:|--:|--:|------:|")
    for g in r.per_session:
        lines.append(f"| {g.key} | {g.n} | {g.wins} | {g.losses} | **{g.net_pnl:+.2f}** |")

    lines.append("\n#### Per-signal_id breakdown on best cell (top 10 by n)")
    top_signals = sorted(r.per_signal, key=lambda g: -g.n)[:10]
    lines.append("| signal_id | n | W | L | net $ |")
    lines.append("|-----------|--:|--:|--:|------:|")
    for g in top_signals:
        lines.append(f"| {g.key} | {g.n} | {g.wins} | {g.losses} | **{g.net_pnl:+.2f}** |")
    lines.append("")
    return "\n".join(lines)


def write_report(
    reports: list[StratumReport],
    tier: str,
    reason: str,
    config: AnalysisConfig,
    data_path: Path,
    md_path: Path,
    json_path: Path,
) -> None:
    tier_emoji = {
        "credible": "PASS",
        "suggestive": "SUGGESTIVE",
        "none": "FAIL",
    }[tier]

    md: list[str] = []
    md.append(f"# Skip tuner report")
    md.append(f"_generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_\n")
    md.append(f"- input: `{data_path}`")
    md.append(
        f"- config: per_trade_cost={config.per_trade_cost}  min_n={config.min_n}  "
        f"train_frac={config.train_frac}  k_folds={config.k_folds}  "
        f"bootstrap={config.n_bootstrap}  permutations={config.n_permutations}  "
        f"seed={config.random_seed}"
    )
    md.append("")
    md.append(f"## VERDICT: {tier_emoji} — {tier}\n")
    md.append(f"{reason}\n")

    md.append(
        "### How to read this\n"
        "- *Credible* requires bootstrap lower CI > 0, Bonferroni-corrected permutation p < 0.05, "
        "positive walk-forward test PnL, ≥50% fold stability, and majority of sessions positive. "
        "All five together rule out the common failure modes.\n"
        "- *Suggestive* means some but not all gates passed — might be real, worth more data.\n"
        "- *No credible edge* is the honest answer when the data can't distinguish the result from noise.\n"
    )

    for r in reports:
        md.append(_md_stratum(r))
        md.append("")

    # Bot patch shape — use the most profitable credible stratum, else the best overall.
    best_overall = max(reports, key=lambda r: r.best_cell_net) if reports else None
    if best_overall is not None:
        s = best_overall.best_strategy
        md.append("## Bot patch shape (informational — do NOT apply without positive verdict)\n")
        md.append(f"For stratum **{best_overall.stratum}**:\n")
        var_sign = "+" if s.var_offset >= 0 else "-"
        var_abs = abs(s.var_offset)
        mom_sign = "-" if s.mom_offset >= 0 else "+"
        mom_abs = abs(s.mom_offset)
        md.append("```python")
        md.append("# in momentum_signal._conditions_met()")
        md.append(f"effective_d   = max(sc.min_delta_pct {mom_sign} {mom_abs:.4f}, 0.0)")
        md.append(f"effective_var = sc.max_variance_pct {var_sign} {var_abs:.4f}")
        md.append("if self._population_stddev() > effective_var: return False")
        md.append("if sc.side == Direction.UP   and self._latest_pct <  effective_d: return False")
        md.append("if sc.side == Direction.DOWN and self._latest_pct > -effective_d: return False")
        md.append(f"if abs(self._latest_pct) < {s.min_abs_pct:.4f}: return False")
        md.append("# paper_trading-side gate (needs ask available at decision time):")
        md.append(f"if entry_ask > {s.ask_cap:.2f}: return False")
        md.append("```\n")

    md.append("## Known limitations\n")
    md.append(
        "- **Selection bias:** every trade in this analysis is a bot **skip**. Conclusions "
        "only apply to the skip population — a rule tuned here might behave differently on "
        "trades the bot currently takes.\n"
        "- **Costs assumed flat:** slippage, gas and order-book dynamics are folded into the "
        "single per-trade cost parameter. Real per-trade cost varies with ask depth and size.\n"
        "- **Outcome trusted from paper_trading log:** we use the bot's recorded resolution; "
        "no independent cross-check against Polymarket.\n"
        "- **Window parameters fixed:** observe_from_s / observe_to_s come from the active signal. "
        "We don't search over those because they aren't replayable from skip records.\n"
        "- **Temporal structure beyond chronological split not modeled:** if markets cluster by "
        "regime, walk-forward with k=5 may under- or over-estimate stability.\n"
    )

    md_path.write_text("\n".join(md), encoding="utf-8")

    json_blob = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": {"tier": tier, "reason": reason},
        "config": asdict(config),
        "strata": [_stratum_to_dict(r) for r in reports],
    }
    json_path.write_text(json.dumps(json_blob, indent=2), encoding="utf-8")


def _stratum_to_dict(r: StratumReport) -> dict[str, object]:
    return {
        "stratum": r.stratum,
        "n_trades": r.n_trades,
        "n_wins": r.n_wins,
        "base_winrate_pct": r.base_winrate_pct,
        "avg_ask": r.avg_ask,
        "break_even_wr_pct": r.break_even_wr_pct,
        "naive_net_if_took_all": r.naive_net_if_took_all,
        "single_knob": [asdict(k) for k in r.single_knob],
        "top_combinations": [
            {
                "rank": c.rank,
                "strategy": asdict(c.strategy),
                "train_n": c.train_n,
                "train_wins": c.train_wins,
                "train_losses": c.train_losses,
                "train_net": c.train_net,
                "test_n": c.test_n,
                "test_wins": c.test_wins,
                "test_losses": c.test_losses,
                "test_net": c.test_net,
            }
            for c in r.top_combinations
        ],
        "best_cell": {
            "strategy": asdict(r.best_strategy),
            "n": r.best_cell_n,
            "wins": r.best_cell_wins,
            "losses": r.best_cell_losses,
            "gross_won": r.best_cell_gross_won,
            "gross_lost": r.best_cell_gross_lost,
            "net_pnl": r.best_cell_net,
            "avg_ask": r.best_cell_avg_ask,
        },
        "train_test": asdict(r.train_test),
        "stability": {
            "folds": [asdict(f) for f in r.stability.folds],
            "positive_fold_count": r.stability.positive_fold_count,
            "fold_count": r.stability.fold_count,
            "stability_score": r.stability.stability_score,
        },
        "bootstrap": asdict(r.bootstrap),
        "permutation": {
            "p_value": r.permutation_p,
            "bonferroni_p_value": r.permutation_bonferroni_p,
            "n_permutations": r.permutation_n,
        },
        "per_session": [asdict(g) for g in r.per_session],
        "per_signal": [asdict(g) for g in r.per_signal],
    }


def run_analysis(
    data_path: Path,
    md_path: Path,
    json_path: Path,
    config: AnalysisConfig,
) -> int:
    print(f"Loading {data_path}")
    records: list[SkipRecord] = load_jsonl(data_path)
    if not records:
        print("  no records loaded", flush=True)
        return 1
    print(f"  {len(records)} records")

    trades = trades_from_records(records)
    grid = default_grid()
    m, v, a, p = grid.shape
    print(f"Grid: {m}×{v}×{a}×{p} = {grid.n_cells} cells")

    strata_labels = ["ALL", "UP", "DOWN"]
    reports: list[StratumReport] = []
    for label in strata_labels:
        sub = _stratum(label, trades)
        if sub.n < config.min_n * 2:
            print(f"  stratum {label}: {sub.n} trades — too small, skipped")
            continue
        print(f"  stratum {label}: analyzing {sub.n} trades")
        rep = analyze_stratum(label, sub, grid, config, n_strata_for_bonferroni=len(strata_labels))
        if rep is not None:
            reports.append(rep)

    tier, reason = _verdict(reports)
    print(f"Verdict: {tier} — {reason}")

    write_report(reports, tier, reason, config, data_path, md_path, json_path)
    print(f"Wrote {md_path} and {json_path}")
    return 0
