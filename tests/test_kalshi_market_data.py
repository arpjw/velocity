from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from signals.kalshi_market_data import discover_markets, parse_market
from signals.kalshi_poller import _sign_request
from scripts.fetch_kalshi_history import candle_to_row, fetch_event_candles
from tests.test_kalshi_ws import make_rsa_key
from cryptography.hazmat.primitives import serialization


def test_parse_market_requires_traded_probability() -> None:
    raw = {
        "ticker": "KXFED-26OCT-T4.25",
        "event_ticker": "KXFED-26OCT",
        "yes_sub_title": "Above 4.25%",
        "last_price_dollars": "0.5600",
        "volume_fp": "125.50",
    }
    market = parse_market(raw)
    assert market is not None and market.price == 0.56
    assert market.volume == 125.5
    assert parse_market({**raw, "volume_fp": "0.00"}) is None


@pytest.mark.asyncio
async def test_discovery_paginates_and_ranks_liquid_markets() -> None:
    responses = [
        {"markets": [{"ticker": "KXFED-1", "last_price_dollars": "0.4", "volume_fp": "2"}], "cursor": "next"},
        {"markets": [{"ticker": "KXFED-2", "last_price_dollars": "0.6", "volume_fp": "8"}], "cursor": ""},
    ]
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = [httpx.Response(200, json=body, request=httpx.Request("GET", "https://example.com")) for body in responses]
    markets = await discover_markets("KXFED", limit=1, client=client)
    assert [market.ticker for market in markets] == ["KXFED-2"]
    assert client.get.call_count == 2


def test_signature_uses_millisecond_timestamp_and_path_without_query(tmp_path, monkeypatch) -> None:
    key_path = make_rsa_key(tmp_path)
    key = serialization.load_pem_private_key(open(key_path, "rb").read(), password=None)
    monkeypatch.setattr("signals.kalshi_poller.time.time", lambda: 1700000000.123)
    headers = _sign_request("test", key, "GET", "https://example.com/trade-api/v2/markets?limit=1")
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000123"


def test_candle_parser_supports_current_and_archived_formats() -> None:
    current = {"end_period_ts": 1700000000, "price": {"close_dollars": "0.5600"}, "yes_bid": {"close_dollars": "0.5400"}, "yes_ask": {"close_dollars": "0.5800"}}
    archived = {"end_period_ts": 1700000000, "price": {"close": "0.5600"}, "yes_bid": {"close": "0.5400"}, "yes_ask": {"close": "0.5800"}}
    for candle in (current, archived):
        row = candle_to_row("KXFED-26OCT-T4.25", candle, 12.5)
        assert row is not None
        assert row["price"] == 0.56
        assert row["yes_bid"] == "0.5400"
        assert row["volume"] == 12.5


def test_fetch_event_uses_exact_market_tickers(monkeypatch) -> None:
    client = MagicMock()
    client.get.side_effect = [
        httpx.Response(200, json={"markets": [{"ticker": "KXFED-26OCT-T4.25"}], "cursor": ""}, request=httpx.Request("GET", "https://example.com")),
        httpx.Response(200, json={"candlesticks": [{"end_period_ts": 1700000000, "price": {"close_dollars": "0.5600"}, "volume_fp": "12.50"}]}, request=httpx.Request("GET", "https://example.com")),
    ]
    monkeypatch.setattr("scripts.fetch_kalshi_history.time.sleep", lambda _: None)
    rows = fetch_event_candles(client, "KXFED-26OCT", 1699999000, 1700001000, historical=False)
    assert len(rows) == 1 and rows[0]["ticker"] == "KXFED-26OCT-T4.25"
    assert "series/KXFED/markets/KXFED-26OCT-T4.25/candlesticks" in client.get.call_args_list[1].args[0]
