"""The nine supporting PDFs of the MetroPulse MICE submission.

Shared rules for all of them:
  * Every capability carries one of the five status labels.
  * Every figure comes from facts.py, which records where it came from.
  * Anything unmeasured renders as [DATA REQUIRED] rather than an estimate.
"""

from __future__ import annotations

import os

from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Spacer

from . import theme as T
from .facts import (APP_STACK, BACKEND_STACK, DATA_REQUIRED, INFRA, f, src)
from .report import (CONTENT_W, Rule, StatusPill, build, bullets, callout,
                     flow_diagram, heading, para, picture, status_row, table)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(HERE, "assets")

META = [
    ("Prepared by", f("founder")),
    ("Organisation status", f("incorporation") + " · " + f("dpiit")),
    ("Submission type", "MICE pre-application / innovation proposal"),
    ("Contact", f("contact")),
]


def _legend():
    """The status key, repeated in every document so no label is ambiguous."""
    rows = [["Label", "Meaning"]]
    for label, meaning in T.STATUS_MEANING.items():
        rows.append([label, meaning])
    return [
        heading("How to read this document", 2),
        para("Every capability below carries exactly one label. The labels are "
             "used consistently across the whole submission."),
        table(rows, widths=[45 * mm, CONTENT_W - 45 * mm]),
        Spacer(1, 4 * mm),
        callout("On numbers",
                "Every figure in this submission is either measured, or "
                "labelled on the page as reported rather than measured. Where "
                "a figure would ordinarily be expected but neither is true, it "
                "is shown as [DATA REQUIRED] rather than estimated.", "info"),
    ]


# ---------------------------------------------------------------- 1. arch
def technical_architecture(path: str) -> str:
    story = [
        heading("Technical architecture"),
        para("MetroPulse is a two-part system: a Python backend that ingests "
             "and serves transit data, and a Flutter application that turns it "
             "into moment-by-moment guidance. The description below is taken "
             "from the repository as it stands, not from a target design.",
             "lead"),
        *_legend(),
        PageBreak(),

        heading("System shape"),
        flow_diagram([
            ("GTFS static", "Timetable, stops,\nroutes, shapes"),
            ("OTD artifacts", "Pathways, gates,\nload profile, OD"),
            ("Loaders", "Match to GTFS stops,\nwholesale replace"),
            ("PostgreSQL", "Normalized store,\n14 migrations"),
            ("Worker", "Position snapshot\nevery 5 s"),
            ("Redis", "Snapshot +\npub/sub"),
            ("FastAPI", "70 REST endpoints\n+ WebSocket"),
            ("Flutter app", "Offline-first\nclient"),
            ("Rider", "One decision\nat a time"),
        ], per_row=3),

        heading("Backend", 2),
        *bullets(BACKEND_STACK),
        Spacer(1, 3 * mm),
        heading("Application", 2),
        *bullets(APP_STACK),
        Spacer(1, 3 * mm),
        heading("Deployment", 2),
        *bullets(INFRA),
        Spacer(1, 4 * mm),

        heading("Scale of the codebase"),
        table([
            ["Component", "Measure", "Source"],
            ["Backend modules", f("py_modules"), src("py_modules")],
            ["Application source files", f("dart_files"), src("dart_files")],
            ["REST endpoints", f("endpoints"), src("endpoints")],
            ["Database migrations", f("migrations"), src("migrations")],
            ["Backend tests", f("backend_tests"), src("backend_tests")],
            ["Application tests", f("app_tests"), src("app_tests")],
        ], widths=[45 * mm, 25 * mm, CONTENT_W - 70 * mm]),

        heading("The realtime seam"),
        para("The architectural decision most relevant to DMRC is that the "
             "realtime path is already built, and only its first block is "
             "missing. Positions enter the system through a single interface; "
             "everything downstream consumes one normalized model."),
        flow_diagram([
            ("Position source", "One interface,\nany implementation"),
            ("Normalized model", "VehiclePosition,\nwith a source label"),
            ("Diff engine", "Only changes are\nstored and sent"),
            ("Redis store", "Current snapshot"),
            ("WebSocket", "Diffs to every\nconnected client"),
            ("Application", "Journey Mode,\nmap, arrivals"),
        ], per_row=3),
        status_row("IMPLEMENTED",
                   "The interface, the normalized model, the diff engine, the "
                   "store, the WebSocket fan-out and the client are all built "
                   "and covered by tests."),
        status_row("REQUIRES DMRC DATA",
                   "A position source carrying real Metro train telemetry. "
                   "Today the only source in production interpolates from the "
                   "published timetable and is labelled schedule_estimate."),
        Spacer(1, 3 * mm),
        callout("Why this matters for a pilot",
                "Connecting a DMRC feed is an adapter and configuration task, "
                "not a rewrite. A conformance suite in the repository "
                "(tests/test_adapter_conformance.py) holds any position source "
                "to the same contract: it must emit the normalized model, "
                "declare its provenance explicitly, use timezone-aware UTC "
                "timestamps, emit stable unique vehicle identifiers, survive an "
                "empty cycle, and round-trip to the client payload unchanged.",
                "good"),

        heading("Data provenance is a first-class field"),
        para("Every position carries a source label that survives all the way "
             "to the screen. This is what allows the application to show "
             "SCHEDULE rather than LIVE over interpolated data, and it is the "
             "mechanism by which official DMRC data would become visibly "
             "distinct the moment it arrived."),
        table([
            ["Source label", "Meaning in the product", "Shown to the rider as"],
            ["realtime_gps", "Real vehicle telemetry — no source emits it today",
             "LIVE (reserved)"],
            ["schedule_estimate", "Interpolated from the timetable", "SCHEDULE"],
            ["prior / model", "Modelled, not observed", "Labelled as estimated"],
        ], widths=[38 * mm, CONTENT_W - 38 * mm - 38 * mm, 38 * mm], keep=True),
    ]
    story += [
        Spacer(1, 4 * mm),
        heading("Open the implementation"),
        para("Architecture, tests and the technical implementation are "
             "available for review in the working repository."),
        Image(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "qr_repo.png"),
            width=30 * mm, height=30 * mm, hAlign="LEFT"),
        para(f("repo_url"), "caption"),
    ]
    return build(path, "Technical Architecture",
                 "System design, data flow and the realtime seam",
                 "Technical Architecture", META, story)


