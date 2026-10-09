from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def append_observation(
    *,
    source: str,
    ticker: str,
    source_timestamp: datetime,
    price: float,
    volume: float,
    bid: object = None,
    ask: object = None,
) -> None:
    if os.getenv("OBSERVATIONS_ENABLED", "true").lower() in ("0", "false", "no"):
        return
    path = Path(os.getenv("OBSERVATION_LOG_PATH", "logs/market_observations.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "observed_at": datetime.now(tz=timezone.utc).isoformat(),
        "timestamp": source_timestamp.isoformat(),
        "source": source,
        "ticker": ticker,
        "price": price,
        "yes_bid": bid,
        "yes_ask": ask,
        "volume": volume,
    }
    with path.open("a") as file:
        file.write(json.dumps(record) + "\n")


def append_shadow_signal(record: dict) -> None:
    path = Path(os.getenv("SHADOW_SIGNAL_LOG_PATH", "logs/shadow_signals.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.write(json.dumps(record) + "\n")
