#!/usr/bin/env python3
"""Evaluate one Fed market family's point-in-time lead and lag against equities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.event_study import load_equity_bars, load_events, load_quotes, run_study
from signals.velocity import VELOCITY_THRESHOLD, VELOCITY_WINDOW_MINUTES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, help="Event manifest CSV")
    parser.add_argument("--kalshi-csv", required=True, help="Normalized Kalshi minute candles CSV")
    parser.add_argument("--equity-csv", required=True, help="Point-in-time equity minute bars CSV")
    parser.add_argument("--output", required=True, help="JSON report output path")
    parser.add_argument("--velocity-threshold", "--threshold", dest="threshold", type=float,
                        default=VELOCITY_THRESHOLD, help="Probability points per minute")
    parser.add_argument("--velocity-window-minutes", type=int, default=VELOCITY_WINDOW_MINUTES)
    parser.add_argument("--volume-multiplier", type=float, default=2.0)
    parser.add_argument("--signal-window-minutes", type=int, default=15,
                        help="Minutes after release to look for the first signal")
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
        velocity_window_minutes=args.velocity_window_minutes,
        volume_multiplier=args.volume_multiplier,
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
