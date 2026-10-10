#!/usr/bin/env python3
"""Write a timing and integrity audit of a shadow observation JSONL log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.event_study import parse_time
from research.observation_audit import audit_observations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("logs/market_observations.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gap-seconds", type=float, default=120)
    parser.add_argument("--receipt-lag-seconds", type=float, default=30)
    parser.add_argument("--start", type=parse_time, help="Inclusive ISO 8601 receipt time")
    parser.add_argument("--end", type=parse_time, help="Exclusive ISO 8601 receipt time")
    args = parser.parse_args()
    report = audit_observations(
        args.input, gap_seconds=args.gap_seconds,
        receipt_lag_seconds=args.receipt_lag_seconds,
        start=args.start, end=args.end,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Audited {len(report['markets'])} source/ticker streams; needs_review={report['needs_review']}")


if __name__ == "__main__":
    main()
