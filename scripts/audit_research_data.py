#!/usr/bin/env python3
"""Write a provenance and coverage report for a Fed study CSV dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.data_audit import audit_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--kalshi-csv", type=Path, required=True)
    parser.add_argument("--equity-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signal-window-minutes", type=int, default=15)
    parser.add_argument("--hold-minutes", type=int, default=120)
    parser.add_argument("--latency-seconds", type=int, default=60)
    args = parser.parse_args()
    report = audit_dataset(
        args.events, args.kalshi_csv, args.equity_csv,
        signal_minutes=args.signal_window_minutes,
        hold_minutes=args.hold_minutes,
        latency_seconds=args.latency_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Audited {len(report['events'])} manifest rows; ready_for_study={report['ready_for_study']}")
    if not report["ready_for_study"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
