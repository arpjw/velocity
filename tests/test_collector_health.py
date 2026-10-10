import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from main import _connector_health_worker
from scripts.check_collector_health import check_health


@pytest.mark.asyncio
async def test_health_worker_writes_snapshot_and_check_reads_it(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "health.jsonl"
    monkeypatch.setenv("CONNECTOR_HEALTH_LOG_PATH", str(path))
    registry = MagicMock()
    registry.get_health_report.return_value = {
        "kalshi_fed": {"status": "ok", "last_update": "now"}
    }
    task = asyncio.create_task(_connector_health_worker(registry, 60))
    try:
        for _ in range(20):
            if path.exists() and path.stat().st_size:
                break
            await asyncio.sleep(0.01)
        assert check_health(path)["ok"] is True
        assert "kalshi_fed" in json.loads(path.read_text())["connectors"]
        stale = json.loads(path.read_text())
        stale["observed_at"] = (datetime.now(tz=timezone.utc) - timedelta(minutes=10)).isoformat()
        path.write_text(json.dumps(stale) + "\n")
        assert check_health(path)["ok"] is False
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_missing_health_log_is_unhealthy(tmp_path: Path) -> None:
    assert check_health(tmp_path / "absent.jsonl") == {
        "ok": False, "reason": "health log missing"
    }
