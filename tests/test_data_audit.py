from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.data_audit import audit_dataset


RELEASE = datetime(2026, 1, 1, 14, tzinfo=timezone.utc)


def _write_dataset(tmp_path: Path) -> tuple[Path, Path, Path]:
    events = tmp_path / "events.csv"
    quotes = tmp_path / "kalshi.csv"
    equity = tmp_path / "equity.csv"
    events.write_text(
        "event_id,release_timestamp,prediction_ticker,equity_ticker,yes_up_equity,"
        "release_direction,release_source,contract_source,equity_source\n"
        "fed-1,2026-01-01T14:00:00Z,KXFED-26JAN-T4.25,XLF,1,1,"
        "public calendar,market rules,minute vendor export\n"
    )
    quotes.write_text(
        "timestamp,ticker,price,volume\n"
        "2026-01-01T13:59:00Z,KXFED-26JAN-T4.25,0.5,10\n"
        "2026-01-01T14:01:00Z,KXFED-26JAN-T4.25,0.6,12\n"
    )
    equity.write_text("timestamp,ticker,open\n" + "".join(
        f"{(RELEASE + timedelta(minutes=n)).isoformat()},XLF,100\n"
        for n in range(137)
    ))
    return events, quotes, equity


def test_complete_csv_dataset_is_ready_for_study(tmp_path: Path) -> None:
    report = audit_dataset(*_write_dataset(tmp_path))
    assert report["ready_for_study"] is True
    assert report["events"][0]["equity_missing_minutes"] == 0
    assert len(report["inputs"]["equity_sha256"]) == 64


def test_missing_provenance_and_minute_fail_audit(tmp_path: Path) -> None:
    events, quotes, equity = _write_dataset(tmp_path)
    events.write_text(events.read_text().replace("minute vendor export", " "))
    equity.write_text(equity.read_text().replace(
        "2026-01-01T14:02:00+00:00,XLF,100\n", ""
    ))
    report = audit_dataset(events, quotes, equity)
    assert report["ready_for_study"] is False
    assert report["events"][0]["issues"] == [
        "missing_equity_source", "missing_equity_minutes"
    ]


def test_duplicate_prediction_timestamp_fails_audit(tmp_path: Path) -> None:
    paths = _write_dataset(tmp_path)
    quotes = paths[1]
    quotes.write_text(quotes.read_text() +
                      "2026-01-01T14:01:00Z,KXFED-26JAN-T4.25,0.6,12\n")
    report = audit_dataset(*paths)
    assert "duplicate_prediction_timestamps" in report["global_issues"]
    assert report["ready_for_study"] is False
