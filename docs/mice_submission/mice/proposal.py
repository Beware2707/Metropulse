"""The main MICE project proposal, rendered as both .docx and .pdf.

The content is defined once as a section list and rendered twice, for the same
reason the deck is: a proposal whose Word and PDF versions disagree is worse
than either on its own.
"""

from __future__ import annotations

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Spacer

from . import theme as T
from .facts import APP_STACK, BACKEND_STACK, DATA_REQUIRED, INFRA, f
from .report import (CONTENT_W, bullets, build, callout, flow_diagram, heading,
                     para, status_row, table)

# Content is a list of (kind, payload) so both renderers walk the same tree.
# kinds: h1, h2, p, lead, ul, status, table, callout, flow, pagebreak


def _content() -> list[tuple]:
    C: list[tuple] = []
    a = C.append

    a(("h1", "1. Executive summary"))
    a(("lead",
       "MetroPulse is a working Android application and backend that turns "
       "Delhi Open Transit Data into moment-by-moment commuter guidance. It is "
       "deployed, tested, and has been used by commuters on the Delhi Metro. "
       "It does not have official realtime Delhi Metro data, and it says so "
       "everywhere that matters — in the product, in this proposal, and on the "
       "first slide of the accompanying deck."))
    a(("p",
       "The submission asks DMRC for four things: a realtime Metro feed, "
       "operational data for crowding and escalators, technical guidance on "
       "feed formats and identifiers, and collaboration on a four-phase pilot. "
       "It does not ask for funding, exclusivity, or any operational role."))
    a(("p",
       "The architectural point most relevant to DMRC is that the realtime "
       "pipeline is already built and only its first block is missing. "
       "Connecting an official feed is an adapter and configuration task, held "
       "to a conformance suite that already exists in the repository."))
    a(("h2", "Status at a glance"))
    a(("table", ([
        ["Area", "Position today"],
        ["Application", f"Built and deployed. {f('app_tests')} tests passing."],
        ["Backend", f"Built and deployed on AWS. {f('backend_tests')} tests passing, "
                    f"{f('endpoints')} endpoints."],
        ["Official data", f"{f('lifts')} lifts, {f('gates')} gates, "
                          f"{f('platforms')} platforms integrated from OTD."],
        ["Realtime Metro data", "Not available. Pipeline built and waiting."],
        ["Crowd measurement", "Not available. Falls back to a generic prior."],
        ["Escalator data", "Does not exist in the approved datasets."],
        ["Commuter trial", f"{f('beta_users')} riders; defect-driven, not instrumented."],
        ["Organisation", f"{f('incorporation')}. {f('dpiit')}."],
    ], [42 * mm, CONTENT_W - 42 * mm])))
    a(("pagebreak", None))

    a(("h1", "2. How to read this proposal"))
    a(("p", "Every capability in this document carries exactly one label."))
    a(("table", ([["Label", "Meaning"]] +
                 [[k, v] for k, v in T.STATUS_MEANING.items()],
                 [45 * mm, CONTENT_W - 45 * mm])))
    a(("callout", ("On numbers",
                   "Every figure here is either measured, or labelled on the "
                   "page as reported rather than measured. Where a figure "
                   "would ordinarily be expected but neither is true, it is "
                   "shown as [DATA REQUIRED] rather than estimated.", "info")))

    a(("h1", "3. The commuter problem"))
    a(("p",
       "A metro journey is not one decision. It is a sequence of them, each "
       "with a different answer at a different moment: when to leave, which "
       "gate to enter, which platform, which coach, where to change, how "
       "crowded it will be, which exit to take, and — for a significant "
       "minority of riders — whether there is a step-free path at all."))
    a(("p",
       "A route planner answers the first of these and stops. The remaining "
       "decisions are made on concourses and platforms, usually under time "
       "pressure, from signage that assumes the rider already knows the "
       "station. The cost of getting them wrong is small individually and "
       "large in aggregate: a wrong exit adds a surface walk, a wrong coach "
       "adds four minutes, a wrong assumption about lifts can end a journey."))

    a(("h1", "4. What MetroPulse does"))
    a(("flow", ([("Plan", "Route and\npreference"), ("Leave", "When to\nleave"),
                 ("Enter", "Which\ngate"), ("Platform", "Which\nplatform"),
                 ("Board", "Which\ncoach"), ("Interchange", "Where to\nchange"),
                 ("Crowd", "How\nbusy"), ("Exit", "Which\nexit")], 4)))
    a(("status", ("IMPLEMENTED",
                  "Plan, leave, enter, platform, board, interchange and exit "
                  "guidance are built and in the shipped application.")))
    a(("status", ("REQUIRES DMRC DATA",
                  "Crowd guidance, which needs operational occupancy data to be "
                  "a measurement rather than a model.")))
    a(("p",
       "The application's flagship screen advances through these moments and "
       "shows only the one in front of the rider. The design principle is "
       "subtraction: a rider walking through a station with a bag in one hand "
       "can act on one instruction, not on a dashboard."))
    a(("pagebreak", None))

    a(("h1", "5. Current implementation"))
    a(("h2", "Backend"))
    a(("ul", BACKEND_STACK))
    a(("h2", "Application"))
    a(("ul", APP_STACK))
    a(("h2", "Deployment"))
    a(("ul", INFRA))
    a(("h2", "Scale"))
    a(("table", ([
        ["Measure", "Value"],
        ["Backend modules", f("py_modules")],
        ["Application source files", f("dart_files")],
        ["REST endpoints", f("endpoints")],
        ["Database migrations", f("migrations")],
        ["Backend tests", f("backend_tests")],
        ["Application tests", f("app_tests")],
        ["Release APK", f("apk_size")],
    ], [70 * mm, CONTENT_W - 70 * mm])))

    a(("h1", "6. Official data integration"))
    a(("status", ("APPROVED DATA", "All counts below are read from the loaded "
                                   "artifacts, not estimated.")))
    a(("table", ([
        ["Artifact", "Contents", "Count"],
        ["pathways.json", "Lifts", f("lifts")],
        ["pathways.json", "Entry / exit gates", f("gates")],
        ["pathways.json", "Platforms", f("platforms")],
        ["pathways.json", "Stations mapped", f("pathway_stations")],
        ["official_stations_gates.json", "Station and gate registry", f("gate_registry")],
        ["hourly_profile.json", "Hourly load entries", f("hourly_profile")],
        ["od_top_destinations.json", "Origin stations", f("od_origins")],
    ], [58 * mm, CONTENT_W - 58 * mm - 22 * mm, 22 * mm])))
    a(("callout", ("Escalators are not in the approved data",
                   "All five normalized OTD artifacts contain zero escalator "
                   "records. MetroPulse therefore makes no escalator claim "
                   "anywhere in the product, and none in this proposal. "
                   "Escalator inventory is requested from DMRC instead.", "warn")))
    a(("callout", ("The timetable has no Sunday service",
                   f"The published GTFS contains {f('trips_weekday')} weekday "
                   f"trips, {f('trips_saturday')} Saturday trips and "
                   f"{f('trips_sunday')} Sunday trips. The calendar declares a "
                   "Sunday service but no trip references it. The application "
                   "detects this and tells the rider it has no timetable for "
                   "the day rather than implying no trains are running.", "warn")))

    a(("h1", "7. Realtime architecture"))
    a(("flow", ([("DMRC realtime", "Requested"), ("Adapter", "Built"),
                 ("Validation", "Built"), ("ID mapping", "Built"),
                 ("Normalized position", "Built"), ("Redis", "Built"),
                 ("WebSocket", "Built"), ("Application", "Built")], 4)))
    a(("p",
       "Positions enter through a single interface and everything downstream "
       "consumes one normalized model carrying an explicit source label. That "
       "label is what allows the application to display SCHEDULE rather than "
       "LIVE over interpolated data — and what would make official DMRC data "
       "visibly distinct the moment it arrived."))
    a(("h2", "Four kinds of data, kept separate"))
    a(("table", ([
        ["Kind", "Status today", "Shown to the rider as"],
        ["Official DMRC realtime", "Not available",
         "LIVE — reserved, never shown today"],
        ["MetroPulse estimate", "In use", "SCHEDULE"],
        ["AI prediction", "In use for delay and coach", "Labelled as estimated"],
        ["Scheduled data", "In use", "Timetable"],
    ], [42 * mm, CONTENT_W - 42 * mm - 42 * mm, 42 * mm])))
    a(("callout", ("The public OTD VehiclePositions feed is not Metro data",
                   "Checked against the live endpoint: vehicle identifiers are "
                   "road registration plates, several thousand vehicles report "
                   "simultaneously, and positions fall across ordinary roads. "
                   "It is Delhi's citywide bus GPS. MetroPulse ships with "
                   "realtime ingestion disabled for this reason.", "warn")))

    a(("h1", "8. AI and voice"))
    a(("status", ("IMPLEMENTED",
                  "On-device voice assistant with a deterministic intent "
                  "classifier: route, when to leave, which coach, fare, next "
                  "station, running late. Offline station search across names, "
                  "aliases and landmarks.")))
    a(("status", ("IMPLEMENTED",
                  "Coach recommendation ranking expected crowding against exit "
                  "alignment; delay and commute prediction behind pluggable "
                  "service interfaces.")))
    a(("status", ("REQUIRES DMRC DATA",
                  "Crowd prediction currently falls back to a generic prior "
                  "because no occupancy observations exist to learn from.")))
    a(("p",
       "No large language model is used. The assistant is a deterministic "
       "classifier over the application's own data, so every answer is a real "
       "figure from the same source the rest of the product shows. It answers "
       "only Delhi Metro questions and declines everything else by design."))

    a(("h1", "9. Accessibility"))
    a(("p",
       "Step-free guidance is built on DMRC's own pathway graph, and every "
       "claim is pitched at the evidence behind it. A gate is described as "
       "step-free only when the graph connects it to a lift-served platform."))
    a(("table", ([
        ["Tier", "Meaning", "Wording used"],
        ["Confirmed", "Graph connects this gate to a lift-served platform",
         "Lift to the platform"],
        ["Not mapped", "The station has lifts, but no mapped path from this gate",
         "Path from this gate not mapped"],
        ["No data", "Nothing is known", "Nothing is said"],
    ], [28 * mm, CONTENT_W - 28 * mm - 48 * mm, 48 * mm])))
    a(("p",
       f"Coverage is partial and stated as such: {f('acc_records')} of "
       f"{f('stations')} stations have an accessibility record, and "
       f"{f('acc_stepfree')} have at least one confirmed step-free gate. The "
       "application never presents 'unmapped' as 'inaccessible' — the "
       "distinction matters to the rider it affects most."))

    a(("h1", "10. Crowd management"))
    a(("flow", ([("Approved data", "Load profile,\nOD pairs"),
                 ("Realtime + historical", "Occupancy\nsignals"),
                 ("Crowd intelligence", "Aggregation with\nprovenance"),
                 ("Detection / prediction", "Where and when\nit builds"),
                 ("Passenger guidance", "One instruction"),
                 ("Rider acts", "Gate, interchange\nor departure time")], 3)))
    a(("callout", ("Scope boundary",
                   "MetroPulse complements DMRC's operational crowd-management "
                   "systems and does not replace them. Control-room detection, "
                   "staff deployment and station regulation remain DMRC's. "
                   "MetroPulse's role is the passenger-facing half: one clear "
                   "instruction before a rider reaches a congested concourse.",
                   "good")))
    a(("pagebreak", None))

    a(("h1", "11. Data governance"))
    a(("ul", [
        "Riders are identified only by an anonymous device identifier — never "
        "a name, email or phone number.",
        "Location stays on the device except when a rider explicitly shares a "
        "trip, which they start and stop themselves.",
        "An opt-in analytics pipeline is built and switched off. It is scoped "
        "so it cannot carry a search query, a spoken phrase, or the stations a "
        "rider travelled between.",
        "Rider contributions to station data are opt-in, per-prompt, and "
        "require agreement from multiple independent riders before use.",
        "A published privacy policy describes exactly what is collected; it is "
        "maintained in the repository alongside the code it describes.",
    ]))
    a(("p",
       "Any DMRC data provided would be used only for commuter-facing guidance "
       "within the agreed pilot scope, labelled as official, and never "
       "presented as more certain than it is."))

    a(("h1", "12. Testing"))
    a(("status", ("IMPLEMENTED",
                  f"{f('backend_tests')} backend tests and {f('app_tests')} "
                  "application tests, all passing.")))
    a(("status", ("IMPLEMENTED",
                  f"A commuter trial with {f('beta_users')} riders on the Delhi "
                  "Metro. Every defect they reported was diagnosed, fixed and "
                  "verified; the fix record is traceable in the repository.")))
    a(("p",
       "The trial was defect-driven rather than instrumented. It surfaced "
       "problems that no test suite would have found — station names nobody "
       "types the way the feed spells them, an assistant that answered a "
       "question without doing anything, and a build configuration that "
       "pointed release builds at a developer machine. All are fixed."))
    a(("table", ([
        ["Metric", "Status"],
        ["Trial participants", f("beta_users") + " (reported, not app-measured)"],
        ["Journeys completed", f("journeys_completed")],
        ["Retention", f("retention")],
        ["Crash-free rate", f("crash_free_rate")],
    ], [60 * mm, CONTENT_W - 60 * mm])))
    a(("p",
       "The three [DATA REQUIRED] rows need the opt-in analytics build in "
       "riders' hands, which in turn needs the privacy policy amendment "
       "published. They are not estimated here."))

    a(("h1", "13. Proposed pilot"))
    a(("status", ("PROPOSED", "All four phases below are proposed, not agreed. "
                              "No dates are asserted.")))
    a(("table", ([
        ["Phase", "Activity", "Exit check"],
        ["01 Technical integration",
         "Connect the adapter to a DMRC feed in a non-public environment; map "
         "identifiers; run the conformance suite against the live feed.",
         "Data flows end to end and passes the contract."],
        ["02 Validation",
         "Compare output against ground truth on selected corridors, including "
         "underground sections.",
         "Accuracy characterised and agreed."],
        ["03 Commuter pilot",
         "A recruited public group on one or two lines, with opt-in analytics "
         "enabled.",
         "Usage and feedback captured."],
        ["04 Evaluation",
         "Joint review of accuracy, usefulness, accessibility and crowd "
         "guidance.",
         "Documented decision to extend, revise or stop."],
    ], [36 * mm, CONTENT_W - 36 * mm - 44 * mm, 44 * mm])))

    a(("h1", "14. Key performance indicators"))
    a(("p",
       "Proposed for agreement with DMRC before phase 02 begins. Baselines "
       "cannot be stated in advance of measurement."))
    a(("table", ([
        ["KPI", "How measured", "Baseline"],
        ["Arrival prediction accuracy",
         "App output versus ground truth on pilot corridors", DATA_REQUIRED],
        ["Position accuracy underground",
         "Tracked station versus actual, on tunnelled sections", DATA_REQUIRED],
        ["Journey completion rate", "Opt-in analytics", DATA_REQUIRED],
        ["Accessible-route usefulness",
         "Structured feedback from step-free riders", DATA_REQUIRED],
        ["Crowd guidance usefulness",
         "Whether riders act on the suggested alternative", DATA_REQUIRED],
    ], [46 * mm, CONTENT_W - 46 * mm - 30 * mm, 30 * mm])))
    a(("pagebreak", None))

    a(("h1", "15. Value to DMRC"))
    a(("ul", [
        "<b>Passenger experience</b> — guidance at the moment of each decision, "
        "in the rider's pocket rather than on a website.",
        "<b>Accessibility</b> — step-free guidance built on DMRC's own pathway "
        "data, with evidence tiers that never overstate what is known.",
        "<b>Crowd management</b> — passenger-facing guidance that complements "
        "control-room systems.",
        "<b>Digital innovation</b> — a working demonstration of what open data "
        "enables when it is taken seriously.",
        "<b>Data utilisation</b> — approved OTD datasets turned into daily "
        "commuter value rather than sitting unused.",
    ]))

    a(("h1", "16. Business model"))
    a(("p",
       "MetroPulse is not incorporated and holds no startup or DPIIT "
       "registration. There is no revenue, no funding and no commercial "
       "arrangement of any kind. This submission does not request funding."))
    a(("p",
       "The founder's stated intent is that MetroPulse remains free for "
       "commuters. Any future sustainability model would be discussed with "
       "DMRC rather than assumed here."))

    a(("h1", "17. Scalability"))
    a(("ul", [
        "The API and worker are separate processes: API replicas scale "
        "horizontally behind a load balancer, with exactly one worker.",
        "Redis pub/sub delivers realtime diffs to every replica, so adding "
        "capacity does not change the data path.",
        "Only changed vehicle positions are stored and broadcast, so cost "
        "scales with movement rather than with fleet size.",
        "The application is offline-first: station data, the network map and "
        "search work without connectivity.",
        "The codebase is cross-platform; an iOS build is a packaging exercise "
        "rather than a rewrite.",
    ]))

    a(("h1", "18. Roadmap"))
    a(("status", ("IN DEVELOPMENT",
                  "Background journey tracking with a next-station notification; "
                  "opt-in rider contributions to station data.")))
    a(("status", ("PROPOSED",
                  "Production hardening — TLS and a domain, restricted firewall, "
                  "secrets management, rate limiting. An instrumented commuter "
                  "trial to produce the metrics currently marked "
                  "[DATA REQUIRED].")))
    a(("status", ("REQUIRES DMRC DATA",
                  "Live train tracking, measured crowding, escalator guidance "
                  "and weekend service guidance.")))
    a(("status", ("PROPOSED",
                  "Longer term: multimodal journeys combining Metro with bus "
                  "and last-mile, and an iOS application.")))

    a(("h1", "19. Requested collaboration"))
    a(("table", ([
        ["Priority", "Request"],
        ["1", "Metro train positions or arrival predictions"],
        ["2", "Station occupancy or gate throughput, and escalator inventory"],
        ["3", "Technical guidance on feed format, identifiers and cadence"],
        ["4", "A named technical contact and agreed evaluation criteria"],
    ], [22 * mm, CONTENT_W - 22 * mm])))

    a(("h1", "20. Risks and mitigations"))
    a(("table", ([
        ["Risk", "Mitigation"],
        ["Realtime identifiers do not match static GTFS",
         "A configurable mapping chain is already implemented: exact match, "
         "explicit map, then rewrite rules."],
        ["Positioning is poor underground",
         "Multi-source tracking is designed and partly built: satellite fix, "
         "coarse network fix, motion-based stop counting and timetable "
         "fallback — each labelled distinctly."],
        ["Crowd data is unavailable during the pilot",
         "Crowd guidance is a separable phase and can be deferred without "
         "affecting the rest."],
        ["The product proves not useful",
         "Phase 04 explicitly permits stopping; every phase has an exit check."],
        ["Single-developer capacity",
         "Acknowledged. The scope of each pilot phase is deliberately small."],
    ], [52 * mm, CONTENT_W - 52 * mm])))

    a(("h1", "21. Current limitations"))
    a(("p", "Stated plainly, because a reviewer will find them anyway."))
    a(("ul", [
        "No official realtime Delhi Metro data. Train positions are "
        "interpolated from the timetable and labelled as estimates.",
        "No measured crowding. The crowd model falls back to a generic prior.",
        "No escalator data anywhere in the approved datasets.",
        "No weekend timetable: the feed contains no Sunday trips.",
        f"Partial accessibility coverage — {f('acc_stepfree')} of "
        f"{f('stations')} stations have a confirmed step-free gate.",
        "The backend is served over plain HTTP against an IP address; TLS and "
        "a domain are outstanding and are a release blocker.",
        "No instrumented commuter metrics, as described in section 12.",
        "Not incorporated; no company documents, financials or certificates "
        "exist and none are included.",
        "Background journey tracking is built but not yet verified on a device, "
        "and its detection thresholds have not been validated on a real train.",
    ]))

    a(("h1", "22. Appendices"))
    a(("h2", "A. Accompanying documents"))
    a(("ul", [
        "MetroPulse_MICE_Pitch_Deck.pptx / .pdf",
        "MetroPulse_Technical_Architecture.pdf",
        "MetroPulse_OTD_Data_Integration.pdf",
        "MetroPulse_Commuter_Testing_Report.pdf",
        "MetroPulse_Crowd_Management_Proposal.pdf",
        "MetroPulse_Realtime_Data_Request.pdf",
        "MetroPulse_MICE_Pilot_Proposal.pdf",
        "MetroPulse_Founder_Profile.pdf",
        "MetroPulse_Roadmap.pdf",
        "MetroPulse_Document_Status.pdf",
        "MetroPulse.apk — installable release build",
    ]))
    a(("h2", "B. Contact"))
    a(("ul", [f("founder"), f("contact_phone"), f("contact_email")]))
    a(("h2", "C. Information still to be supplied"))
    a(("ul", [
        f"Journey completion, retention and crash-free rate — {DATA_REQUIRED}. "
        "All three need the consent-gated analytics build in riders' hands.",
    ]))
    return C