# ----------------------------------------------------------------- 2. OTD
def otd_data_integration(path: str) -> str:
    story = [
        heading("Official OTD data integration"),
        para("MetroPulse is built on Delhi Open Transit Data. This document "
             "records exactly which artifacts are loaded, how they are matched "
             "to the GTFS network, and — equally important — what they do not "
             "contain.", "lead"),
        *_legend(),
        PageBreak(),

        heading("Artifacts loaded"),
        status_row("APPROVED DATA", "All figures below are counted from the "
                                    "loaded artifacts."),
        Spacer(1, 3 * mm),
        table([
            ["Artifact", "Contents", "Count"],
            ["pathways.json", "Lifts", f("lifts")],
            ["pathways.json", "Entry / exit gates", f("gates")],
            ["pathways.json", "Platforms", f("platforms")],
            ["pathways.json", "Walk / lift edges", f("pathway_edges")],
            ["pathways.json", "Stations mapped", f("pathway_stations")],
            ["official_stations_gates.json", "Station and gate registry", f("gate_registry")],
            ["hourly_profile.json", "Hourly station load entries", f("hourly_profile")],
            ["od_top_destinations.json", "Origin stations with top destinations", f("od_origins")],
        ], widths=[62 * mm, CONTENT_W - 62 * mm - 25 * mm, 25 * mm]),
        Spacer(1, 4 * mm),

        heading("How the data is matched", 2),
        para("OTD artifacts identify stations by name and coordinate; the "
             "timetable identifies them by GTFS stop id. The loaders reconcile "
             "the two by normalised name first and nearest-coordinate second, "
             "and report any record they could not match rather than dropping "
             "it silently. Each loader replaces its table wholesale inside one "
             "transaction, so a re-run cannot leave stale rows behind."),
        PageBreak(),

        heading("What the approved data does not contain"),
        callout("Escalators: zero records",
                "All five normalized OTD artifacts were checked for escalator "
                "data. None contains a single escalator record, and the "
                "pathway graph has no escalator node type. MetroPulse therefore "
                "makes no escalator claim anywhere in the product, and no "
                "escalator guidance is offered in this submission. Escalator "
                "inventory appears in the Realtime and Operational Data Request "
                "instead."),
        callout("Weekend service: not in the timetable",
                f"The published GTFS contains {f('trips_weekday')} weekday trips, "
                f"{f('trips_saturday')} Saturday trips and {f('trips_sunday')} "
                "Sunday trips. The calendar declares a Sunday service, but no "
                "trip references it. The application detects this and tells the "
                "rider it has no timetable for the day rather than implying that "
                "no trains are running."),
        Spacer(1, 3 * mm),

        heading("Accessibility coverage, measured"),
        para("Coverage is partial, and the product is explicit about it. These "
             "figures were measured against the deployed backend."),
        table([
            ["Measure", "Value", "Meaning"],
            ["Stations with an accessibility record", f("acc_records"),
             "Pathway data exists for the station"],
            ["Stations with a confirmed step-free gate", f("acc_stepfree"),
             "A gate is graph-connected to a lift-served platform"],
            ["Stations total", f("stations"), "Whole network in the GTFS feed"],
        ], widths=[70 * mm, 22 * mm, CONTENT_W - 92 * mm]),
        Spacer(1, 3 * mm),
        status_row("IMPLEMENTED",
                   "Three-tier accessibility guidance: confirmed step-free, "
                   "lifts present but path unmapped, or no data. The product "
                   "never presents 'unmapped' as 'inaccessible'."),
        status_row("REQUIRES DMRC DATA",
                   "Complete pathway coverage for the remaining stations, and "
                   "escalator inventory."),
    ]
    return build(path, "OTD Data Integration",
                 "Which official datasets are loaded, and what they omit",
                 "OTD Data Integration", META, story)


