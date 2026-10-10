"""Summarize timing and integrity of prospective market observation logs."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from research.event_study import parse_time


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_observations(
    path: Path,
    *,
    gap_seconds: float = 120,
    receipt_lag_seconds: float = 30,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    if gap_seconds <= 0 or receipt_lag_seconds < 0:
        raise ValueError("gap threshold must be positive and receipt lag cannot be negative")
    if (start and start.tzinfo is None) or (end and end.tzinfo is None):
        raise ValueError("audit bounds must include a timezone")
    if start and end and start >= end:
        raise ValueError("audit start must precede end")

    groups: dict[tuple[str, str], list[tuple[datetime, datetime, str | None]]] = defaultdict(list)
    malformed_rows = 0
    skipped_outside_window = 0
    with path.open() as file:
        for line in file:
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("observation must be an object")
                source = row["source"]
                ticker = row["ticker"]
                if not isinstance(source, str) or not source or not isinstance(ticker, str) or not ticker:
                    raise ValueError("source and ticker required")
                if not isinstance(row["observed_at"], str) or not isinstance(row["timestamp"], str):
                    raise ValueError("observation timestamps must be strings")
                receipt = parse_time(row["observed_at"])
                source_time = parse_time(row["timestamp"])
                observation_id = row.get("observation_id")
                if observation_id is not None and not isinstance(observation_id, str):
                    raise ValueError("invalid observation ID")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                malformed_rows += 1
                continue
            if (start and receipt < start) or (end and receipt >= end):
                skipped_outside_window += 1
                continue
            groups[(source, ticker)].append((receipt, source_time, observation_id))

    markets = []
    for (source, ticker), points in sorted(groups.items()):
        points.sort(key=lambda point: point[0])
        gaps = []
        late_deliveries = 0
        source_after_receipt = 0
        source_time_reversals = 0
        duplicate_ids = 0
        seen_ids: set[str] = set()
        max_interval = 0.0
        if start:
            leading = (points[0][0] - start).total_seconds()
            max_interval = max(max_interval, leading)
            if leading > gap_seconds:
                gaps.append({"kind": "leading", "from": start.isoformat(),
                             "to": points[0][0].isoformat(), "seconds": round(leading, 3)})
        for index, (receipt, source_time, observation_id) in enumerate(points):
            lag = (receipt - source_time).total_seconds()
            if lag > receipt_lag_seconds:
                late_deliveries += 1
            if lag < 0:
                source_after_receipt += 1
            if observation_id:
                if observation_id in seen_ids:
                    duplicate_ids += 1
                seen_ids.add(observation_id)
            if index:
                previous_receipt, previous_source, _ = points[index - 1]
                elapsed = (receipt - previous_receipt).total_seconds()
                max_interval = max(max_interval, elapsed)
                if elapsed > gap_seconds:
                    gaps.append({
                        "kind": "internal",
                        "from": previous_receipt.isoformat(),
                        "to": receipt.isoformat(),
                        "seconds": round(elapsed, 3),
                    })
                if source_time < previous_source:
                    source_time_reversals += 1
        if end:
            trailing = (end - points[-1][0]).total_seconds()
            max_interval = max(max_interval, trailing)
            if trailing > gap_seconds:
                gaps.append({"kind": "trailing", "from": points[-1][0].isoformat(),
                             "to": end.isoformat(), "seconds": round(trailing, 3)})
        issues = []
        if gaps:
            issues.append("receipt_gaps")
        if late_deliveries:
            issues.append("late_deliveries")
        if source_after_receipt:
            issues.append("source_after_receipt")
        if source_time_reversals:
            issues.append("source_time_reversals")
        if duplicate_ids:
            issues.append("duplicate_observation_ids")
        if len(points) < 2:
            issues.append("insufficient_observations")
        markets.append({
            "source": source,
            "ticker": ticker,
            "observations": len(points),
            "first_received_at": points[0][0].isoformat(),
            "last_received_at": points[-1][0].isoformat(),
            "gap_count": len(gaps),
            "max_observed_interval_seconds": round(max_interval, 3),
            "first_gaps": gaps[:10],
            "late_deliveries": late_deliveries,
            "source_after_receipt": source_after_receipt,
            "source_time_reversals": source_time_reversals,
            "duplicate_observation_ids": duplicate_ids,
            "issues": issues,
        })

    return {
        "schema_version": 1,
        "purpose": "observation timing audit, not a market uptime guarantee",
        "input_sha256": _file_hash(path),
        "assumptions": {
            "gap_seconds": gap_seconds,
            "receipt_lag_seconds": receipt_lag_seconds,
            "start_inclusive": start.isoformat() if start else None,
            "end_exclusive": end.isoformat() if end else None,
            "gap_basis": "time between received observations for each source and ticker",
        },
        "malformed_rows": malformed_rows,
        "skipped_outside_window": skipped_outside_window,
        "markets": markets,
        "needs_review": malformed_rows > 0 or not markets or any(
            market["issues"] for market in markets
        ),
    }
