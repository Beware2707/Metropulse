"""Offline bundle endpoints with ETag-based client caching."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse

from metropulse.api.deps import get_commuter
from metropulse.api.schemas_commuter import OfflineManifestOut
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/offline", tags=["offline"])


@router.get("/manifest", response_model=OfflineManifestOut)
async def offline_manifest(
    services: CommuterServices = Depends(get_commuter),
) -> OfflineManifestOut:
    """Current bundle version metadata; clients poll this cheaply."""
    manifest = await services.offline.manifest()
    if manifest is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no static dataset loaded yet"
        )
    return OfflineManifestOut.from_domain(manifest)


@router.get("/bundle")
async def offline_bundle(
    if_none_match: str | None = Header(default=None),
    services: CommuterServices = Depends(get_commuter),
) -> Response:
    """The full offline data bundle. Supports If-None-Match / ETag."""
    result = await services.offline.bundle()
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no static dataset loaded yet"
        )
    manifest, bundle = result
    etag = f'"{manifest.version}"'
    if if_none_match is not None and if_none_match.strip() == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return JSONResponse(content=bundle, headers={"ETag": etag})
