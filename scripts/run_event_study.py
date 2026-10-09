#!/usr/bin/env python3
"""Evaluate one Fed market family's point-in-time lead and lag against equities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.event_study import load_equity_bars, load_events, load_quotes, run_study


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, help="Event manifest CSV")
    parser.add_argument("--kalshi-csv", required=True, help="Normalized Kalshi minute candles CSV")
    parser.add_argument("--equity-csv", required=True, help="Point-in-time equity minute bars CSV")
    parser.add_argument("--output", required=True, help="JSON report output path")
    parser.add_argument("--threshold", type=float, default=0.05, help="Probability move, default 0.05")
    parser.add_argument("--signal-window-minutes", type=int, default=15)
    parser.add_argument("--hold-minutes", type=int, default=120)
    parser.add_argument("--latency-seconds", type=int, default=60)
    parser.add_argument("--round-trip-cost-bps", type=float, default=30)
    args = parser.parse_args()
    report = run_study(
        load_events(args.events),
        load_quotes(args.kalshi_csv),
        load_equity_bars(args.equity_csv),
        threshold=args.threshold,
        window_minutes=args.signal_window_minutes,
        hold_minutes=args.hold_minutes,
        latency_seconds=args.latency_seconds,
        round_trip_cost_bps=args.round_trip_cost_bps,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"train": report["train"], "holdout": report["holdout"]}, indent=2))
    print(f"Wrote event-level report to {output}")


if __name__ == "__main__":
    main()
