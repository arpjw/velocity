#!/usr/bin/env python3
"""Export observed Kalshi quotes to the event study CSV schema."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from research.event_study import parse_time


def export_observations(input_path: Path, output_path: Path, ticker: str | None = None) -> int:
    rows: list[dict] = []
    with input_path.open() as file:
        for line in file:
            try:
                record = json.loads(line)
                if record.get("source") != "kalshi":
                    continue
                if ticker and record.get("ticker") != ticker:
                    continue
                observed_at = parse_time(record["observed_at"])
                source_at = parse_time(record["timestamp"])
                rows.append({
                    "timestamp": max(observed_at, source_at).isoformat(),
                    "ticker": record["ticker"],
                    "price": record["price"],
                    "yes_bid": record.get("yes_bid") or "",
                    "yes_ask": record.get("yes_ask") or "",
                    "volume": record["volume"],
                })
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
    rows.sort(key=lambda row: (row["timestamp"], row["ticker"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=["timestamp", "ticker", "price", "yes_bid", "yes_ask", "volume"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="logs/market_observations.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--ticker", help="Optional exact market ticker")
    args = parser.parse_args()
    count = export_observations(Path(args.input), Path(args.output), args.ticker)
    print(f"Wrote {count} observed Kalshi quotes to {args.output}")


if __name__ == "__main__":
    main()
