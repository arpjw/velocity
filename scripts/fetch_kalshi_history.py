#!/usr/bin/env python3
"""Fetch one Kalshi event's minute candles for point-in-time research."""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from signals.kalshi_market_data import KALSHI_BASE_URL


def candle_to_row(ticker: str, candle: dict, cumulative_volume: float) -> dict | None:
    price = candle.get("price") or {}
    close = price.get("close_dollars", price.get("close"))
    timestamp = candle.get("end_period_ts")
    if close is None or timestamp is None:
        return None
    bid = candle.get("yes_bid") or {}
    ask = candle.get("yes_ask") or {}
    return {
        "timestamp": datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat(),
        "ticker": ticker,
        "price": float(close),
        "yes_bid": bid.get("close_dollars", bid.get("close")) or "",
        "yes_ask": ask.get("close_dollars", ask.get("close")) or "",
        "volume": cumulative_volume,
    }


def fetch_event_candles(
    client: httpx.Client,
    event_ticker: str,
    start_ts: int,
    end_ts: int,
    *,
    historical: bool,
) -> list[dict]:
    prefix = "historical/markets" if historical else "markets"
    params = {"event_ticker": event_ticker, "limit": 1000}
    tickers: list[str] = []
    cursor = ""
    while True:
        if cursor:
            params["cursor"] = cursor
        response = client.get(f"{KALSHI_BASE_URL}/{prefix}", params=params)
        response.raise_for_status()
        payload = response.json()
        tickers.extend(str(m["ticker"]) for m in payload.get("markets", []) if m.get("ticker"))
        cursor = payload.get("cursor") or ""
        if not cursor:
            break
    rows: list[dict] = []
    for ticker in tickers:
        if historical:
            path = f"historical/markets/{ticker}/candlesticks"
        else:
            series = event_ticker.split("-")[0]
            path = f"series/{series}/markets/{ticker}/candlesticks"
        response = client.get(
            f"{KALSHI_BASE_URL}/{path}",
            params={"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1},
        )
        response.raise_for_status()
        cumulative_volume = 0.0
        for candle in response.json().get("candlesticks", []):
            cumulative_volume += float(candle.get("volume_fp", candle.get("volume", 0)) or 0)
            row = candle_to_row(ticker, candle, cumulative_volume)
            if row is not None:
                rows.append(row)
        time.sleep(0.25)
    return sorted(rows, key=lambda row: (row["timestamp"], row["ticker"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-ticker", required=True, help="Exact event, e.g. KXFED-26OCT")
    parser.add_argument("--start", required=True, help="UTC start in ISO 8601 format")
    parser.add_argument("--end", required=True, help="UTC end in ISO 8601 format")
    parser.add_argument("--historical", action="store_true", help="Use archived market endpoints")
    parser.add_argument("--output", required=True, help="CSV output path")
    args = parser.parse_args()
    start_ts = int(datetime.fromisoformat(args.start.replace("Z", "+00:00")).timestamp())
    end_ts = int(datetime.fromisoformat(args.end.replace("Z", "+00:00")).timestamp())
    if start_ts >= end_ts:
        parser.error("--start must precede --end")
    with httpx.Client(timeout=20.0) as client:
        rows = fetch_event_candles(
            client, args.event_ticker, start_ts, end_ts, historical=args.historical
        )
    if not rows:
        parser.error("No candles found for this event and time range")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=["timestamp", "ticker", "price", "yes_bid", "yes_ask", "volume"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} candles across {len({row['ticker'] for row in rows})} markets to {output}")


if __name__ == "__main__":
    main()
