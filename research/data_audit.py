"""Audit the provenance and coverage of a Fed event-study CSV dataset."""

from __future__ import annotations

import csv
import hashlib
from datetime import timedelta
from pathlib import Path

from research.event_study import load_equity_bars, load_events, load_quotes, parse_time


PROVENANCE_FIELDS = ("release_source", "contract_source", "equity_source")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _duplicates(points: list) -> int:
    keys = [(point.ticker, point.timestamp) for point in points]
    return len(keys) - len(set(keys))


def audit_dataset(
    events_path: Path,
    quotes_path: Path,
    equity_path: Path,
    *,
    baseline_minutes: int = 10,
    signal_minutes: int = 15,
    hold_minutes: int = 120,
    latency_seconds: int = 60,
) -> dict:
    if min(baseline_minutes, signal_minutes, hold_minutes) <= 0 or latency_seconds < 0:
        raise ValueError("audit windows must be positive and latency cannot be negative")

    with events_path.open(newline="") as file:
        manifest = list(csv.DictReader(file))
    events = load_events(events_path)
    quotes = load_quotes(quotes_path)
    equity = load_equity_bars(equity_path)
    provenance = {
        (row["event_id"], parse_time(row["release_timestamp"]),
         row["prediction_ticker"], row["equity_ticker"]): row
        for row in manifest
    }

    all_quotes = [point for values in quotes.values() for point in values]
    all_bars = [point for values in equity.values() for point in values]
    global_issues: list[str] = []
    if _duplicates(all_quotes):
        global_issues.append("duplicate_prediction_timestamps")
    if _duplicates(all_bars):
        global_issues.append("duplicate_equity_timestamps")
    if any(
        later.volume < earlier.volume
        for values in quotes.values()
        for earlier, later in zip(values, values[1:])
    ):
        global_issues.append("prediction_volume_counter_reset")

    event_reports = []
    for event in events:
        key = (event.event_id, event.release_timestamp,
               event.prediction_ticker, event.equity_ticker)
        source_row = provenance[key]
        event_quotes = quotes.get(event.prediction_ticker, [])
        event_bars = equity.get(event.equity_ticker, [])
        release = event.release_timestamp
        baseline = [point for point in event_quotes
                    if release - timedelta(minutes=baseline_minutes) <= point.timestamp < release]
        postrelease = [point for point in event_quotes
                       if release < point.timestamp <= release + timedelta(minutes=signal_minutes)]
        window_quotes = [point for point in event_quotes
                         if release - timedelta(minutes=60) <= point.timestamp
                         <= release + timedelta(minutes=signal_minutes)]
        quote_gaps = [
            (later.timestamp - earlier.timestamp).total_seconds()
            for earlier, later in zip(window_quotes, window_quotes[1:])
        ]

        start = release.replace(second=0, microsecond=0)
        end = release + timedelta(
            minutes=signal_minutes + hold_minutes, seconds=latency_seconds
        )
        observed_minutes = {point.timestamp for point in event_bars}
        expected_minutes = []
        minute = start
        while minute <= end:
            expected_minutes.append(minute)
            minute += timedelta(minutes=1)
        missing_minutes = [minute for minute in expected_minutes if minute not in observed_minutes]

        issues = [f"missing_{field}" for field in PROVENANCE_FIELDS
                  if not (source_row.get(field) or "").strip()]
        if not baseline:
            issues.append("missing_prediction_baseline")
        if not postrelease:
            issues.append("missing_prediction_signal_window")
        if quote_gaps and max(quote_gaps) > 300:
            issues.append("prediction_gap_over_five_minutes")
        if missing_minutes:
            issues.append("missing_equity_minutes")
        event_reports.append({
            "event_id": event.event_id,
            "release_timestamp": release.isoformat(),
            "prediction_ticker": event.prediction_ticker,
            "equity_ticker": event.equity_ticker,
            "baseline_quotes": len(baseline),
            "postrelease_quotes": len(postrelease),
            "max_prediction_gap_seconds": max(quote_gaps) if quote_gaps else None,
            "equity_expected_minutes": len(expected_minutes),
            "equity_missing_minutes": len(missing_minutes),
            "equity_coverage_pct": round(
                100 * (len(expected_minutes) - len(missing_minutes)) / len(expected_minutes), 2
            ),
            "first_missing_equity_minutes": [item.isoformat() for item in missing_minutes[:10]],
            "issues": issues,
        })

    return {
        "schema_version": 1,
        "purpose": "data coverage audit, not evidence of a trading edge",
        "inputs": {
            "events_sha256": _digest(events_path),
            "prediction_sha256": _digest(quotes_path),
            "equity_sha256": _digest(equity_path),
        },
        "assumptions": {
            "baseline_minutes": baseline_minutes,
            "signal_minutes": signal_minutes,
            "hold_minutes": hold_minutes,
            "latency_seconds": latency_seconds,
            "maximum_prediction_gap_seconds": 300,
            "equity_cadence": "every UTC minute from release through latest hypothetical exit",
        },
        "events": event_reports,
        "global_issues": global_issues,
        "ready_for_study": bool(event_reports) and not global_issues and all(
            not row["issues"] for row in event_reports
        ),
    }
