"""MetroPulse — DMRC / MICE pitch deck.

Sixteen slides, diagram-led. Every figure comes from `facts.py`; every
capability carries one of the five status labels. Escalators are deliberately
shown as absent on the OTD slide because the approved artifacts contain none.

The deck is described once and rendered twice — see `scene.py` for why.
"""

from __future__ import annotations

import os

from . import theme as T
from .facts import f
from .scene import CENTER, LEFT, MIDDLE, RIGHT, TOP, Recorder, render_pdf, render_pptx

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

W, H = 13.333, 7.5
M = 0.7


class _Align:
    LEFT, CENTER, RIGHT = LEFT, CENTER, RIGHT


class _Anchor:
    TOP, MIDDLE = TOP, MIDDLE


PP_ALIGN = _Align
MSO_ANCHOR = _Anchor


class Deck:
    """Adapter keeping the slide-building code readable: it takes a slide
    handle it does not need, so each call reads like a drawing instruction."""

    def __init__(self) -> None:
        self.rec = Recorder()

    def slide(self, dark: bool = False):
        return self.rec.slide(dark)

    def rect(self, s, x, y, w, h, fill, radius=False, line=None):
        self.rec.rect(x, y, w, h, fill, radius)

    def text(self, s, x, y, w, h, runs, *, size=12, bold=False, colour=T.BODY,
             font=None, align=LEFT, anchor=TOP, spacing=None, space_after=0):
        body = chr(10).join(runs) if isinstance(runs, list) else runs
        self.rec.text(x, y, w, h, body, size=size, bold=bold, colour=colour,
                      font=font, align=align, anchor=anchor,
                      spacing=spacing or 1.0)

    def bullets(self, s, x, y, w, h, items, *, size=11.5, colour=T.BODY,
                space_after=7):
        self.rec.bullets(x, y, w, h, items, size=size, colour=colour,
                         gap=space_after)

    def pill(self, s, x, y, label, *, w=None):
        return self.rec.pill(x, y, label)

    def arrow(self, s, x, y, w, h=0.16):
        self.rec.arrow(x, y, w, h)

    def step(self, s, x, y, w, h, title, sub, colour, light=True):
        self.rec.step(x, y, w, h, title, sub, colour, light)

    def header(self, s, kicker, title, num):
        self.rec.header(kicker, title, num)

    def foot(self, s, txt):
        self.rec.foot(txt)

    def img(self, s, name, x, y, w=None, h=None):
        self.rec.image(os.path.join(ASSETS, name), x, y, h=h)


