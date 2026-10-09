# Fed event study

This study measures whether a specific Kalshi Fed contract moves before a chosen equity. It produces research returns, not broker orders. Each manifest row must name an exact market ticker and the meaning of a rising Yes probability for that equity.

## Inputs

Copy `research/events.example.csv` to `data/events.csv`, then add one reviewed row per exact contract and equity pair. Its columns are:

| Column | Meaning |
| --- | --- |
| `event_id` | Stable event identifier, shared across equities for the same release |
| `release_timestamp` | Public Fed release time with UTC offset |
| `prediction_ticker` | Exact `KXFED-...` market ticker |
| `equity_ticker` | Equity or ETF symbol |
| `yes_up_equity` | `1` if rising Yes odds imply rising equity, `-1` if falling |
| `release_direction` | Optional independently observed public release direction, `1` or `-1` |

`kalshi.csv` is produced by `python -m scripts.fetch_kalshi_history` and contains `timestamp,ticker,price,yes_bid,yes_ask,volume`. Prices are dollars on `[0,1]`; volume is cumulative per market. Candles are timestamped at the *end* of the minute. The study uses the bid/ask midpoint where available and never uses a quote at the release time as its prerelease reference.

For prospective shadow data, run `python main.py --dry-run` and export the Kalshi observations with `python -m scripts.export_observations --output data/observed-kxfed.csv`. The export uses the later of source and receipt timestamps so a delayed update cannot be treated as known before it was received. `logs/shadow_signals.jsonl` records candidates without placing orders.

`equity.csv` has `timestamp,ticker,open`. Each timestamp is the **start** of a one minute bar in UTC. Use raw, point-in-time prices from an intraday data provider, including delisted symbols when relevant. Do not use daily bars or revised adjusted prices. The study buys or sells hypothetically at the first bar open after latency and exits at the first bar open after the hold window. A bar more than two minutes late is treated as missing.

## Run

```bash
python -m scripts.fetch_kalshi_history --event-ticker KXFED-26OCT --start 2026-10-28T16:00:00Z --end 2026-10-28T22:00:00Z --output data/kxfed-26oct.csv
python -m scripts.run_event_study --events data/events.csv --kalshi-csv data/kxfed-26oct.csv --equity-csv data/equity-minute.csv --output data/report.json
```

The event date above is illustrative. Use the actual public release timestamp and a window with prerelease and postrelease observations. Supply multiple events before interpreting the train and later chronological holdout summaries.

Default signal threshold is a five percentage point probability change in fifteen minutes with increased traded volume. The default equity horizon is two hours, with sixty seconds of latency and 30 basis points of round trip cost. The report includes the equity move between release and the signal, a sixty minute prerelease placebo window, and an optional baseline based on independently specified public release direction. The baseline is omitted if that direction is unavailable.

The report includes a threshold and latency sensitivity grid computed on the training events only. A positive mean from a few correlated Fed contracts is not evidence of a robust edge. Keep the selected threshold fixed before looking at the holdout; inspect missing bars, liquidity, and whether the equity had already moved on the public announcement.
