"""MetroPulse command-line entry points.

Commands:
    python -m metropulse.cli load-static <gtfs.zip>      validate + load into PostgreSQL
    python -m metropulse.cli validate-static <gtfs.zip>  validate only
    python -m metropulse.cli run-worker                  run the realtime polling worker
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import zipfile
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from metropulse.application.commuter.analytics import purge_analytics
from metropulse.application.commuter.rule_engine import CommuterRuleEngine
from metropulse.application.events import FEED_UPDATED, EventBus
from metropulse.application.realtime_engine import (
    PollResult,
    RealtimeEngine,
    cleanup_history,
)
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.config import Settings, get_settings
from metropulse.domain.exceptions import GtfsValidationError
from metropulse.infrastructure.gtfs_rt.client import GtfsRtClient
from metropulse.logging_config import configure_logging
from metropulse.wiring import build_http_client, build_resources

logger = logging.getLogger(__name__)


async def load_static(settings: Settings, zip_path: Path) -> int:
    """Validate and load a GTFS static ZIP; returns a process exit code."""
    resources = build_resources(settings)
    try:
        loader = GtfsStaticLoader(resources.session_factory)
        result = await loader.load(zip_path)
        print(result.summary())
        for warning in result.report.warnings:
            print(warning.render())
        return 0
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        print(f"cannot read GTFS archive {zip_path}: {exc}", file=sys.stderr)
        return 2
    except GtfsValidationError as exc:
        print("validation failed:", file=sys.stderr)
        for line in exc.errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    finally:
        await resources.close()


async def validate_static(settings: Settings, zip_path: Path) -> int:
    """Validate a GTFS static ZIP without loading; returns an exit code."""
    resources = build_resources(settings)
    try:
        try:
            report = await GtfsStaticLoader(resources.session_factory).validate_only(zip_path)
        except (FileNotFoundError, zipfile.BadZipFile) as exc:
            print(f"cannot read GTFS archive {zip_path}: {exc}", file=sys.stderr)
            return 2
        for issue in report.issues:
            print(issue.render())
        if report.has_errors:
            print(f"{len(report.errors)} error(s) found", file=sys.stderr)
            return 1
        print("dataset is valid" + (f" ({len(report.warnings)} warning(s))"
                                    if report.warnings else ""))
        return 0
    finally:
        await resources.close()


async def run_worker(settings: Settings) -> int:
    """Run the realtime polling worker until interrupted."""
    resources = build_resources(settings)
    http = build_http_client(settings)
    try:
        client = GtfsRtClient(
            http,
            settings.gtfs_rt_vehicle_positions_url,
            settings.dmrc_api_key,
            max_attempts=settings.fetch_max_attempts,
        )

        rule_engine = CommuterRuleEngine(
            resources.vehicle_store,
            resources.resolver,
            resources.eta_engine,
            resources.session_factory,
            resources.commuter.notifications,
            resources.commuter.last_train,
            resources.commuter.journeys,
            journey_max_age_hours=settings.journey_max_age_hours,
        )

        # Event-driven notifications: commuter rules run exactly when a feed
        # poll lands, not on an unrelated polling timer.
        event_bus = EventBus()

        async def _on_feed_updated(_result: PollResult) -> None:
            await rule_engine.evaluate_realtime_safe()

        event_bus.subscribe(FEED_UPDATED, _on_feed_updated)

        engine = RealtimeEngine(
            client,
            resources.vehicle_store,
            resources.session_factory,
            resources.train_service,
            stale_after_seconds=settings.stale_after_seconds,
            event_bus=event_bus,
        )

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            engine.poll_safe,
            "interval",
            seconds=settings.poll_interval_seconds,
            max_instances=1,
            coalesce=True,
            id="realtime-poll",
        )
        scheduler.add_job(
            rule_engine.evaluate_reminders_safe,
            "interval",
            seconds=settings.reminder_eval_interval_seconds,
            max_instances=1,
            coalesce=True,
            id="last-train-reminders",
        )
        scheduler.add_job(
            cleanup_history,
            "interval",
            hours=1,
            args=[resources.session_factory, settings.history_retention_hours],
            id="history-retention",
        )
        scheduler.add_job(
            purge_analytics,
            "interval",
            hours=24,
            args=[resources.session_factory, settings.analytics_retention_days],
            id="analytics-retention",
        )
        scheduler.start()
        logger.info(
            "realtime worker started: polling every %.1fs, staleness threshold %.0fs",
            settings.poll_interval_seconds,
            settings.stale_after_seconds,
        )

        stop = asyncio.Event()
        _install_signal_handlers(stop)
        await engine.poll_safe()  # prime the snapshot immediately
        try:
            await stop.wait()
        finally:
            scheduler.shutdown(wait=False)
        logger.info("realtime worker stopped")
        return 0
    finally:
        await http.aclose()
        await resources.close()


def _install_signal_handlers(stop: asyncio.Event) -> None:
    """Trigger a clean shutdown on SIGINT/SIGTERM.

    Windows event loops don't support add_signal_handler; there Ctrl+C
    surfaces as KeyboardInterrupt from asyncio.run, which is also fine.
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            break


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="metropulse", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    load = sub.add_parser("load-static", help="validate and load a GTFS static ZIP")
    load.add_argument("zip_path", type=Path, help="path to the GTFS static ZIP")

    validate = sub.add_parser("validate-static", help="validate a GTFS static ZIP")
    validate.add_argument("zip_path", type=Path, help="path to the GTFS static ZIP")

    sub.add_parser("run-worker", help="run the realtime polling worker")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)

    if args.command == "load-static":
        return asyncio.run(load_static(settings, args.zip_path))
    if args.command == "validate-static":
        return asyncio.run(validate_static(settings, args.zip_path))
    if args.command == "run-worker":
        try:
            return asyncio.run(run_worker(settings))
        except KeyboardInterrupt:
            logger.info("realtime worker interrupted")
            return 0
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