# ------------------------------------------------------------- 3. testing
def testing_report(path: str) -> str:
    story = [
        heading("Commuter and engineering testing report"),
        para("This document separates what has been verified from what has "
             "not. MetroPulse has substantial automated coverage, has been "
             f"exercised on real devices, and has been used by {f('beta_users')} "
             "riders on the Delhi Metro. That trial was defect-driven rather "
             "than instrumented, so it produced a fix record and not usage "
             "metrics — and no usage metric is stated here.", "lead"),
        *_legend(),
        PageBreak(),

        heading("Automated verification"),
        status_row("IMPLEMENTED", "All suites below pass at the time of writing."),
        Spacer(1, 3 * mm),
        table([
            ["Suite", "Tests", "Scope"],
            ["Backend (pytest)", f("backend_tests"),
             "Loaders, services, API, realtime engine, adapter conformance"],
            ["Application (flutter test)", f("app_tests"),
             "Domain logic, widgets, golden images, provenance labelling"],
        ], widths=[45 * mm, 20 * mm, CONTENT_W - 65 * mm]),
        Spacer(1, 4 * mm),

        heading("Testing approach worth noting", 2),
        *bullets([
            "New tests are validated by reverting the fix and confirming they "
            "fail — a test that passes against the bug it claims to catch is "
            "worse than no test.",
            "Provenance rules are tested directly: a schedule-derived position "
            "may never be labelled live, and an approach alert may never be "
            "issued without a measured distance.",
            "The realtime adapter contract is enforced against both a reference "
            "adapter and the shipped decoder, so the contract is proven both "
            "satisfiable and satisfied.",
        ]),
        Spacer(1, 3 * mm),

        heading("Field verification"),
        status_row("IMPLEMENTED",
                   "The full commuter flow has been walked on a real device "
                   "build against the deployed backend: search, plan, start a "
                   "journey, journey guidance, station detail, tickets."),
        Spacer(1, 2 * mm),
        para("This is developer verification on a device, distinct from the "
             "commuter trial described below. Both were used: the "
             "device walk-through catches what is visibly broken, and the "
             "commuter trial catches what is wrong in ways only a real journey "
             "reveals — a station name nobody types the way the feed spells it, "
             "or an assistant that answers a question without doing anything."),
        PageBreak(),

        heading("Device measurements"),
        para("Taken on 14 August 2026 against the deployed backend, by "
             "scripting the core commuter flow and reading the device log. "
             "These say whether the build works. They are not usage data and "
             "must not be read as any of the commuter metrics above.", "lead"),
        table([
            ["Measurement", "Result", "What it does and does not show"],
            ["Core flow completed",
             f("device_sessions"),
             "Search, station detail, accessibility, network map and back to "
             "home, six times. Shows the build is stable through the flow; "
             "says nothing about whether a rider would finish a real journey."],
            ["Crashes",
             f("device_crashes"),
             "No fatal exception and no process crash in those sessions. Six "
             "sessions is far too small to state a crash-free rate, which is "
             "why one is not stated."],
            ["ANRs",
             f("device_anr"),
             "Reason recorded as a GPU hang in the emulator graphics stack, "
             "not application code. Listed rather than omitted."],
            ["Backend serving positions",
             f("live_trains"),
             "Schedule-estimated train positions served at 22:31 IST. "
             "Confirms the position pipeline runs end to end — with the "
             "timetable as its source, not a realtime feed."],
        ], widths=[34 * mm, 24 * mm, CONTENT_W - 58 * mm]),
        callout("Why these are not the metrics on the previous page",
                "A completion rate answers 'do riders finish journeys'. Six "
                "scripted sessions on one emulator answer 'does the build "
                "survive the flow'. Presenting the second as though it were "
                "the first would be the exact substitution this submission "
                "exists to avoid, so the two are kept on separate pages with "
                "different names.", "warn"),

        heading("Commuter trial"),
        status_row("IMPLEMENTED",
                   f"A commuter trial was run with {f('beta_users')} riders "
                   "using the application on the Delhi Metro."),
        Spacer(1, 2 * mm),
        para("The trial was defect-driven rather than instrumented: riders used "
             "the application on real journeys and reported what did not work. "
             "Every reported defect was diagnosed, fixed and verified, and each "
             "fix is traceable in the project's release audit. That record is "
             "the trial evidence — it is stronger than a satisfaction score, "
             "because each item can be independently checked in the repository."),
        Spacer(1, 2 * mm),
        heading("Defects reported by commuters, and their resolution", 2),
        table([
            ["Reported by riders", "Diagnosis", "Status"],
            ["Station names could not be found — \"dwarka sector 10\", "
             "\"mayur vihar 1\"",
             "The published names are \"Dwarka Sector - 10\" and \"Mayur "
             "Vihar-I\"; matching was literal, so hyphenated names — "
             f"{f('hyphenated_stops')} of the network's {f('stations')} stops — "
             "could never match what riders type.",
             "Fixed"],
            ["The assistant would not give a route",
             "The only route trigger was the literal phrase \"route to\", so "
             "\"best route from A to B\" was unrecognised. It also always "
             "assumed the rider's home station as the origin.",
             "Fixed"],
            ["\"Set up a new journey\" did nothing",
             "No matching intent existed; the assistant answered with a "
             "sentence and did not open the planner.",
             "Fixed"],
            ["A home station could not be set",
             "The add-station control opened search but never returned the "
             "chosen station, so no favourite could be saved at all.",
             "Fixed"],
            ["No way back from a saved-stations screen",
             "A pushed route with a custom header and no back control.",
             "Fixed"],
            ["Only the WhatsApp ticket link opened",
             "Android 11+ package visibility: without a queries declaration, "
             "no browser could be resolved.",
             "Fixed"],
            ["The app sat on \"connecting\" and never loaded",
             "Release builds defaulted to a developer machine address, "
             "unroutable from any real device.",
             "Fixed"],
        ], widths=[52 * mm, CONTENT_W - 52 * mm - 20 * mm, 20 * mm]),
        Spacer(1, 4 * mm),
        callout("What the trial did not produce, and why",
                "The application's own analytics was not collecting during the "
                "trial — it is built, consent-gated, and deliberately switched "
                "off pending a privacy policy amendment. So the trial produced "
                "defect reports and qualitative feedback, but no measured "
                "completion, retention or crash figures. Those are shown below "
                "as [DATA REQUIRED] rather than reconstructed from "
                "recollection. When the pipeline is enabled it records feature "
                "usage and journey outcomes only: it is scoped so that it "
                "cannot carry a search query, a spoken phrase, or the stations "
                "a rider travelled between."),
        table([
            ["Metric", "Status", "What is needed"],
            ["Trial participants", f("beta_users"),
             "Reported by the founder; not app-measured"],
            ["Journeys completed", f("journeys_completed"),
             "The opt-in analytics build in riders' hands"],
            ["Retention", f("retention"), "A trial running over several weeks"],
            ["Crash-free rate", f("crash_free_rate"),
             "Crash reporting configured with a project key"],
        ], widths=[42 * mm, 32 * mm, CONTENT_W - 74 * mm], keep=True),
        Spacer(1, 3 * mm),
        status_row("IN DEVELOPMENT",
                   "Analytics pipeline built, consent-gated, not yet "
                   "collecting. It is enabled only after the privacy policy "
                   "amendment is published and a rider opts in."),
    ]
    return build(path, "Commuter Testing Report",
                 "What has been verified, and what has not",
                 "Testing Report", META, story)


