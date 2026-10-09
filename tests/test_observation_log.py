import json
from datetime import datetime, timezone

from research.observation_log import append_observation
from scripts.export_observations import export_observations


def test_typed_observation_validates_and_deduplicates_export(tmp_path, monkeypatch) -> None:
    log = tmp_path / "observations.jsonl"
    output = tmp_path / "quotes.csv"
    monkeypatch.setenv("OBSERVATION_LOG_PATH", str(log))
    timestamp = datetime(2026, 10, 9, 18, tzinfo=timezone.utc)
    observation = dict(
        source="kalshi", ticker="KXFED-26OCT-T4.25", source_timestamp=timestamp,
        price=0.55, volume=10.75, bid="0.54", ask="0.56", price_kind="last_trade",
    )
    assert append_observation(**observation)
    assert append_observation(**observation)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert records[0]["schema_version"] == 1
    assert records[0]["observation_id"] == records[1]["observation_id"]
    assert records[0]["volume"] == 10.75
    midpoint = dict(observation, price_kind="midpoint", price=0.55)
    assert append_observation(**midpoint)
    assert export_observations(log, output) == 1


def test_invalid_quote_is_not_recorded(tmp_path, monkeypatch) -> None:
    log = tmp_path / "observations.jsonl"
    monkeypatch.setenv("OBSERVATION_LOG_PATH", str(log))
    assert not append_observation(
        source="kalshi", ticker="KXFED-26OCT-T4.25",
        source_timestamp=datetime.now(tz=timezone.utc), price=0.55,
        volume=10, bid="0.7", ask="0.6",
    )
    assert not log.exists()
