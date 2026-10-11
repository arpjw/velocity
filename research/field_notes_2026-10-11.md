# Fed research kickoff, 2026-10-11

Status: input collection and protocol review. There is no equity minute dataset, completed event study, or evidence of an equity trading edge.

## Market lifecycle finding

The [July 29 Fed statement](https://www.federalreserve.gov/monetarypolicy/fomcpresconf20260729.htm) was released at 2:00 p.m. Eastern, or 18:00 UTC. The [July `KXFED-26JUL-T3.75` market](https://external-api.kalshi.com/trade-api/v2/historical/markets/KXFED-26JUL-T3.75) closed at 17:55 UTC. The other July meeting markets inspected had the same close time. The archived minute export from 16:00 to 18:30 UTC contains 124 candles across six July markets and no candle after the public release. A postrelease signal study cannot use contracts that settle on that same meeting.

Contracts for a later meeting can stay open across the current statement. The public minute-candle exports are sparse across six exploratory 2026 release windows:

| Public statement | Later-meeting event | Candle rows | Markets with candles | Markets with a trade in both the prior 10 and next 15 minutes |
| --- | --- | ---: | ---: | ---: |
| January 28 | `KXFED-26MAR` | 5 | 2 | 0 |
| March 18 | `KXFED-26APR` | 2 | 1 | 0 |
| April 29 | `KXFED-26JUN` | 7 | 2 | 0 |
| June 17 | `KXFED-26JUL` | 6 | 5 | 0 |
| July 29 | `KXFED-26SEP` | 14 | 3 | 0 |
| September 16 | `KXFED-26OCT` | 27 | 4 | 1 |

The sole market with trades on both sides, `KXFED-26OCT-T3.75`, has a 1,740-second gap within the 60-minute prerelease through 15-minute postrelease window. That exceeds the existing five-minute audit limit. None of these six exports supplies a complete trade-candle event under the current study rule. These screens used market data already observed, so they are exploratory and cannot be presented as an untouched holdout. Sparse candles do not prove the market itself was inactive; they do show that this historical last-trade feed is insufficient for the current replay without further data.

Local raw exports and the first shadow diagnostic logs are under `results/research/2026-10-11/`. The first public REST run is labeled `pre-fix` because it repeatedly recorded unchanged last-trade prices as fresh observations. Do not use that log for a signal study.

## Protocol to test next

1. For each public Fed statement, use exact contracts for the **next scheduled meeting** whose published close time is after the full postrelease signal window. Record the official statement release time, exact market rules, market close time, and the contract selection rule before inspecting equity returns. The [Fed calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) lists October 28 and December 9 as the remaining 2026 decisions. For the October statement, inspect December contracts, not October contracts.
2. Treat the already screened 2026 history as exploratory. For the next prospective event, retain every eligible exact contract with a prerelease trade no older than ten minutes. Record no-signal and missing-data contracts; do not select only contracts that trade after the statement. A proposed equity hypothesis is that rising odds of a higher Fed target-rate upper bound predict a falling long-duration Treasury ETF price. Review that mapping and the exact market rules before placing it in the manifest.
3. Use a 90-minute hold as a prespecified regular-session scenario for 2:00 p.m. Eastern releases. A signal as late as 2:15 p.m. plus 60 seconds of entry latency would have a latest hypothetical exit at 3:46 p.m. The current two-hour default can extend past the 4:00 p.m. equity close. Keep the default 15-minute signal window, 60-second latency, and 30-basis-point round-trip allowance as research assumptions. Evaluate costs and latency sensitivity on training releases only.
4. Obtain raw, point-in-time one-minute equity bars with UTC bar-start timestamps. Quotes are preferable for spread-aware pricing. [Massive Stocks Basic](https://massive.com/pricing?product=stocks) currently lists free historical minute aggregates, subject to account access; its [aggregate API](https://www.massive.com/docs/rest/stocks/aggregates/custom-bars) supports unadjusted bars. `scripts/fetch_massive_equity.py` is ready to fetch a single ticker and date into a normalized CSV, raw JSON, and provenance sidecar once `MASSIVE_API_KEY` is configured locally. Historical aggregates do not establish contemporaneous executable bid/ask prices or their original availability time. No account or paid plan has been created for this project.
5. Audit hashes, provenance, missing minutes, prediction gaps, and volume resets before running a study. A passing mechanical audit does not establish when a historical vendor bar became available. Report independent release counts and keep the later prospective release untouched until parameters are fixed.

## Prospective shadow collection

Public Kalshi REST market snapshots expose a last-trade price without its trade timestamp. The collector now labels unchanged-volume snapshots as `reference` and only feeds a last-trade observation to the velocity tracker when cumulative volume increases. It timestamps that observation at receipt, a conservative bound on when the trade became known to this collector. An authenticated WebSocket would supply a more direct source timestamp if access becomes available.

A short public REST pilot on October 11 tracked two December contracts. It wrote six `reference` snapshots, no new-trade export rows, no signal, and no order. Connector health passed during the run, and the filtered observation log passed the offline timing audit. This verifies the collection path on a quiet Sunday; it does not test event-day behavior. The filtered pilot files are under `results/research/2026-10-11/`.

Before the October 28 statement, select and record the December contract tickers. Run `python main.py --dry-run` from before the prerelease baseline through the postrelease signal window. Check `python -m scripts.check_collector_health`, run `python -m scripts.audit_observation_log --output results/observation-audit.json`, and export with `python -m scripts.export_observations --output results/observed-kxfed.csv`. Compare receipt times with hypothetical equity entry times once an equity source exists. Do not infer an edge from a quiet-market collector check.
