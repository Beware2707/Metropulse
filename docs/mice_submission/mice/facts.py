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

    # ---- device measurements, 2026-08-14 ----
    # These are developer device testing, NOT commuter analytics. They are
    # small-n and they measure whether the build works, not whether riders
    # complete journeys. Everywhere they appear they must say so, because a
    # reader who mistakes them for usage data has been misled by us, not by
    # their own carelessness.
    "device_sessions": ("6 of 6",
                        "core commuter flow walked end to end on device, "
                        "scripted, 2026-08-14"),
    "device_crashes": ("0",
                       "fatal exceptions and process crashes across those "
                       "six sessions, from logcat"),
    "device_anr": ("1",
                   "one ANR, reason 'Buffer processing hung up due to stuck "
                   "fence — indicates GPU hang': an emulator graphics fault, "
                   "not an application defect"),
    "live_trains": ("293",
                    "schedule-estimated train positions served by the "
                    "deployed backend at 22:31 IST, 2026-08-14"),

    # ---- the public OTD VehiclePositions feed, measured ----
    # A capture of that feed (trains.json, 2026-07-05) was analysed rather than
    # assumed. Every figure below is from that capture. This is why MetroPulse
    # ships with realtime ingestion disabled: the feed is real, but it is not
    # Metro. Presenting it as Metro would have been the easiest possible way to
    # look further along than the product is.
    "feed_vehicles": ("3,476", "trains.json capture, 2026-07-05T01:26-01:37Z"),
    "feed_plate_ids": ("3,476 of 3,476",
                       "every vehicle_id matches an Indian road registration "
                       "plate pattern; prefixes DL1P and DL51"),
    "feed_resolved": ("0", "vehicles the Metro resolver could match to a "
                           "Metro route, station or trip"),
    "feed_median_dist": ("720 m",
                         "median distance from a reporting vehicle to the "
                         "nearest of the 262 Metro stations"),
    "feed_near_station": ("1.0%",
                          "share of vehicles within 50 m of any Metro station"),
    "feed_max_dist": ("30.5 km",
                      "furthest reporting vehicle from the Metro network"),
    "feed_routes": ("1,107", "distinct route_id values in the capture"),
    "feed_window": ("11 minutes",
                    "span of timestamps across all 3,476 simultaneous reports"),

    # ---- organisation ----
    "founder": ("Jai Pratap Singh", "repository git history"),
    "incorporation": ("Not incorporated", "stated by the founder"),
    "dpiit": ("No DPIIT / startup registration", "stated by the founder"),
    "contact": ("+91 91037 52190  ·  riddlesforeverbiz@gmail.com",
                "provided by the founder"),
    "contact_phone": ("+91 91037 52190", "provided by the founder"),
    "contact_email": ("riddlesforeverbiz@gmail.com", "provided by the founder"),
    "repo_url": ("github.com/Beware2707/Metropulse",
                 "git remote of the working repository — public, verified "
                 "reachable (HTTP 200) on 2026-08-15"),
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