# ------------------------------------------------------------------- docx
def _docx(path: str) -> str:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)

    # Cover
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = t.add_run("MetroPulse")
    r.font.size = Pt(40)
    r.font.bold = True
    r.font.color.rgb = RGBColor(*T.rgb(T.INK))
    s = doc.add_paragraph()
    r = s.add_run("MICE Project Proposal\nCommuter intelligence for the Delhi Metro")
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(*T.rgb(T.PRIMARY))
    doc.add_paragraph()
    for k, v in [("Prepared by", f("founder")),
                 ("Organisation status", f"{f('incorporation')} · {f('dpiit')}"),
                 ("Submission type", "MICE pre-application / innovation proposal"),
                 ("Phone", f("contact_phone")), ("Email", f("contact_email"))]:
        p = doc.add_paragraph()
        rr = p.add_run(f"{k}:  ")
        rr.font.bold = True
        rr.font.size = Pt(10)
        p.add_run(v).font.size = Pt(10)
    doc.add_page_break()

    for kind, payload in _content():
        if kind == "h1":
            doc.add_heading(payload, level=1)
        elif kind == "h2":
            doc.add_heading(payload, level=2)
        elif kind in ("p", "lead"):
            p = doc.add_paragraph(_plain(payload))
            if kind == "lead":
                p.runs[0].font.size = Pt(12)
        elif kind == "ul":
            for item in payload:
                doc.add_paragraph(_plain(item), style="List Bullet")
        elif kind == "status":
            label, text = payload
            p = doc.add_paragraph()
            r = p.add_run(f"[{label}]  ")
            r.font.bold = True
            r.font.color.rgb = RGBColor(*T.rgb(T.STATUS[label]))
            p.add_run(_plain(text))
        elif kind == "table":
            rows, _ = payload
            tbl = doc.add_table(rows=len(rows), cols=len(rows[0]))
            tbl.style = "Light Grid Accent 1"
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    cl = tbl.cell(i, j)
                    cl.text = _plain(str(cell))
                    for pp in cl.paragraphs:
                        for rr in pp.runs:
                            rr.font.size = Pt(9)
                            if i == 0:
                                rr.font.bold = True
        elif kind == "callout":
            title, body, _kind = payload
            p = doc.add_paragraph()
            r = p.add_run(title + "\n")
            r.font.bold = True
            p.add_run(_plain(body)).font.size = Pt(10)
        elif kind == "flow":
            steps, _per = payload
            p = doc.add_paragraph()
            p.add_run("  →  ".join(s[0] for s in steps)).font.bold = True
        elif kind == "pagebreak":
            doc.add_page_break()
    doc.save(path)
    return path


