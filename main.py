import argparse
import asyncio
import collections
import json
import logging
import os
import signal
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv

load_dotenv()

from connectors.base import PrismConnector, PrismRegistry
from execution.exit_manager import ExitManager, TrackedPosition, yfinance_price_fetcher
from execution.exposure_manager import ExposureManager
from execution.mcp_client import make_client
from execution.sizer import size_basket
from signals.contract_mapper import ContractMapper
from signals.deduplicator import SignalDeduplicator
from signals.gatekeeper import SignalGatekeeper
from signals.market_hours import MarketHoursGuard
from signals.velocity import VelocitySignal, VelocityTracker
from research.observation_log import append_shadow_signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_signal_count = 0
_order_count = 0
_tasks: list[asyncio.Task] = []
_off_hours_queue: list[VelocitySignal] = []


class SessionMemory:
    def __init__(self, max_entries: int = 50) -> None:
        self._max = max_entries
        self.signals_fired: int = 0
        self.signals_suppressed: int = 0
        self.signals_approved: int = 0
        self._log_path = Path(os.getenv("SESSION_STATE_LOG_PATH", "logs/session_state.jsonl"))
        self._order_log = Path(os.getenv("ORDER_LOG_PATH", "logs/orders.jsonl"))

    def record_fired(self) -> None:
        self.signals_fired += 1

    def record_suppressed(self) -> None:
        self.signals_suppressed += 1

    def record_approved(self) -> None:
        self.signals_approved += 1

    def _load_recent_pnl(self) -> list[dict]:
        if not self._order_log.exists():
            return []
        try:
            lines = self._order_log.read_text().splitlines()
            recent = []
            for line in lines[-self._max:]:
                try:
                    r = json.loads(line)
                    if r.get("pnl_usd") is not None:
                        recent.append({
                            "order_id": r.get("id"),
                            "ticker": r.get("ticker"),
                            "pnl_usd": r.get("pnl_usd"),
                        })
                except (json.JSONDecodeError, KeyError):
                    pass
            return recent
        except OSError:
            return []

    def snapshot(self, client) -> dict:
        try:
            positions = client.get_positions()
            open_count = len(positions)
        except Exception:
            open_count = 0
        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "signals_fired": self.signals_fired,
            "signals_suppressed": self.signals_suppressed,
            "signals_approved": self.signals_approved,
            "open_positions": open_count,
            "recent_pnl": self._load_recent_pnl(),
        }

    def write_snapshot(self, client) -> None:
        if os.getenv("SESSION_MEMORY_ENABLED", "true").lower() in ("0", "false", "no"):
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        snap = self.snapshot(client)
        with self._log_path.open("a") as f:
            f.write(json.dumps(snap) + "\n")


def determine_side(velocity: float, direction: str) -> str:
    return "buy" if (velocity > 0) == (direction == "up") else "sell"


