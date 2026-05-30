# PolyDataLibrary

Long-term market history archive for BTC 5-minute Up/Down prediction markets.

## How It Works

The PolyDataCollector maintains a rolling pool of ~500 active Parquet files (v3.3; shrunk from 600 to keep the engine's freshest fold closer to the present). When new markets push the pool over its limit, the oldest resolved files are moved here instead of being deleted. This preserves all historical market data for future research.

## Directory Structure

```
markets/
  _staged/          ← raw Parquet files awaiting compression (gitignored)
  1712345678.zip    ← compressed archive of 1000 market files (committed)
  1712456789.zip
  ...
```

## Archive Process

1. Oldest files from the collector's active pool are moved to `markets/_staged/`
2. A background task in the collector periodically checks `_staged/`
3. When 1000+ files accumulate, they are compressed into a timestamped ZIP archive in `markets/`
4. The raw staged files are deleted after successful compression

ZIP filenames use the Unix timestamp of their creation (e.g., `1712345678.zip`).

## Git Strategy

- `markets/_staged/` is gitignored (raw parquets are transient)
- ZIP archives in `markets/` are committed to preserve long-term history

## License

Source-available under the **PolySignalLab Source-Available License v1.0** — see [LICENSE](LICENSE). Commercial use is permitted, but if you use a modified version you must disclose your modifications to the author (privately is fine — public release is not required). See the LICENSE for the exact terms.