def _plain(text: str) -> str:
    return text.replace("<b>", "").replace("</b>", "")


# -------------------------------------------------------------------- pdf
def _pdf(path: str) -> str:
    story: list = []
    for kind, payload in _content():
        if kind == "h1":
            story.append(heading(payload, 1))
        elif kind == "h2":
            story.append(heading(payload, 2))
        elif kind == "p":
            story.append(para(payload))
        elif kind == "lead":
            story.append(para(payload, "lead"))
        elif kind == "ul":
            story.extend(bullets(payload))
        elif kind == "status":
            story.append(status_row(*payload))
            story.append(Spacer(1, 1.5 * mm))
        elif kind == "table":
            rows, widths = payload
            story.append(table(rows, widths=widths))
            story.append(Spacer(1, 3 * mm))
        elif kind == "callout":
            story.append(callout(*payload))
        elif kind == "flow":
            steps, per = payload
            story.append(flow_diagram(steps, per_row=per))
        elif kind == "pagebreak":
            story.append(PageBreak())
    return build(path, "MICE Project Proposal",
                 "Commuter intelligence for the Delhi Metro",
                 "Project Proposal",
                 [("Prepared by", f("founder")),
                  ("Organisation status", f"{f('incorporation')} · {f('dpiit')}"),
                  ("Submission type", "MICE pre-application / innovation proposal"),
                  ("Phone", f("contact_phone")),
                  ("Email", f("contact_email"))],
                 story)


def build_all(docx_path: str, pdf_path: str) -> tuple[str, str]:
    return _docx(docx_path), _pdf(pdf_path)
