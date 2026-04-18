"""Data schema for skip records written to / read from data.txt (JSONL).

Every field needed to replay a skip decision under an alternative rule set
lives on SkipRecord — the analyzer never goes back to raw logs. mom_gap,
var_gap, abs_latest_pct and pnl_if_won are derived here so the analyzer
can vectorize without recomputing them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkipRecord:
    session: str
    signal_id: str
    side: str
    activated_at: str
    momentum_ts: str
    window_ts: int
    latest_pct: float
    need_op: str
    need_value: float
    stddev: float
    max_var: float
    entry_ask_up: float
    entry_ask_dn: float
    entry_ask: float
    resolved_outcome: str
    won: bool
    mom_gap: float
    var_gap: float
    abs_latest_pct: float
    pnl_if_won: float
    min_delta_pct: float
    max_variance_pct: float
    observe_from_s: float
    observe_to_s: float
