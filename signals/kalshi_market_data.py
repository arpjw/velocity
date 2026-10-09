from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

KALSHI_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


@dataclass(frozen=True)
class KalshiMarket:
    ticker: str
    event_ticker: str
    yes_sub_title: str
    volume: float
    price: float


def parse_market(raw: dict) -> KalshiMarket | None:
    try:
        ticker = str(raw["ticker"])
        price = float(raw["last_price_dollars"])
        volume = float(raw["volume_fp"])
    except (KeyError, TypeError, ValueError):
        return None
    if not ticker or not 0 < price < 1 or volume <= 0:
        return None
    return KalshiMarket(
        ticker=ticker,
        event_ticker=str(raw.get("event_ticker") or ""),
        yes_sub_title=str(raw.get("yes_sub_title") or ""),
        volume=volume,
        price=price,
    )


async def discover_markets(
    series_ticker: str,
    *,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[KalshiMarket]:
    if limit <= 0:
        return []
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    markets: list[KalshiMarket] = []
    cursor = ""
    try:
        while True:
            params: dict[str, str | int] = {
                "series_ticker": series_ticker,
                "status": "open",
                "limit": 1000,
            }
            if cursor:
                params["cursor"] = cursor
            response = await client.get(f"{KALSHI_BASE_URL}/markets", params=params)
            response.raise_for_status()
            payload = response.json()
            markets.extend(
                market
                for raw in payload.get("markets", [])
                if (market := parse_market(raw)) is not None
            )
            cursor = payload.get("cursor") or ""
            if not cursor:
                break
        markets.sort(key=lambda market: market.volume, reverse=True)
        return markets[:limit]
    finally:
        if owns_client:
            await client.aclose()


def source_time_from_ms(raw: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None
