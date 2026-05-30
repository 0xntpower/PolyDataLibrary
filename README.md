# PolyDataLibrary

Long-term market history archive for BTC 5-minute Up/Down prediction markets.

## How It Works

The PolyDataCollector drains resolved market windows through a **three-tier pool**
— active (`data/`, ~500 files) → historical (`historical/`, ~1000 files) →
this archive. When the collector's historical pool overflows, the oldest resolved
files land here (in `markets/`) instead of being deleted, preserving all
historical market data for future research.

## Directory Structure

```
markets/                ← compressed market-window archives
  _staged/              ← raw Parquet files awaiting compression (gitignored)
  1712345678.zip        ← compressed archive of ~1000 market files (committed)
  ...
archive/                ← curated research artifacts
  legendary_signals/    ← notable discovered signals + dev progress
  past-trading-logs/    ← older trading-session logs
system_logs/            ← per-version PAPER-trading session logs (v1.8 … v3.4)
  v3.4_paper_logs/      ← bot/orchestrator logs + post-mortem + configs
  skip_tuner/           ← skip-decision tuning scripts/data
  ...
```

> Note: only **paper-session** logs are kept here. Live-session logs were removed
> because they embedded real on-chain account identifiers.

## Archive Process (markets/)

1. Oldest files from the collector's historical pool are moved to `markets/_staged/`
2. A background task in the collector periodically checks `_staged/`
3. When ~1000 files accumulate, they are compressed into a timestamped ZIP in `markets/`
4. The raw staged files are deleted after successful compression

ZIP filenames use the Unix timestamp of their creation (e.g., `1712345678.zip`).

## Git Strategy

- `markets/_staged/` and `system_logs/current_tmp_session/` are gitignored (transient)
- ZIP archives in `markets/`, the curated `archive/` artifacts, and the
  `system_logs/` paper-session sets are committed to preserve long-term history
- Python bytecode / caches / editor backups are gitignored (see `.gitignore`)

## License

Source-available under the **PolySignalLab Source-Available License v1.0** — see [LICENSE](LICENSE). Commercial use is permitted, but if you use a modified version you must disclose your modifications to the author (privately is fine — public release is not required). See the LICENSE for the exact terms.
