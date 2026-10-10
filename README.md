# Velocity

Velocity is a research project testing whether a sharp change in a prediction market contract precedes a move in a related equity. The proposition is unproven. A public announcement may move both markets at once, and any apparent lead can disappear after entry delay, spread, fees, or a different event sample.

The default mode is **shadow**: it records market observations and candidate signals without placing orders. Live execution is disabled in code while order acknowledgements, fills, exits, and account state cannot be reconciled safely. The site displays public Kalshi market data and makes no performance claim.

## What is built

- Kalshi public REST discovery of active, traded Fed contracts, plus polling and WebSocket parsing for current dollar-denominated price fields.
- The Kalshi connector refreshes discovered markets every five minutes and reports observation freshness separately from signal time. `KALSHI_DISCOVERY_INTERVAL_SECONDS` and `KALSHI_STALE_SECONDS` adjust the refresh and stale thresholds.
- Polymarket CLOB market subscription by resolved outcome asset ID.
- Timestamped observation and shadow candidate logs. The export uses the later of exchange and receipt timestamps.
- Shadow candidates are deduplicated by source, contract, and direction over a configurable thirty minute window, including across restarts (`SHADOW_DEDUP_WINDOW_MINUTES`).
- A point-in-time Fed event study using exact Kalshi market tickers and one-minute equity bars, with delayed entry, costs, prerelease checks, and chronological train and holdout summaries.
- Mock execution code for software checks. Mock fills and the older daily-bar backtest are not evidence of a tradable edge.

## Run in shadow mode

Use Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/healthcheck.py
python main.py --dry-run
```

The example environment leaves market credentials blank. Public Kalshi polling can run without a key. Configure optional sources in `.env` only if you use them. The process runs until interrupted; `--dry-run` forces shadow mode even if the environment requests mock execution. Market observations go to `logs/market_observations.jsonl`, and candidate signals go to `logs/shadow_signals.jsonl`. No signal during a short run is a normal outcome.

To export observations for analysis:

```bash
python -m scripts.export_observations --output data/observed-kxfed.csv
```

Do not put broker keys or private account data in the repository.

## Study a Fed release

The study requires a manually reviewed manifest with the actual public release time, an exact `KXFED-...` market ticker, a chosen equity, a prespecified direction mapping, and source references. Start with [the manifest template](research/events.example.csv). Provide a point-in-time equity CSV with `timestamp,ticker,open`, where timestamps mark the start of each one-minute UTC bar. See [research instructions](research/README.md) for the full input definitions and limitations. Run `python -m scripts.audit_research_data` on the CSVs before interpreting a report; its coverage result does not establish a trading edge.

```bash
python -m scripts.fetch_kalshi_history \
  --event-ticker KXFED-26OCT \
  --start 2026-10-08T16:00:00Z \
  --end 2026-10-08T22:00:00Z \
  --output data/kxfed-event.csv

python -m scripts.run_event_study \
  --events data/events.csv \
  --kalshi-csv data/kxfed-event.csv \
  --equity-csv data/equity-minute.csv \
  --output data/event-study-report.json
```

The dates above show command syntax; choose a real release and its matching market. Use `--historical` with the fetch command for archived markets. The study replays the running velocity rule, which defaults to 0.15 probability points per minute over a five-minute rolling window. It looks for signals in the fifteen minutes after release, then assumes sixty seconds of entry latency, thirty basis points of round trip cost, and a two-hour horizon. These are research assumptions, not optimized trading parameters. Do not interpret a positive result from a few correlated markets or a single release as evidence of an edge.

## Current limits and next decisions

1. Collect several real releases and minute equity bars with known availability times. Include missing and delisted instruments, and check for revised or adjusted data.
2. Compare against reactions to the public release itself and placebo windows; report trade counts, missing data, spread, slippage, and threshold sensitivity. Select parameters on earlier events and evaluate later events only once.
3. Continue prospective shadow logging. Check that observations arrive before the hypothetical equity entry and that results survive realistic costs and regime changes.
4. Consider live execution only after independent out-of-sample evidence and a broker integration that confirms fills, partial fills, rejected orders, exits, and account state. The current `EXECUTION_MODE=live` path raises an error by design.

The old generic contract-to-equity map is retained for historical simulation. A series label such as `KXFED` does not identify the direction of an individual threshold contract and cannot authorize an equity order.

## Development

```bash
pytest -q
cd ui && npm ci && npm run build
```

The UI is a Next.js site. Its `/api/markets` route fetches public KXFED markets server-side, displays recently traded contracts, and labels values as last trades. It does not display simulated P&L. `UI.md` is the original design brief; this README and the current code describe present behavior.

The `/research` page reads the audit and study JSON reports locally in the browser. It shows coverage, missing rows, training and holdout summaries, and per-release results without uploading research files.

GitHub Actions runs the Python test suite on Python 3.11 and 3.13, and builds the UI and audits its production dependencies on Node 22 for pushes and pull requests. Run `python scripts/healthcheck.py` separately when checking live API reachability.

The connector format and extension workflow are in [CONTRIBUTING_CONNECTORS.md](CONTRIBUTING_CONNECTORS.md). Additional modules for sizing, alerts, an Oracle, a dashboard, and a legacy backtest remain in the repository. They have not been validated as a profitable or safe live trading system.
