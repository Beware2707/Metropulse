"""Every figure used anywhere in the submission, with its provenance.

The rule for this package: no number appears in any document unless it appears
here first, with a source that can be re-checked. Anything that would have to
be invented is DATA_REQUIRED instead, and renders as a visible placeholder
rather than a plausible-looking estimate.
"""

from __future__ import annotations

DATA_REQUIRED = "[DATA REQUIRED]"
TO_BE_PROVIDED = "[TO BE PROVIDED]"

#: name -> (value, source)
FACTS: dict[str, tuple[str, str]] = {
    # ---- network / GTFS ----
    "stations": ("262", "DMRC GTFS static stops.txt, loaded in production"),
    "routes": ("36", "DMRC GTFS static routes.txt"),
    "trips_weekday": ("5,379", "GTFS trips.txt, service_id=weekday"),
    "trips_saturday": ("59", "GTFS trips.txt, service_id=saturday"),
    "trips_sunday": ("0", "GTFS trips.txt — no trip references the sunday service"),

    # ---- approved OTD artifacts ----
    "lifts": ("845", "otd_normalized/pathways.json"),
    "gates": ("667", "otd_normalized/pathways.json"),
    "platforms": ("355", "otd_normalized/pathways.json"),
    "pathway_edges": ("1,307", "otd_normalized/pathways.json"),
    "pathway_stations": ("220", "otd_normalized/pathways.json"),
    "pathway_lines": ("9", "otd_normalized/pathways.json coverage block"),
    "gate_registry": ("951", "otd_normalized/official_stations_gates.json"),
    "hourly_profile": ("747", "otd_normalized/hourly_profile.json"),
    "od_origins": ("249", "otd_normalized/od_top_destinations.json"),
    "escalators": ("0", "all five normalized OTD artifacts contain no escalator record"),

    # ---- accessibility coverage ----
    "acc_records": ("181", "measured against the deployed backend, /stations/{id}/accessibility"),
    "acc_stepfree": ("56", "stations with at least one graph-confirmed step-free gate"),
    "underground": ("63", "OTD facilities summary, elevated=false"),
    "elevated": ("152", "OTD facilities summary, elevated=true"),
    "facilities_records": ("215", "OTD facilities summary"),

    # ---- engineering ----
    "backend_tests": ("500", "pytest, full suite"),
    "app_tests": ("380", "flutter test, full suite"),
    "endpoints": ("70", "deployed OpenAPI document"),
    "migrations": ("14", "alembic/versions"),
    "py_modules": ("129", "src/**/*.py"),
    "dart_files": ("115", "app/lib/**/*.dart, excluding generated"),
    "apk_size": ("88.2 MB", "flutter build apk --release"),

    # ---- commuter trial: not measured, must not be invented ----
    # A real commuter trial: 25 riders used the app and reported defects,
    # each of which was diagnosed and fixed. The evidence is the fix list,
    # which is traceable in RELEASE_AUDIT.md — not an instrumented metric,
    # because the analytics pipeline is consent-gated and still switched off.
    "beta_users": ("25", "commuter trial participants, reported by the founder"),
    "journeys_completed": (DATA_REQUIRED, "requires the analytics opt-in to ship"),
    "retention": (DATA_REQUIRED, "requires a commuter trial"),
    "crash_free_rate": (DATA_REQUIRED, "crash reporting is wired but not yet configured"),

    # ---- founder background ----
    # All from the résumé supplied by the founder on 2026-08-11. These are
    # self-reported credentials, not repository-verifiable facts, and the
    # Founder Profile says so on the page.
    "founder_location": ("New Delhi, India", "founder's résumé"),
    "founder_role": ("Data Analyst — operations analytics and business "
                     "intelligence", "founder's résumé"),
    "founder_degree": ("B.Sc. Mathematics, Dr. Ram Manohar Lohia Avadh "
                       "University, 2020", "founder's résumé"),
    "founder_pg": ("M.Sc. Data Science, IU International University of "
                   "Applied Sciences, Germany — in progress",
                   "founder's résumé"),
    "founder_employer": ("Amazon Operations, New Delhi — Senior Seller "
                         "Performance Support Associate, Apr 2023 to Oct 2025",
                         "founder's résumé"),
    "founder_internship": ("Data Analytics intern, Skill Manthan Technologies, "
                           "Nov 2025 to May 2026 (grade A++, ref SM-2026-001047)",
                           "founder's résumé"),
    "founder_languages": ("English (professional), Hindi (native)",
                          "founder's résumé"),
    "founder_linkedin": ("linkedin.com/in/jai-pratap-singh-data-analyst",
                         "founder's résumé"),

    # ---- network naming (drives the search-matching defect story) ----
    "hyphenated_stops": ("31", "GTFS stops.txt — stop names containing a hyphen"),

    # ---- organisation ----
    "founder": ("Jai Pratap Singh", "repository git history"),
    "incorporation": ("Not incorporated", "stated by the founder"),
    "dpiit": ("No DPIIT / startup registration", "stated by the founder"),
    "contact": ("+91 91037 52190  ·  riddlesforeverbiz@gmail.com",
                "provided by the founder"),
    "contact_phone": ("+91 91037 52190", "provided by the founder"),
    "contact_email": ("riddlesforeverbiz@gmail.com", "provided by the founder"),
}


def f(key: str) -> str:
    """The value of a fact."""
    return FACTS[key][0]


def src(key: str) -> str:
    """Where the value came from."""
    return FACTS[key][1]


# ------------------------------------------------------------------ stack
BACKEND_STACK = [
    "Python · FastAPI · Uvicorn",
    "PostgreSQL · SQLAlchemy (async) · Alembic",
    "Redis — snapshot store and pub/sub",
    "APScheduler — polling and retention jobs",
    "gtfs-realtime-bindings · protobuf",
    "httpx · tenacity — resilient upstream calls",
]

APP_STACK = [
    "Flutter · Dart",
    "Riverpod — state; GoRouter — navigation",
    "Hive — offline store; Dio — HTTP",
    "web_socket_channel — live updates",
    "MapLibre GL — map rendering",
    "geolocator · flutter_foreground_task — journey tracking",
    "speech_to_text · flutter_tts — voice assistant",
]

INFRA = [
    "Docker Compose: api, worker, migrate, postgres, redis",
    "Deployed on AWS EC2 (ap-south-1)",
    "Alembic migrations applied in production",
]
