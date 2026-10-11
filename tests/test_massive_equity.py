from datetime import date

import httpx
import pytest

from scripts.fetch_massive_equity import fetch_bars, normalize_bars


def test_fetch_uses_header_auth_and_unadjusted_minute_bars() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.params["adjusted"] == "false"
        assert "/TLT/range/1/minute/2026-09-16/2026-09-16" in request.url.path
        return httpx.Response(200, json={
            "status": "OK", "ticker": "TLT", "adjusted": False,
            "results": [{"t": 1789581600000, "o": 90.25}],
        })

    with httpx.Client(
        transport=httpx.MockTransport(respond),
        headers={"Authorization": "Bearer test-key"},
    ) as client:
        payload, url = fetch_bars(client, "TLT", date(2026, 9, 16))

    assert "test-key" not in url
    assert normalize_bars(payload, "TLT") == [
        {"timestamp": "2026-09-16T18:00:00+00:00", "ticker": "TLT", "open": 90.25}
    ]


def test_incomplete_or_adjusted_vendor_data_is_rejected() -> None:
    payload = {
        "status": "OK", "ticker": "TLT", "adjusted": False,
        "results": [{"t": 1789581600000, "o": 90.25}],
    }
    with pytest.raises(ValueError, match="adjustment"):
        normalize_bars({**payload, "adjusted": True}, "TLT")
    with pytest.raises(ValueError, match="incomplete"):
        normalize_bars({**payload, "next_url": "https://api.massive.com/next"}, "TLT")
