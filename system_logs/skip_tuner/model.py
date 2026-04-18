"""Vectorized trade arrays and strategy evaluation.

Trades hold numpy-backed parallel arrays so every strategy evaluation is
a boolean mask AND a dot product. A Strategy is just four offsets — the
same four tunables the plan calls out.

PnL accounting (per $1 staked):
    win  -> pnl_if_won[i]  = (1 - entry_ask[i]) / entry_ask[i]
    loss -> -1
Per-trade cost is subtracted uniformly after the win/loss term, so
applying it doesn't need to repartition the arrays.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .schema import SkipRecord


FloatArr = npt.NDArray[np.float64]
BoolArr = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class Trades:
    mom_gap: FloatArr
    var_gap: FloatArr
    entry_ask: FloatArr
    abs_latest_pct: FloatArr
    pnl_if_won: FloatArr
    won: BoolArr
    side: npt.NDArray[np.str_]
    session: npt.NDArray[np.str_]
    signal_id: npt.NDArray[np.str_]
    momentum_ts: npt.NDArray[np.str_]

    @property
    def n(self) -> int:
        return int(self.mom_gap.shape[0])

    def subset(self, mask: BoolArr) -> "Trades":
        return Trades(
            mom_gap=self.mom_gap[mask],
            var_gap=self.var_gap[mask],
            entry_ask=self.entry_ask[mask],
            abs_latest_pct=self.abs_latest_pct[mask],
            pnl_if_won=self.pnl_if_won[mask],
            won=self.won[mask],
            side=self.side[mask],
            session=self.session[mask],
            signal_id=self.signal_id[mask],
            momentum_ts=self.momentum_ts[mask],
        )


def trades_from_records(records: list[SkipRecord]) -> Trades:
    n = len(records)
    mom_gap = np.empty(n, dtype=np.float64)
    var_gap = np.empty(n, dtype=np.float64)
    entry_ask = np.empty(n, dtype=np.float64)
    abs_latest = np.empty(n, dtype=np.float64)
    pnl_if_won = np.empty(n, dtype=np.float64)
    won = np.empty(n, dtype=np.bool_)
    side = np.empty(n, dtype=object)
    session = np.empty(n, dtype=object)
    signal_id = np.empty(n, dtype=object)
    momentum_ts = np.empty(n, dtype=object)

    for i, r in enumerate(records):
        mom_gap[i] = r.mom_gap
        var_gap[i] = r.var_gap
        entry_ask[i] = r.entry_ask
        abs_latest[i] = r.abs_latest_pct
        pnl_if_won[i] = r.pnl_if_won
        won[i] = r.won
        side[i] = r.side
        session[i] = r.session
        signal_id[i] = r.signal_id
        momentum_ts[i] = r.momentum_ts

    return Trades(
        mom_gap=mom_gap,
        var_gap=var_gap,
        entry_ask=entry_ask,
        abs_latest_pct=abs_latest,
        pnl_if_won=pnl_if_won,
        won=won,
        side=side.astype(np.str_),
        session=session.astype(np.str_),
        signal_id=signal_id.astype(np.str_),
        momentum_ts=momentum_ts.astype(np.str_),
    )


@dataclass(frozen=True, slots=True)
class Strategy:
    mom_offset: float
    var_offset: float
    ask_cap: float
    min_abs_pct: float

    def describe(self) -> str:
        return (
            f"mom_offset={self.mom_offset:+.4f} "
            f"var_offset={self.var_offset:+.4f} "
            f"ask_cap={self.ask_cap:.2f} "
            f"min_abs_pct={self.min_abs_pct:.4f}"
        )


def strategy_mask(trades: Trades, strat: Strategy) -> BoolArr:
    return (
        (trades.mom_gap <= strat.mom_offset + 1e-12)
        & (trades.var_gap <= strat.var_offset + 1e-12)
        & (trades.entry_ask <= strat.ask_cap + 1e-12)
        & (trades.abs_latest_pct >= strat.min_abs_pct - 1e-12)
    )


def pnl_array(trades: Trades, per_trade_cost: float) -> FloatArr:
    """Per-trade net PnL if this trade is taken (before masking)."""
    return np.where(trades.won, trades.pnl_if_won, -1.0) - per_trade_cost


def pnl_array_with_outcomes(
    trades: Trades, won_override: BoolArr, per_trade_cost: float
) -> FloatArr:
    """Same as pnl_array but with a replacement win/loss vector.

    Used for label-shuffle permutation tests.
    """
    return np.where(won_override, trades.pnl_if_won, -1.0) - per_trade_cost
