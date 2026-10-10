from __future__ import annotations

import csv
import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

from signals.velocity import (
    VELOCITY_THRESHOLD,
    VELOCITY_WINDOW_MINUTES,
    PricePoint,
    VelocitySignal,
    VelocityTracker,
)


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
    bid: float | None = None
    ask: float | None = None


def load_events(path: str | Path) -> list[EventSpec]:
    with Path(path).open(newline="") as file:
        rows = list(csv.DictReader(file))
    events: list[EventSpec] = []
    seen: set[tuple[str, datetime, str, str]] = set()
    for row in rows:
        direction = int(row["yes_up_equity"])
        release = int(row["release_direction"]) if row.get("release_direction") else None
        if direction not in (-1, 1) or release not in (None, -1, 1):
            raise ValueError("directions must be +1 or -1")
        if not row["prediction_ticker"].startswith("KXFED-"):
            raise ValueError("this study requires an exact KXFED market ticker")
        event = EventSpec(
            event_id=row["event_id"],
            release_timestamp=parse_time(row["release_timestamp"]),
            prediction_ticker=row["prediction_ticker"],
            equity_ticker=row["equity_ticker"],
            yes_up_equity=direction,
            release_direction=release,
        )
        key = (event.event_id, event.release_timestamp,
               event.prediction_ticker, event.equity_ticker)
        if key in seen:
            raise ValueError(f"duplicate event/contract/equity row: {key}")
        seen.add(key)
        events.append(event)
    return sorted(events, key=lambda event: (event.release_timestamp, event.event_id))


