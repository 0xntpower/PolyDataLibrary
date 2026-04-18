#!/usr/bin/env python3
"""Skip-decision analyzer.

For every [SKIP] triplet recorded in `skips.txt` this tool:
  * locates the SIGNAL_SWAP_ACTIVE entry in `bot.log` that was active at skip time,
  * resolves the market outcome from `600_markets_pool.txt` (window_ts -> UP/DOWN),
  * decides whether the bot's bet would have hit and would have won,
  * explains which condition failed (momentum vs. variance) and by how much,
  * sweeps a momentum-threshold relaxation parameter and reports the
    winrate / EV that each relaxation level would have produced.

Run from this folder:  python analyze_skips.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
HERE = Path(__file__).resolve().parent
SKIPS_PATH = HERE / "skips.txt"
MARKETS_PATH = HERE / "600_markets_pool.txt"
BOT_LOG_PATHS = [
    HERE.parent / "v3.0_paper_logs" / "bot.log",
    HERE.parent / "v3.1_paper_logs" / "bot.log",
    HERE / "bot.log",
]

MOMENTUM_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}).*?strategy\.momentum_signal: \[SKIP\]\s+"
    r"rank=(?P<rank>\d+)\s+side=(?P<side>\w+)\s+reason=(?P<reason>\S+)\s+"
    r"latest_pct=(?P<latest>-?\d+\.\d+)\s+need=(?P<need>\S+)\s+"
    r"stddev=(?P<stddev>-?\d+\.\d+)\s+max_var=(?P<maxvar>-?\d+\.\d+)"
)
PAPER_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}).*?execution\.paper_trading: paper "
    r"window_ts=(?P<wts>\d+).*?outcome=(?P<outcome>\w+).*?"
    r"bid_up=(?P<bid_up>-?\d+\.\d+).*?ask_up=(?P<ask_up>-?\d+\.\d+).*?"
    r"bid_dn=(?P<bid_dn>-?\d+\.\d+).*?ask_dn=(?P<ask_dn>-?\d+\.\d+)"
)
SWAP_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}).*?SIGNAL_SWAP_ACTIVE:\s*(?P<json>\{.+\})"
)
MARKET_RE = re.compile(r"market_(\d+)_resolved_(UP|DOWN)\.parquet")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


@dataclass(frozen=True, slots=True)
class Signal:
    activated_at: str
    rank: int
    side: str
    observe_from_s: float
    observe_to_s: float
    min_delta_pct: float
    max_variance_pct: float
    train_win_rate: float
    oos_win_rate: float
    oos_matches: int
    smart_score: float
    avg_entry_price: float
    ev_per_trade: float

    @property
    def signal_id(self) -> str:
        return (
            f"{self.side}_{self.observe_from_s:g}_{self.observe_to_s:g}"
            f"_{self.min_delta_pct:g}_{self.max_variance_pct:g}"
        )


@dataclass(frozen=True, slots=True)
class Skip:
    momentum_ts: str
    paper_ts: str
    window_ts: int
    side: str
    rank: int
    reason: str
    latest_pct: float
    need_op: str
    need_value: float
    stddev: float
    max_var: float
    paper_outcome: str
    bid_up: float
    ask_up: float
    bid_dn: float
    ask_dn: float


def load_signals() -> list[Signal]:
    out: list[Signal] = []
    for path in BOT_LOG_PATHS:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = strip_ansi(raw)
                m = SWAP_RE.search(line)
                if not m:
                    continue
                data = json.loads(m.group("json"))
                out.append(
                    Signal(
                        activated_at=m.group("ts"),
                        rank=int(data["rank"]),
                        side=str(data["side"]).lower(),
                        observe_from_s=float(data["observeFromS"]),
                        observe_to_s=float(data["observeToS"]),
                        min_delta_pct=float(data["minDeltaPct"]),
                        max_variance_pct=float(data["maxVariancePct"]),
                        train_win_rate=float(data.get("trainWinRatePct", 0.0)),
                        oos_win_rate=float(data.get("oosWinRatePct", 0.0)),
                        oos_matches=int(data.get("oosMatches", 0)),
                        smart_score=float(data.get("smartScore", 0.0)),
                        avg_entry_price=float(data.get("avgEntryPrice", 0.0)),
                        ev_per_trade=float(data.get("evPerTrade", 0.0)),
                    )
                )
    out.sort(key=lambda s: s.activated_at)
    return out


def load_markets() -> dict[int, str]:
    outcomes: dict[int, str] = {}
    with MARKETS_PATH.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            m = MARKET_RE.search(raw)
            if m:
                outcomes[int(m.group(1))] = m.group(2).lower()
    return outcomes


def parse_need(need: str) -> tuple[str, float]:
    for op in ("<=", ">=", "<", ">"):
        if need.startswith(op):
            return op, float(need[len(op):])
    raise ValueError(f"unparseable need: {need!r}")


def load_skips() -> list[Skip]:
    raw_lines = SKIPS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    cleaned = [strip_ansi(line) for line in raw_lines if line.strip()]

    pending_mom: dict[str, str] | None = None
    skips: list[Skip] = []

    for line in cleaned:
        m_mom = MOMENTUM_RE.search(line)
        if m_mom:
            pending_mom = m_mom.groupdict()
            continue
        m_pap = PAPER_RE.search(line)
        if m_pap and pending_mom is not None:
            need_op, need_val = parse_need(pending_mom["need"])
            skips.append(
                Skip(
                    momentum_ts=pending_mom["ts"],
                    paper_ts=m_pap.group("ts"),
                    window_ts=int(m_pap.group("wts")),
                    side=pending_mom["side"].lower(),
                    rank=int(pending_mom["rank"]),
                    reason=pending_mom["reason"],
                    latest_pct=float(pending_mom["latest"]),
                    need_op=need_op,
                    need_value=need_val,
                    stddev=float(pending_mom["stddev"]),
                    max_var=float(pending_mom["maxvar"]),
                    paper_outcome=m_pap.group("outcome").lower(),
                    bid_up=float(m_pap.group("bid_up")),
                    ask_up=float(m_pap.group("ask_up")),
                    bid_dn=float(m_pap.group("bid_dn")),
                    ask_dn=float(m_pap.group("ask_dn")),
                )
            )
            pending_mom = None
    return skips


def signal_for(signals: list[Signal], skip_ts: str) -> Signal | None:
    active: Signal | None = None
    for sig in signals:
        if sig.activated_at <= skip_ts:
            active = sig
        else:
            break
    return active


def fail_breakdown(skip: Skip) -> tuple[str, float, float]:
    """Return (failed_label, momentum_deficit, variance_deficit).

    momentum_deficit > 0 means we were short of the threshold by that much.
    variance_deficit > 0 means stddev exceeded the cap by that much.
    """
    if skip.need_op == "<=":
        momentum_ok = skip.latest_pct <= skip.need_value
        mom_def = skip.latest_pct - skip.need_value
    elif skip.need_op == ">=":
        momentum_ok = skip.latest_pct >= skip.need_value
        mom_def = skip.need_value - skip.latest_pct
    else:
        raise ValueError(f"unsupported op {skip.need_op}")

    var_ok = skip.stddev <= skip.max_var
    var_def = skip.stddev - skip.max_var

    if not momentum_ok and not var_ok:
        label = "momentum+variance"
    elif not momentum_ok:
        label = "momentum"
    elif not var_ok:
        label = "variance"
    else:
        label = "none"
    return label, mom_def, var_def


def is_tradeable(entry_ask: float) -> bool:
    """True iff the bot could actually have placed an order at this price.

    ask<=0 means empty orderbook (no shares available at any price); ask>1
    cannot happen on Polymarket but guard against garbage. ask=1.0 is a
    legitimate (but zero-upside) fill.
    """
    return 0.0 < entry_ask <= 1.0


def trade_pnl_per_dollar(entry_ask: float, won: bool) -> float:
    """PnL per $1 staked. Assumes is_tradeable(entry_ask) is True.

    Win : receive 1/entry_ask shares -> profit = (1 - entry_ask) / entry_ask
          (at entry_ask == 1.0 this is 0 — you paid a dollar and got a dollar)
    Loss: lose the entire $1 stake -> -1.0
    """
    return (1.0 - entry_ask) / entry_ask if won else -1.0


def main() -> int:
    if not SKIPS_PATH.exists():
        print(f"skips.txt not found at {SKIPS_PATH}", file=sys.stderr)
        return 1
    if not any(p.exists() for p in BOT_LOG_PATHS):
        print("no bot.log files found", file=sys.stderr)
        return 1
    if not MARKETS_PATH.exists():
        print(f"600_markets_pool.txt not found at {MARKETS_PATH}", file=sys.stderr)
        return 1

    signals = load_signals()
    outcomes = load_markets()
    skips = load_skips()

    if not skips:
        print("No skips parsed.", file=sys.stderr)
        return 1

    print("=" * 170)
    print(
        f" SKIP ANALYSIS  | skips parsed: {len(skips)}  "
        f"| signal swaps: {len(signals)}  | resolved markets in pool: {len(outcomes)}"
    )
    print("=" * 170)

    win_count = 0
    loss_count = 0
    unknown_count = 0
    untradeable_count = 0
    fail_counts: dict[str, int] = defaultdict(int)
    momentum_only_skips: list[tuple[float, bool, float]] = []  # (mom_deficit, won, entry_ask)

    rows = []
    for idx, skip in enumerate(skips, start=1):
        sig = signal_for(signals, skip.momentum_ts)

        market_outcome = outcomes.get(skip.window_ts)
        outcome = market_outcome or skip.paper_outcome or None
        bet_side = skip.side
        would_win: bool | None = (outcome == bet_side) if outcome else None

        label, mom_def, var_def = fail_breakdown(skip)
        fail_counts[label] += 1

        entry_ask = skip.ask_dn if bet_side == "down" else skip.ask_up
        if label == "momentum" and would_win is not None:
            if is_tradeable(entry_ask):
                momentum_only_skips.append((mom_def, bool(would_win), entry_ask))
            else:
                untradeable_count += 1

        if would_win is True:
            win_count += 1
        elif would_win is False:
            loss_count += 1
        else:
            unknown_count += 1

        rows.append((idx, skip, sig, outcome, would_win, label, mom_def, var_def, entry_ask))

    # ---- per-skip listing ---------------------------------------------------
    header = (
        f"{'#':>4} | {'window_ts':>10} | {'time':<19} | {'signal_id':<28} | "
        f"{'side':<4} | {'latest_pct':>10} | {'need':<11} | {'stddev':>7} | "
        f"{'max_var':>7} | {'failed':<18} | {'mom_gap':>8} | {'var_gap':>8} | "
        f"{'entry_ask':>9} | {'outcome':<7} | {'verdict':<8}"
    )
    print()
    print(header)
    print("-" * len(header))
    for idx, skip, sig, outcome, would_win, label, mom_def, var_def, entry_ask in rows:
        sid = sig.signal_id if sig else "(none)"
        need_str = f"{skip.need_op}{skip.need_value:+.4f}"
        out_str = outcome or "?"
        verdict = "WIN" if would_win is True else ("LOSS" if would_win is False else "?")
        print(
            f"{idx:>4} | {skip.window_ts:>10} | {skip.momentum_ts[:19]:<19} | "
            f"{sid:<28} | {skip.side:<4} | {skip.latest_pct:>+10.4f} | "
            f"{need_str:<11} | {skip.stddev:>7.4f} | {skip.max_var:>7.4f} | "
            f"{label:<18} | {mom_def:>+8.4f} | {var_def:>+8.4f} | "
            f"{entry_ask:>9.4f} | {out_str:<7} | {verdict:<8}"
        )

    total = win_count + loss_count + unknown_count
    resolved = win_count + loss_count
    base_wr = (win_count / resolved * 100.0) if resolved else 0.0

    # ---- summary ------------------------------------------------------------
    print()
    print("=" * 170)
    print(" SUMMARY")
    print("=" * 170)
    print(f"Total skips                            : {total}")
    print(f"  Markets resolved                     : {resolved}")
    print(f"  Markets missing from pool            : {unknown_count}")
    print(f"Would-have-won (bet matches outcome)   : {win_count}")
    print(f"Would-have-lost (bet wrong)            : {loss_count}")
    print(f"Naive winrate if every skip was taken  : {base_wr:.2f}% ({win_count}/{resolved})")
    print(f"Momentum-only skips excluded (ask<=0)  : {untradeable_count}  (orderbook empty on bot's side)")
    print()
    print("Failure reasons:")
    for k, v in sorted(fail_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<22} : {v}")

    # ---- relaxation sweep ---------------------------------------------------
    print()
    print("=" * 170)
    print(" RELAXATION SWEEP — momentum threshold")
    print(" 'mom_gap' = how much further latest_pct was from the bot's required threshold (positive = missed by that much).")
    print(" Each row shows: if you relaxed minDeltaPct so any skip with mom_gap <= GAP became a trade,")
    print(" how many trades you'd have taken, the winrate, and an EV column priced at the recorded entry ask.")
    print(" (Variance-failed skips are excluded — they need a different knob.)")
    print("=" * 170)

    if not momentum_only_skips:
        print("(no momentum-only skips with resolved markets)")
        return 0

    max_gap = max(d for d, _, _ in momentum_only_skips)
    step = 0.005

    # Per-sweep-row record: (gap, n, wins, losses, winrate,
    #                        avg_entry, gross_won, gross_lost, net_pnl)
    sweep: list[tuple[float, int, int, int, float, float, float, float, float]] = []
    gap = step
    while gap <= max_gap + step:
        taken = [(w, ask) for d, w, ask in momentum_only_skips if d <= gap + 1e-9]
        n = len(taken)
        wins = sum(1 for w, _ in taken if w)
        losses = n - wins
        wr = (wins / n * 100.0) if n else 0.0
        # Cashflow at $1 per trade, no compounding:
        #   gross_won  = sum of PROFIT on winning trades ((1-ask)/ask each)
        #   gross_lost = losses × $1 (every loss forfeits the whole stake)
        #   net_pnl    = gross_won - gross_lost
        gross_won = sum((1.0 - ask) / ask for w, ask in taken if w)
        gross_lost = float(losses)
        net_pnl = gross_won - gross_lost
        avg_entry = sum(ask for _, ask in taken) / n if n else 0.0
        sweep.append((gap, n, wins, losses, wr, avg_entry, gross_won, gross_lost, net_pnl))
        gap += step

    print(
        f"{'gap':>7} | {'taken':>5} | {'wins':>5} | {'loss':>5} | {'wr%':>6} | "
        f"{'avg_ask':>7} | {'$won':>8} | {'$lost':>8} | {'net $':>8}"
    )
    print("-" * 90)
    for gap, n, wins, losses, wr, ae, gw, gl, net in sweep:
        print(
            f"{gap:>7.4f} | {n:>5} | {wins:>5} | {losses:>5} | {wr:>5.1f}% | "
            f"{ae:>7.4f} | {gw:>+8.2f} | {gl:>+8.2f} | {net:>+8.2f}"
        )

    print()
    print("=" * 170)
    print(" BEST OFFSET — where 'offset' = how much closer to 0 we let latest_pct be vs the signal's threshold")
    print(" (equivalent to: allow the bot to fire when |latest_pct| >= min_delta_pct - offset)")
    print("=" * 170)
    print(" Cashflow assumes $1 per trade, no compounding. A LOSS forfeits the whole $1.")
    print(" A WIN at ask A returns (1/A) shares worth $1 total -> profit = (1-A)/A dollars.")
    print("=" * 170)

    # Require strictly profitable rows (more money won than lost in dollars —
    # not just more wins than losses, because a win at ask=0.95 only pays ~5c
    # while a loss costs $1). Ties broken by larger net, more trades, lower gap.
    profitable_rows = [r for r in sweep if r[8] > 0]
    if not profitable_rows:
        print("No offset produced a positive net PnL.")
        # Still show the best we *could* do (least-bad), just for context.
        least_bad = max(sweep, key=lambda r: (r[8], r[1], -r[0]))
        print(f"Least-bad row: gap={least_bad[0]:.4f}  "
              f"trades={least_bad[1]}  wins={least_bad[2]}  losses={least_bad[3]}  "
              f"won=${least_bad[6]:.2f}  lost=${least_bad[7]:.2f}  net=${least_bad[8]:+.2f}")
        return 0

    best_net = max(profitable_rows, key=lambda r: (r[8], r[1], -r[0]))
    best_wr_any = max(profitable_rows, key=lambda r: (r[4], r[2], -r[0]))
    best_margin = max(profitable_rows, key=lambda r: (r[2] - r[3], r[2], -r[0]))

    def describe(
        label: str,
        row: tuple[float, int, int, int, float, float, float, float, float],
    ) -> None:
        gap, n, wins, losses, wr, avg_entry, gross_won, gross_lost, net_pnl = row
        roi_pct = (net_pnl / n * 100.0) if n else 0.0
        print(f"  {label}:")
        print(f"    offset                : {gap:.4f}  ({gap * 100:.2f} percentage points)")
        print(f"    trades taken          : {n}")
        print(f"    wins / losses         : {wins} / {losses}   (net +{wins - losses} trades)")
        print(f"    winrate               : {wr:.2f}%")
        print(f"    avg entry ask         : {avg_entry:.4f}")
        print(f"    total $ WON (profits) : +${gross_won:.2f}   <- sum over wins of (1-ask)/ask")
        print(f"    total $ LOST (stakes) : -${gross_lost:.2f}   <- {losses} losses × $1 stake each")
        print(f"    NET PnL               : {net_pnl:+.2f} USD")
        print(f"    ROI per $1 staked     : {roi_pct:+.2f}%  (net / trades)")
        print()

    describe("Best net PnL (dollars won minus dollars lost)", best_net)
    if best_wr_any != best_net:
        describe("Highest winrate (still net-profitable)", best_wr_any)
    if best_margin != best_net and best_margin != best_wr_any:
        describe("Biggest wins-minus-losses trade margin (still net-profitable)", best_margin)

    # Explain the comparison: the bot checks latest_pct <= -d (DOWN) or >= +d (UP).
    # Relaxing by `offset` means the new effective threshold is (d - offset).
    gap = best_net[0]
    print(f"  In bot.momentum_signal terms: change the fire test to use")
    print(f"     effective_d = max(sc.min_delta_pct - {gap:.4f}, 0.0)")
    print(f"  and compare latest_pct against ±effective_d.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