# --------------------------------------------------------------- 4. crowd
def crowd_management(path: str) -> str:
    story = [
        heading("Crowd management proposal"),
        para("Crowding is the commuter problem MetroPulse is least able to "
             "solve alone and best positioned to solve with DMRC. This document "
             "sets out the intended chain from data to passenger instruction, "
             "and is explicit that it complements rather than replaces DMRC's "
             "operational systems.", "lead"),
        *_legend(),
        PageBreak(),

        heading("The chain"),
        flow_diagram([
            ("Approved data", "Hourly load profile,\nOD pairs, gates"),
            ("Realtime + historical", "Occupancy signals,\noperational feeds"),
            ("Crowd intelligence", "Aggregation, always\nwith provenance"),
            ("Detection / prediction", "Where and when\ncrowding builds"),
            ("Passenger guidance", "One instruction,\nnot a dashboard"),
            ("Rider acts", "Alternative gate,\ninterchange or time"),
        ], per_row=3),
        Spacer(1, 2 * mm),
        callout("Scope boundary",
                "MetroPulse complements DMRC's operational crowd-management "
                "systems and does not replace them. Its role is the "
                "passenger-facing half of the chain: turning crowd information "
                "into one clear instruction before a rider reaches a congested "
                "concourse. Control-room detection, staff deployment and station "
                "regulation remain entirely DMRC's.", "good"),

        heading("Before the crowd forms"),
        para("The proposition is passenger-flow optimisation, not a crowd "
             "alert. An alert tells a rider they are already inside a "
             "bottleneck; the aim here is to predict where passenger "
             "pressure is likely to build and guide riders before they "
             "enter it — a different gate, a slightly earlier departure, a "
             "different interchange, or a lift-first route."),
        status_row("PROPOSED",
                   'Example instructions: "Use Gate 3 instead" · "Leave 8 '
                   'minutes earlier" · "Use the next interchange route" · '
                   '"Lift route currently preferred".'),
        Spacer(1, 3 * mm),

        heading("What goes in"),
        para("Five inputs, of which two are available today. Each keeps its "
             "own provenance the whole way through, so a crowd figure derived "
             "partly from rider reports can never be presented as though it "
             "came from DMRC.", "lead"),
        table([
            ["Input", "What it contributes", "Status"],
            ["Official DMRC data",
             "Operational occupancy or gate throughput — the only input that "
             "makes crowd figures measured rather than modelled.",
             "REQUIRES DMRC DATA"],
            ["Station infrastructure",
             "Gate, platform and pathway counts, which set how much load a "
             "station can absorb before it congests.",
             "APPROVED DATA"],
            ["Historical patterns",
             f"The hourly load profile ({f('hourly_profile')} entries) and "
             f"origin-destination pairs ({f('od_origins')} origins), which "
             "give the shape of a normal day.",
             "APPROVED DATA"],
            ["Events",
             "Scheduled large gatherings near a station, which move demand in "
             "ways history does not predict.",
             "PROPOSED"],
            ["Aggregated rider observations",
             "Opt-in reports, used only after multiple independent riders "
             "agree, and never overwriting official data.",
             "IMPLEMENTED"],
        ], widths=[42 * mm, CONTENT_W - 42 * mm - 34 * mm, 34 * mm]),

        heading("What intelligence does with it"),
        table([
            ["", "Question", "Output"],
            ["Detect", "Where is crowding building right now?",
             "A station and a direction, with the confidence attached."],
            ["Predict", "Where will it build next?",
             "A window ahead of the rider, not a report after the fact."],
            ["Recommend", "What should this rider do differently?",
             "Exactly one action, chosen for this journey."],
        ], widths=[26 * mm, 64 * mm, CONTENT_W - 90 * mm]),
        para("The third row is the one that matters. A rider walking toward a "
             "gate cannot use a heat map; they can use a sentence. Everything "
             "upstream exists to produce one instruction that fits in the "
             "seconds a rider has while moving."),

        heading("What the passenger is told"),
        table([
            ["Instruction", "When it fires", "What it saves"],
            ["Use an alternative gate",
             "The nearest gate is congested but another is not",
             "Queueing at the entry a rider would have chosen by habit"],
            ["Change at a different station",
             "The usual interchange is loaded and a viable alternative exists",
             "The most stressful minute of the journey"],
            ["Leave a few minutes later or earlier",
             "A short shift moves the rider off the peak",
             "Standing for the whole trip instead of sitting"],
            ["Congestion warning",
             "No good alternative exists and the rider should simply know",
             "Being surprised, which is worse than being warned"],
        ], widths=[46 * mm, (CONTENT_W - 46 * mm) / 2, (CONTENT_W - 46 * mm) / 2]),
        callout("Why exactly one instruction",
                "Showing a rider three options during a commute is the same "
                "as showing none: they are moving, holding a phone in one "
                "hand, and the decision has a deadline. The hard part of "
                "crowd guidance is not computing the alternatives, it is "
                "choosing between them on the rider's behalf and being right "
                "often enough to be trusted.", "info"),

        heading("What exists today"),
        status_row("APPROVED DATA",
                   f"Hourly station load profile ({f('hourly_profile')} entries) "
                   f"and origin–destination pairs ({f('od_origins')} origins) "
                   "are loaded and served."),
        status_row("IMPLEMENTED",
                   "A crowd-aware journey planner surface, a coach "
                   "recommendation that balances expected crowding against exit "
                   "alignment, and a rider crowd-reporting endpoint."),
        status_row("REQUIRES DMRC DATA",
                   "Measured occupancy. Without it, crowd figures fall back to "
                   "a generic prior."),
        Spacer(1, 3 * mm),
        callout("An honest limitation, stated plainly",
                "With no occupancy observations available, the crowd model "
                "currently falls back to a generic assumption that trains fill "
                "toward the middle. That assumption is identical on every line, "
                "in every direction, at every hour. The product therefore "
                "words its coach advice as a general pattern rather than as a "
                "measurement of this line. This is a data gap, not an "
                "architectural one: the prediction interface is pluggable, and "
                "a model trained on real occupancy would implement the same "
                "interface with no schema change."),

        heading("What DMRC data would unlock"),
        table([
            ["Data", "What becomes possible", "Label"],
            ["Station occupancy or gate throughput",
             "Measured crowding rather than a modelled prior; congestion "
             "detection at concourse level", "REQUIRES DMRC DATA"],
            ["Train loading by coach",
             "Coach recommendations grounded in observation", "REQUIRES DMRC DATA"],
            ["Realtime train positions",
             "Crowd guidance tied to the specific train a rider will board",
             "REQUIRES DMRC DATA"],
        ], widths=[52 * mm, CONTENT_W - 52 * mm - 34 * mm, 34 * mm]),
        Spacer(1, 4 * mm),

        heading("Passenger-side outcomes"),
        para("The output of the chain is deliberately narrow. A rider on a "
             "platform cannot act on a heat map; they can act on one of three "
             "things:"),
        *bullets([
            "<b>Alternative gate</b> — enter or exit by a less congested gate at "
            "the same station.",
            "<b>Alternative interchange</b> — change at a different station where "
            "the transfer is less crowded.",
            "<b>Alternative departure time</b> — leave a few minutes earlier or "
            "later to avoid a predicted peak.",
        ]),
        Spacer(1, 3 * mm),
        status_row("PROPOSED",
                   "The guidance surface above is designed but not built, "
                   "because it should be built against real occupancy data "
                   "rather than against a prior."),
    ]
    return build(path, "Crowd Management Proposal",
                 "From approved data to one passenger instruction",
                 "Crowd Management", META, story)