# =========================================================== build the deck
def build(out_path: str) -> str:
    d = Deck()

    # -------------------------------------------------------- 01 title
    s = d.slide(dark=True)
    d.rect(s, M, 1.52, 4.75, 0.36, T.INK_SOFT, radius=True)
    d.text(s, M, 1.52, 4.75, 0.36, "NO OFFICIAL REALTIME METRO DATA TODAY",
           size=9, bold=True, colour="7FE3D2", font=T.HEAD,
           align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    d.text(s, M, 2.2, 8.6, 1.2, "MetroPulse", size=60, bold=True,
           colour="FFFFFF", font=T.HEAD)
    d.text(s, M, 3.45, 8.6, 0.5, "Commuter intelligence for the Delhi Metro",
           size=20, colour="9DB4DC")
    d.text(s, M, 4.15, 8.0, 1.0,
           "A working Android application and backend, built on approved Delhi "
           "Open Transit Data.\nSubmitted as a MICE pre-application / innovation "
           "proposal.", size=12.5, colour="C3D2EC", spacing=1.5)
    d.text(s, M, 6.45, 8.0, 0.32,
           f"{f('founder')}  ·  Independent developer  ·  {f('incorporation')}",
           size=11, colour="7C93BE")
    d.img(s, "home.png", 9.75, 0.95, h=5.6)

    # -------------------------------------------------------- 02 problem
    s = d.slide()
    d.header(s, "The commuter problem", "A journey is eight decisions, not one route", "02")
    items = [
        ("When do I leave?", "Timetables live on a website, not in the moment"),
        ("Which gate?", "Large stations have many; signage assumes you know"),
        ("Which platform?", "Direction is clearer on the platform than before it"),
        ("Which coach?", "Position at the destination decides a four-minute walk"),
        ("Where do I change?", "Interchanges are the most stressful minute of a trip"),
        ("How crowded?", "Unknown until the doors open"),
        ("Which exit?", "The wrong one adds a long surface walk"),
        ("Is there a lift?", "Step-free routing is largely invisible today"),
    ]
    cw, ch = 2.82, 1.34
    for i, (t, sub) in enumerate(items):
        col, row = i % 4, i // 4
        x, y = M + col * (cw + 0.21), 1.92 + row * (ch + 0.3)
        d.rect(s, x, y, cw, ch, T.CARD, radius=True)
        d.text(s, x + 0.17, y + 0.15, 0.4, 0.3, str(i + 1), size=15, bold=True,
               colour=T.PRIMARY, font=T.HEAD)
        d.text(s, x + 0.56, y + 0.15, cw - 0.72, 0.32, t, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.17, y + 0.56, cw - 0.34, 0.7, sub, size=10.5)
    d.foot(s, "Each decision has a different answer at a different moment. "
              "A route plan answers only the first.")

    # -------------------------------------------------------- 03 the gap
    s = d.slide()
    d.header(s, "Why route planning is not enough",
             "Planning ends where the journey begins", "03")
    d.rect(s, M, 2.55, 5.7, 2.55, T.CARD, radius=True)
    d.text(s, M + 0.32, 2.75, 5.1, 0.3, "A route planner gives you", size=13,
           bold=True, colour=T.MUTED, font=T.HEAD)
    d.bullets(s, M + 0.32, 3.2, 5.06, 3.0, [
        "Origin, destination, interchanges and total time",
        "One answer, computed once, before you leave",
        "No awareness of where you are standing",
        "No gate, platform, coach or exit guidance",
    ], size=12.5, space_after=11)
    d.rect(s, M + 6.1, 2.55, 5.83, 2.55, T.INK, radius=True)
    d.text(s, M + 6.42, 2.75, 5.2, 0.3, "MetroPulse adds", size=13, bold=True,
           colour="7FE3D2", font=T.HEAD)
    d.bullets(s, M + 6.42, 3.2, 5.19, 3.0, [
        "Guidance that changes as the journey moves",
        "Gate, platform, coach and exit when each one matters",
        "Step-free guidance from DMRC's own pathway graph",
        "Every claim labelled with where it came from",
    ], size=12.5, colour="D7E0F2", space_after=11)
    d.foot(s, "The difference is not more data on one screen — it is the right "
              "single fact at the right minute.")

    # -------------------------------------------------------- 04 journey
    s = d.slide()
    d.header(s, "MetroPulse", "One continuous journey, eight moments", "04")
    stages = ["Plan", "Leave", "Enter", "Platform", "Board", "Interchange", "Crowd", "Exit"]
    subs = ["Route and\npreference", "When to\nleave", "Which\ngate", "Which\nplatform",
            "Which\ncoach", "Where to\nchange", "How\nbusy", "Which\nexit"]
    bw, gap = 1.35, 0.155
    for i, st in enumerate(stages):
        x = M + i * (bw + gap)
        on = i != 6
        d.step(s, x, 2.55, bw, 1.55, st, subs[i], T.INK if on else T.CARD, light=on)
        if i < len(stages) - 1:
            d.arrow(s, x + bw + 0.012, 3.24, gap - 0.024)
    d.pill(s, M, 4.40, "IMPLEMENTED")
    d.text(s, M + 2.45, 4.40, 8.6, 0.27,
           "Plan · Leave · Enter · Platform · Board · Interchange · Exit",
           size=11, anchor=MSO_ANCHOR.MIDDLE)
    d.pill(s, M, 4.85, "REQUIRES DMRC DATA")
    d.text(s, M + 2.45, 4.85, 8.6, 0.27,
           "Crowd — needs operational occupancy data to be measured rather than modelled",
           size=11, anchor=MSO_ANCHOR.MIDDLE)
    d.foot(s, "Journey Mode advances through these moments and shows only the "
              "one in front of the rider.")

    # -------------------------------------------------------- 05 product
    s = d.slide()
    d.header(s, "Product today", "A working application, not a prototype", "05")
    shots = [("home.png", "Home", "Context before search"),
             ("planner.png", "Planner", "Route and preferences"),
             ("journey_mode.png", "Journey Mode", "Guidance in the moment"),
             ("station_detail.png", "Station", "Gates, exits, facilities"),
             ("network_map.png", "Network map", "Octilinear schematic")]
    iw, gapx = 1.9, 0.45
    for i, (fn, title, sub) in enumerate(shots):
        x = M + i * (iw + gapx)
        d.img(s, fn, x, 1.8, h=4.1)
        d.text(s, x - 0.2, 6.0, iw + 0.4, 0.28, title, size=12, bold=True,
               colour=T.INK, font=T.HEAD, align=PP_ALIGN.CENTER)
        d.text(s, x - 0.25, 6.28, iw + 0.5, 0.28, sub, size=9.5, colour=T.MUTED,
               align=PP_ALIGN.CENTER)
    d.pill(s, W - M - 1.55, 0.8, "IMPLEMENTED", w=1.55)
    d.foot(s, "Screenshots taken from the current release build running against "
              "the deployed backend.")

    # -------------------------------------------------------- 06 OTD data
    s = d.slide()
    d.header(s, "Official OTD data already integrated",
             "Loaded, matched to GTFS stops, and served", "06")
    stats = [(f("lifts"), "lifts", "DMRC GTFS-Pathways"),
             (f("gates"), "entry / exit gates", "DMRC GTFS-Pathways"),
             (f("platforms"), "platforms", "DMRC GTFS-Pathways"),
             (f("pathway_stations"), "stations mapped", f("pathway_lines") + " lines covered")]
    cw = 2.87
    for i, (big, lab, sub) in enumerate(stats):
        x = M + i * (cw + 0.21)
        d.rect(s, x, 1.9, cw, 1.66, T.CARD, radius=True)
        d.text(s, x + 0.22, 2.0, cw - 0.44, 0.66, big, size=35, bold=True,
               colour=T.PRIMARY, font=T.HEAD)
        d.text(s, x + 0.22, 2.68, cw - 0.44, 0.3, lab, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.22, 3.0, cw - 0.44, 0.34, sub, size=10, colour=T.MUTED)
    d.pill(s, M, 3.72, "APPROVED DATA")
    d.rect(s, M, 4.16, 5.7, 2.0, T.CARD, radius=True)
    d.text(s, M + 0.27, 4.32, 5.2, 0.28, "Also integrated", size=12, bold=True,
           colour=T.INK, font=T.HEAD)
    d.bullets(s, M + 0.27, 4.66, 5.16, 1.4, [
        f"Station and gate registry — {f('gate_registry')} records",
        f"Hourly station load profile — {f('hourly_profile')} entries",
        f"Origin–destination top pairs — {f('od_origins')} origins",
    ], size=11, space_after=6)
    d.rect(s, M + 6.1, 4.16, 5.83, 2.0, T.CARD_WARN, radius=True)
    d.text(s, M + 6.37, 4.32, 5.3, 0.28,
           "Escalators: not present in the approved data", size=12, bold=True,
           colour=T.WARN_HEAD, font=T.HEAD)
    d.text(s, M + 6.37, 4.66, 5.3, 1.4,
           "All five normalized OTD artifacts were checked and contain zero "
           "escalator records. MetroPulse therefore makes no escalator claim "
           "anywhere in the product. Escalator inventory is on the list of data "
           "requested from DMRC.", size=10.5, colour=T.WARN_TEXT)
    d.foot(s, "Counts read directly from the loaded artifacts, not estimated.")

    # -------------------------------------------------------- 07 realtime
    s = d.slide()
    d.header(s, "Realtime architecture",
             "The adapter boundary already exists and is tested", "07")
    chain = [("DMRC\nrealtime", T.VIOLET), ("Adapter", T.PRIMARY),
             ("Validation", T.PRIMARY), ("ID mapping", T.PRIMARY),
             ("Normalized\nposition", T.INK), ("Redis", T.INK),
             ("WebSocket", T.INK), ("Flutter app", T.TEAL)]
    bw, gp = 1.36, 0.14
    for i, (label, col) in enumerate(chain):
        x = M + i * (bw + gp)
        d.step(s, x, 2.0, bw, 1.06, label, None, col)
        if i < len(chain) - 1:
            d.arrow(s, x + bw + 0.015, 2.45, gp - 0.03)
    d.pill(s, M, 3.26, "REQUIRES DMRC DATA")
    d.pill(s, M + 2.3, 3.26, "IMPLEMENTED")
    d.text(s, M + 4.0, 3.26, 7.4, 0.27,
           "Only the first block is missing. Everything downstream is built and "
           "held to a conformance suite.", size=11, anchor=MSO_ANCHOR.MIDDLE)
    four = [("OFFICIAL DMRC REALTIME", "Not available today", T.VIOLET),
            ("METROPULSE ESTIMATE", "Interpolated from the timetable", T.AMBER),
            ("AI PREDICTION", "Modelled, and labelled as modelled", T.PRIMARY),
            ("SCHEDULED DATA", "The published GTFS timetable", T.SLATE)]
    for i, (title, sub, col) in enumerate(four):
        x = M + i * (cw + 0.21)
        d.rect(s, x, 4.0, cw, 1.66, T.CARD, radius=True)
        d.rect(s, x + 0.22, 4.18, 0.44, 0.13, col, radius=True)
        d.text(s, x + 0.22, 4.4, cw - 0.44, 0.5, title, size=10.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.22, 4.92, cw - 0.44, 0.6, sub, size=10.5)
    d.text(s, M, 5.82, W - M * 2, 0.32,
           "These four are already visually distinct in the product: the app "
           "shows SCHEDULE, never LIVE, over interpolated positions.",
           size=11.5, bold=True, colour=T.INK)
    d.foot(s, "tests/test_adapter_conformance.py holds any position source to "
              "the same contract, including the shipped decoder.")

    # -------------------------------------------------------- 08 AI + voice
    s = d.slide()
    d.header(s, "AI and voice", "What runs today, and what is waiting on data", "08")
    d.rect(s, M, 2.4, 5.7, 3.1, T.CARD, radius=True)
    d.text(s, M + 0.32, 2.58, 5.1, 0.3, "Implemented", size=14, bold=True,
           colour=T.TEAL, font=T.HEAD)
    d.bullets(s, M + 0.32, 2.99, 5.06, 3.2, [
        "On-device voice assistant — speech in, spoken answer out",
        "Deterministic intent classifier: route, when to leave, which coach, "
        "fare, next station, running late",
        "Offline station search across names, aliases and landmarks",
        "Coach recommendation ranking crowding against exit alignment",
        "Delay and commute prediction behind pluggable service ports",
    ], size=11, space_after=8)
    d.pill(s, M + 0.32, 4.90, "IMPLEMENTED")
    d.rect(s, M + 6.1, 2.4, 5.83, 3.1, T.CARD_WARN, radius=True)
    d.text(s, M + 6.42, 2.58, 5.2, 0.3, "Constrained by data, not by code",
           size=14, bold=True, colour=T.WARN_HEAD, font=T.HEAD)
    d.bullets(s, M + 6.42, 2.99, 5.19, 3.2, [
        "Crowd prediction currently falls back to a generic prior — there are "
        "no occupancy observations to learn from",
        "The prediction interfaces are already pluggable: a model implements "
        "the same port with no schema change",
        "The assistant answers only Delhi Metro questions and declines "
        "everything else by design",
    ], size=11, colour=T.WARN_TEXT, space_after=8)
    d.pill(s, M + 6.42, 4.90, "REQUIRES DMRC DATA")
    d.foot(s, "No large language model is used. The assistant is a "
              "deterministic classifier over the app's own data.")

    # -------------------------------------------------------- 09 accessibility
    s = d.slide()
    d.header(s, "Accessibility", "Step-free guidance, with its evidence attached", "09")
    flow = [("DMRC pathway\ngraph", T.PRIMARY), ("Gate → lift →\nplatform chain", T.PRIMARY),
            ("Reachability\ncheck", T.INK), ("Named gate\nguidance", T.TEAL)]
    for i, (label, col) in enumerate(flow):
        x = M + i * 2.3
        d.step(s, x, 1.95, 2.02, 1.18, label, None, col)
        if i < len(flow) - 1:
            d.arrow(s, x + 2.04, 2.45, 0.24, h=0.18)
    tiers = [("Confirmed", "DMRC's graph connects this gate to a lift-served platform", T.TEAL),
             ("Not mapped", "The station has lifts, but no mapped path from this gate", T.AMBER),
             ("No data", "Nothing is claimed at all", T.SLATE)]
    for i, (title, sub, col) in enumerate(tiers):
        y = 3.45 + i * 0.92
        d.rect(s, M, y, 8.1, 0.8, T.CARD, radius=True)
        d.rect(s, M + 0.24, y + 0.24, 0.16, 0.33, col, radius=True)
        d.text(s, M + 0.58, y + 0.13, 1.8, 0.3, title, size=12, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, M + 0.58, y + 0.43, 7.2, 0.3, sub, size=10.5)
    d.img(s, "station_detail.png", 9.6, 3.45, h=3.4)
    d.text(s, M, 6.3, 8.3, 0.5,
           f"{f('acc_stepfree')} of {f('stations')} stations currently have a "
           "graph-confirmed step-free gate. The app never presents "
           "\"unmapped\" as \"inaccessible\".", size=11, bold=True, colour=T.INK)
    d.foot(s, "Coverage measured against the deployed backend.")

    # -------------------------------------------------------- 10 crowd
    s = d.slide()
    d.header(s, "Crowd management",
             "From data to a decision the passenger can act on", "10")
    chain = [("Approved data", "Hourly load profile\nOD pairs · gates", T.PRIMARY),
             ("Realtime +\nhistorical signals", "Occupancy reports\nOperational feeds", T.VIOLET),
             ("Crowd\nintelligence", "Aggregation with\nprovenance", T.INK),
             ("Detection /\nprediction", "Where and when\nit builds", T.INK),
             ("Passenger\nguidance", "One instruction,\nnot a dashboard", T.TEAL)]
    bw2, gp2 = 2.24, 0.18
    for i, (title, sub, col) in enumerate(chain):
        x = M + i * (bw2 + gp2)
        d.step(s, x, 1.9, bw2, 1.66, title, sub, col)
        if i < len(chain) - 1:
            d.arrow(s, x + bw2 + 0.01, 2.65, gp2 - 0.02, h=0.18)
    d.pill(s, M, 3.72, "APPROVED DATA")
    d.pill(s, M + 1.85, 3.72, "REQUIRES DMRC DATA")
    for i, o in enumerate(["Alternative gate", "Alternative interchange",
                           "Alternative departure time"]):
        x = M + 6.55 + i * 1.95
        d.rect(s, x, 3.68, 1.84, 0.56, T.CARD_GOOD, radius=True)
        d.text(s, x + 0.06, 3.68, 1.72, 0.56, o, size=9.5, colour=T.GOOD_TEXT,
               align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    d.rect(s, M, 4.5, W - M * 2, 1.5, T.INK, radius=True)
    d.text(s, M + 0.36, 4.7, 11.2, 0.36,
           "MetroPulse complements DMRC's operational crowd-management systems "
           "— it does not replace them.", size=14, bold=True, colour="FFFFFF",
           font=T.HEAD)
    d.text(s, M + 0.36, 5.12, 11.2, 0.76,
           "Its role is the passenger-facing half: turning crowd information "
           "into one clear instruction before someone reaches a congested "
           "concourse. Control-room detection, staffing and station regulation "
           "remain DMRC's.", size=11.5, colour="C3D2EC")
    d.foot(s, "Crowd prediction today falls back to a generic prior — no "
              "occupancy observations exist yet. A data gap, not an architectural one.")

    # -------------------------------------------------------- 11 testing
    s = d.slide()
    d.header(s, "Engineering evidence", "What is actually verified", "11")
    stats = [(f("backend_tests"), "backend tests", "pytest, full suite green"),
             (f("app_tests"), "app tests", "Flutter unit and widget"),
             (f("endpoints"), "API endpoints", "live on the deployed backend"),
             (f("migrations"), "schema migrations", "Alembic, applied in production")]
    for i, (big, lab, sub) in enumerate(stats):
        x = M + i * (cw + 0.21)
        d.rect(s, x, 1.9, cw, 1.66, T.CARD, radius=True)
        d.text(s, x + 0.22, 2.0, cw - 0.44, 0.66, big, size=35, bold=True,
               colour=T.TEAL, font=T.HEAD)
        d.text(s, x + 0.22, 2.68, cw - 0.44, 0.3, lab, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.22, 3.0, cw - 0.44, 0.34, sub, size=10, colour=T.MUTED)
    d.rect(s, M, 3.78, 5.7, 1.98, T.CARD, radius=True)
    d.text(s, M + 0.32, 3.93, 5.1, 0.3, "Verified in the field", size=13,
           bold=True, colour=T.INK, font=T.HEAD)
    d.bullets(s, M + 0.32, 4.28, 5.06, 1.4, [
        f"A commuter trial with {f('beta_users')} riders on the Delhi Metro",
        "Every defect they reported was diagnosed, fixed and verified — "
        "station name matching, ticket links, navigation, journey setup",
        "Backend deployed and serving on AWS",
    ], size=11, space_after=7)
    d.rect(s, M + 6.1, 3.78, 5.83, 1.98, T.CARD_WARN, radius=True)
    d.text(s, M + 6.42, 3.93, 5.2, 0.3, "Not yet measured", size=13, bold=True,
           colour=T.WARN_HEAD, font=T.HEAD)
    d.bullets(s, M + 6.42, 4.28, 5.19, 1.4, [
        "Journey completion rate — [DATA REQUIRED]",
        "Retention — [DATA REQUIRED]",
        "Crash-free rate — [DATA REQUIRED]",
    ], size=11, colour=T.WARN_TEXT, space_after=7)
    d.text(s, M, 5.96, 11.9, 0.3,
           "The trial was defect-driven, not instrumented: riders reported "
           "what was broken. The three metrics on the right need the "
           "consent-gated analytics build, which has not shipped.",
           size=11)
    d.foot(s, "No commuter metric is stated that has not been measured.")

    # -------------------------------------------------------- 12 pilot
    s = d.slide()
    d.header(s, "Proposed DMRC / MICE pilot", "Four phases, each with an exit check", "12")
    phases = [("01", "Technical integration",
               "Connect the realtime adapter to a DMRC feed in a test environment",
               "Data flows end to end"),
              ("02", "Validation",
               "Compare app output against ground truth on selected corridors",
               "Accuracy agreed with DMRC"),
              ("03", "Commuter pilot",
               "A limited public group on one or two lines",
               "Usage and feedback captured"),
              ("04", "Evaluation",
               "Joint review of accuracy, usefulness and crowd guidance",
               "Decision to extend or stop")]
    for i, (num, title, body, exit_check) in enumerate(phases):
        x = M + i * 3.02
        d.rect(s, x, 1.95, 2.83, 3.55, T.CARD, radius=True)
        d.text(s, x + 0.24, 2.1, 1.2, 0.5, num, size=24, bold=True,
               colour=T.RULE, font=T.HEAD)
        d.text(s, x + 0.24, 2.64, 2.36, 0.66, title, size=13.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.24, 3.32, 2.36, 1.24, body, size=11)
        d.rect(s, x + 0.24, 4.66, 2.36, 0.66, T.CARD_GOOD, radius=True)
        d.text(s, x + 0.36, 4.66, 2.12, 0.66, exit_check, size=9.5,
               colour=T.GOOD_TEXT, anchor=MSO_ANCHOR.MIDDLE)
    d.pill(s, M, 5.72, "PROPOSED")
    d.text(s, M + 1.35, 5.72, 8.5, 0.27,
           "Timelines to be agreed with DMRC — no dates are asserted here.",
           size=11, anchor=MSO_ANCHOR.MIDDLE)
    d.foot(s, "Each phase has a stopping point, so a pilot that is not working "
              "can be stopped at an agreed moment rather than drifting.")

    # -------------------------------------------------------- 13 value
    s = d.slide()
    d.header(s, "Value to DMRC", "Five areas, none of them operational", "13")
    vals = [("Passenger experience",
             "Guidance at the moment of each decision, in the rider's pocket"),
            ("Accessibility",
             "Step-free guidance built on DMRC's own pathway data, with evidence tiers"),
            ("Crowd management",
             "Passenger-facing guidance that complements control-room systems"),
            ("Digital innovation",
             "A working application demonstrating what open data enables"),
            ("Data utilisation",
             "Approved OTD datasets turned into daily commuter value")]
    for i, (title, body) in enumerate(vals):
        col, row = i % 3, i // 3
        x, y = M + col * 4.0, 1.95 + row * 2.2
        d.rect(s, x, y, 3.8, 1.98, T.CARD, radius=True)
        d.rect(s, x + 0.26, y + 0.26, 0.36, 0.36, T.PRIMARY, radius=True)
        d.text(s, x + 0.26, y + 0.26, 0.36, 0.36, str(i + 1), size=12,
               bold=True, colour="FFFFFF", font=T.HEAD, align=PP_ALIGN.CENTER,
               anchor=MSO_ANCHOR.MIDDLE)
        d.text(s, x + 0.74, y + 0.28, 2.86, 0.36, title, size=13, bold=True,
               colour=T.INK, font=T.HEAD, anchor=MSO_ANCHOR.MIDDLE)
        d.text(s, x + 0.26, y + 0.76, 3.3, 1.06, body, size=11)
    d.foot(s, "MetroPulse is a commuter-facing layer. It seeks no role in "
              "signalling, operations or station control.")

    # -------------------------------------------------------- 14 asks
    s = d.slide()
    d.header(s, "What MetroPulse needs from DMRC", "Four requests, in priority order", "14")
    asks = [("Realtime data",
             "Train positions or arrival predictions for Metro rolling stock. The public "
             "OTD VehiclePositions endpoint is Delhi's citywide bus feed, not Metro.", T.VIOLET),
            ("Operational data",
             "Station occupancy or gate throughput, and escalator inventory — none of "
             "which exist in the approved datasets.", T.VIOLET),
            ("Technical guidance",
             "Feed format, identifier conventions and update cadence, so the adapter "
             "maps correctly the first time.", T.PRIMARY),
            ("Pilot collaboration",
             "A named technical contact, and agreement on the evaluation criteria for "
             "each pilot phase.", T.PRIMARY)]
    for i, (title, body, col) in enumerate(asks):
        y = 1.92 + i * 1.2
        d.rect(s, M, y, W - M * 2, 1.06, T.CARD, radius=True)
        d.rect(s, M + 0.26, y + 0.3, 0.16, 0.46, col, radius=True)
        d.text(s, M + 0.62, y + 0.16, 3.0, 0.36, title, size=14, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, M + 0.62, y + 0.54, 10.6, 0.46, body, size=11)
    d.foot(s, "MetroPulse is not requesting funding in this submission.")

    # -------------------------------------------------------- 15 vision
    s = d.slide()
    d.header(s, "Long-term vision", "Delhi Metro first, then the rest of the journey", "15")
    horizons = [("Now", "Delhi Metro",
                 "Schedule-based guidance on approved open data", T.TEAL, False),
                ("With DMRC data", "Delhi Metro, live",
                 "Realtime positions, measured crowding, accessible routing", T.PRIMARY, True),
                ("Later", "Multimodal Delhi",
                 "Metro plus bus and last-mile, as one continuous journey", T.SLATE, False)]
    for i, (kick, title, body, col, dark) in enumerate(horizons):
        x = M + i * 4.0
        d.rect(s, x, 2.05, 3.8, 3.15, T.INK if dark else T.CARD, radius=True)
        d.text(s, x + 0.3, 2.3, 3.2, 0.28, kick.upper(), size=10, bold=True,
               colour="7FE3D2" if dark else col, font=T.HEAD)
        d.text(s, x + 0.3, 2.68, 3.2, 0.76, title, size=19, bold=True,
               colour="FFFFFF" if dark else T.INK, font=T.HEAD)
        d.text(s, x + 0.3, 3.54, 3.22, 1.4, body, size=12,
               colour="C3D2EC" if dark else T.BODY)
    d.text(s, M, 5.55, 11.2, 0.32,
           "Each step depends on the one before it. Multimodal expansion is not "
           "proposed for the pilot.", size=11.5)
    d.foot(s, "Bus and last-mile integration already exists in limited form via "
              "the licensed Delhi Transport Stack API.")

    # -------------------------------------------------------- 16 close
    s = d.slide(dark=True)
    d.text(s, M, 2.3, 9.6, 2.0, "Make every Delhi Metro\njourney predictable.",
           size=44, bold=True, colour="FFFFFF", font=T.HEAD, spacing=1.2)
    d.text(s, M, 4.62, 8.0, 0.36, f"MetroPulse  ·  {f('founder')}", size=15,
           colour="9DB4DC")
    d.text(s, M, 5.05, 8.0, 0.32, f"Contact details: {f('contact')}", size=12,
           colour="6E86B4")

    render_pptx(d.rec, out_path)
    render_pdf(d.rec, out_path.replace('.pptx', '.pdf'))
    return out_path
