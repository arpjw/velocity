import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.observation_audit import audit_observations


BASE = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)


def _record(minutes: int, source_minutes: int, observation_id: str) -> str:
    return json.dumps({
        "source": "kalshi", "ticker": "KXFED-26JAN-T4.25",
        "observed_at": (BASE + timedelta(minutes=minutes)).isoformat(),
        "timestamp": (BASE + timedelta(minutes=source_minutes)).isoformat(),
        "observation_id": observation_id,
    })


def test_audit_distinguishes_receipt_gaps_late_data_and_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "observations.jsonl"
    path.write_text("\n".join([
        _record(0, 0, "first"),
        _record(1, 0, "second"),
        _record(6, 6, "second"),
        "not json",
        json.dumps({"source": "kalshi", "ticker": "KXFED-26JAN-T4.25",
                    "observed_at": None, "timestamp": 123}),
    ]) + "\n")
    report = audit_observations(path, gap_seconds=120, receipt_lag_seconds=30)
    market = report["markets"][0]
    assert market["gap_count"] == 1
    assert market["max_observed_interval_seconds"] == 300
    assert market["first_gaps"][0]["seconds"] == 300
    assert market["late_deliveries"] == 1
    assert market["duplicate_observation_ids"] == 1
    assert report["malformed_rows"] == 2
    assert report["needs_review"] is True
    assert len(report["input_sha256"]) == 64


def test_audit_filters_by_receipt_window_and_detects_source_reversal(tmp_path: Path) -> None:
    path = tmp_path / "observations.jsonl"
    path.write_text("\n".join([
        _record(0, 0, "outside"),
        _record(1, 1, "first"),
        _record(2, 0, "second"),
    ]) + "\n")
    report = audit_observations(path, start=BASE + timedelta(minutes=1),
                                end=BASE + timedelta(minutes=3))
    market = report["markets"][0]
    assert report["skipped_outside_window"] == 1
    assert market["observations"] == 2
    assert market["source_time_reversals"] == 1


def test_clean_stream_does_not_need_review(tmp_path: Path) -> None:
    path = tmp_path / "observations.jsonl"
    path.write_text(_record(0, 0, "first") + "\n" + _record(1, 1, "second") + "\n")
    assert audit_observations(path)["needs_review"] is False


def test_bounded_window_reports_leading_and_trailing_gaps(tmp_path: Path) -> None:
    path = tmp_path / "observations.jsonl"
    path.write_text(_record(3, 3, "first") + "\n" + _record(4, 4, "second") + "\n")
    report = audit_observations(path, start=BASE, end=BASE + timedelta(minutes=8))
    assert [gap["kind"] for gap in report["markets"][0]["first_gaps"]] == [
        "leading", "trailing"
    ]
