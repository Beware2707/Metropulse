"""Composition root: builds the object graph from Settings.

Both entry points (API app and realtime worker) assemble their dependencies
here so tests can substitute an entire pre-built :class:`AppResources` with
in-memory fakes without monkeypatching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from metropulse.application.commuter.alerts import (
    DestinationAlertService,
    RiderReportService,
    ServiceAlertService,
)
from metropulse.application.commuter.journey_share import JourneyShareService
from metropulse.application.commuter.analytics import AnalyticsService
from metropulse.application.commuter.coach import (
    CoachRecommendationService,
    HistoricalCrowdPredictor,
)
from metropulse.application.commuter.commute_card import CommuteCardService
from metropulse.application.commuter.exits import ExitService
from metropulse.application.commuter.favourites import FavouritesService
from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.crowd_forecast import CrowdForecastService
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.notifications import (
    LoggingNotificationChannel,
    NotificationService,
)
from metropulse.application.commuter.offline import OfflineBundleService
from metropulse.application.commuter.users import UserService
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.eta_service import CachedEtaService
from metropulse.application.intelligence.llm_delay_refiner import (
    LlmEnhancedDelayEstimator,
)
from metropulse.application.intelligence.commute_impact import CommuteImpactService
from metropulse.application.intelligence.commute_predictor import (
    CommutePredictionService,
)
from metropulse.application.intelligence.delay_predictor import DelayPredictionService
from metropulse.application.intelligence.smart_recommendations import (
    SmartRecommendationService,
)
from metropulse.application.intelligence.place_roles import PlaceRoleInferenceService
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.application.live_hub import ConnectionManager, LiveHub, ReplayBuffer
from metropulse.application.ports import CommutePredictor, DelayEstimator, RecommendationEngine
from metropulse.application.route_resolver import IdMapper, MappingRule, RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.config import Settings
from metropulse.infrastructure.db.base import (
    SessionFactory,
    create_engine,
    create_session_factory,
)
from metropulse.infrastructure.redis.eta_cache import RedisEtaCache
from metropulse.infrastructure.redis.event_publisher import RedisDomainEventPublisher
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


@dataclass
class CommuterServices:
    """The commuter feature service bundle, built once per process."""

    users: UserService
    favourites: FavouritesService
    notifications: NotificationService
    destination_alerts: DestinationAlertService
    service_alerts: ServiceAlertService
    last_train: LastTrainService
    journeys: JourneyService
    coach: CoachRecommendationService
    exits: ExitService
    offline: OfflineBundleService
    analytics: AnalyticsService
    planner: JourneyPlanner
    commute_card: CommuteCardService
    commute_predictor: CommutePredictor
    delay_predictor: DelayEstimator
    smart_recommendations: RecommendationEngine
    place_roles: PlaceRoleInferenceService
    commute_impact: CommuteImpactService
    journey_share: JourneyShareService
    rider_reports: RiderReportService
    crowd_forecast: CrowdForecastService


@dataclass
class AppResources:
    """Everything a MetroPulse process needs, built once at startup."""

    settings: Settings
    engine: AsyncEngine | None
    session_factory: SessionFactory
    redis: Redis
    vehicle_store: RedisVehicleStore
    resolver: RouteResolver
    train_service: TrainService
    eta_engine: EtaEngine
    eta_service: CachedEtaService
    live_hub: LiveHub
    commuter: CommuterServices
    event_publisher: RedisDomainEventPublisher | None = None
    owns_connections: bool = True

    async def close(self) -> None:
        """Dispose owned connections (no-op for injected test resources)."""
        if not self.owns_connections:
            return
        await self.redis.aclose()
        if self.engine is not None:
            await self.engine.dispose()


def build_id_mapper(settings: Settings) -> IdMapper:
    """Construct the ID mapper from configured rules and the optional map file.

    Fully configuration-driven: an agency profile (env rules and/or a JSON
    file with maps + rules) is all it takes to support a new transit agency.
    """
    trip_map, route_map = settings.load_static_id_maps()
    rules = [
        MappingRule(field=rule.field, pattern=rule.pattern, replacement=rule.replacement)
        for rule in settings.load_id_mapping_rules()
    ]
    return IdMapper(rules=rules, trip_id_map=trip_map, route_id_map=route_map)


def build_commuter_services(
    settings: Settings,
    session_factory: SessionFactory,
    redis: Redis,
    vehicle_store: RedisVehicleStore,
    event_publisher: RedisDomainEventPublisher | None = None,
) -> CommuterServices:
    """Assemble the commuter service bundle over shared infrastructure."""
    predictor = HistoricalCrowdPredictor(
        session_factory,
        lookback_days=settings.crowd_lookback_days,
        hour_window=settings.crowd_hour_window,
    )
    favourites = FavouritesService()
    last_train = LastTrainService(timezone=settings.timezone)
    planner = JourneyPlanner(session_factory)
    coach = CoachRecommendationService(
        predictor, default_coach_count=settings.default_coach_count
    )
    exits = ExitService()
    historical_delay_predictor = DelayPredictionService(
        planner, lookback_days=settings.delay_prediction_lookback_days
    )
    # Transparently overlays a cached LLM refinement (Claude, OpenAI, or
    # Gemini -- see llm_delay_refiner.py) when one exists and is fresh --
    # every consumer below keeps depending on the DelayEstimator Protocol,
    # unaware this wrapper exists. On a cache miss (including "the feature
    # isn't configured at all", the default), this is a pure pass-through
    # to the historical estimate.
    delay_predictor = LlmEnhancedDelayEstimator(
        historical_delay_predictor,
        max_age=timedelta(seconds=settings.llm_delay_refinement_max_age_seconds),
        max_adjustment_fraction=settings.llm_delay_refinement_max_adjustment_fraction,
    )
    return CommuterServices(
        users=UserService(),
        favourites=favourites,
        notifications=NotificationService(channels=(LoggingNotificationChannel(),)),
        destination_alerts=DestinationAlertService(vehicle_store),
        service_alerts=ServiceAlertService(
            publish=vehicle_store.publish_diff, event_publisher=event_publisher
        ),
        last_train=last_train,
        journeys=JourneyService(event_publisher=event_publisher),
        coach=coach,
        exits=exits,
        offline=OfflineBundleService(session_factory, redis),
        analytics=AnalyticsService(max_batch=settings.analytics_max_batch),
        planner=planner,
        commute_card=CommuteCardService(favourites, last_train, planner, coach),
        commute_predictor=CommutePredictionService(
            planner,
            coach,
            exits,
            lookback_days=settings.commute_prediction_lookback_days,
        ),
        delay_predictor=delay_predictor,
        smart_recommendations=SmartRecommendationService(planner, coach, exits, delay_predictor),
        place_roles=PlaceRoleInferenceService(lookback_days=settings.commute_prediction_lookback_days),
        commute_impact=CommuteImpactService(monthly_window_days=settings.commute_replay_window_days),
        journey_share=JourneyShareService(),
        rider_reports=RiderReportService(),
        crowd_forecast=CrowdForecastService(),
    )


def build_resources(settings: Settings) -> AppResources:
    """Build the full production object graph from settings."""
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis: Redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        health_check_interval=30,
        max_connections=50,
    )
    vehicle_store = RedisVehicleStore(redis)
    resolver = RouteResolver(
        session_factory,
        build_id_mapper(settings),
        station_radius_m=settings.station_radius_m,
    )
    train_service = TrainService(vehicle_store, resolver, settings.stale_after_seconds)
    eta_engine = EtaEngine(
        session_factory,
        EtaParameters(
            default_speed_mps=settings.default_speed_mps,
            min_speed_mps=settings.min_speed_mps,
            max_speed_mps=settings.max_speed_mps,
            dwell_time_seconds=settings.dwell_time_seconds,
            station_radius_m=settings.station_radius_m,
            timezone=settings.timezone,
        ),
    )
    eta_service = CachedEtaService(
        eta_engine, RedisEtaCache(redis, ttl_seconds=settings.poll_interval_seconds * 6)
    )
    live_hub = LiveHub(ConnectionManager(), ReplayBuffer(settings.ws_replay_buffer_size))
    event_publisher = RedisDomainEventPublisher(redis)
    return AppResources(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        vehicle_store=vehicle_store,
        resolver=resolver,
        train_service=train_service,
        eta_engine=eta_engine,
        eta_service=eta_service,
        live_hub=live_hub,
        commuter=build_commuter_services(
            settings, session_factory, redis, vehicle_store, event_publisher
        ),
        event_publisher=event_publisher,
    )


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    """HTTP client for the realtime feed with sane timeouts and pooling."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        headers={"User-Agent": "MetroPulse/1.0"},
    )
