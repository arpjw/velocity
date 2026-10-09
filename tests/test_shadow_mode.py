import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from main import handle_signal
from scripts.export_observations import export_observations
from signals.velocity import VelocitySignal


@pytest.mark.asyncio
async def test_shadow_mode_records_candidate_without_orders(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "shadow.jsonl"
    monkeypatch.setenv("EXECUTION_MODE", "shadow")
    monkeypatch.setenv("SHADOW_SIGNAL_LOG_PATH", str(log))
    signal = VelocitySignal(
        contract_slug="KXFED-26OCT-T4.25", velocity=0.06, window_minutes=5,
        timestamp=datetime(2026, 10, 9, 18, tzinfo=timezone.utc),
        price=0.6, volume_delta=100, source="kalshi_fed",
    )
    client = MagicMock()
    mapper = MagicMock()
    mapper.get_basket.return_value = {"basket": ["XLF"]}
    hours = MagicMock()
    hours.is_open.return_value = False
    await handle_signal(
        signal, mapper, client, MagicMock(), MagicMock(), MagicMock(), hours
    )
    client.submit_order.assert_not_called()
    recorded = json.loads(log.read_text())
    assert recorded["contract_slug"] == "KXFED-26OCT-T4.25"
    assert recorded["equity_market_open"] is False
    assert recorded["source"] == "kalshi_fed"


def test_export_uses_receipt_time_when_update_arrives_late(tmp_path: Path) -> None:
    source = tmp_path / "observations.jsonl"
    output = tmp_path / "quotes.csv"
    source.write_text(json.dumps({
        "source": "kalshi", "ticker": "KXFED-26OCT-T4.25",
        "timestamp": "2026-10-09T18:00:00+00:00",
        "observed_at": "2026-10-09T18:00:03+00:00",
        "price": 0.6, "yes_bid": 0.59, "yes_ask": 0.61, "volume": 10,
    }) + "\n")
    assert export_observations(source, output) == 1
    with output.open(newline="") as file:
        row = next(csv.DictReader(file))
    assert row["timestamp"] == "2026-10-09T18:00:03+00:00"
