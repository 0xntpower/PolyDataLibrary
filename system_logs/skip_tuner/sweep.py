"""Grid construction and mask precomputation for fast sweeps.

The mask matrix is the heart of performance: one int8 row per grid cell,
one column per trade. Evaluating a cell's PnL is then just `masks @ pnl`,
which BLAS runs at memory-bandwidth speeds. Permutation null replays this
matmul 2000× on shuffled PnL vectors — sub-second per replay.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .model import Strategy, Trades, pnl_array

Int8Arr = npt.NDArray[np.int8]
FloatArr = npt.NDArray[np.float64]
IntArr = npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class Grid:
    mom_offsets: FloatArr
    var_offsets: FloatArr
    ask_caps: FloatArr
    pct_floors: FloatArr

    @property
    def shape(self) -> tuple[int, int, int, int]:
        return (
            int(self.mom_offsets.shape[0]),
            int(self.var_offsets.shape[0]),
            int(self.ask_caps.shape[0]),
            int(self.pct_floors.shape[0]),
        )

    @property
    def n_cells(self) -> int:
        m, v, a, p = self.shape
        return m * v * a * p

    def strategy_at(self, idx: int) -> Strategy:
        m, v, a, p = self.shape
        mi, rem = divmod(idx, v * a * p)
        vi, rem = divmod(rem, a * p)
        ai, pi = divmod(rem, p)
        return Strategy(
            mom_offset=float(self.mom_offsets[mi]),
            var_offset=float(self.var_offsets[vi]),
            ask_cap=float(self.ask_caps[ai]),
            min_abs_pct=float(self.pct_floors[pi]),
        )


def default_grid() -> Grid:
    """Coarse but full-coverage grid. 23 * 8 * 11 * 11 = 22,264 cells.

    Refine later if a region of interest emerges.
    """
    return Grid(
        mom_offsets=np.round(np.arange(-0.02, 0.2001, 0.01), 4),
        var_offsets=np.round(np.arange(-0.02, 0.0501, 0.01), 4),
        ask_caps=np.round(np.arange(0.50, 1.0001, 0.05), 4),
        pct_floors=np.round(np.arange(0.00, 0.1001, 0.01), 4),
    )


def build_cell_masks(trades: Trades, grid: Grid) -> Int8Arr:
    """Return an (n_cells, n_trades) int8 matrix where [i, j] = 1 iff
    strategy i fires on trade j. int8 so the @ with a float PnL vector
    stays in BLAS. ~20 MB for the default grid.
    """
    n = trades.n
    mom_m = (trades.mom_gap[None, :] <= grid.mom_offsets[:, None] + 1e-12)
    var_m = (trades.var_gap[None, :] <= grid.var_offsets[:, None] + 1e-12)
    ask_m = (trades.entry_ask[None, :] <= grid.ask_caps[:, None] + 1e-12)
    pct_m = (trades.abs_latest_pct[None, :] >= grid.pct_floors[:, None] - 1e-12)

    m, v, a, p = grid.shape
    masks = np.empty((m * v * a * p, n), dtype=np.int8)
    idx = 0
    for mi in range(m):
        row_m = mom_m[mi]
        for vi in range(v):
            row_mv = row_m & var_m[vi]
            for ai in range(a):
                row_mva = row_mv & ask_m[ai]
                for pi in range(p):
                    masks[idx] = (row_mva & pct_m[pi]).astype(np.int8)
                    idx += 1
    return masks


@dataclass(frozen=True, slots=True)
class CellMetrics:
    counts: IntArr       # (n_cells,) trade count per cell
    wins: IntArr         # (n_cells,) win count per cell
    net_pnl: FloatArr    # (n_cells,) dollar net PnL per cell
    gross_won: FloatArr  # (n_cells,) sum of profits on winning trades
    avg_ask: FloatArr    # (n_cells,) avg entry ask, 0 for empty cells


def evaluate_grid(
    trades: Trades,
    masks: Int8Arr,
    per_trade_cost: float,
) -> CellMetrics:
    pnl = pnl_array(trades, per_trade_cost)
    won_int = trades.won.astype(np.int64)
    ask = trades.entry_ask
    profit_if_won = trades.pnl_if_won * trades.won  # 0 for losses

    counts = masks.sum(axis=1).astype(np.int64)
    wins = (masks.astype(np.int64) * won_int[None, :]).sum(axis=1)
    net_pnl = masks.astype(np.float64) @ pnl
    gross_won = masks.astype(np.float64) @ profit_if_won
    ask_sum = masks.astype(np.float64) @ ask
    with np.errstate(divide="ignore", invalid="ignore"):
        avg_ask = np.where(counts > 0, ask_sum / np.maximum(counts, 1), 0.0)
    return CellMetrics(
        counts=counts,
        wins=wins,
        net_pnl=net_pnl,
        gross_won=gross_won,
        avg_ask=avg_ask,
    )
