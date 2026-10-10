#!/usr/bin/env python3
"""Check the most recent connector health snapshot from a running shadow collector."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def check_health(path: Path, max_age_seconds: float = 180) -> dict:
    if max_age_seconds <= 0:
        raise ValueError("max age must be positive")
    if not path.exists():
        return {"ok": False, "reason": "health log missing"}
    try:
        last = path.read_text().splitlines()[-1]
        snapshot = json.loads(last)
        observed_at = datetime.fromisoformat(snapshot["observed_at"])
        if observed_at.tzinfo is None:
            raise ValueError("timestamp lacks timezone")
        connectors = snapshot["connectors"]
        if not isinstance(connectors, dict):
            raise ValueError("connectors must be an object")
    except (IndexError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"ok": False, "reason": "invalid health snapshot"}
    age = (datetime.now(tz=timezone.utc) - observed_at).total_seconds()
    degraded = [slug for slug, report in connectors.items()
                if not isinstance(report, dict) or report.get("status") != "ok"]
    return {
        "ok": 0 <= age <= max_age_seconds and not degraded and bool(connectors),
        "age_seconds": round(age, 1),
        "degraded_connectors": degraded,
        "connector_count": len(connectors),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("logs/connector_health.jsonl"))
    parser.add_argument("--max-age-seconds", type=float, default=180)
    args = parser.parse_args()
    report = check_health(args.log, args.max_age_seconds)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
