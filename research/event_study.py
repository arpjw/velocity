from __future__ import annotations

import csv
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median


def parse_time(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value}")
    return timestamp.astimezone(timezone.utc)


@dataclass(frozen=True)
class EventSpec:
    event_id: str
    release_timestamp: datetime
    prediction_ticker: str
    equity_ticker: str
    yes_up_equity: int
    release_direction: int | None = None


@dataclass(frozen=True)
class Quote:
    timestamp: datetime
    ticker: str
    price: float
    volume: float


@dataclass(frozen=True)
class EquityBar:
    timestamp: datetime
    ticker: str
    open: float


def load_events(path: str | Path) -> list[EventSpec]:
    with Path(path).open(newline="") as file:
        rows = list(csv.DictReader(file))
    events: list[EventSpec] = []
    for row in rows:
        direction = int(row["yes_up_equity"])
        release = int(row["release_direction"]) if row.get("release_direction") else None
        if direction not in (-1, 1) or release not in (None, -1, 1):
            raise ValueError("directions must be +1 or -1")
        if not row["prediction_ticker"].startswith("KXFED-"):
            raise ValueError("this study requires an exact KXFED market ticker")
        events.append(EventSpec(
            event_id=row["event_id"],
            release_timestamp=parse_time(row["release_timestamp"]),
            prediction_ticker=row["prediction_ticker"],
            equity_ticker=row["equity_ticker"],
            yes_up_equity=direction,
            release_direction=release,
        ))
    return sorted(events, key=lambda event: (event.release_timestamp, event.event_id))


def load_quotes(path: str | Path) -> dict[str, list[Quote]]:
    by_ticker: dict[str, list[Quote]] = {}
    with Path(path).open(newline="") as file:
        for row in csv.DictReader(file):
            try:
                bid = float(row["yes_bid"])
                ask = float(row["yes_ask"])
                price = (bid + ask) / 2 if 0 < bid <= ask < 1 else float(row["price"])
            except (KeyError, TypeError, ValueError):
                price = float(row["price"])
            if not 0 <= price <= 1:
                raise ValueError("prediction quote outside [0, 1]")
            ticker = row["ticker"]
            by_ticker.setdefault(ticker, []).append(Quote(
                timestamp=parse_time(row["timestamp"]),
                ticker=ticker,
                price=price,
                volume=float(row["volume"]),
            ))
    for quotes in by_ticker.values():
        quotes.sort(key=lambda quote: quote.timestamp)
    return by_ticker


def load_equity_bars(path: str | Path) -> dict[str, list[EquityBar]]:
    by_ticker: dict[str, list[EquityBar]] = {}
    with Path(path).open(newline="") as file:
        for row in csv.DictReader(file):
            opening_price = float(row["open"])
            if not math.isfinite(opening_price) or opening_price <= 0:
                raise ValueError("equity open must be positive and finite")
            ticker = row["ticker"]
            by_ticker.setdefault(ticker, []).append(EquityBar(
                timestamp=parse_time(row["timestamp"]), ticker=ticker, open=opening_price
            ))
    for bars in by_ticker.values():
        bars.sort(key=lambda bar: bar.timestamp)
    return by_ticker


def first_signal(
    quotes: list[Quote],
    release: datetime,
    *,
    threshold: float,
    window_minutes: int,
    max_staleness_minutes: int = 10,
) -> tuple[Quote, float] | None:
    times = [quote.timestamp for quote in quotes]
    start = bisect_left(times, release)
    if start == 0:
        return None
    before = quotes[start - 1]
    if release - before.timestamp > timedelta(minutes=max_staleness_minutes):
        return None
    end = release + timedelta(minutes=window_minutes)
    for quote in quotes[start:]:
        if quote.timestamp > end:
            break
        change = quote.price - before.price
        if abs(change) >= threshold and quote.volume > before.volume:
            return quote, change
    return None


def next_open(bars: list[EquityBar], target: datetime, max_delay_minutes: int = 2) -> float | None:
    times = [bar.timestamp for bar in bars]
    index = bisect_left(times, target)
    if index >= len(bars) or bars[index].timestamp - target > timedelta(minutes=max_delay_minutes):
        return None
    return bars[index].open


