"""Statistical safeguards: walk-forward, bootstrap CI, permutation null.

Every function here takes the precomputed mask matrix from sweep and a
PnL vector so the heavy work (one ~22k×900 matmul per replay) stays in
BLAS. Results are plain dataclasses — no numpy types leak into report.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .model import Trades, pnl_array, pnl_array_with_outcomes
from .sweep import CellMetrics, evaluate_grid

Int8Arr = npt.NDArray[np.int8]
FloatArr = npt.NDArray[np.float64]
IntArr = npt.NDArray[np.int64]
BoolArr = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class TrainTestResult:
    best_cell_idx: int
    train_n: int
    train_wins: int
    train_losses: int
    train_net: float
    test_n: int
    test_wins: int
    test_losses: int
    test_net: float


@dataclass(frozen=True, slots=True)
class FoldResult:
    fold_idx: int
    n: int
    wins: int
    losses: int
    net_pnl: float


@dataclass(frozen=True, slots=True)
class StabilityResult:
    folds: list[FoldResult]
    positive_fold_count: int
    fold_count: int

    @property
    def stability_score(self) -> float:
        return self.positive_fold_count / self.fold_count if self.fold_count else 0.0


@dataclass(frozen=True, slots=True)
class BootstrapCI:
    mean_net: float
    lower_95: float
    upper_95: float
    frac_positive: float
    n_resamples: int


@dataclass(frozen=True, slots=True)
class PermutationResult:
    observed_best_net: float
    null_best_distribution: FloatArr
    p_value: float
    n_permutations: int


def _best_cell(metrics: CellMetrics, min_n: int) -> int:
    """Index of the profitable cell with the largest net PnL satisfying
    the minimum-trade constraint. Falls back to argmax net if none pass.
    """
    eligible = metrics.counts >= min_n
    if not eligible.any():
        return int(np.argmax(metrics.net_pnl))
    net_masked = np.where(eligible, metrics.net_pnl, -np.inf)
    return int(np.argmax(net_masked))


def train_test_split(
    trades: Trades,
    masks: Int8Arr,
    per_trade_cost: float,
    train_frac: float,
    min_n: int,
) -> TrainTestResult:
    """Sort-chronological 60/40 split: pick best cell on train, report
    held-out test PnL. The gap between train_net and test_net is the
    most direct overfit indicator in the report.
    """
    n = trades.n
    cut = int(round(n * train_frac))
    cut = max(min_n, min(n - min_n, cut))

    train_mask = np.zeros(n, dtype=np.bool_)
    train_mask[:cut] = True
    test_mask = ~train_mask

    pnl = pnl_array(trades, per_trade_cost)
    won_int = trades.won.astype(np.int64)
    masks_f = masks.astype(np.float64)
    masks_i = masks.astype(np.int64)

    train_counts = masks_i[:, :cut].sum(axis=1)
    train_wins = (masks_i[:, :cut] * won_int[None, :cut]).sum(axis=1)
    train_net = masks_f[:, :cut] @ pnl[:cut]

    eligible = train_counts >= min_n
    if eligible.any():
        masked = np.where(eligible, train_net, -np.inf)
        best_idx = int(np.argmax(masked))
    else:
        best_idx = int(np.argmax(train_net))

    test_counts = masks_i[best_idx, cut:].sum()
    test_wins_val = (masks_i[best_idx, cut:] * won_int[cut:]).sum()
    test_net_val = (masks_f[best_idx, cut:] * pnl[cut:]).sum()

    return TrainTestResult(
        best_cell_idx=best_idx,
        train_n=int(train_counts[best_idx]),
        train_wins=int(train_wins[best_idx]),
        train_losses=int(train_counts[best_idx] - train_wins[best_idx]),
        train_net=float(train_net[best_idx]),
        test_n=int(test_counts),
        test_wins=int(test_wins_val),
        test_losses=int(test_counts - test_wins_val),
        test_net=float(test_net_val),
    )


def k_fold_stability(
    trades: Trades,
    masks: Int8Arr,
    cell_idx: int,
    per_trade_cost: float,
    k: int,
) -> StabilityResult:
    """Split the (already chronological) trade list into k equal contiguous
    folds, compute the cell's PnL inside each. Cells that won overall but
    depended on one hot streak will show most folds ≤ 0 here.
    """
    n = trades.n
    pnl = pnl_array(trades, per_trade_cost)
    won_int = trades.won.astype(np.int64)
    row = masks[cell_idx].astype(np.float64)
    row_i = masks[cell_idx].astype(np.int64)

    folds: list[FoldResult] = []
    positive = 0
    edges = np.linspace(0, n, k + 1, dtype=np.int64)
    for i in range(k):
        lo, hi = int(edges[i]), int(edges[i + 1])
        if hi <= lo:
            continue
        slice_counts = int(row_i[lo:hi].sum())
        slice_wins = int((row_i[lo:hi] * won_int[lo:hi]).sum())
        slice_net = float((row[lo:hi] * pnl[lo:hi]).sum())
        folds.append(
            FoldResult(
                fold_idx=i,
                n=slice_counts,
                wins=slice_wins,
                losses=slice_counts - slice_wins,
                net_pnl=slice_net,
            )
        )
        if slice_net > 0:
            positive += 1
    return StabilityResult(folds=folds, positive_fold_count=positive, fold_count=len(folds))


def bootstrap_ci(
    trades: Trades,
    masks: Int8Arr,
    cell_idx: int,
    per_trade_cost: float,
    n_resamples: int,
    rng: np.random.Generator,
) -> BootstrapCI:
    """Resample the trades captured by this cell with replacement.
    CI on net PnL — if the lower bound crosses zero, we can't distinguish
    the cell's edge from sampling noise on the same set of trades.
    """
    mask_row = masks[cell_idx].astype(np.bool_)
    captured_pnl = pnl_array(trades, per_trade_cost)[mask_row]
    n = captured_pnl.shape[0]
    if n == 0:
        return BootstrapCI(0.0, 0.0, 0.0, 0.0, n_resamples)

    idx = rng.integers(0, n, size=(n_resamples, n))
    resampled = captured_pnl[idx].sum(axis=1)
    lower, upper = np.quantile(resampled, [0.025, 0.975])
    return BootstrapCI(
        mean_net=float(resampled.mean()),
        lower_95=float(lower),
        upper_95=float(upper),
        frac_positive=float((resampled > 0).mean()),
        n_resamples=n_resamples,
    )


def permutation_null(
    trades: Trades,
    masks: Int8Arr,
    per_trade_cost: float,
    min_n: int,
    n_permutations: int,
    rng: np.random.Generator,
) -> PermutationResult:
    """Shuffle win/loss labels n_permutations times, re-run the full grid
    search each time, record the best cell's net PnL under the null. The
    p-value is the fraction of null runs whose best ≥ real best — the
    direct antidote to data dredging across ~22k cells.
    """
    pnl_real = pnl_array(trades, per_trade_cost)
    masks_f = masks.astype(np.float64)
    masks_i = masks.astype(np.int64)
    counts = masks_i.sum(axis=1)
    eligible = counts >= min_n

    real_net = masks_f @ pnl_real
    real_masked = np.where(eligible, real_net, -np.inf)
    real_best = float(real_masked.max())

    won = trades.won.copy()
    null_bests = np.empty(n_permutations, dtype=np.float64)
    for i in range(n_permutations):
        rng.shuffle(won)
        pnl_i = pnl_array_with_outcomes(trades, won, per_trade_cost)
        net_i = masks_f @ pnl_i
        masked = np.where(eligible, net_i, -np.inf)
        null_bests[i] = masked.max()

    at_or_above = int((null_bests >= real_best).sum())
    p_value = (at_or_above + 1) / (n_permutations + 1)
    return PermutationResult(
        observed_best_net=real_best,
        null_best_distribution=null_bests,
        p_value=p_value,
        n_permutations=n_permutations,
    )


@dataclass(frozen=True, slots=True)
class GroupBreakdown:
    key: str
    n: int
    wins: int
    losses: int
    net_pnl: float


def group_breakdown_for_cell(
    trades: Trades,
    masks: Int8Arr,
    cell_idx: int,
    per_trade_cost: float,
    group_values: npt.NDArray[np.str_],
) -> list[GroupBreakdown]:
    pnl = pnl_array(trades, per_trade_cost)
    mask_row = masks[cell_idx].astype(np.bool_)
    captured = np.where(mask_row)[0]
    keys = group_values[captured]
    pnl_captured = pnl[captured]
    won_captured = trades.won[captured]

    out: list[GroupBreakdown] = []
    for k in sorted(set(keys.tolist())):
        sel = keys == k
        n = int(sel.sum())
        wins = int(won_captured[sel].sum())
        net = float(pnl_captured[sel].sum())
        out.append(
            GroupBreakdown(
                key=str(k),
                n=n,
                wins=wins,
                losses=n - wins,
                net_pnl=net,
            )
        )
    return out


def pick_best(metrics: CellMetrics, min_n: int) -> int:
    return _best_cell(metrics, min_n)
