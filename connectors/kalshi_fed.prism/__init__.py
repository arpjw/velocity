import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Callable

from connectors.base import PrismConnector, PrismMetadata
from signals.kalshi_poller import KalshiPoller
from signals.velocity import VelocitySignal, VelocityTracker
from signals.contract_mapper import ContractMapper
from signals.kalshi_market_data import discover_markets

logger = logging.getLogger(__name__)


class KalshiFedConnector(PrismConnector):
    metadata = PrismMetadata(
        name="Kalshi Fed Markets",
        slug="kalshi_fed",
        version="1.0.0",
        author="arpjw",
        source_type="prediction_market",
        transport="websocket",
        description="Streams KXFED contract prices from Kalshi via WebSocket.",
        auth_required=False,
        auth_fields=[],
        contract_slugs=["KXFED"],
        poll_interval_seconds=None,
        capabilities=["velocity", "volume"],
    )

    def __init__(self) -> None:
        self._running_task: asyncio.Task | None = None
        self._last_update: datetime | None = None
        self._last_signal: datetime | None = None
        self._started_at: datetime | None = None
        self._status = "ok"
        self._message = "not started"

    async def start(
        self,
        tracker: VelocityTracker,
        mapper: ContractMapper,
        handle_signal: Callable,
    ) -> None:
        self._running_task = asyncio.current_task()
        self._started_at = datetime.now(tz=timezone.utc)
        self._message = "waiting for observations"

        tickers_env = os.getenv("KALSHI_TICKERS", "")
        configured = [t.strip() for t in tickers_env.split(",") if t.strip()]
        interval = float(os.getenv("POLL_INTERVAL_SECONDS", "30"))
        refresh_seconds = float(os.getenv("KALSHI_DISCOVERY_INTERVAL_SECONDS", "300"))
        if interval <= 0 or refresh_seconds <= 0:
            raise ValueError("poll and discovery intervals must be positive")

        async def _on_signal(sig: VelocitySignal) -> None:
            self._last_signal = datetime.now(tz=timezone.utc)
            await handle_signal(sig)

        def _on_observation(timestamp: datetime) -> None:
            self._last_update = timestamp
            self._status = "ok"
            self._message = "receiving observations"

        try:
            tracked = configured
            while True:
                if not configured:
                    try:
                        markets = await discover_markets("KXFED")
                        discovered = [market.ticker for market in markets]
                        if discovered:
                            tracked = discovered
                        else:
                            self._status = "degraded"
                            self._message = "no traded KXFED markets found"
                    except Exception as exc:
                        self._status = "degraded"
                        self._message = f"market discovery failed: {exc}"
                        logger.warning("KXFED market discovery failed: %s", exc)
                if not tracked:
                    await asyncio.sleep(refresh_seconds)
                    continue
                poller = KalshiPoller(
                    api_key=os.getenv("KALSHI_API_KEY", ""),
                    tracked_tickers=tracked,
                    tracker=tracker,
                    on_observation=_on_observation,
                )
                try:
                    await asyncio.wait_for(
                        poller.run(interval_seconds=interval, on_signal=_on_signal),
                        timeout=refresh_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
                except Exception as exc:
                    self._status = "degraded"
                    self._message = f"poller failed: {exc}"
                    logger.exception("KXFED poller failed")
                    await asyncio.sleep(min(30, refresh_seconds))
        except asyncio.CancelledError:
            self._message = "stopped"
            raise

    async def stop(self) -> None:
        if self._running_task is not None:
            self._running_task.cancel()

    def health_check(self) -> dict:
        reference = self._last_update or self._started_at
        age = (datetime.now(tz=timezone.utc) - reference).total_seconds() if reference else None
        stale_seconds = float(os.getenv("KALSHI_STALE_SECONDS", "180"))
        status = "degraded" if age is not None and age > stale_seconds else self._status
        return {
            "status": status,
            "message": "observations stale" if status == "degraded" and age is not None and age > stale_seconds else self._message,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "last_signal": self._last_signal.isoformat() if self._last_signal else None,
            "observation_age_seconds": round(age, 1) if age is not None else None,
        }