async def _submit_signal(
    signal: VelocitySignal,
    mapper: ContractMapper,
    client,
    exit_manager: ExitManager,
    deduplicator: SignalDeduplicator,
    exposure_manager: ExposureManager,
    size_multiplier: float = 1.0,
    gatekeeper: SignalGatekeeper | None = None,
    session_memory: SessionMemory | None = None,
) -> None:
    global _signal_count, _order_count

    if not deduplicator.should_fire(signal):
        logger.info("dedup: suppressing duplicate signal for %s", signal.contract_slug)
        if session_memory:
            session_memory.record_suppressed()
        return

    _signal_count += 1
    basket = mapper.get_execution_basket(signal.contract_slug)
    if basket is None:
        logger.info("no outcome-specific execution basket for %s", signal.contract_slug)
        return

    if gatekeeper is not None:
        dedup_window = int(os.getenv("DEDUP_WINDOW_MINUTES", "30"))
        signal = await gatekeeper.evaluate(
            signal,
            source=signal.source,
            basket=basket,
            dedup_window_minutes=dedup_window,
        )
        if signal is None:
            if session_memory:
                session_memory.record_suppressed()
            return
        if session_memory:
            session_memory.record_approved()

        if os.getenv("GATEKEEPER_SCALE_POSITION", "false").lower() not in ("0", "false", "no"):
            gc = getattr(signal, "gatekeeper_confidence", None)
            if gc is not None:
                size_multiplier = size_multiplier * float(gc)

    side = determine_side(signal.velocity, basket["direction"])
    if side != "buy":
        logger.info("sell entry skipped for %s: short execution is not implemented", signal.contract_slug)
        return
    sizes = size_basket(basket, velocity=signal.velocity)
    if size_multiplier != 1.0:
        sizes = {t: round(s * size_multiplier, 2) for t, s in sizes.items()}

    entry_prices = await asyncio.to_thread(yfinance_price_fetcher, list(sizes))
    sizes = {
        ticker: size for ticker, size in sizes.items()
        if entry_prices.get(ticker, 0) > 0 and size > 0
    }
    if not sizes:
        logger.warning("no valid equity entry prices for %s", signal.contract_slug)
        return

    total_size = sum(sizes.values())
    can_open, reason = exposure_manager.can_open(signal.contract_slug, total_size)
    if not can_open:
        logger.warning(
            "EXPOSURE LIMIT slug=%s reason=%s", signal.contract_slug, reason
        )
        return

    strategy_id = f"velocity:{signal.contract_slug}:{signal.timestamp.strftime('%Y%m%dT%H%M%S')}"

    logger.info(
        "SIGNAL slug=%s velocity=%.4f price=%.3f side=%s strategy=%s",
        signal.contract_slug,
        signal.velocity,
        signal.price,
        side,
        strategy_id,
    )

    for ticker, dollar_size in sizes.items():
        try:
            order = client.submit_order(ticker, side, dollar_size, strategy_id)
        except Exception as exc:
            logger.error("order submission failed for %s: %s", ticker, exc)
            continue
        if order.get("status") != "filled":
            logger.warning("order is not filled for %s; exposure not registered", ticker)
            continue
        _order_count += 1
        exposure_manager.register_open(signal.contract_slug, ticker, dollar_size)
        exit_manager.register(
            TrackedPosition(
                order_id=order["id"],
                ticker=ticker,
                side=side,
                size=dollar_size,
                entry_time=signal.timestamp,
                strategy_id=strategy_id,
                direction=basket["direction"],
                contract_slug=signal.contract_slug,
                entry_velocity=signal.velocity,
                exit_hours=float(basket.get("exit_hours", 2.0)),
                exit_adverse_pct=float(basket.get("exit_adverse_pct", 0.03)),
                entry_price=entry_prices[ticker],
            )
        )


async def handle_signal(
    signal: VelocitySignal,
    mapper: ContractMapper,
    client,
    exit_manager: ExitManager,
    deduplicator: SignalDeduplicator,
    exposure_manager: ExposureManager,
    hours_guard: MarketHoursGuard,
    gatekeeper: SignalGatekeeper | None = None,
    session_memory: SessionMemory | None = None,
) -> None:
    global _signal_count
    if os.getenv("EXECUTION_MODE", "shadow") == "shadow":
        basket = mapper.get_basket(signal.contract_slug)
        recorded = append_shadow_signal({
            "observed_at": datetime.now(tz=timezone.utc).isoformat(),
            "timestamp": signal.timestamp.isoformat(),
            "source": signal.source,
            "contract_slug": signal.contract_slug,
            "price": signal.price,
            "velocity": signal.velocity,
            "volume_delta": signal.volume_delta,
            "equity_market_open": hours_guard.is_open(),
            "hypothesis_basket": basket.get("basket", []) if basket else [],
        }, window_minutes=int(os.getenv("SHADOW_DEDUP_WINDOW_MINUTES", "30")))
        if not recorded:
            if session_memory:
                session_memory.record_suppressed()
            return
        _signal_count += 1
        if session_memory:
            session_memory.record_fired()
        if session_memory:
            session_memory.write_snapshot(client)
        return

    if session_memory:
        session_memory.record_fired()

    if not hours_guard.is_open():
        mode = os.getenv("OFF_HOURS_MODE", "suppress")
        mins = hours_guard.minutes_to_open()
        if mode == "queue":
            _off_hours_queue.append(signal)
            logger.info(
                "queued off-hours signal slug=%s velocity=%.4f mins_to_open=%s",
                signal.contract_slug,
                signal.velocity,
                f"{mins:.1f}" if mins is not None else "unknown",
            )
        else:
            logger.info(
                "suppressed off-hours signal slug=%s velocity=%.4f mins_to_open=%s",
                signal.contract_slug,
                signal.velocity,
                f"{mins:.1f}" if mins is not None else "unknown",
            )
        if session_memory:
            session_memory.write_snapshot(client)
        return

    await _submit_signal(
        signal, mapper, client, exit_manager, deduplicator, exposure_manager,
        gatekeeper=gatekeeper,
        session_memory=session_memory,
    )
    if session_memory:
        session_memory.write_snapshot(client)


