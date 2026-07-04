"""Tests for dataset versioning and offline bundle serving."""

from __future__ import annotations

from pathlib import Path

import fakeredis.aioredis
import httpx

from gtfs_fixture import write_gtfs_zip
from metropulse.application.commuter.offline import OfflineBundleService
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import DatasetVersionRepository


async def test_loader_records_dataset_version(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    result = await GtfsStaticLoader(session_factory).load(gtfs_zip)
    assert result.version is not None
    async with session_factory() as session:
        latest = await DatasetVersionRepository(session).latest("gtfs_static")
        assert latest is not None
        assert latest.version == result.version
        assert latest.checksum.startswith(result.version)


async def test_bundle_before_any_load_is_none(
    session_factory: SessionFactory, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    service = OfflineBundleService(session_factory, fake_redis)
    assert await service.manifest() is None
    assert await service.bundle() is None


async def test_bundle_contents_and_caching(
    loaded_session_factory: SessionFactory, fake_redis: fakeredis.aioredis.FakeRedis
) -> None:
    service = OfflineBundleService(loaded_session_factory, fake_redis)
    result = await service.bundle()
    assert result is not None
    manifest, bundle = result

    assert manifest.station_count == 4
    assert manifest.route_count == 1
    assert len(manifest.checksum) == 64

    assert [s["stop_id"] for s in bundle["stations"]] == ["S1", "S2", "S3", "S4"]
    assert bundle["routes"][0]["route_id"] == "R1"
    assert bundle["route_stations"]["R1"]["0"] == ["S1", "S2", "S3", "S4"]
    assert bundle["route_stations"]["R1"]["1"] == ["S4", "S3", "S2", "S1"]

    # Second call is served from the Redis cache with identical metadata.
    cached = await service.bundle()
    assert cached is not None
    assert cached[0].checksum == manifest.checksum
    assert cached[0].generated_at == manifest.generated_at


async def test_reload_bumps_version(
    session_factory: SessionFactory, tmp_path: Path
) -> None:
    loader = GtfsStaticLoader(session_factory)
    first = await loader.load(write_gtfs_zip(tmp_path / "a.zip"))
    changed = write_gtfs_zip(
        tmp_path / "b.zip",
        overrides={
            "routes.txt": (
                "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\n"
                "R1,DMRC,RED,Red Line Extended,1,EE1C25\n"
            )
        },
    )
    second = await loader.load(changed)
    assert first.version != second.version
    async with session_factory() as session:
        latest = await DatasetVersionRepository(session).latest("gtfs_static")
        assert latest is not None
        assert latest.version == second.version


async def test_offline_api_manifest_bundle_and_etag(
    api_client: httpx.AsyncClient,
) -> None:
    manifest = await api_client.get("/api/v1/offline/manifest")
    assert manifest.status_code == 200
    version = manifest.json()["version"]
    assert manifest.json()["station_count"] == 4

    bundle = await api_client.get("/api/v1/offline/bundle")
    assert bundle.status_code == 200
    assert bundle.headers["ETag"] == f'"{version}"'
    assert bundle.json()["version"] == version

    not_modified = await api_client.get(
        "/api/v1/offline/bundle", headers={"If-None-Match": f'"{version}"'}
    )
    assert not_modified.status_code == 304

    stale_client = await api_client.get(
        "/api/v1/offline/bundle", headers={"If-None-Match": '"old-version"'}
    )
    assert stale_client.status_code == 200
