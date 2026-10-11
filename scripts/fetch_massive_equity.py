#!/usr/bin/env python3
"""Fetch unadjusted one-minute equity bars for one date from Massive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv


BASE_URL = "https://api.massive.com"
SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]*")


def normalize_bars(payload: dict, ticker: str) -> list[dict]:
    if payload.get("ticker") != ticker or payload.get("adjusted") is not False:
        raise ValueError("vendor response ticker or adjustment setting does not match request")
    if payload.get("status") != "OK" or payload.get("next_url"):
        raise ValueError("vendor response is incomplete or not OK")
    values = payload.get("results")
    if not isinstance(values, list) or not values:
        raise ValueError("vendor response contains no minute bars")
    rows = []
    for bar in values:
        try:
            timestamp = datetime.fromtimestamp(int(bar["t"]) / 1000, tz=timezone.utc)
            opening_price = float(bar["o"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid minute bar in vendor response") from exc
        if not math.isfinite(opening_price) or opening_price <= 0:
            raise ValueError("invalid equity open in vendor response")
        rows.append({"timestamp": timestamp.isoformat(), "ticker": ticker, "open": opening_price})
    rows.sort(key=lambda row: row["timestamp"])
    if len({row["timestamp"] for row in rows}) != len(rows):
        raise ValueError("duplicate equity minute in vendor response")
    return rows


def fetch_bars(client: httpx.Client, ticker: str, session_date: date) -> tuple[dict, str]:
    day = session_date.isoformat()
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/minute/{day}/{day}"
    response = client.get(url, params={"adjusted": "false", "sort": "asc", "limit": 50000})
    response.raise_for_status()
    return response.json(), str(response.request.url)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ticker = args.ticker.upper()
    if not SYMBOL.fullmatch(ticker):
        parser.error("--ticker must be a US equity or ETF symbol")
    load_dotenv()
    api_key = os.getenv("MASSIVE_API_KEY", "")
    if not api_key:
        parser.error("MASSIVE_API_KEY is required")

    raw_path = args.output.with_suffix(".raw.json")
    provenance_path = args.output.with_suffix(".provenance.json")
    for path in (args.output, raw_path, provenance_path):
        if path.exists():
            parser.error(f"output already exists: {path}")
    with httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=20.0) as client:
        payload, request_url = fetch_bars(client, ticker, args.date)
    rows = normalize_bars(payload, ticker)
    raw_text = json.dumps(payload, indent=2) + "\n"
    retrieved_at = datetime.now(tz=timezone.utc).isoformat()
    provenance = {
        "provider": "Massive Stocks minute aggregates",
        "source_url": request_url,
        "retrieved_at": retrieved_at,
        "ticker": ticker,
        "session_date": args.date.isoformat(),
        "adjusted": False,
        "raw_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
        "bar_count": len(rows),
        "limitation": "Historical bar availability at the original event time is unverified; no bid/ask quotes",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw_text)
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
    with args.output.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["timestamp", "ticker", "open"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} unadjusted {ticker} minute bars to {args.output}")


if __name__ == "__main__":
    main()