# ------------------------------------------------------------ 5. realtime
def realtime_request(path: str) -> str:
    story = [
        heading("Realtime and operational data request"),
        para("This document states precisely what MetroPulse is asking DMRC "
             "for, why each item is needed, and what it would enable. It also "
             "records what MetroPulse has already established about the public "
             "feeds, so that no time is spent re-checking it.", "lead"),
        *_legend(),
        PageBreak(),

        heading("Decision requested from DMRC / MICE"),
        para("The entire ask, on one page.", "lead"),
        table([
            ["", "Requested"],
            ["1 · Realtime Metro data",
             "Vehicle positions or train movement, ETA or trip updates, and "
             "service alerts — in a test environment first."],
            ["2 · Operational station data",
             "Facility operational status, gate closures, accessibility "
             "changes, and escalator inventory and status."],
            ["3 · Aggregated passenger-flow data",
             "Station occupancy, gate throughput or other aggregated, "
             "non-personal crowd indicators — whichever DMRC can share."],
            ["4 · Technical collaboration",
             "Feed specification, identifier mapping, data refresh "
             "expectations, and a named pilot technical contact."],
            ["5 · Pilot",
             "A controlled ninety-day pilot on selected stations and routes, "
             "evaluated against the KPIs in the pilot proposal."],
        ], widths=[46 * mm, CONTENT_W - 46 * mm]),
        callout("No funding or exclusivity is requested at this stage",
                "Items 4 and 5 cost nothing but time, and remove most of the "
                "risk from items 1 to 3.", "good"),
        PageBreak(),

        heading("What has already been checked"),
        callout("The public OTD VehiclePositions endpoint is not Metro data",
                "The endpoint published on the Delhi Open Transit Data portal "
                "carries Delhi's citywide bus GPS, not Metro rolling stock: "
                "vehicle identifiers are road registration plates, several "
                "thousand vehicles report simultaneously, and positions fall "
                "across ordinary roads. MetroPulse therefore ships with "
                "realtime ingestion disabled and interpolates train positions "
                "from the published timetable instead, labelled as an estimate "
                "everywhere it appears."),

        heading("Requested data"),
        table([
            ["Priority", "Data", "Why it is needed"],
            ["1", "Metro train positions or arrival predictions",
             "The single missing input to an otherwise complete realtime "
             "pipeline. Enables true arrival times and live journey tracking."],
            ["2", "Station occupancy or gate throughput",
             "Turns crowd guidance from a generic prior into a measurement."],
            ["3", "Escalator inventory and, ideally, status",
             "Absent from every approved artifact. Required before any "
             "escalator guidance can honestly be shown."],
            ["4", "Complete station pathway coverage",
             f"Pathway data currently covers {f('pathway_stations')} stations; "
             f"only {f('acc_stepfree')} have a confirmed step-free gate."],
            ["5", "Weekend timetable",
             f"The published GTFS contains {f('trips_sunday')} Sunday trips, so "
             "the app has no service data for Sundays."],
        ], widths=[16 * mm, 52 * mm, CONTENT_W - 68 * mm]),
        PageBreak(),

        heading("Technical guidance requested"),
        *bullets([
            "Feed format and transport — GTFS-Realtime protobuf over HTTP is "
            "already supported end to end; any other format needs a decoder.",
            "Identifier conventions — whether realtime trip and route "
            "identifiers match the published static GTFS, and if not, the "
            "mapping rules.",
            "Update cadence and expected latency, so staleness thresholds are "
            "set from fact rather than assumption.",
            "Authentication method — the client currently supports a key "
            "parameter; a header-based scheme is a small change if specified.",
        ]),
        Spacer(1, 3 * mm),

        heading("What MetroPulse commits to in return"),
        *bullets([
            "Provenance is preserved: official DMRC data would be labelled as "
            "such and shown distinctly from estimates and predictions.",
            "No official data would be presented as more certain than it is; "
            "staleness is detected and surfaced.",
            "Data would be used only for commuter-facing guidance within the "
            "agreed pilot scope.",
            "Findings from validation — including any discrepancies observed — "
            "would be reported back to DMRC.",
        ]),
        Spacer(1, 3 * mm),
        callout("What is not being asked for",
                "MetroPulse is not requesting funding, exclusivity, or any "
                "operational role. It is not asking for passenger personal "
                "data of any kind.", "good"),
    ]
    return build(path, "Realtime Data Request",
                 "What MetroPulse needs from DMRC, and why",
                 "Data Request", META, story)


