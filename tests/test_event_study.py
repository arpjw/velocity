from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from research.event_study import (
    EquityBar,
    EventSpec,
    Quote,
    evaluate_event,
    first_signal,
    load_events,
    next_open,
    run_study,
)


RELEASE = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)


def event(release: datetime = RELEASE, event_id: str = "fed-1") -> EventSpec:
    return EventSpec(event_id, release, "KXFED-26JAN-T4.25", "XLF", 1, 1)


def quote(minutes: int, price: float, volume: float, release: datetime = RELEASE) -> Quote:
    return Quote(release + timedelta(minutes=minutes), "KXFED-26JAN-T4.25", price, volume)


def bar(minutes: int, opening: float, release: datetime = RELEASE) -> EquityBar:
    return EquityBar(release + timedelta(minutes=minutes), "XLF", opening)


def test_signal_uses_strictly_prerelease_reference_and_volume() -> None:
    quotes = [quote(-1, 0.50, 10), quote(0, 0.53, 10), quote(1, 0.56, 11)]
    detected = first_signal(quotes, RELEASE, threshold=0.02, window_minutes=15)
    assert detected is not None and detected[0].timestamp == RELEASE + timedelta(minutes=1)
    assert detected[1].velocity == pytest.approx(0.03)
    assert first_signal(quotes[1:], RELEASE, threshold=0.02, window_minutes=15) is None
    assert first_signal([quote(-1, 0.5, 10), quote(1, 0.6, 10)], RELEASE, threshold=0.02, window_minutes=15) is None


def test_replay_uses_velocity_not_absolute_probability_move() -> None:
    assert first_signal(
        [quote(-4, 0.5, 10), quote(1, 0.56, 20)],
        RELEASE, threshold=0.02, window_minutes=15,
    ) is None


def test_event_prices_first_available_intraday_open_after_latency() -> None:
    result = evaluate_event(
        event(),
        [quote(-1, 0.5, 10), quote(1, 0.56, 20)],
        [bar(1, 100), bar(2, 101), bar(122, 103)],
        threshold=0.02,
        window_minutes=15,
        hold_minutes=120,
        latency_seconds=60,
        round_trip_cost_bps=30,
    )
    assert result["status"] == "priced"
    assert result["velocity_per_minute"] == pytest.approx(0.03)
    assert result["pre_signal_move_bps"] == pytest.approx(100)
    assert result["signal_net_bps"] == pytest.approx((103 / 101 - 1) * 10000 - 30)
    assert result["release_baseline_net_bps"] == pytest.approx(270)


def test_stale_equity_bar_is_not_used() -> None:
    assert next_open([bar(5, 100)], RELEASE, max_delay_minutes=2) is None


def test_chronological_holdout_and_missing_signal() -> None:
    later = RELEASE + timedelta(days=1)
    events = [event(), event(later, "fed-2")]
    report = run_study(
        events,
        {"KXFED-26JAN-T4.25": [quote(-1, 0.5, 10), quote(1, 0.56, 20), quote(-1, 0.5, 10, later), quote(1, 0.51, 20, later)]},
        {"XLF": [bar(1, 100), bar(2, 101), bar(122, 103)]},
        threshold=0.02,
    )
    assert report["train"]["signals"] == 1
    assert report["holdout"]["signals"] == 0
    assert report["holdout"]["mean_net_bps"] is None
    assert len(report["train_sensitivity"]) == 9


def test_multiple_contracts_for_one_release_count_as_one_event() -> None:
    second_ticker = "KXFED-26JAN-T4.50"
    first_quotes = [quote(-1, 0.5, 10), quote(1, 0.56, 20)]
    second_quotes = [
        Quote(point.timestamp, second_ticker, point.price, point.volume)
        for point in first_quotes
    ]
    report = run_study(
        [event(), EventSpec("fed-1", RELEASE, second_ticker, "XLF", 1, 1)],
        {event().prediction_ticker: first_quotes, second_ticker: second_quotes},
        {"XLF": [bar(1, 100), bar(2, 101), bar(122, 103)]},
        threshold=0.02,
    )
    assert report["train"]["events"] == 1
    assert report["train"]["contract_rows"] == 2
    assert report["train"]["signals"] == 1
    assert report["train"]["priced"] == 1
    assert report["train"]["priced_contracts"] == 2
    assert len(report["event_results"]) == 1
    assert report["event_results"][0]["mean_net_bps"] == report["train"]["mean_net_bps"]
    assert all(item["events"] == 1 for item in report["train_sensitivity"])


def test_manifest_requires_exact_market_and_direction(tmp_path: Path) -> None:
    manifest = tmp_path / "events.csv"
    manifest.write_text("event_id,release_timestamp,prediction_ticker,equity_ticker,yes_up_equity,release_direction\nfed,2026-01-01T14:00:00Z,KXFED,XLF,1,1\n")
    with pytest.raises(ValueError, match="exact KXFED"):
        load_events(manifest)


def test_manifest_rejects_duplicate_contract_equity_pair(tmp_path: Path) -> None:
    manifest = tmp_path / "events.csv"
    row = "fed,2026-01-01T14:00:00Z,KXFED-26JAN-T4.25,XLF,1,1\n"
    manifest.write_text(
        "event_id,release_timestamp,prediction_ticker,equity_ticker,yes_up_equity,release_direction\n"
        + row + row
    )
    with pytest.raises(ValueError, match="duplicate event/contract/equity"):
        load_events(manifest)
