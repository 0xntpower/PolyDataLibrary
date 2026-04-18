"""Extract SkipRecord entries from bot.log files into data.txt (JSONL).

Pairing rule: a record is emitted only when three log lines appear in
order within MAX_PAIR_GAP_S seconds of each other —
    strategy.momentum_signal [SKIP]  (decision-time momentum evaluation)
    execution.paper_trading   SKIP   (snapshot of book + resolved outcome)
    strategy.window_handler  [SKIP]  (confirms full skip path ran)

Records with no active signal swap, with an empty book on the bet side,
or with unresolved outcomes are dropped with a per-session counter
printed to stderr — silent drops would mask data quality issues.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path

from .schema import SkipRecord

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")
MOMENTUM_RE = re.compile(
    r"strategy\.momentum_signal: \[SKIP\]\s+"
    r"rank=(?P<rank>\d+)\s+side=(?P<side>\w+)\s+reason=(?P<reason>\S+)\s+"
    r"latest_pct=(?P<latest>-?\d+\.\d+)\s+need=(?P<need>\S+)\s+"
    r"stddev=(?P<stddev>-?\d+\.\d+)\s+max_var=(?P<maxvar>-?\d+\.\d+)"
)
PAPER_RE = re.compile(
    r"execution\.paper_trading: paper window_ts=(?P<wts>\d+).*?outcome=(?P<outcome>\w+).*?"
    r"bid_up=(?P<bid_up>-?\d+\.\d+).*?ask_up=(?P<ask_up>-?\d+\.\d+).*?"
    r"bid_dn=(?P<bid_dn>-?\d+\.\d+).*?ask_dn=(?P<ask_dn>-?\d+\.\d+)"
)
WINDOW_RE = re.compile(r"strategy\.window_handler: WINDOW_DECISION \[SKIP\]")
SWAP_RE = re.compile(r"SIGNAL_SWAP_ACTIVE:\s*(?P<json>\{.+\})")
VERSION_RE = re.compile(r"^v(\d+(?:\.\d+)*)_paper_logs$")

MAX_PAIR_GAP_S = 360.0


@dataclass(frozen=True, slots=True)
class _Swap:
    activated_at: str
    side: str
    min_delta_pct: float
    max_variance_pct: float
    observe_from_s: float
    observe_to_s: float

    @property
    def signal_id(self) -> str:
        return (
            f"{self.side}_{self.observe_from_s:g}_{self.observe_to_s:g}"
            f"_{self.min_delta_pct:g}_{self.max_variance_pct:g}"
        )


def _strip(line: str) -> str:
    return ANSI_RE.sub("", line)


def _parse_ts(line: str) -> datetime | None:
    m = TS_RE.search(line)
    if m is None:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")


def _parse_ts_string(line: str) -> str:
    m = TS_RE.search(line)
    return m.group(1) if m is not None else ""


def _parse_need(need: str) -> tuple[str, float] | None:
    for op in ("<=", ">=", "<", ">"):
        if need.startswith(op):
            try:
                return op, float(need[len(op):])
            except ValueError:
                return None
    return None


def _parse_version(name: str) -> tuple[int, ...] | None:
    m = VERSION_RE.match(name)
    if m is None:
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def find_sessions(root: Path, n: int) -> list[tuple[str, Path]]:
    """Return [(session_name, bot_log_path), ...] for the N newest sessions,
    chronologically ordered (oldest first) so the output JSONL stays monotonic.
    Only warns about a missing bot.log if that folder would otherwise have
    been selected — silent skip for old sessions the user didn't ask for.
    """
    parsed: list[tuple[tuple[int, ...], str, Path, bool]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        v = _parse_version(child.name)
        if v is None:
            continue
        bot_log = child / "bot.log"
        parsed.append((v, child.name, bot_log, bot_log.exists()))
    parsed.sort(key=lambda t: t[0], reverse=True)
    top_n = parsed[:n]
    missing = [t for t in top_n if not t[3]]
    for _, name, _, _ in missing:
        print(f"  warn: {name} has no bot.log — skipped")
    chosen = [t for t in top_n if t[3]]
    chosen.sort(key=lambda t: t[0])
    return [(name, path) for _, name, path, _ in chosen]


def _build_record(
    session: str,
    swap: _Swap,
    mom: dict[str, str],
    pap: dict[str, str],
) -> SkipRecord | None:
    side = mom["side"].lower()
    if side not in ("up", "down"):
        return None

    parsed_need = _parse_need(mom["need"])
    if parsed_need is None:
        return None
    need_op, need_val = parsed_need

    latest_pct = float(mom["latest"])
    stddev = float(mom["stddev"])
    max_var = float(mom["maxvar"])

    if need_op == ">=":
        mom_gap = need_val - latest_pct
    elif need_op == "<=":
        mom_gap = latest_pct - need_val
    else:
        return None
    var_gap = stddev - max_var

    ask_up = float(pap["ask_up"])
    ask_dn = float(pap["ask_dn"])
    entry_ask = ask_up if side == "up" else ask_dn
    if not (0.0 < entry_ask <= 1.0):
        return None
    pnl_if_won = (1.0 - entry_ask) / entry_ask

    outcome = pap["outcome"].lower()
    if outcome not in ("up", "down"):
        return None

    return SkipRecord(
        session=session,
        signal_id=swap.signal_id,
        side=side,
        activated_at=swap.activated_at,
        momentum_ts=mom["ts"],
        window_ts=int(pap["wts"]),
        latest_pct=latest_pct,
        need_op=need_op,
        need_value=need_val,
        stddev=stddev,
        max_var=max_var,
        entry_ask_up=ask_up,
        entry_ask_dn=ask_dn,
        entry_ask=entry_ask,
        resolved_outcome=outcome,
        won=outcome == side,
        mom_gap=mom_gap,
        var_gap=var_gap,
        abs_latest_pct=abs(latest_pct),
        pnl_if_won=pnl_if_won,
        min_delta_pct=swap.min_delta_pct,
        max_variance_pct=swap.max_variance_pct,
        observe_from_s=swap.observe_from_s,
        observe_to_s=swap.observe_to_s,
    )


def extract_session(session: str, bot_log: Path) -> list[SkipRecord]:
    records: list[SkipRecord] = []
    active_swap: _Swap | None = None
    pending_mom: dict[str, str] | None = None
    pending_mom_ts: datetime | None = None
    pending_pap: dict[str, str] | None = None
    dropped_untradeable = 0
    dropped_no_swap = 0
    dropped_stale = 0

    with bot_log.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = _strip(raw)

            m_swap = SWAP_RE.search(line)
            if m_swap is not None:
                try:
                    data = json.loads(m_swap.group("json"))
                except JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                active_swap = _Swap(
                    activated_at=_parse_ts_string(line),
                    side=str(data.get("side", "")).lower(),
                    min_delta_pct=float(data.get("minDeltaPct", 0.0)),
                    max_variance_pct=float(data.get("maxVariancePct", 0.0)),
                    observe_from_s=float(data.get("observeFromS", 0.0)),
                    observe_to_s=float(data.get("observeToS", 0.0)),
                )
                continue

            ts = _parse_ts(line)
            if ts is None:
                continue

            m_mom = MOMENTUM_RE.search(line)
            if m_mom is not None:
                pending_mom = m_mom.groupdict()
                pending_mom["ts"] = _parse_ts_string(line)
                pending_mom_ts = ts
                pending_pap = None
                continue

            m_pap = PAPER_RE.search(line)
            if (
                m_pap is not None
                and pending_mom is not None
                and pending_mom_ts is not None
            ):
                if (ts - pending_mom_ts).total_seconds() > MAX_PAIR_GAP_S:
                    dropped_stale += 1
                    pending_mom = None
                    pending_mom_ts = None
                    continue
                pending_pap = m_pap.groupdict()
                continue

            if (
                WINDOW_RE.search(line)
                and pending_mom is not None
                and pending_mom_ts is not None
                and pending_pap is not None
            ):
                if (ts - pending_mom_ts).total_seconds() > MAX_PAIR_GAP_S:
                    dropped_stale += 1
                elif active_swap is None:
                    dropped_no_swap += 1
                else:
                    rec = _build_record(session, active_swap, pending_mom, pending_pap)
                    if rec is None:
                        dropped_untradeable += 1
                    else:
                        records.append(rec)
                pending_mom = None
                pending_mom_ts = None
                pending_pap = None

    print(
        f"  {session}: kept {len(records)}  "
        f"(dropped: untradeable={dropped_untradeable} no_active_signal={dropped_no_swap} stale={dropped_stale})"
    )
    return records


def write_jsonl(records: list[SkipRecord], output: Path) -> None:
    with output.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(asdict(rec)) + "\n")


def collect(root: Path, n_sessions: int, output: Path) -> int:
    print(f"Collecting up to {n_sessions} latest sessions from {root}")
    sessions = find_sessions(root, n_sessions)
    if not sessions:
        print("  no matching session folders found")
        return 1
    print(f"  selected: {', '.join(name for name, _ in sessions)}")
    all_records: list[SkipRecord] = []
    for name, log_path in sessions:
        all_records.extend(extract_session(name, log_path))
    all_records.sort(key=lambda r: r.momentum_ts)
    write_jsonl(all_records, output)
    print(f"Wrote {len(all_records)} records -> {output}")
    return 0


def load_jsonl(path: Path) -> list[SkipRecord]:
    records: list[SkipRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_num}: bad JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{line_num}: expected JSON object")
            records.append(
                SkipRecord(
                    session=str(data["session"]),
                    signal_id=str(data["signal_id"]),
                    side=str(data["side"]),
                    activated_at=str(data["activated_at"]),
                    momentum_ts=str(data["momentum_ts"]),
                    window_ts=int(data["window_ts"]),
                    latest_pct=float(data["latest_pct"]),
                    need_op=str(data["need_op"]),
                    need_value=float(data["need_value"]),
                    stddev=float(data["stddev"]),
                    max_var=float(data["max_var"]),
                    entry_ask_up=float(data["entry_ask_up"]),
                    entry_ask_dn=float(data["entry_ask_dn"]),
                    entry_ask=float(data["entry_ask"]),
                    resolved_outcome=str(data["resolved_outcome"]),
                    won=bool(data["won"]),
                    mom_gap=float(data["mom_gap"]),
                    var_gap=float(data["var_gap"]),
                    abs_latest_pct=float(data["abs_latest_pct"]),
                    pnl_if_won=float(data["pnl_if_won"]),
                    min_delta_pct=float(data["min_delta_pct"]),
                    max_variance_pct=float(data["max_variance_pct"]),
                    observe_from_s=float(data["observe_from_s"]),
                    observe_to_s=float(data["observe_to_s"]),
                )
            )
    return records
