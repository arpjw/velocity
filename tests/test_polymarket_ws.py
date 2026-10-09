import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from signals.polymarket_poller import PolymarketPoller
from signals.velocity import PricePoint, VelocitySignal, VelocityTracker


def make_poller(use_websocket=True) -> PolymarketPoller:
    tracker = VelocityTracker(window_minutes=5, threshold=0.0, history_minutes=60)
    mapper = MagicMock()
    poller = PolymarketPoller(
        condition_ids=["cond-1", "cond-2"],
        tracker=tracker,
        mapper=mapper,
        use_websocket=use_websocket,
    )
    poller._asset_to_condition = {"asset-1": "cond-1", "asset-2": "cond-2"}
    poller._volume_by_asset = {"asset-1": 0.0, "asset-2": 0.0}
    return poller


def price_change_msg(market: str, price: float) -> str:
    return json.dumps({"event_type": "price_change", "market": "cond-1", "price_changes": [{"asset_id": market, "best_bid": str(price - 0.01), "best_ask": str(price + 0.01)}]})


def price_change_list(market: str, price: float) -> str:
    return json.dumps([json.loads(price_change_msg(market, price))])


def make_dummy_signal(slug: str = "cond-1") -> VelocitySignal:
    return VelocitySignal(
        contract_slug=slug,
        velocity=0.25,
        window_minutes=5,
        timestamp=datetime.now(tz=timezone.utc),
        price=0.6,
        volume_delta=10,
    )


class TestWsMessageParsing:
    @pytest.mark.asyncio
    async def test_price_change_dict_fires_signal(self):
        poller = make_poller()
        dummy = make_dummy_signal("cond-1")
        poller._tracker.update = MagicMock(return_value=dummy)
        signals = []

        async def on_signal(sig):
            signals.append(sig)

        raw = price_change_msg("asset-1", 0.6)
        await poller._handle_ws_message(raw, on_signal)

        assert len(signals) == 1
        assert signals[0].contract_slug == "cond-1"

    @pytest.mark.asyncio
    async def test_price_change_list_fires_signal(self):
        poller = make_poller()
        dummy = make_dummy_signal("cond-1")
        poller._tracker.update = MagicMock(return_value=dummy)
        signals = []

        async def on_signal(sig):
            signals.append(sig)

        raw = price_change_list("asset-1", 0.6)
        await poller._handle_ws_message(raw, on_signal)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_unknown_event_type_ignored(self):
        poller = make_poller()
        fired = []

        async def on_signal(sig):
            fired.append(sig)

        raw = json.dumps({"event_type": "book", "market": "cond-1", "price": 0.6})
        await poller._handle_ws_message(raw, on_signal)
        assert fired == []

    @pytest.mark.asyncio
    async def test_unknown_market_ignored(self):
        poller = make_poller()
        fired = []

        async def on_signal(sig):
            fired.append(sig)

        raw = price_change_msg("unknown-asset", 0.6)
        await poller._handle_ws_message(raw, on_signal)
        assert fired == []

    @pytest.mark.asyncio
    async def test_invalid_json_ignored(self):
        poller = make_poller()
        fired = []

        async def on_signal(sig):
            fired.append(sig)

        await poller._handle_ws_message("not json {{{{", on_signal)
        assert fired == []

    @pytest.mark.asyncio
    async def test_missing_price_ignored(self):
        poller = make_poller()
        fired = []

        async def on_signal(sig):
            fired.append(sig)

        raw = json.dumps({"event_type": "price_change", "price_changes": [{"asset_id": "asset-1"}]})
        await poller._handle_ws_message(raw, on_signal)
        assert fired == []

    @pytest.mark.asyncio
    async def test_last_trade_updates_cumulative_volume(self):
        poller = make_poller()
        poller._tracker.update = MagicMock(return_value=None)
        raw = json.dumps({"event_type": "last_trade_price", "asset_id": "asset-1", "price": "0.62", "size": "3.5", "timestamp": "1782753357257"})
        await poller._handle_ws_message(raw, AsyncMock())
        assert poller._volume_by_asset["asset-1"] == 3.5
        assert poller._tracker.update.call_args.args[0] == "cond-1"
        assert poller._tracker.update.call_args.args[1].price == 0.62

    @pytest.mark.asyncio
    async def test_subscribe_uses_yes_asset_ids(self):
        poller = make_poller()
        ws = AsyncMock()
        await poller._send_subscribe(ws)
        assert json.loads(ws.send.call_args.args[0]) == {"type": "market", "assets_ids": ["asset-1", "asset-2"]}

    def test_rest_price_uses_yes_outcome(self):
        poller = make_poller()
        market = {"tokens": [{"outcome": "No", "price": "0.4"}, {"outcome": "Yes", "price": "0.6"}], "volume": "10"}
        assert poller._extract_price_volume(market) == (0.6, 10)


class TestWsFallback:
    @pytest.mark.asyncio
    async def test_rest_fallback_on_connection_failure(self):
        poller = make_poller(use_websocket=True)
        rest_called = []

        async def fake_run_rest(interval_seconds, on_signal):
            rest_called.append(True)

        async def fake_run_ws(on_signal):
            return False

        poller._run_rest = fake_run_rest
        poller._run_websocket = fake_run_ws

        await poller.run(30, AsyncMock())
        assert rest_called

    @pytest.mark.asyncio
    async def test_disabled_websocket_goes_directly_to_rest(self):
        poller = make_poller(use_websocket=False)
        rest_called = []

        async def fake_run_rest(interval_seconds, on_signal):
            rest_called.append(True)

        poller._run_rest = fake_run_rest

        await poller.run(30, AsyncMock())
        assert rest_called

    @pytest.mark.asyncio
    async def test_backoff_increments_on_failure(self):
        import websockets.exceptions

        poller = make_poller()
        poller._resolve_assets = AsyncMock()
        sleep_calls = []

        original_sleep = asyncio.sleep

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("signals.polymarket_poller.ws_connect") as mock_connect, \
             patch("asyncio.sleep", fake_sleep):
            mock_connect.side_effect = OSError("connection refused")
            result = await poller._run_websocket(AsyncMock())

        assert result is False
        if sleep_calls:
            assert sleep_calls[0] <= sleep_calls[-1]
