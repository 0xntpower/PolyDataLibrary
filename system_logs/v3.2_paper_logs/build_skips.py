#!/usr/bin/env python3
"""Build a combined skips.txt from v3.0, v3.1 and v3.2 bot logs.

Only keeps paper_trading [SKIP] lines whose preceding momentum_signal [SKIP]
is within `MAX_PAIR_GAP_S` seconds. That filters out paper-trading skips from
periods where the bot had no active signal evaluation (bot startup, signal
swaps, waiting for data) which would otherwise pair with a stale momentum
record from an unrelated window.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS_ROOT = HERE.parent
SOURCES = [
    LOGS_ROOT / "v3.0_paper_logs" / "bot.log",
    LOGS_ROOT / "v3.1_paper_logs" / "bot.log",
    LOGS_ROOT / "v3.2_paper_logs" / "bot.log",
]
OUTPUT = HERE / "skips.txt"
MAX_PAIR_GAP_S = 360.0  # 6 minutes (5-min window + small buffer)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")
MOMENTUM_RE = re.compile(
    r"strategy\.momentum_signal: \[SKIP\].*latest_pct=-?\d+\.\d+"
)
PAPER_RE = re.compile(
    r"execution\.paper_trading: paper window_ts=\d+ \[SKIP\]"
)
WINDOW_RE = re.compile(
    r"strategy\.window_handler: WINDOW_DECISION \[SKIP\]"
)


def parse_ts(line: str) -> datetime | None:
    m = TS_RE.search(ANSI_RE.sub("", line))
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")


def extract_triplets(log_path: Path) -> list[tuple[datetime, str, str, str]]:
    triplets: list[tuple[datetime, str, str, str]] = []
    pending_mom_line: str | None = None
    pending_mom_ts: datetime | None = None
    pending_paper_line: str | None = None

    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            clean = ANSI_RE.sub("", raw)
            ts = parse_ts(clean)
            if ts is None:
                continue

            if MOMENTUM_RE.search(clean):
                pending_mom_line = raw.rstrip("\n")
                pending_mom_ts = ts
                pending_paper_line = None
                continue

            if PAPER_RE.search(clean) and pending_mom_line and pending_mom_ts:
                if (ts - pending_mom_ts).total_seconds() > MAX_PAIR_GAP_S:
                    # Stale momentum — drop and keep scanning
                    pending_mom_line = None
                    pending_mom_ts = None
                    continue
                pending_paper_line = raw.rstrip("\n")
                continue

            if (
                WINDOW_RE.search(clean)
                and pending_mom_line
                and pending_paper_line
                and pending_mom_ts
            ):
                if (ts - pending_mom_ts).total_seconds() > MAX_PAIR_GAP_S:
                    pending_mom_line = None
                    pending_mom_ts = None
                    pending_paper_line = None
                    continue
                triplets.append((
                    pending_mom_ts,
                    pending_mom_line,
                    pending_paper_line,
                    raw.rstrip("\n"),
                ))
                pending_mom_line = None
                pending_mom_ts = None
                pending_paper_line = None
    return triplets


def main() -> int:
    all_triplets: list[tuple[datetime, str, str, str]] = []
    for src in SOURCES:
        if not src.exists():
            print(f"warn: missing {src}")
            continue
        found = extract_triplets(src)
        print(f"{src.parent.name}: {len(found)} complete triplets")
        all_triplets.extend(found)

    all_triplets.sort(key=lambda t: t[0])

    with OUTPUT.open("w", encoding="utf-8") as out:
        for _, mom, pap, win in all_triplets:
            out.write(mom + "\n")
            out.write(pap + "\n")
            out.write(win + "\n")

    print(f"wrote {len(all_triplets)} triplets ({len(all_triplets) * 3} lines) to {OUTPUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