def evaluate_event(
    event: EventSpec,
    quotes: list[Quote],
    bars: list[EquityBar],
    *,
    threshold: float,
    window_minutes: int,
    hold_minutes: int,
    latency_seconds: int,
    round_trip_cost_bps: float,
    placebo_offset_minutes: int = 60,
) -> dict:
    result: dict = {
        "event_id": event.event_id,
        "release_timestamp": event.release_timestamp.isoformat(),
        "prediction_ticker": event.prediction_ticker,
        "equity_ticker": event.equity_ticker,
        "status": "no_signal",
    }
    quote_times = [quote.timestamp for quote in quotes]
    release_start = bisect_left(quote_times, event.release_timestamp)
    if (
        release_start == 0
        or event.release_timestamp - quotes[release_start - 1].timestamp > timedelta(minutes=10)
    ):
        result["status"] = "missing_prediction_baseline"
        return result
    if (
        release_start >= len(quotes)
        or quotes[release_start].timestamp > event.release_timestamp + timedelta(minutes=window_minutes)
    ):
        result["status"] = "missing_prediction_window"
        return result
    placebo_release = event.release_timestamp - timedelta(minutes=placebo_offset_minutes)
    placebo_start = bisect_left(quote_times, placebo_release)
    placebo_eligible = (
        placebo_start > 0
        and placebo_release - quotes[placebo_start - 1].timestamp <= timedelta(minutes=10)
    )
    placebo = first_signal(
        quotes,
        placebo_release,
        threshold=threshold,
        window_minutes=window_minutes,
    )
    result["placebo_fired"] = placebo is not None if placebo_eligible else None
    signal = first_signal(
        quotes, event.release_timestamp, threshold=threshold, window_minutes=window_minutes
    )
    if signal is None:
        return result
    quote, probability_change = signal
    side = event.yes_up_equity * (1 if probability_change > 0 else -1)
    result.update({
        "signal_timestamp": quote.timestamp.isoformat(),
        "probability_change": round(probability_change, 6),
        "side": side,
        "status": "missing_equity_bars",
    })
    latency = timedelta(seconds=latency_seconds)
    entry = next_open(bars, quote.timestamp + latency)
    exit_price = next_open(bars, quote.timestamp + timedelta(minutes=hold_minutes) + latency)
    release_open = next_open(bars, event.release_timestamp + latency)
    if entry is None or exit_price is None or release_open is None:
        return result
    cost = round_trip_cost_bps / 10000
    result.update({
        "status": "priced",
        "signal_net_bps": round(((exit_price / entry - 1) * side - cost) * 10000, 4),
        "pre_signal_move_bps": round((entry / release_open - 1) * side * 10000, 4),
    })
    if event.release_direction is not None:
        result["release_baseline_net_bps"] = round(
            ((exit_price / release_open - 1) * event.release_direction - cost) * 10000, 4
        )
    return result


def _summary(rows: list[dict]) -> dict:
    priced = [row for row in rows if row["status"] == "priced"]
    returns = [row["signal_net_bps"] for row in priced]
    baseline = [row["release_baseline_net_bps"] for row in priced if "release_baseline_net_bps" in row]
    eligible_placebos = [row for row in rows if row.get("placebo_fired") is not None]
    return {
        "events": len(rows),
        "signals": sum("signal_timestamp" in row for row in rows),
        "priced": len(priced),
        "missing_prediction_data": sum(row["status"].startswith("missing_prediction") for row in rows),
        "missing_equity_bars": sum(row["status"] == "missing_equity_bars" for row in rows),
        "mean_net_bps": round(mean(returns), 4) if returns else None,
        "median_net_bps": round(median(returns), 4) if returns else None,
        "positive_rate": round(sum(value > 0 for value in returns) / len(returns), 4) if returns else None,
        "mean_pre_signal_move_bps": round(mean(row["pre_signal_move_bps"] for row in priced), 4) if priced else None,
        "release_baseline_count": len(baseline),
        "release_baseline_mean_bps": round(mean(baseline), 4) if baseline else None,
        "placebo_signals": sum(row["placebo_fired"] for row in eligible_placebos),
        "placebo_eligible": len(eligible_placebos),
    }


def run_study(
    events: list[EventSpec],
    quotes: dict[str, list[Quote]],
    equity_bars: dict[str, list[EquityBar]],
    *,
    threshold: float = 0.05,
    window_minutes: int = 15,
    hold_minutes: int = 120,
    latency_seconds: int = 60,
    round_trip_cost_bps: float = 30.0,
) -> dict:
    if not 0 < threshold <= 1 or min(window_minutes, hold_minutes) <= 0:
        raise ValueError("threshold and windows must be positive")
    if latency_seconds < 0 or round_trip_cost_bps < 0:
        raise ValueError("latency and costs cannot be negative")
    distinct_events = sorted({(event.release_timestamp, event.event_id) for event in events})
    split_index = max(1, int(len(distinct_events) * 0.7)) if distinct_events else 0
    train_keys = set(distinct_events[:split_index])
    results = []
    for event in events:
        row = evaluate_event(
            event,
            quotes.get(event.prediction_ticker, []),
            equity_bars.get(event.equity_ticker, []),
            threshold=threshold,
            window_minutes=window_minutes,
            hold_minutes=hold_minutes,
            latency_seconds=latency_seconds,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        row["split"] = "train" if (event.release_timestamp, event.event_id) in train_keys else "holdout"
        results.append(row)
    sensitivity = []
    train_events = [event for event in events if (event.release_timestamp, event.event_id) in train_keys]
    for trial_threshold in sorted({max(0.01, threshold * 0.6), threshold, min(1.0, threshold * 1.6)}):
        for trial_latency in sorted({0, latency_seconds, max(300, latency_seconds * 3)}):
            trial_rows = [
                evaluate_event(
                    event,
                    quotes.get(event.prediction_ticker, []),
                    equity_bars.get(event.equity_ticker, []),
                    threshold=trial_threshold,
                    window_minutes=window_minutes,
                    hold_minutes=hold_minutes,
                    latency_seconds=trial_latency,
                    round_trip_cost_bps=round_trip_cost_bps,
                )
                for event in train_events
            ]
            sensitivity.append({
                "threshold": round(trial_threshold, 6),
                "latency_seconds": trial_latency,
                **_summary(trial_rows),
            })
    return {
        "assumptions": {
            "threshold_probability_points": threshold,
            "signal_window_minutes": window_minutes,
            "hold_minutes": hold_minutes,
            "latency_seconds": latency_seconds,
            "round_trip_cost_bps": round_trip_cost_bps,
            "equity_price": "first bar open at or after target, at most two minutes late",
        },
        "train": _summary([row for row in results if row["split"] == "train"]),
        "holdout": _summary([row for row in results if row["split"] == "holdout"]),
        "train_sensitivity": sensitivity,
        "results": results,
    }