def load_quotes(path: str | Path) -> dict[str, list[Quote]]:
    by_ticker: dict[str, list[Quote]] = {}
    with Path(path).open(newline="") as file:
        for row in csv.DictReader(file):
            price = float(row["price"])
            if not math.isfinite(price) or not 0 <= price <= 1:
                raise ValueError("prediction quote outside [0, 1]")
            volume = float(row["volume"])
            if not math.isfinite(volume) or volume < 0:
                raise ValueError("prediction volume must be finite and nonnegative")
            ticker = row["ticker"]
            by_ticker.setdefault(ticker, []).append(Quote(
                timestamp=parse_time(row["timestamp"]),
                ticker=ticker,
                price=price,
                volume=volume,
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
            bid = float(row["bid"]) if row.get("bid") else None
            ask = float(row["ask"]) if row.get("ask") else None
            if (bid is None) != (ask is None):
                raise ValueError("equity bid and ask must both be supplied")
            if bid is not None and (not math.isfinite(bid) or not math.isfinite(ask)
                                    or not 0 < bid <= ask):
                raise ValueError("equity bid/ask must be finite, positive, and ordered")
            ticker = row["ticker"]
            by_ticker.setdefault(ticker, []).append(EquityBar(
                timestamp=parse_time(row["timestamp"]), ticker=ticker, open=opening_price,
                bid=bid, ask=ask,
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
    velocity_window_minutes: int = VELOCITY_WINDOW_MINUTES,
    volume_multiplier: float = 2.0,
    max_staleness_minutes: int = 10,
) -> tuple[Quote, VelocitySignal] | None:
    times = [quote.timestamp for quote in quotes]
    start = bisect_left(times, release)
    if start == 0:
        return None
    before = quotes[start - 1]
    if release - before.timestamp > timedelta(minutes=max_staleness_minutes):
        return None
    tracker = VelocityTracker(
        window_minutes=velocity_window_minutes,
        threshold=threshold,
        volume_multiplier=volume_multiplier,
    )
    replay_start = bisect_left(times, release - timedelta(minutes=60))
    end = release + timedelta(minutes=window_minutes)
    for quote in quotes[replay_start:]:
        if quote.timestamp > end:
            break
        signal = tracker.update(
            quote.ticker,
            PricePoint(timestamp=quote.timestamp, price=quote.price, volume=quote.volume),
        )
        # A candle ending at the release time contains prerelease data.
        if quote.timestamp > release and signal is not None:
            return quote, signal
    return None


def next_bar(
    bars: list[EquityBar], target: datetime, max_delay_minutes: int = 2
) -> EquityBar | None:
    times = [bar.timestamp for bar in bars]
    index = bisect_left(times, target)
    if index >= len(bars) or bars[index].timestamp - target > timedelta(minutes=max_delay_minutes):
        return None
    return bars[index]


def next_open(bars: list[EquityBar], target: datetime, max_delay_minutes: int = 2) -> float | None:
    bar = next_bar(bars, target, max_delay_minutes)
    return bar.open if bar else None


def _execution_price(bar: EquityBar, side: int, *, opening: bool, price_model: str) -> float | None:
    if price_model == "bar_open":
        return bar.open
    if bar.bid is None or bar.ask is None:
        return None
    return bar.ask if (side == 1) == opening else bar.bid


def evaluate_event(
    event: EventSpec,
    quotes: list[Quote],
    bars: list[EquityBar],
    *,
    threshold: float,
    window_minutes: int,
    velocity_window_minutes: int = VELOCITY_WINDOW_MINUTES,
    volume_multiplier: float = 2.0,
    hold_minutes: int,
    latency_seconds: int,
    round_trip_cost_bps: float,
    price_model: str = "bar_open",
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
        velocity_window_minutes=velocity_window_minutes,
        volume_multiplier=volume_multiplier,
    )
    result["placebo_fired"] = placebo is not None if placebo_eligible else None
    signal = first_signal(
        quotes, event.release_timestamp, threshold=threshold,
        window_minutes=window_minutes,
        velocity_window_minutes=velocity_window_minutes,
        volume_multiplier=volume_multiplier,
    )
    if signal is None:
        return result
    quote, velocity_signal = signal
    side = event.yes_up_equity * (1 if velocity_signal.velocity > 0 else -1)
    result.update({
        "signal_timestamp": quote.timestamp.isoformat(),
        "probability_change_from_release_baseline": round(
            quote.price - quotes[release_start - 1].price, 6
        ),
        "velocity_per_minute": round(velocity_signal.velocity, 6),
        "side": side,
        "status": "missing_equity_bars",
    })
    latency = timedelta(seconds=latency_seconds)
    entry_bar = next_bar(bars, quote.timestamp + latency)
    exit_bar = next_bar(bars, quote.timestamp + timedelta(minutes=hold_minutes) + latency)
    release_bar = next_bar(bars, event.release_timestamp + latency)
    if entry_bar is None or exit_bar is None or release_bar is None:
        return result
    entry = _execution_price(entry_bar, side, opening=True, price_model=price_model)
    exit_price = _execution_price(exit_bar, side, opening=False, price_model=price_model)
    baseline_entry = (
        _execution_price(release_bar, event.release_direction, opening=True,
                         price_model=price_model)
        if event.release_direction is not None else None
    )
    baseline_exit = (
        _execution_price(exit_bar, event.release_direction, opening=False,
                         price_model=price_model)
        if event.release_direction is not None else None
    )
    if entry is None or exit_price is None or (
        event.release_direction is not None and (baseline_entry is None or baseline_exit is None)
    ):
        result["status"] = "missing_equity_quotes"
        return result
    cost = round_trip_cost_bps / 10000
    result.update({
        "status": "priced",
        "signal_net_bps": round(((exit_price / entry - 1) * side - cost) * 10000, 4),
        "pre_signal_move_bps": round((entry_bar.open / release_bar.open - 1) * side * 10000, 4),
        "entry_price": entry,
        "exit_price": exit_price,
    })
    if event.release_direction is not None:
        result["release_baseline_net_bps"] = round(
            ((baseline_exit / baseline_entry - 1) * event.release_direction - cost) * 10000, 4
        )
    return result


def _event_results(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["release_timestamp"], row["event_id"]), []).append(row)
    events = []
    for (release_timestamp, event_id), contracts in sorted(grouped.items()):
        priced = [row for row in contracts if row["status"] == "priced"]
        returns = [row["signal_net_bps"] for row in priced]
        baseline = [row["release_baseline_net_bps"] for row in priced
                    if "release_baseline_net_bps" in row]
        eligible_placebos = [row["placebo_fired"] for row in contracts
                             if row.get("placebo_fired") is not None]
        events.append({
            "event_id": event_id,
            "release_timestamp": release_timestamp,
            "split": contracts[0].get("split"),
            "contract_rows": len(contracts),
            "priced_contracts": len(priced),
            "signals": sum("signal_timestamp" in row for row in contracts),
            "mean_net_bps": round(mean(returns), 4) if returns else None,
            "mean_pre_signal_move_bps": round(
                mean(row["pre_signal_move_bps"] for row in priced), 4
            ) if priced else None,
            "release_baseline_mean_bps": round(mean(baseline), 4) if baseline else None,
            "placebo_fired": any(eligible_placebos) if eligible_placebos else None,
            "missing_prediction_contracts": sum(
                row["status"].startswith("missing_prediction") for row in contracts
            ),
            "missing_equity_contracts": sum(
                row["status"] in {"missing_equity_bars", "missing_equity_quotes"}
                for row in contracts
            ),
        })
    return events


def _event_summary(events: list[dict]) -> dict:
    priced = [event for event in events if event["mean_net_bps"] is not None]
    returns = [event["mean_net_bps"] for event in priced]
    baseline = [event["release_baseline_mean_bps"] for event in priced
                if event["release_baseline_mean_bps"] is not None]
    placebos = [event["placebo_fired"] for event in events
                if event["placebo_fired"] is not None]
    return {
        "events": len(events),
        "contract_rows": sum(event["contract_rows"] for event in events),
        "signals": sum(event["signals"] > 0 for event in events),
        "priced": len(priced),
        "priced_contracts": sum(event["priced_contracts"] for event in events),
        "missing_prediction_contracts": sum(event["missing_prediction_contracts"] for event in events),
        "missing_equity_contracts": sum(event["missing_equity_contracts"] for event in events),
        "mean_net_bps": round(mean(returns), 4) if returns else None,
        "median_net_bps": round(median(returns), 4) if returns else None,
        "positive_rate": round(sum(value > 0 for value in returns) / len(returns), 4) if returns else None,
        "mean_pre_signal_move_bps": round(
            mean(event["mean_pre_signal_move_bps"] for event in priced), 4
        ) if priced else None,
        "release_baseline_count": len(baseline),
        "release_baseline_mean_bps": round(mean(baseline), 4) if baseline else None,
        "placebo_signals": sum(placebos),
        "placebo_eligible": len(placebos),
    }


def run_study(
    events: list[EventSpec],
    quotes: dict[str, list[Quote]],
    equity_bars: dict[str, list[EquityBar]],
    *,
    threshold: float = VELOCITY_THRESHOLD,
    window_minutes: int = 15,
    velocity_window_minutes: int = VELOCITY_WINDOW_MINUTES,
    volume_multiplier: float = 2.0,
    hold_minutes: int = 120,
    latency_seconds: int = 60,
    round_trip_cost_bps: float = 30.0,
    price_model: str = "bar_open",
) -> dict:
    if not 0 < threshold <= 1 or min(window_minutes, velocity_window_minutes, hold_minutes) <= 0:
        raise ValueError("threshold and windows must be positive")
    if latency_seconds < 0 or round_trip_cost_bps < 0 or volume_multiplier < 0:
        raise ValueError("latency and costs cannot be negative")
    if price_model not in {"bar_open", "bid_ask"}:
        raise ValueError("price_model must be bar_open or bid_ask")
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
            velocity_window_minutes=velocity_window_minutes,
            volume_multiplier=volume_multiplier,
            hold_minutes=hold_minutes,
            latency_seconds=latency_seconds,
            round_trip_cost_bps=round_trip_cost_bps,
            price_model=price_model,
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
                    velocity_window_minutes=velocity_window_minutes,
                    volume_multiplier=volume_multiplier,
                    hold_minutes=hold_minutes,
                    latency_seconds=trial_latency,
                    round_trip_cost_bps=round_trip_cost_bps,
                    price_model=price_model,
                )
                for event in train_events
            ]
            sensitivity.append({
                "threshold": round(trial_threshold, 6),
                "latency_seconds": trial_latency,
                **_event_summary(_event_results(trial_rows)),
            })
    event_results = _event_results(results)
    train_event_results = [row for row in event_results if row["split"] == "train"]
    holdout_event_results = [row for row in event_results if row["split"] == "holdout"]
    return {
        "assumptions": {
            "velocity_threshold_per_minute": threshold,
            "signal_window_minutes": window_minutes,
            "velocity_window_minutes": velocity_window_minutes,
            "volume_multiplier": volume_multiplier,
            "hold_minutes": hold_minutes,
            "latency_seconds": latency_seconds,
            "round_trip_cost_bps": round_trip_cost_bps,
            "equity_price": "first bar at or after target, at most two minutes late",
            "price_model": price_model,
            "bid_ask_rule": "buy at ask, sell at bid" if price_model == "bid_ask" else None,
        },
        "train": _event_summary(train_event_results),
        "holdout": _event_summary(holdout_event_results),
        "event_results": event_results,
        "train_sensitivity": sensitivity,
        "results": results,
    }