# --------------------------------------------------------------- 6. pilot
def pilot_proposal(path: str) -> str:
    story = [
        heading("Ninety-day pilot proposal"),
        para("Five stages across ninety days, each ending in an exit check, so "
             "the pilot can be stopped as easily as it can be continued. The "
             "ninety days are a shape, not a commitment: the start date and "
             "the pilot lines are DMRC to choose.", "lead"),
        *_legend(),
        PageBreak(),

        heading("The five stages"),
        status_row("PROPOSED", "Every stage below is proposed, not agreed."),
        Spacer(1, 3 * mm),
        table([
            ["Stage", "Activity", "Exit criterion"],
            ["Days 0-15 — Technical integration",
             "Scope and data-handling terms agreed; the adapter connected to "
             "a DMRC feed in a non-public environment; identifiers mapped; "
             "the conformance suite run against the live feed rather than a "
             "fixture.",
             "Feed successfully consumed and mapped."],
            ["Days 16-30 — Data validation",
             "Freshness, completeness and accuracy measured against ground "
             "truth on selected corridors, including underground sections "
             "where satellite positioning is unavailable.",
             "Agreed freshness and completeness thresholds achieved."],
            ["Days 31-60 — Controlled commuter pilot",
             "A predefined passenger cohort uses the application on selected "
             "routes with opt-in analytics enabled, so the metrics currently "
             "marked [DATA REQUIRED] can be measured for the first time.",
             "The cohort completes its test journeys."],
            ["Days 61-75 — Crowd and accessibility experiments",
             "Selected crowd-guidance and step-free scenarios run and "
             "measured against DMRC's own observations for the same period.",
             "Selected scenarios validated."],
            ["Days 76-90 — Evaluation",
             "Joint review of accuracy, usefulness, accessibility and crowd "
             "guidance, written up including the negative findings.",
             "MICE receives the final performance report."],
        ], widths=[38 * mm, CONTENT_W - 38 * mm - 42 * mm, 42 * mm]),
        Spacer(1, 2 * mm),
        heading("Three possible endings", 2),
        table([
            ["Outcome", "Meaning"],
            ["GO", "Extend beyond the pilot lines, on terms discussed then."],
            ["ITERATE", "Revise and re-run the stage that missed its "
                        "criterion."],
            ["STOP", "Wind down. The findings are delivered either way."],
        ], widths=[26 * mm, CONTENT_W - 26 * mm]),
        callout("Why every stage ends in a check",
                "A pilot without stopping points tends to continue on "
                "momentum. Naming the check in advance makes the decision to "
                "stop a normal outcome rather than an admission, which is the "
                "only way a negative result gets reported honestly.",
                "info"),
        PageBreak(),

        heading("Pilot KPIs"),
        para("None of these is measured today. Baselines are set jointly in "
             "the first week of the commuter-pilot stage, so any improvement "
             "is measured against something both sides agreed to. Targets are "
             "deliberately not asserted here, because a target set without a "
             "baseline is a guess.", "lead"),

        heading("Passenger", 2),
        table([
            ["KPI", "How it is measured"],
            ["Passenger decision success rate — headline",
             "Did MetroPulse give the correct actionable instruction at the "
             "moment it was needed? Correct gate, platform, interchange, "
             "accessibility route, exit and realtime status, each confirmed "
             "in-app at the moment of use."],
            ["Journey completion rate",
             "Opt-in analytics: journeys started against journeys that reach "
             "the destination station."],
            ["Step-free journeys completed",
             "Sessions with accessibility mode on that finished without "
             "falling back to a stepped route."],
            ["Rider-reported usefulness",
             "A short in-app survey at journey end; free text is kept "
             "separate from the metric."],
        ], widths=[62 * mm, CONTENT_W - 62 * mm]),

        heading("System", 2),
        table([
            ["KPI", "How it is measured"],
            ["Arrival-time error against ground truth",
             "Seconds, per line and per hour, compared with DMRC own record "
             "for the same trip."],
            ["Position accuracy underground",
             "Metres, compared against station arrival events rather than "
             "against a satellite fix that does not exist below ground."],
            ["Feed availability and staleness",
             "Adapter conformance metrics already emitted today: gap "
             "duration, stale-snapshot count, rejected-record count."],
            ["Crash-free session rate",
             "Crash reporting, which is wired but not yet configured."],
        ], widths=[62 * mm, CONTENT_W - 62 * mm]),

        heading("Crowd", 2),
        table([
            ["KPI", "How it is measured"],
            ["Congestion detected against congestion observed",
             "MetroPulse detections compared with DMRC station reports for "
             "the same period."],
            ["Guidance acted on",
             "Share of crowd warnings after which the rider selected an "
             "alternative gate, interchange or departure time."],
            ["Load shifted off a peak",
             "Distribution of chosen departure times before and after "
             "guidance is enabled."],
            ["False-positive warnings",
             "Reviewed jointly with DMRC. A warning nobody needed is a "
             "defect, not a rounding error."],
        ], widths=[62 * mm, CONTENT_W - 62 * mm]),
        PageBreak(),

        heading("What each side provides"),
        heading("MetroPulse provides", 2),
        *bullets([
            "The application and backend, already built and deployed.",
            "Engineering work for integration, validation and reporting.",
            "A written report at each stage, including negative findings.",
            "Compliance with any data-handling conditions DMRC sets.",
        ]),
        heading("DMRC is asked for", 2),
        *bullets([
            "Access to a realtime feed in a test environment.",
            "A named technical contact for feed questions.",
            "Agreement on the evaluation criteria before validation begins.",
            "Guidance on any approval required before a public pilot group.",
        ]),
        Spacer(1, 4 * mm),
        callout("No commercial terms are proposed",
                "This submission requests no funding, no exclusivity and no "
                "commercial arrangement. What happens after a successful "
                "pilot is a separate conversation, and should be had on its "
                "own merits.", "good"),
    ]
    return build(path, "Ninety-Day Pilot Proposal",
                 "Five stages, five exit checks, and how success is measured",
                 "Pilot Proposal", META, story)


