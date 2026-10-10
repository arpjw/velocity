import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from connectors.base import PrismConnector


def _connector():
    return PrismConnector.from_prism_package(Path("connectors/kalshi_fed.prism"))


@pytest.mark.asyncio
async def test_discovery_refreshes_tickers_and_observation_sets_health(monkeypatch) -> None:
    connector = _connector()
    globals_ = type(connector).start.__globals__
    discovered = [
        [SimpleNamespace(ticker="KXFED-1")],
        [SimpleNamespace(ticker="KXFED-2")],
    ]
    discover = AsyncMock(side_effect=discovered)
    tracked = []

    class FakePoller:
        def __init__(self, *, tracked_tickers, on_observation, **_kwargs):
            tracked.append(tracked_tickers)
            self.on_observation = on_observation

        async def run(self, **_kwargs):
            self.on_observation(datetime.now(tz=timezone.utc))
            await asyncio.sleep(1)

    monkeypatch.setitem(globals_, "discover_markets", discover)
    monkeypatch.setitem(globals_, "KalshiPoller", FakePoller)
    monkeypatch.setenv("KALSHI_DISCOVERY_INTERVAL_SECONDS", "0.02")
    monkeypatch.delenv("KALSHI_TICKERS", raising=False)
    task = asyncio.create_task(connector.start(MagicMock(), MagicMock(), AsyncMock()))
    try:
        for _ in range(30):
            if len(tracked) >= 2:
                break
            await asyncio.sleep(0.01)
        assert tracked[:2] == [["KXFED-1"], ["KXFED-2"]]
        health = connector.health_check()
        assert health["status"] == "ok"
        assert health["last_update"] is not None
        assert health["last_signal"] is None
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_health_marks_stale_observations_without_a_signal(monkeypatch) -> None:
    connector = _connector()
    connector._started_at = datetime.now(tz=timezone.utc) - timedelta(minutes=4)
    monkeypatch.setenv("KALSHI_STALE_SECONDS", "180")
    assert connector.health_check()["status"] == "degraded"
    assert connector.health_check()["message"] == "observations stale"