async def _queue_replay_worker(
    hours_guard: MarketHoursGuard,
    mapper: ContractMapper,
    client,
    exit_manager: ExitManager,
    deduplicator: SignalDeduplicator,
    exposure_manager: ExposureManager,
    gatekeeper: SignalGatekeeper | None = None,
    session_memory: SessionMemory | None = None,
) -> None:
    was_open = hours_guard.is_open()
    while True:
        await asyncio.sleep(30)
        is_open = hours_guard.is_open()
        if is_open and not was_open and _off_hours_queue:
            queued = list(_off_hours_queue)
            _off_hours_queue.clear()
            logger.info("market opened — replaying %d queued signals", len(queued))
            for sig in queued:
                decay = hours_guard.edge_decay_factor(sig.timestamp)
                if decay == 0.0:
                    logger.warning(
                        "queue replay: dropped stale signal slug=%s (edge decay=0.0)",
                        sig.contract_slug,
                    )
                    continue
                await _submit_signal(
                    sig, mapper, client, exit_manager, deduplicator, exposure_manager,
                    size_multiplier=decay,
                    gatekeeper=gatekeeper,
                    session_memory=session_memory,
                )
        was_open = is_open


async def _supervise_connector(
    connector: PrismConnector,
    tracker: VelocityTracker,
    mapper: ContractMapper,
    handle: Callable[[VelocitySignal], Awaitable[None]],
    retrying: dict[str, dict],
    *,
    restart_seconds: float = 5,
) -> None:
    if restart_seconds <= 0:
        raise ValueError("connector restart delay must be positive")
    slug = connector.metadata.slug
    failures = 0
    while True:
        try:
            retrying.pop(slug, None)
            await connector.start(tracker, mapper, handle)
            return  # Some optional connectors intentionally return when unconfigured.
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            delay = min(restart_seconds * 2 ** min(failures - 1, 6), 300)
            retrying[slug] = {
                "status": "degraded",
                "message": f"connector failed; retrying in {delay:g}s",
                "failure_type": type(exc).__name__,
                "failure_count": failures,
            }
            logger.error("connector %s failed (%s); retrying in %ss", slug,
                         type(exc).__name__, delay)
            await asyncio.sleep(delay)


