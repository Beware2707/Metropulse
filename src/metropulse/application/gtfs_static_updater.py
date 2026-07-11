"""Optional background job: detect and load DMRC static GTFS feed updates.

Off by default (see ``config.Settings.gtfs_static_auto_update_enabled``).
When enabled, :meth:`GtfsStaticUpdateService.check_for_update_safe` runs on
a schedule (``cli.py``'s ``run_worker``) and does a full CSRF-protected POST
to DMRC's static feed endpoint every cycle -- there is no lighter,
metadata-only endpoint -- but skips the expensive parse+validate+load step
whenever the response's ``ETag`` matches what is already stored (see
:class:`~metropulse.infrastructure.gtfs_static.dmrc_client.DmrcStaticFeedClient`).

Safety-critical constraint (see ``data/raw_gtfs/OVERRIDE_NOTES.md``): this
service NEVER "fixes" or extends ``calendar.txt`` ``end_date`` values on
freshly downloaded data.
:class:`~metropulse.application.static_loader.GtfsStaticLoader` is the sole
authority on what gets written -- it validates and transactionally replaces
the static tables exactly as DMRC published them, nothing more. This
service only *additionally* inspects the freshly loaded calendar for
already-expired ``end_date``s and logs a prominent warning, so a human
operator can notice and decide -- exactly as ``OVERRIDE_NOTES.md``
describes -- whether a manual date-extension override is warranted again.
There is no "auto-extend" code path anywhere in this module, deliberately.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from sqlalchemy import select

from metropulse.application.static_loader import GtfsStaticLoader, LoadResult
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import GtfsValidationError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import DatasetVersion
from metropulse.infrastructure.db.commuter_repositories import DatasetVersionRepository
from metropulse.infrastructure.db.models import Calendar
from metropulse.infrastructure.gtfs_static.dmrc_client import (
    DmrcStaticFeedClient,
    StaticFeedResponse,
)

logger = logging.getLogger(__name__)

# Distinct from GtfsStaticLoader's own "gtfs_static" DatasetVersion kind (a
# content hash of whatever was actually loaded, written by the loader
# itself): this kind tracks the *remote* feed's ETag purely to decide
# whether a check needs to do the expensive validate+load at all. Using a
# clearly different kind means the two row families can never collide or be
# mistaken for one another.
REMOTE_ETAG_KIND = "gtfs_static_remote_etag"


class GtfsStaticUpdateService:
    """Periodically checks DMRC's static feed and loads it when it changes."""

    def __init__(
        self,
        client: DmrcStaticFeedClient,
        loader: GtfsStaticLoader,
        session_factory: SessionFactory,
    ) -> None:
        self._client = client
        self._loader = loader
        self._session_factory = session_factory

    async def check_for_update_safe(self) -> LoadResult | None:
        """Scheduler entry point: never raises.

        Matches the ``*_safe`` convention every other scheduled job in
        ``cli.py``'s ``run_worker`` uses (e.g.
        ``LlmDelayRefinementScheduler.evaluate_safe``) -- one failed check
        must never kill the APScheduler loop.
        """
        try:
            return await self.check_for_update()
        except Exception:
            logger.exception("DMRC static feed update check failed")
            return None

    async def check_for_update(self) -> LoadResult | None:
        """One check-and-maybe-load cycle.

        Returns the :class:`LoadResult` if a reload happened, otherwise
        ``None`` (feed unchanged, or the new data failed validation).

        DMRC exposes no lightweight metadata endpoint -- the full POST is
        unavoidable just to see the response's ``ETag``/``Last-Modified``
        headers -- but the expensive parse+validate+transactional-replace
        only runs when that ETag actually differs from what is already
        stored.
        """
        response = await self._client.fetch()
        previous_etag = await self._last_seen_etag()

        if response.etag is not None and response.etag == previous_etag:
            logger.debug(
                "DMRC static feed unchanged (ETag %s); skipping reload", response.etag
            )
            return None
        if response.etag is None:
            logger.warning(
                "DMRC static feed response carried no ETag header; cannot cheaply "
                "detect whether it changed, attempting a reload anyway"
            )

        logger.info(
            "DMRC static feed ETag changed (%r -> %r); downloading and validating",
            previous_etag, response.etag,
        )

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
                tmp_file.write(response.content)
                tmp_path = Path(tmp_file.name)

            try:
                result = await self._loader.load(tmp_path)
            except GtfsValidationError as exc:
                # Deliberately do NOT store the new ETag: the same bad
                # version will be re-flagged (not silently accepted) on the
                # next check, since it will still look "changed" against
                # whatever ETag we last successfully loaded.
                logger.error(
                    "downloaded DMRC static feed failed validation; NOT loaded, "
                    "NOT recording its ETag: %s",
                    "; ".join(exc.errors[:10])
                    + (f" (+{len(exc.errors) - 10} more)" if len(exc.errors) > 10 else ""),
                )
                return None

            await self._warn_on_expired_calendars()
            await self._store_remote_etag(response)
            return result
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    async def _last_seen_etag(self) -> str | None:
        async with self._session_factory() as session:
            latest = await DatasetVersionRepository(session).latest(REMOTE_ETAG_KIND)
            return latest.checksum if latest is not None else None

    async def _store_remote_etag(self, response: StaticFeedResponse) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                DatasetVersionRepository(session).add(
                    DatasetVersion(
                        kind=REMOTE_ETAG_KIND,
                        version=response.last_modified or "",
                        checksum=response.etag or "",
                        created_at=utcnow(),
                    )
                )

    async def _warn_on_expired_calendars(self) -> None:
        """Log a prominent warning for any newly loaded ``calendar`` row
        whose ``end_date`` has already passed.

        See ``data/raw_gtfs/OVERRIDE_NOTES.md``: this service must NEVER
        silently patch or extend dates -- the freshly loaded data is left
        exactly as DMRC published it. This only surfaces the fact so a
        human operator can decide whether a manual override (as documented
        there) is warranted again.
        """
        today = utcnow().date()
        async with self._session_factory() as session:
            rows = (await session.execute(select(Calendar))).scalars().all()
        expired = [row for row in rows if row.end_date < today]
        if not expired:
            return
        details = ", ".join(f"{row.service_id} (end_date={row.end_date})" for row in expired)
        logger.warning(
            "DMRC static feed reload: %d calendar service_id(s) have an end_date "
            "already in the past (today=%s) -- upstream schedule data may be "
            "stale. Loaded AS-IS with NO auto-patching; a human operator should "
            "review and consider a manual override, see "
            "data/raw_gtfs/OVERRIDE_NOTES.md. Affected: %s",
            len(expired), today, details,
        )