# --------------------------------------------------------------- 6b. risks
def risk_and_mitigation(path: str) -> str:
    story = [
        heading("Risk and mitigation"),
        para("Every risk MetroPulse can foresee in a DMRC pilot, with the "
             "mitigation that exists today. Where a mitigation is not built "
             "yet it is named as outstanding, rather than described as though "
             "it were finished.", "lead"),
        *_legend(),
        PageBreak(),

        heading("Realtime and data risks"),
        table([
            ["Risk", "Mitigation", "Status"],
            ["The feed fails, or goes stale without failing",
             "Staleness thresholds are enforced in the adapter. Past the "
             "threshold the position is dropped and the app falls back to "
             "SCHEDULE and says so, rather than showing a train frozen on "
             "the map.",
             "IMPLEMENTED"],
            ["Realtime identifiers do not match static GTFS",
             "A configurable mapping chain: exact match, then an explicit "
             "map, then rewrite rules. A conformance suite fails the build "
             "when a source violates the contract.",
             "IMPLEMENTED"],
            ["The feed carries a position that is absent or impossible",
             "The decoder rejects null-island coordinates, out-of-range "
             "values and NaN, and logs duplicate vehicle identifiers at "
             "error level instead of silently keeping the last one.",
             "IMPLEMENTED"],
            ["Static data goes stale after a network change",
             "Loaders replace each table wholesale inside a single "
             "transaction, so a re-run cannot leave a mix of old and new "
             "rows for the same station.",
             "IMPLEMENTED"],
        ], widths=[44 * mm, CONTENT_W - 44 * mm - 32 * mm, 32 * mm]),

        heading("Accuracy and trust risks"),
        table([
            ["Risk", "Mitigation", "Status"],
            ["A prediction is simply wrong",
             "No prediction is presented as fact. Every value carries its "
             "trust level to the screen, so a wrong estimate misleads nobody "
             "about what kind of claim it was.",
             "IMPLEMENTED"],
            ["Positioning is poor underground",
             "Multi-source tracking: satellite fix, coarse network fix, "
             "motion-based stop counting and timetable fallback, each "
             "labelled distinctly rather than blended into one false "
             "confidence.",
             "IN DEVELOPMENT"],
            ["A rider report is wrong, or malicious",
             "Rider observations appear only after agreement from multiple "
             "independent riders, and never overwrite official data: they "
             "sit at the lowest trust level.",
             "IMPLEMENTED"],
            ["Crowd data is unavailable during the pilot",
             "Crowd guidance is a separable stage and can be deferred "
             "without affecting the rest of the pilot.",
             "PROPOSED"],
        ], widths=[44 * mm, CONTENT_W - 44 * mm - 32 * mm, 32 * mm]),

        heading("Privacy, security and operational risks"),
        table([
            ["Risk", "Mitigation", "Status"],
            ["Rider location is over-collected",
             "Location tracking is opt-in per journey and the rider can stop "
             "it at any time. Location stays on the device except when the "
             "rider explicitly shares a trip.",
             "IMPLEMENTED"],
            ["Analytics reveals where an individual travels",
             "The analytics API is shaped so it cannot express the private "
             "thing: no search query, no spoken phrase and no station pair "
             "can be attached to an event.",
             "IMPLEMENTED"],
            ["Credentials leak through the client",
             "The licensed Transport Stack key is held server-side and "
             "proxied. It is not in the application package and not in "
             "version control.",
             "IMPLEMENTED"],
            ["API load during a public pilot",
             "Diff-based WebSocket fan-out and a Redis snapshot keep the "
             "per-client cost low. Rate limiting and a restricted firewall "
             "are named as hardening still to do.",
             "IN DEVELOPMENT"],
            ["Single-developer capacity",
             "Acknowledged, and the reason each pilot stage is deliberately "
             "small with its own exit check rather than one large "
             "commitment.",
             "PROPOSED"],
        ], widths=[44 * mm, CONTENT_W - 44 * mm - 32 * mm, 32 * mm]),
        callout("A risk with no mitigation is still listed",
                "Two rows above are marked IN DEVELOPMENT and two PROPOSED. "
                "That is the honest state of the work. A risk register in "
                "which every risk is already fully handled is a risk "
                "register nobody checked.", "warn"),
    ]
    return build(path, "Risk and Mitigation",
                 "Every foreseeable risk, and what exists to handle it",
                 "Risk Register", META, story)


# ------------------------------------------------------------- 7. founder
def founder_profile(path: str) -> str:
    story = [
        heading("Founder profile"),
        para("Two kinds of claim appear below and they are kept apart. "
             "Biographical details come from the founder's résumé and are "
             "self-reported. Everything under <i>Evidenced by the project</i> "
             "can be checked directly in the repository and the deployed "
             "system.", "lead"),
        Spacer(1, 3 * mm),

        heading("Why I built MetroPulse — founder's statement", 2),
        para("MetroPulse was built around a simple observation: a passenger's "
             "information need does not end when they receive a route. The "
             "difficult decisions happen inside the station, during "
             "interchanges, and immediately before reaching the destination. "
             "The project turns transit data into contextual guidance at the "
             "moment each of those decisions is made."),
        Spacer(1, 2 * mm),

        heading("Biographical — self-reported", 2),
        table([
            ["Field", "Value"],
            ["Name", f("founder")],
            ["Location", f("founder_location")],
            ["Role on this project",
             "Independent developer — sole author of MetroPulse"],
            ["Professional field", f("founder_role")],
            ["Current employment", f("founder_employer")],
            ["Recent internship", f("founder_internship")],
            ["Education", f("founder_degree")],
            ["Postgraduate", f("founder_pg")],
            ["Languages", f("founder_languages")],
            ["Organisation status", f("incorporation")],
            ["Startup / DPIIT registration", f("dpiit")],
            ["Contact", f("contact")],
            ["LinkedIn", f("founder_linkedin")],
        ], widths=[42 * mm, CONTENT_W - 42 * mm]),
        Spacer(1, 5 * mm),

        PageBreak(),
        heading("Evidenced by the project"),
        para("Unlike the table above, the following can be verified directly "
             "from the MetroPulse repository and the deployed system."),
        *bullets([
            f"Sole author of a production-grade backend "
            f"({f('py_modules')} modules) and a Flutter application "
            f"({f('dart_files')} source files).",
            f"{f('backend_tests')} backend tests and {f('app_tests')} "
            "application tests, all passing.",
            f"{f('endpoints')} REST endpoints and a WebSocket stream, deployed "
            "and serving on AWS.",
            "Integration of official Delhi Open Transit Data, including "
            "reconciliation of OTD station records against the GTFS network.",
            "A licensed Delhi Transport Stack API integration for bus and "
            "last-mile data.",
            "Android application built, signed and installed on a real device.",
        ]),
        Spacer(1, 4 * mm),
        callout("What this submission does not include",
                "MetroPulse is not incorporated and holds no startup or DPIIT "
                "registration. No company documents, financial statements or "
                "client certificates exist, and none are included. This is "
                "submitted as an individual innovation proposal.", "info"),
    ]
    return build(path, "Founder Profile",
                 "Self-reported background, kept separate from project evidence",
                 "Founder Profile", META, story)


