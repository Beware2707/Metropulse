"""Versioned REST API (v1)."""

from fastapi import APIRouter

from metropulse.api.v1.admin_stats import router as admin_stats_router
from metropulse.api.v1.alerts import router as alerts_router
from metropulse.api.v1.analytics import router as analytics_router
from metropulse.api.v1.commute import router as commute_router
from metropulse.api.v1.eta import router as eta_router
from metropulse.api.v1.favourites import router as favourites_router
from metropulse.api.v1.intelligence import router as intelligence_router
from metropulse.api.v1.journey_plan import router as journey_plan_router
from metropulse.api.v1.journeys import router as journeys_router
from metropulse.api.v1.notifications import router as notifications_router
from metropulse.api.v1.offline import router as offline_router
from metropulse.api.v1.recommendations import router as recommendations_router
from metropulse.api.v1.reminders import router as reminders_router
from metropulse.api.v1.replay import router as replay_router
from metropulse.api.v1.routes import router as routes_router
from metropulse.api.v1.stations import router as stations_router
from metropulse.api.v1.trains import router as trains_router
from metropulse.api.v1.users import router as users_router

router = APIRouter(prefix="/api/v1")
router.include_router(trains_router)
router.include_router(stations_router)
router.include_router(routes_router)
router.include_router(eta_router)
router.include_router(users_router)
router.include_router(favourites_router)
router.include_router(alerts_router)
router.include_router(reminders_router)
router.include_router(journeys_router)
router.include_router(journey_plan_router)
router.include_router(recommendations_router)
router.include_router(offline_router)
router.include_router(analytics_router)
router.include_router(notifications_router)
router.include_router(commute_router)
router.include_router(intelligence_router)
router.include_router(replay_router)
router.include_router(admin_stats_router)
