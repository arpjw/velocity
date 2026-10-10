import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from connectors.base import PrismRegistry
from main import _supervise_connector


@pytest.mark.asyncio
async def test_failed_connector_retries_without_stopping_sibling() -> None:
    started_again = asyncio.Event()
    sibling_alive = asyncio.Event()
    retrying: dict[str, dict] = {}

    class Connector:
        metadata = SimpleNamespace(slug="failing")
        calls = 0

        async def start(self, *_args):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary outage")
            started_again.set()
            await asyncio.Event().wait()

    async def sibling():
        await asyncio.sleep(0.005)
        sibling_alive.set()

    connector = Connector()
    task = asyncio.create_task(_supervise_connector(
        connector, MagicMock(), MagicMock(), AsyncMock(), retrying,
        restart_seconds=0.02,
    ))
    try:
        await sibling()
        assert sibling_alive.is_set()
        assert retrying["failing"]["status"] == "degraded"
        await asyncio.wait_for(started_again.wait(), timeout=1)
        assert connector.calls == 2
        assert "failing" not in retrying
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_intentional_connector_return_does_not_retry() -> None:
    connector = MagicMock()
    connector.metadata.slug = "idle"
    connector.start = AsyncMock(return_value=None)
    await _supervise_connector(connector, MagicMock(), MagicMock(), AsyncMock(), {},
                                restart_seconds=0.01)
    connector.start.assert_awaited_once()


def test_health_report_isolates_bad_connector() -> None:
    registry = PrismRegistry()
    good = MagicMock()
    good.metadata.slug = "good"
    good.health_check.return_value = {"status": "ok"}
    bad = MagicMock()
    bad.metadata.slug = "bad"
    bad.health_check.side_effect = ValueError("private details")
    registry.register(good)
    registry.register(bad)
    report = registry.get_health_report()
    assert report["good"] == {"status": "ok"}
    assert report["bad"] == {
        "status": "degraded", "message": "health check failed",
        "failure_type": "ValueError",
    }
