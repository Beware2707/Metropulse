"""MetroPulse command-line entry points.

Commands:
    python -m metropulse.cli load-static <gtfs.zip>      validate + load into PostgreSQL
    python -m metropulse.cli validate-static <gtfs.zip>  validate only
    python -m metropulse.cli check-gtfs-update            check DMRC's static feed once, load if changed
                                                           (NOT read-only: a fresh DB's first run has no
                                                           prior ETag on record, so it always loads --
                                                           see check_gtfs_update()'s docstring)
    python -m metropulse.cli load-station-facilities <xlsx>  load curated station accessibility/parking
                                                           facilities from a Delhi Transport Stack xlsx
    python -m metropulse.cli load-last-mile <zip_path>    load curated shared-mobility (e-rickshaw)
                                                           last-mile routes from a Delhi Transport Stack
                                                           GTFS feed (shared_mobility_gtfs_v1.zip)
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

import contextlib
from typing import Any

from metropulse.application.commuter.analytics import purge_analytics
from metropulse.application.commuter.journey_share import (
    forget_expired_share_positions,
)
from metropulse.application.commuter.last_mile_loader import load_last_mile_routes
from metropulse.application.commuter.station_exit_loader import load_station_exits
from metropulse.application.commuter.rule_engine import CommuterRuleEngine
from metropulse.application.commuter.station_facility_loader import load_station_facilities
from metropulse.application.consumers import EtaWarmer, FeedAnalyticsRecorder
from metropulse.application.intelligence.llm_delay_refiner import (
    LlmDelayRefinementScheduler,
)
from metropulse.application.intelligence.delay_predictor import DelayPredictionService
from metropulse.application.intelligence.proactive_scheduler import (
    ProactiveCommuteSchedulerService,
)
from metropulse.application.gtfs_static_updater import GtfsStaticUpdateService
from metropulse.application.realtime_engine import RealtimeEngine, cleanup_history
from metropulse.application.schedule_position_source import ScheduleEstimatedPositionSource
from metropulse.infrastructure.claude.client import ClaudeClient
from metropulse.infrastructure.gemini.client import GeminiClient
from metropulse.infrastructure.gtfs_static.dmrc_client import DmrcStaticFeedClient
from metropulse.infrastructure.llm_fallback import MultiProviderLlmClient
from metropulse.infrastructure.openai.client import OpenAiClient
from metropulse.infrastructure.redis.stream_bus import RedisStreamConsumer
from metropulse.infrastructure.redis.vehicle_store import UPDATES_STREAM
from metropulse.tracing import configure_tracing
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.config import Settings, get_settings
from metropulse.domain.exceptions import FeedFetchError, GtfsValidationError
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


async def check_gtfs_update(settings: Settings) -> int:
    """Run one DMRC static feed check-and-maybe-load cycle immediately.

    Manual counterpart to the ``gtfs-static-update`` scheduled job (see
    ``run_worker``) -- useful for testing/operating the feature without
    waiting for ``gtfs_static_check_interval_seconds`` to elapse. Runs
    regardless of ``settings.gtfs_static_auto_update_enabled``, same as
    ``load-static``/``validate-static`` run regardless of any scheduler
    setting. Returns a process exit code.

    NOT a read-only check: change detection is a remote ETag compared
    against the last one this database has on record. The very first run
    against a fresh database has no prior ETag to compare against, so it
    is always treated as "changed" and performs a real transactional
    replace of the static schedule tables -- including superseding any
    manually-applied override (see data/raw_gtfs/OVERRIDE_NOTES.md) with
    whatever DMRC's live feed actually contains. Confirm you want that
    before running this against a database seeded from an overridden
    dataset for the first time.
    """
    resources = build_resources(settings)
    http = build_http_client(settings)
    try:
        service = GtfsStaticUpdateService(
            DmrcStaticFeedClient(
                http, settings.gtfs_static_url, max_attempts=settings.fetch_max_attempts
            ),
            GtfsStaticLoader(resources.session_factory),
            resources.session_factory,
        )
        try:
            result = await service.check_for_update()
        except FeedFetchError as exc:
            print(f"cannot fetch DMRC static feed: {exc}", file=sys.stderr)
            return 2
        if result is None:
            print("no update applied (feed unchanged, or new data failed validation -- see logs)")
            return 0
        print(result.summary())
        for warning in result.report.warnings:
            print(warning.render())
        return 0
    finally:
        await http.aclose()
        await resources.close()


async def load_station_facilities_cmd(settings: Settings, xlsx_path: Path) -> int:
    """Load curated station accessibility/parking facilities from an xlsx.

    Prints how many facilities were loaded, how many matched by name vs.
    nearest-coordinate fallback, and -- critically -- every xlsx row that
    matched neither, with its station_name/station_code, so an operator can
    see exactly what needs manual attention. This must never be swallowed
    or summarized away. Returns a process exit code.
    """
    resources = build_resources(settings)
    try:
        result = await load_station_facilities(resources.session_factory, xlsx_path)
        print(f"loaded {len(result.facilities)} station facilities")
        print(f"  matched by name: {result.name_matched}")
        print(f"  matched by coordinate: {result.coordinate_matched}")
        if result.unmatched:
            print(f"  unmatched: {len(result.unmatched)} row(s) need manual attention:")
            for row in result.unmatched:
                print(
                    f"    station_name={row.get('station_name')!r} "
                    f"station_code={row.get('station_code')!r}"
                )
        else:
            print("  unmatched: 0")
        return 0
    finally:
        await resources.close()


async def load_last_mile_cmd(settings: Settings, zip_path: Path) -> int:
    """Load curated shared-mobility (e-rickshaw) last-mile routes from a
    Delhi Transport Stack GTFS feed.

    Prints how many routes were loaded, how many hub stops matched by name
    vs. nearest-coordinate fallback, and -- critically -- every unmatched
    route's route_id/route_short_name/hub-stop-name, so an operator can see
    exactly what needs manual attention. This must never be swallowed or
    summarized away. Returns a process exit code.
    """
    resources = build_resources(settings)
    try:
        result = await load_last_mile_routes(resources.session_factory, zip_path)
        print(f"loaded {len(result.routes)} last-mile routes")
        print(f"  matched by name: {result.name_matched}")
        print(f"  matched by coordinate: {result.coordinate_matched}")
        if result.unmatched:
            print(f"  unmatched: {len(result.unmatched)} route(s) need manual attention:")
            for row in result.unmatched:
                print(
                    f"    route_id={row.get('route_id')!r} "
                    f"route_short_name={row.get('route_short_name')!r} "
                    f"hub_stop_name={row.get('hub_stop_name')!r}"
                )
        else:
            print("  unmatched: 0")
        return 0
    finally:
        await resources.close()


async def load_station_exits_cmd(settings: Settings, json_path: Path) -> int:
    """Load station exit gates + nearby landmarks from the OSM-derived artifact.

    Prints how many gates were loaded, how many matched a stop by name vs.
    nearest-coordinate fallback, and every unmatched gate's station name -- no
    silent drops. Returns a process exit code.
    """
    resources = build_resources(settings)
    try:
        result = await load_station_exits(resources.session_factory, json_path)
        stations = len({e.stop_id for e in result.exits})
        landmarks = sum(len(e.landmarks or []) for e in result.exits)
        print(f"loaded {len(result.exits)} exit gates across {stations} stations")
        print(f"  matched by name: {result.name_matched}")
        print(f"  matched by coordinate: {result.coordinate_matched}")
        print(f"  landmarks attached: {landmarks}")
        if result.unmatched:
            print(f"  unmatched: {len(result.unmatched)} gate(s) need manual attention:")
            for gate in result.unmatched:
                print(
                    f"    name={gate.get('name')!r} "
                    f"station_name={gate.get('station_name')!r}"
                )
        else:
            print("  unmatched: 0")
        return 0
    finally:
        await resources.close()


async def run_worker(settings: Settings) -> int:
    """Run the realtime polling worker until interrupted."""
    resources = build_resources(settings)
    http = build_http_client(settings)
    try:
        # gtfs_rt_enabled gates whether the configured URL is trusted as a
        # real, licensed metro vehicle feed. Off by default: the worker then
        # estimates positions from the static schedule instead of polling a
        # feed that (as configured today) is actually Delhi's bus GPS, not
        # metro trains -- see config.Settings.gtfs_rt_enabled.
        feed: GtfsRtClient | None = None
        position_source: ScheduleEstimatedPositionSource | None = None
        if settings.gtfs_rt_enabled:
            feed = GtfsRtClient(
                http,
                settings.gtfs_rt_vehicle_positions_url,
                settings.dmrc_api_key.get_secret_value(),
                max_attempts=settings.fetch_max_attempts,
            )
        else:
            position_source = ScheduleEstimatedPositionSource(
                resources.session_factory, resources.commuter.last_train, resources.resolver
            )

        # gtfs_static_auto_update_enabled gates the periodic DMRC static
        # feed check entirely -- off by default (see
        # config.Settings.gtfs_static_auto_update_enabled). None here means
        # the scheduler job below is simply never registered.
        gtfs_static_updater: GtfsStaticUpdateService | None = None
        if settings.gtfs_static_auto_update_enabled:
            gtfs_static_updater = GtfsStaticUpdateService(
                DmrcStaticFeedClient(
                    http, settings.gtfs_static_url, max_attempts=settings.fetch_max_attempts
                ),
                GtfsStaticLoader(resources.session_factory),
                resources.session_factory,
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
            delay_notify_seconds=settings.journey_delay_notify_seconds,
            event_publisher=resources.event_publisher,
        )

        proactive_scheduler = ProactiveCommuteSchedulerService(
            resources.commuter.commute_predictor,
            resources.commuter.notifications,
            resources.session_factory,
            lead_minutes=settings.proactive_commute_lead_minutes,
            min_confidence=settings.proactive_commute_min_confidence,
            timezone=settings.timezone,
            # Same window CommutePredictionService itself uses, so the two
            # can never drift apart from an independent config change.
            history_window_days=settings.commute_prediction_lookback_days,
        )

        # Each provider is only constructed when its key is configured; the
        # combined client tries whichever ones exist in priority order
        # (Claude, then OpenAI, then Gemini) and fails over on any single
        # provider's error. None (not a real client) whenever zero keys are
        # configured -- the scheduler's evaluate_safe() checks for exactly
        # this and no-ops, touching neither the network nor the database.
        anthropic_key = settings.anthropic_api_key.get_secret_value()
        openai_key = settings.openai_api_key.get_secret_value()
        google_key = settings.google_api_key.get_secret_value()
        providers: list[tuple[str, Any]] = []
        if anthropic_key:
            providers.append(
                ("claude", ClaudeClient(http, anthropic_key, model=settings.claude_model))
            )
        if openai_key:
            providers.append(
                ("openai", OpenAiClient(http, openai_key, model=settings.openai_model))
            )
        if google_key:
            providers.append(
                ("gemini", GeminiClient(http, google_key, model=settings.gemini_model))
            )
        llm_client = MultiProviderLlmClient(providers) if providers else None
        llm_delay_scheduler = LlmDelayRefinementScheduler(
            # Deliberately a *fresh*, unwrapped DelayPredictionService, not
            # resources.commuter.delay_predictor (which is already the
            # LLM-enhanced wrapper) -- the scheduler must always refine
            # the plain historical baseline, never an already-refined
            # estimate from a prior cycle, or refinements would compound.
            DelayPredictionService(
                resources.commuter.planner,
                lookback_days=settings.delay_prediction_lookback_days,
            ),
            llm_client,
            resources.session_factory,
            min_sample_size=settings.llm_delay_refinement_min_sample_size,
            max_buckets_per_cycle=settings.llm_delay_refinement_max_buckets_per_cycle,
            lookback_days=settings.delay_prediction_lookback_days,
        )

        engine = RealtimeEngine(
            feed,
            resources.vehicle_store,
            resources.session_factory,
            resources.train_service,
            stale_after_seconds=settings.stale_after_seconds,
            event_publisher=resources.event_publisher,
            position_source=position_source,
        )

        # Event-driven pipeline: the poller appends update events to a Redis
        # stream; independent consumer groups react to every event and survive
        # worker restarts (pending entries are redelivered).
        eta_warmer = EtaWarmer(
            resources.resolver, resources.eta_service, resources.event_publisher
        )
        analytics_recorder = FeedAnalyticsRecorder(resources.session_factory)

        async def _notify_handler(event: dict[str, Any]) -> None:
            if event.get("type") == "update":
                await rule_engine.evaluate_realtime_safe()

        consumers = [
            (
                RedisStreamConsumer(resources.redis, UPDATES_STREAM, "notify", "worker-notify"),
                _notify_handler,
            ),
            (
                RedisStreamConsumer(resources.redis, UPDATES_STREAM, "eta", "worker-eta"),
                eta_warmer.handle,
            ),
            (
                RedisStreamConsumer(
                    resources.redis, UPDATES_STREAM, "analytics", "worker-analytics"
                ),
                analytics_recorder.handle,
            ),
        ]
        consumer_tasks = [
            asyncio.create_task(consumer.run(handler), name=f"consumer-{consumer.group}")
            for consumer, handler in consumers
        ]

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
            proactive_scheduler.evaluate_safe,
            "interval",
            seconds=settings.proactive_commute_eval_interval_seconds,
            max_instances=1,
            coalesce=True,
            id="predicted-departure-notices",
        )
        scheduler.add_job(
            llm_delay_scheduler.evaluate_safe,
            "interval",
            seconds=settings.llm_delay_refinement_eval_interval_seconds,
            max_instances=1,
            coalesce=True,
            id="llm-delay-refinement",
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
        scheduler.add_job(
            forget_expired_share_positions,
            "interval",
            hours=1,
            args=[
                resources.session_factory,
                settings.share_position_retention_hours,
            ],
            id="share-position-retention",
        )
        if gtfs_static_updater is not None:
            scheduler.add_job(
                gtfs_static_updater.check_for_update_safe,
                "interval",
                seconds=settings.gtfs_static_check_interval_seconds,
                max_instances=1,
                coalesce=True,
                id="gtfs-static-update",
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
            for task in consumer_tasks:
                task.cancel()
            for task in consumer_tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
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

    sub.add_parser(
        "check-gtfs-update",
        help=(
            "check DMRC's static feed once and load it if changed -- NOT read-only: "
            "a database's first-ever run has no prior ETag to compare, so it always "
            "loads (see check_gtfs_update()'s docstring)"
        ),
    )

    load_facilities = sub.add_parser(
        "load-station-facilities",
        help="load curated station accessibility/parking facilities from an xlsx",
    )
    load_facilities.add_argument(
        "xlsx_path", type=Path, help="path to the station facilities xlsx"
    )

    load_last_mile = sub.add_parser(
        "load-last-mile",
        help="load curated shared-mobility (e-rickshaw) last-mile routes from a GTFS ZIP",
    )
    load_last_mile.add_argument(
        "zip_path", type=Path, help="path to the shared-mobility GTFS ZIP"
    )

    load_exits = sub.add_parser(
        "load-station-exits",
        help="load station exit gates + nearby landmarks from the OSM artifact",
    )
    load_exits.add_argument(
        "json_path", type=Path, nargs="?", default=Path("data/station_exits.json"),
        help="path to station_exits.json (default: data/station_exits.json)",
    )

    sub.add_parser("run-worker", help="run the realtime polling worker")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if args.command == "run-worker":
        configure_tracing("metropulse-worker")

    if args.command == "load-static":
        return asyncio.run(load_static(settings, args.zip_path))
    if args.command == "validate-static":
        return asyncio.run(validate_static(settings, args.zip_path))
    if args.command == "check-gtfs-update":
        return asyncio.run(check_gtfs_update(settings))
    if args.command == "load-station-facilities":
        return asyncio.run(load_station_facilities_cmd(settings, args.xlsx_path))
    if args.command == "load-last-mile":
        return asyncio.run(load_last_mile_cmd(settings, args.zip_path))
    if args.command == "load-station-exits":
        return asyncio.run(load_station_exits_cmd(settings, args.json_path))
    if args.command == "run-worker":
        try:
            return asyncio.run(run_worker(settings))
        except KeyboardInterrupt:
            logger.info("realtime worker interrupted")
            return 0
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
