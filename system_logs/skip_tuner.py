#!/usr/bin/env python3
"""Production-grade skip-decision tuner.

Usage (from system_logs/):
    python skip_tuner.py --collect 3              # build data.txt from 3 latest sessions
    python skip_tuner.py --analyze                # read data.txt, write report.md + report.json
    python skip_tuner.py --collect 3 --analyze    # both

Optional:
    --data PATH                 override data.txt location
    --per-trade-cost 0.01       transaction cost per $1 stake
    --min-n 30                  minimum trades per cell / fold
    --train-frac 0.6            chronological train/test split
    --k-folds 5
    --bootstrap 10000
    --permutations 2000
    --seed 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skip_tuner.collect import collect
from skip_tuner.report import AnalysisConfig, run_analysis


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Skip-decision tuner")
    p.add_argument("-c", "--collect", type=int, metavar="N", default=None,
                   help="Collect latest N sessions into data.txt")
    p.add_argument("--analyze", action="store_true",
                   help="Analyze data.txt and write report.md + report.json")
    p.add_argument("--data", type=Path, default=Path("data.txt"),
                   help="Path to JSONL data file (default: ./data.txt)")
    p.add_argument("--report-md", type=Path, default=Path("report.md"))
    p.add_argument("--report-json", type=Path, default=Path("report.json"))
    p.add_argument("--per-trade-cost", type=float, default=0.01,
                   help="Subtracted from every trade's PnL (default 0.01 = 1%%)")
    p.add_argument("--min-n", type=int, default=30,
                   help="Minimum trades per cell / fold to be considered")
    p.add_argument("--train-frac", type=float, default=0.6,
                   help="Fraction of trades (chronological) in the train set")
    p.add_argument("--k-folds", type=int, default=5,
                   help="Number of contiguous folds for stability")
    p.add_argument("--bootstrap", type=int, default=10000,
                   help="Bootstrap resamples for CI on best cell")
    p.add_argument("--permutations", type=int, default=2000,
                   help="Label shuffles for the permutation null")
    p.add_argument("--seed", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.collect is None and not args.analyze:
        build_parser().print_help()
        return 2

    cwd = Path.cwd()
    data_path = args.data if args.data.is_absolute() else cwd / args.data
    md_path = args.report_md if args.report_md.is_absolute() else cwd / args.report_md
    json_path = args.report_json if args.report_json.is_absolute() else cwd / args.report_json

    if args.collect is not None:
        if args.collect <= 0:
            print("--collect N: N must be positive", file=sys.stderr)
            return 2
        rc = collect(root=cwd, n_sessions=args.collect, output=data_path)
        if rc != 0:
            return rc

    if args.analyze:
        if not data_path.exists():
            print(f"data file not found: {data_path}", file=sys.stderr)
            return 1
        config = AnalysisConfig(
            per_trade_cost=args.per_trade_cost,
            min_n=args.min_n,
            train_frac=args.train_frac,
            k_folds=args.k_folds,
            n_bootstrap=args.bootstrap,
            n_permutations=args.permutations,
            random_seed=args.seed,
        )
        return run_analysis(data_path, md_path, json_path, config)

    return 0


if __name__ == "__main__":
    sys.exit(main())
