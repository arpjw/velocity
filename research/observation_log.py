from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


logger = logging.getLogger(__name__)
PriceKind = Literal["last_trade", "midpoint", "reference"]


@dataclass(frozen=True)
class MarketObservation:
    source: str
    ticker: str
    source_timestamp: datetime
    observed_at: datetime
    price: float
    volume: float
    price_kind: PriceKind
    bid: float | None = None
    ask: float | None = None
    asset_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source or not self.ticker:
            raise ValueError("observation source and ticker are required")
        if self.source_timestamp.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("observation timestamps must include a timezone")
        if self.price_kind not in ("last_trade", "midpoint", "reference"):
            raise ValueError("unknown observation price kind")
        if not math.isfinite(self.price) or not 0 <= self.price <= 1:
            raise ValueError("observation price outside [0, 1]")
        if not math.isfinite(self.volume) or self.volume < 0:
            raise ValueError("observation volume must be finite and nonnegative")
        for quote in (self.bid, self.ask):
            if quote is not None and (not math.isfinite(quote) or not 0 <= quote <= 1):
                raise ValueError("observation bid/ask outside [0, 1]")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("observation bid exceeds ask")

    def to_record(self) -> dict:
        source_time = self.source_timestamp.astimezone(timezone.utc).isoformat()
        observed_at = self.observed_at.astimezone(timezone.utc).isoformat()
        identity = json.dumps(
            [self.source, self.ticker, self.asset_id, source_time,
             self.price_kind, self.price, self.volume],
            separators=(",", ":"),
        )
        return {
            "schema_version": 1,
            "observation_id": hashlib.sha256(identity.encode()).hexdigest(),
            "observed_at": observed_at,
            "timestamp": source_time,
            "source": self.source,
            "ticker": self.ticker,
            "asset_id": self.asset_id,
            "price_kind": self.price_kind,
            "price": self.price,
            "yes_bid": self.bid,
            "yes_ask": self.ask,
            "volume": self.volume,
        }


def _optional_price(raw: object) -> float | None:
    return None if raw is None or raw == "" else float(raw)


def append_observation(
    *,
    source: str,
    ticker: str,
    source_timestamp: datetime,
    price: float,
    volume: float,
    bid: object = None,
    ask: object = None,
    price_kind: PriceKind = "last_trade",
    asset_id: str | None = None,
) -> bool:
    try:
        observation = MarketObservation(
            source=source, ticker=ticker,
            source_timestamp=source_timestamp,
            observed_at=datetime.now(tz=timezone.utc),
            price=float(price), volume=float(volume),
            price_kind=price_kind,
            bid=_optional_price(bid), ask=_optional_price(ask),
            asset_id=asset_id,
        )
    except (TypeError, ValueError) as exc:
        logger.warning("dropping invalid %s observation for %s: %s", source, ticker, exc)
        return False
    if os.getenv("OBSERVATIONS_ENABLED", "true").lower() in ("0", "false", "no"):
        return True
    path = Path(os.getenv("OBSERVATION_LOG_PATH", "logs/market_observations.jsonl"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as file:
            file.write(json.dumps(observation.to_record()) + "\n")
    except OSError as exc:
        logger.error("observation log unavailable for %s: %s", ticker, exc)
        return False
    return True


def append_shadow_signal(record: dict) -> None:
    path = Path(os.getenv("SHADOW_SIGNAL_LOG_PATH", "logs/shadow_signals.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.write(json.dumps(record) + "\n")