# ------------------------------------------------------------- 8. roadmap
def roadmap(path: str) -> str:
    story = [
        heading("Roadmap"),
        para("Ordered by dependency rather than by date. Items later in the "
             "list cannot sensibly be built before the ones above them.", "lead"),
        *_legend(),
        PageBreak(),

        heading("Near term — independent of DMRC"),
        status_row("IN DEVELOPMENT",
                   "Journey tracking in the background, with an ongoing "
                   "notification showing the next station. Decision logic is "
                   "built and tested; device verification is outstanding."),
        status_row("IN DEVELOPMENT",
                   "Opt-in rider contributions — coach-to-exit observations "
                   "confirmed by multiple independent riders before use."),
        status_row("PROPOSED",
                   "Production hardening: TLS certificate and domain, "
                   "restricted firewall, secrets management, rate limiting."),
        status_row("PROPOSED",
                   "An instrumented commuter trial to produce the metrics "
                   f"currently marked [DATA REQUIRED]. The {f('beta_users')}-rider "
                   "trial already run was defect-driven, with analytics off."),
        Spacer(1, 4 * mm),

        heading("Dependent on DMRC data"),
        status_row("REQUIRES DMRC DATA",
                   "Live train tracking through the existing adapter — no user "
                   "interface rewrite required."),
        status_row("REQUIRES DMRC DATA",
                   "Measured crowding, replacing the current generic prior."),
        status_row("REQUIRES DMRC DATA",
                   "Escalator guidance, which cannot be built at all until "
                   "escalator data exists."),
        status_row("REQUIRES DMRC DATA",
                   "Weekend service guidance, which requires a timetable "
                   "containing weekend trips."),
        Spacer(1, 4 * mm),

        heading("Longer term"),
        status_row("PROPOSED",
                   "Multimodal journeys — Metro plus bus and last-mile as one "
                   "continuous trip. Limited bus and last-mile integration "
                   "already exists via the licensed Delhi Transport Stack API."),
        status_row("PROPOSED",
                   "iOS application. The codebase is cross-platform; no iOS "
                   "build has been produced."),
        Spacer(1, 4 * mm),
        callout("On sequencing",
                "The most valuable next step is not a new feature. It is "
                "validating the existing journey-tracking thresholds on a real "
                "train, because everything built on top of them inherits any "
                "error in them.", "info"),
    ]
    return build(path, "Roadmap",
                 "Ordered by dependency, not by date", "Roadmap", META, story)


# -------------------------------------------------------------- 9. status
def document_status(path: str) -> str:
    docs = [
        ["Pitch_Deck.pptx / .pdf", "Complete",
         "20 slides, editable and as PDF."],
        ["Project_Proposal.docx / .pdf", "Complete",
         "24 sections, editable and as PDF."],
        ["Technical_Architecture.pdf", "Complete",
         "Drawn from the repository as built."],
        ["OTD_Data_Integration.pdf", "Complete",
         "Counts taken from the loaded artifacts."],
        ["Commuter_Validation.pdf", "Partial",
         "Automated coverage complete. The 25-rider trial was defect-driven "
         "rather than instrumented, so usage metrics remain [DATA REQUIRED]."],
        ["Crowd_Management.pdf", "Complete",
         "The guidance surface is labelled PROPOSED, not built. Crowd "
         "prediction needs occupancy data that does not exist yet."],
        ["Realtime_Data_Request.pdf", "Complete",
         "Includes the measured evidence that the public VehiclePositions "
         "feed is Delhi bus GPS, not Metro."],
        ["Pilot_Proposal.pdf", "Complete",
         "Ninety days, five stages, five exit checks. No start date "
         "asserted; that is DMRC to choose."],
        ["Risk_and_Mitigation.pdf", "Complete",
         "Two risks carry IN DEVELOPMENT mitigations and two PROPOSED, which "
         "is the honest state rather than an oversight."],
        ["Founder_Profile.pdf", "Complete",
         "Biographical fields are self-reported and labelled as such, kept "
         "separate from repository-verifiable claims."],
        ["Roadmap.pdf", "Complete",
         "Ordered by dependency, not by date."],
        ["Document_Status.pdf", "Complete", "This document."],
        ["Demo/", "Complete",
         "Signed release APK, twelve screenshots from that build, and a "
         "five-minute walkthrough."],
        ["README.md", "Complete",
         "Reading order, claims discipline, and what is still outstanding."],
    ]
    story = [
        heading("Document status"),
        para("An index of the submission package, with an honest statement of "
             "what is complete and what still needs information that could not "
             "be derived from the project.", "lead"),
        Spacer(1, 3 * mm),
        table([["Document", "Status", "Note"]] + docs,
              widths=[74 * mm, 20 * mm, CONTENT_W - 94 * mm]),
        PageBreak(),

        heading("Information required before submission"),
        callout("These must be supplied manually",
                "None of the items below exist in the repository, and none has "
                "been invented."),
        table([
            ["Item", "Appears in", "Placeholder"],
            ["Journeys completed", "Testing Report", DATA_REQUIRED],
            ["Retention", "Testing Report", DATA_REQUIRED],
            ["Crash-free rate", "Testing Report", DATA_REQUIRED],
        ], widths=[56 * mm, CONTENT_W - 56 * mm - 34 * mm, 34 * mm]),
        Spacer(1, 4 * mm),

        heading("Claims discipline used throughout"),
        *bullets([
            "No feature is described that is not present in the repository.",
            f"The only commuter number stated is the {f('beta_users')} trial "
            "participants, and it is labelled as founder-reported rather than "
            "app-measured. No usage rate is stated at all.",
            "MetroPulse is never described as having official realtime Delhi "
            "Metro data.",
            "Escalator guidance is not claimed, because the approved data "
            "contains no escalator records.",
            "Every capability carries one of five labels distinguishing what is "
            "built, what is approved data, what is in progress, what is "
            "proposed, and what depends on DMRC.",
        ]),
    ]
    return build(path, "Document Status",
                 "What is complete, and what still needs information",
                 "Document Status", META, story)


ALL = {
    "Technical_Architecture.pdf": technical_architecture,
    "OTD_Data_Integration.pdf": otd_data_integration,
    "Commuter_Validation.pdf": testing_report,
    "Crowd_Management.pdf": crowd_management,
    "Realtime_Data_Request.pdf": realtime_request,
    "Pilot_Proposal.pdf": pilot_proposal,
    "Risk_and_Mitigation.pdf": risk_and_mitigation,
    "Founder_Profile.pdf": founder_profile,
    "Roadmap.pdf": roadmap,
    "Document_Status.pdf": document_status,
}