async def _connector_health_worker(
    registry: PrismRegistry,
    interval_seconds: float,
    retrying: dict[str, dict] | None = None,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("connector health interval must be positive")
    path = Path(os.getenv("CONNECTOR_HEALTH_LOG_PATH", "logs/connector_health.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        health = registry.get_health_report()
        if retrying:
            for slug, state in retrying.items():
                health[slug] = {**health.get(slug, {}), **state}
        snapshot = {"observed_at": datetime.now(tz=timezone.utc).isoformat(),
                    "connectors": health}
        with path.open("a") as file:
            file.write(json.dumps(snapshot) + "\n")
        for slug, report in health.items():
            if report.get("status") != "ok":
                logger.warning("connector %s status=%s: %s", slug, report.get("status"),
                               report.get("message"))
        await asyncio.sleep(interval_seconds)


def _print_startup_banner(
    dry_run: bool,
    mode: str,
    hours_guard: MarketHoursGuard,
    exposure_manager: ExposureManager,
    registry: PrismRegistry,
) -> None:
    mapper_path = "data/contract_equity_map.json"
    try:
        contract_count = len(json.loads(Path(mapper_path).read_text()))
    except Exception:
        contract_count = 0

    is_open = hours_guard.is_open()
    market_status = "OPEN" if is_open else "CLOSED"
    if not is_open:
        mins = hours_guard.minutes_to_open()
        if mins is not None:
            market_status += f" (opens in {mins:.0f}m)"

    connectors = registry.get_all()

    banner = "DRY RUN MODE — shadow signals only" if dry_run else ""
    print("=" * 60)
    if banner:
        print(f"  *** {banner} ***")
    print(f"  execution mode      : {mode}")
    print(f"  portfolio value     : ${os.getenv('PORTFOLIO_VALUE', '10000')}")
    print(f"  max position pct    : {os.getenv('MAX_POSITION_PCT', '0.05')}")
    print(f"  velocity threshold  : {os.getenv('VELOCITY_THRESHOLD', '0.15')}")
    print(f"  velocity window     : {os.getenv('VELOCITY_WINDOW_MINUTES', '5')}m")
    print(f"  contracts tracked   : {contract_count}")
    print(f"  market hours status : {market_status}")
    print(f"  off hours mode      : {os.getenv('OFF_HOURS_MODE', 'suppress')}")
    print(f"  max factor exposure : {os.getenv('MAX_FACTOR_EXPOSURE_PCT', '0.15')}")
    print(f"  max total exposure  : {os.getenv('MAX_TOTAL_EXPOSURE_PCT', '0.40')}")
    print(f"  prism connectors    : {len(connectors)}")
    for c in connectors:
        print(f"    - {c.metadata.name} ({c.metadata.slug})")
    print("=" * 60)


async def main() -> None:
    global _tasks

    parser = argparse.ArgumentParser(description="Robinhood velocity signal engine")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run signal collection without orders regardless of EXECUTION_MODE",
    )
    args = parser.parse_args()

    if args.dry_run:
        os.environ["EXECUTION_MODE"] = "shadow"

    mode = os.getenv("EXECUTION_MODE", "shadow")

    mapper = ContractMapper()
    client = make_client()
    deduplicator = SignalDeduplicator()
    exposure_manager = ExposureManager()
    hours_guard = MarketHoursGuard()
    gatekeeper = SignalGatekeeper()
    session_memory = SessionMemory()
    exit_check_interval = float(os.getenv("EXIT_CHECK_INTERVAL_SECONDS", "60"))

    tracker = VelocityTracker()
    exit_manager = ExitManager(
        client=client,
        price_fetcher=yfinance_price_fetcher,
        check_interval_seconds=exit_check_interval,
        velocity_tracker=tracker,
        exposure_manager=exposure_manager,
    )

    registry = PrismRegistry()
    n = registry.load_directory(Path("connectors"))
    custom_path = Path("connectors/custom")
    if custom_path.exists():
        n += registry.load_directory(custom_path)
    if n == 0:
        logger.warning(
            "no prism connectors loaded — check auth env vars and connectors/ directory"
        )

    _print_startup_banner(args.dry_run, mode, hours_guard, exposure_manager, registry)

    async def _on_signal(sig: VelocitySignal) -> None:
        await handle_signal(
            sig, mapper, client, exit_manager, deduplicator, exposure_manager, hours_guard,
            gatekeeper=gatekeeper,
            session_memory=session_memory,
        )

    retrying: dict[str, dict] = {}
    restart_seconds = float(os.getenv("CONNECTOR_RESTART_SECONDS", "5"))
    if restart_seconds <= 0:
        raise ValueError("CONNECTOR_RESTART_SECONDS must be positive")
    coroutines: list = [exit_manager.run(), _connector_health_worker(
        registry, float(os.getenv("CONNECTOR_HEALTH_INTERVAL_SECONDS", "60")), retrying
    )]

    for connector in registry.get_all():
        async def on_connector_signal(sig: VelocitySignal, source: str = connector.metadata.slug) -> None:
            sig.source = source
            await _on_signal(sig)

        coroutines.append(_supervise_connector(
            connector, tracker, mapper, on_connector_signal, retrying,
            restart_seconds=restart_seconds,
        ))

    if os.getenv("OFF_HOURS_MODE", "suppress") == "queue":
        coroutines.append(
            _queue_replay_worker(
                hours_guard, mapper, client, exit_manager, deduplicator, exposure_manager,
                gatekeeper=gatekeeper,
                session_memory=session_memory,
            )
        )

    loop = asyncio.get_running_loop()

    def _shutdown(signum, frame):
        logger.info("shutdown signal received (%s)", signum)
        for task in _tasks:
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: _shutdown(s, None))

    _tasks = [asyncio.create_task(c) for c in coroutines]
    try:
        await asyncio.gather(*_tasks)
    except asyncio.CancelledError:
        pass
    finally:
        for connector in registry.get_all():
            await connector.stop()

        if mode == "live":
            try:
                client.cancel_all("*")
            except Exception as exc:
                logger.warning("cancel_all on shutdown failed: %s", exc)

        positions = client.get_positions()
        factor_exposure = exposure_manager.get_factor_exposure()
        print("\n=== Shutdown Summary ===")
        print(f"  signals fired  : {_signal_count}")
        print(f"  orders placed  : {_order_count}")
        print(f"  open positions : {len(positions)}")
        if factor_exposure:
            print("  factor exposure:")
            for factor, pct in sorted(factor_exposure.items()):
                print(f"    {factor}: {pct*100:.1f}%")
        print("========================")


def _log_error(exc: BaseException) -> None:
    error_log = Path("logs/errors.jsonl")
    error_log.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    with error_log.open("a") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        _log_error(exc)
        logger.error("unexpected error: %s", exc, exc_info=True)
        sys.exit(1)
