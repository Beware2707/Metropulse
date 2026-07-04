"""Versioned REST API (v1)."""

from fastapi import APIRouter

from metropulse.api.v1.eta import router as eta_router
from metropulse.api.v1.routes import router as routes_router
from metropulse.api.v1.stations import router as stations_router
from metropulse.api.v1.trains import router as trains_router

router = APIRouter(prefix="/api/v1")
router.include_router(trains_router)
router.include_router(stations_router)
router.include_router(routes_router)
router.include_router(eta_router)
