from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from main import _submit_signal
from signals.contract_mapper import ContractMapper
from signals.velocity import VelocitySignal


def test_series_mapping_is_not_an_execution_mapping() -> None:
    mapper = ContractMapper()
    assert mapper.get_basket("KXFED-26OCT-T4.25") is not None
    assert mapper.get_execution_basket("KXFED-26OCT-T4.25") is None


@pytest.mark.asyncio
async def test_mock_skips_sell_entry_without_short_support() -> None:
    mapper = MagicMock()
    mapper.get_execution_basket.return_value = {
        "direction": "down", "basket": ["XLF"], "confidence": 1.0
    }
    dedup = MagicMock()
    dedup.should_fire.return_value = True
    client = MagicMock()
    signal = VelocitySignal(
        contract_slug="KXFED-26OCT-T4.25", velocity=0.2, window_minutes=5,
        timestamp=datetime(2026, 10, 9, 18, tzinfo=timezone.utc),
        price=0.6, volume_delta=100,
    )
    await _submit_signal(signal, mapper, client, MagicMock(), dedup, MagicMock())
    client.submit_order.assert_not_called()
