"""MetroPulse — DMRC / MICE pitch deck.

Twenty slides, diagram-led, one core message each. Every figure comes from
`facts.py`; every capability carries one of the five status labels. Escalators
are deliberately shown as absent on the OTD slide because the approved
artifacts contain none, and the public VehiclePositions feed is shown as
measured rather than described, because the measurement is the whole point.

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

    # ---------------------------------------------------------- composites
    def statline(self, s, x, y, w, big, label, sub, *, colour=None):
        """A large number with its label and its source underneath."""
        self.rect(s, x, y, w, 1.66, T.CARD, radius=True)
        self.text(s, x + 0.22, y + 0.1, w - 0.44, 0.66, big, size=35, bold=True,
                  colour=colour or T.PRIMARY, font=T.HEAD)
        self.text(s, x + 0.22, y + 0.78, w - 0.44, 0.3, label, size=12.5,
                  bold=True, colour=T.INK, font=T.HEAD)
        self.text(s, x + 0.22, y + 1.1, w - 0.44, 0.34, sub, size=10,
                  colour=T.MUTED)

    def labelled(self, s, x, y, w, label, text, *, colour):
        """A colour chip, a bold label and a line of text — an evidence row."""
        self.rect(s, x, y + 0.05, 0.13, 0.34, colour, radius=True)
        self.text(s, x + 0.3, y, 2.6, 0.3, label, size=10.5, bold=True,
                  colour=T.INK, font=T.HEAD)
        self.text(s, x + 3.0, y, w - 3.0, 0.42, text, size=11, colour=T.BODY)


# =========================================================== build the deck
def build(out_path: str) -> str:
    d = Deck()
    cw = (W - M * 2 - 0.21 * 3) / 4          # four-across card width

    # ---------------------------------------------------------- 01 title
    s = d.slide(dark=True)
    d.rect(s, M, 1.52, 4.75, 0.36, T.INK_SOFT, radius=True)
    d.text(s, M, 1.52, 4.75, 0.36, "NO OFFICIAL REALTIME METRO DATA TODAY",
           size=9, bold=True, colour="7FE3D2", font=T.HEAD,
           align=CENTER, anchor=MIDDLE)
    d.text(s, M, 2.2, 8.6, 1.2, "MetroPulse", size=60, bold=True,
           colour="FFFFFF", font=T.HEAD)
    d.text(s, M, 3.45, 8.6, 0.5, "The Delhi Metro journey companion",
           size=20, colour="9DB4DC")
    d.text(s, M, 4.15, 8.0, 1.0,
           "A working Android application and backend, built on approved Delhi "
           "Open Transit Data and tested with real commuters.\nSubmitted as a "
           "MICE pre-application / innovation proposal.",
           size=12.5, colour="C3D2EC", spacing=1.5)
    d.text(s, M, 6.45, 8.0, 0.32,
           f"{f('founder')}  ·  Independent developer  ·  {f('incorporation')}",
           size=11, colour="7C93BE")
    d.img(s, "home.png", 9.75, 0.95, h=5.6)

    # -------------------------------------------------------- 02 problem
    s = d.slide()
    d.header(s, "The commuter problem",
             "A journey is eight decisions, not one route", "02")
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
    for i, (q, why) in enumerate(items):
        col, row = i % 4, i // 4
        x = M + col * (cw + 0.21)
        y = 2.15 + row * 1.86
        d.rect(s, x, y, cw, 1.62, T.CARD, radius=True)
        d.text(s, x + 0.22, y + 0.16, 0.4, 0.3, str(i + 1), size=15, bold=True,
               colour=T.PRIMARY, font=T.HEAD)
        d.text(s, x + 0.62, y + 0.16, cw - 0.84, 0.3, q, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.22, y + 0.68, cw - 0.44, 0.8, why, size=10.5)
    d.foot(s, "Each decision has a different answer at a different moment. "
              "A route plan answers only the first.")

    # ----------------------------------------- 03 why planning is not enough
    s = d.slide()
    d.header(s, "Why route planning is not enough",
             "Planning ends where the journey begins", "03")
    chain = ["Route", "Station", "Platform", "Interchange", "Exit",
             "Accessibility", "Realtime", "Crowd"]
    bw, gap = 1.35, 0.155
    for i, label in enumerate(chain):
        x = M + i * (bw + gap)
        answered = i == 0
        d.step(s, x, 2.3, bw, 0.86, label, "",
               T.CARD if answered else T.INK, light=not answered)
        if i < len(chain) - 1:
            d.arrow(s, x + bw + 0.012, 2.65, gap - 0.024)
    d.text(s, M, 3.28, bw, 0.4, "answered by a\nroute planner", size=9,
           colour=T.MUTED, align=CENTER)
    d.text(s, M + bw + gap, 3.28, 11.0, 0.3,
           "left to the rider, in the station, under time pressure", size=9.5,
           colour=T.MUTED)
    d.rect(s, M, 4.1, 5.7, 2.05, T.CARD, radius=True)
    d.text(s, M + 0.32, 4.3, 5.1, 0.3, "A route planner gives you", size=13,
           bold=True, colour=T.MUTED, font=T.HEAD)
    d.bullets(s, M + 0.32, 4.72, 5.06, 1.3, [
        "One answer, computed once, before you leave",
        "No awareness of where you are standing",
        "No gate, platform, coach or exit guidance",
    ], size=12, space_after=9)
    d.rect(s, M + 6.1, 4.1, 5.83, 2.05, T.INK, radius=True)
    d.text(s, M + 6.42, 4.3, 5.2, 0.3, "MetroPulse adds", size=13, bold=True,
           colour="7FE3D2", font=T.HEAD)
    d.bullets(s, M + 6.42, 4.72, 5.19, 1.3, [
        "Guidance that changes as the journey moves",
        "Gate, platform, coach and exit when each one matters",
        "Every claim labelled with where it came from",
    ], size=12, colour="D7E0F2", space_after=9)
    d.foot(s, "The difference is not more data on one screen — it is the right "
              "single fact at the right minute.")

    # ---------------------------------------------------- 04 the experience
    s = d.slide()
    d.header(s, "The MetroPulse experience",
             "One continuous journey, not a list of screens", "04")
    shots = [("home.png", "Home", "Context before search"),
             ("planner.png", "Plan", "Route and preferences"),
             ("journey_mode.png", "Journey Mode", "Guidance in the moment"),
             ("station_detail.png", "Station", "Gates, exits, facilities"),
             ("network_map.png", "Network", "Octilinear schematic")]
    iw, gapx = 1.9, 0.45
    for i, (fn, title, sub) in enumerate(shots):
        x = M + i * (iw + gapx)
        d.img(s, fn, x, 1.9, h=4.0)
        d.text(s, x - 0.2, 6.02, iw + 0.4, 0.28, title, size=12, bold=True,
               colour=T.INK, font=T.HEAD, align=CENTER)
        d.text(s, x - 0.25, 6.3, iw + 0.5, 0.28, sub, size=9.5, colour=T.MUTED,
               align=CENTER)
    d.pill(s, W - M - 1.55, 0.8, "IMPLEMENTED")
    d.foot(s, "Screenshots taken from the current release build running "
              "against the deployed backend.")

    # ------------------------------------------------- 05 a working product
    s = d.slide()
    d.header(s, "This is a working product", "Evidence, not intent", "05")
    stats = [(f("backend_tests"), "backend tests", "pytest, full suite green"),
             (f("app_tests"), "app tests", "Flutter unit and widget"),
             (f("endpoints"), "API endpoints", "live on the deployed backend"),
             (f("beta_users"), "commuters", "used the app on the Delhi Metro")]
    for i, (big, lab, sub) in enumerate(stats):
        d.statline(s, M + i * (cw + 0.21), 1.95, cw, big, lab, sub,
                   colour=T.TEAL)
    rows = [
        (T.TEAL, "APPLICATION",
         "Android release build, signed and installed; offline-first client."),
        (T.TEAL, "BACKEND",
         f"Deployed on AWS and serving today; {f('migrations')} schema "
         "migrations applied in production."),
        (T.PRIMARY, "OFFICIAL DATA",
         f"{f('pathway_stations')} stations of DMRC pathway data loaded and "
         "matched to the GTFS network."),
        (T.TEAL, "COMMUTER TRIAL",
         f"{f('beta_users')} riders; every defect they reported diagnosed, "
         "fixed and verified in the repository."),
    ]
    for i, (col, lab, txt) in enumerate(rows):
        d.labelled(s, M, 3.95 + i * 0.62, W - M * 2, lab, txt, colour=col)
    d.foot(s, "No commuter usage rate is claimed. The trial produced a fix "
              "record, and the fix record is the evidence.")

    # -------------------------------------------------------- 06 OTD data
    s = d.slide()
    d.header(s, "Official OTD data already integrated",
             "Loaded, matched to GTFS stops, and served", "06")
    otd = [(f("lifts"), "lifts", "DMRC GTFS-Pathways"),
           (f("gates"), "entry / exit gates", "DMRC GTFS-Pathways"),
           (f("platforms"), "platforms", "DMRC GTFS-Pathways"),
           (f("pathway_stations"), "stations mapped",
            f"{f('pathway_lines')} lines covered")]
    for i, (big, lab, sub) in enumerate(otd):
        d.statline(s, M + i * (cw + 0.21), 1.95, cw, big, lab, sub)
    d.pill(s, M, 3.82, "APPROVED DATA")
    d.rect(s, M, 4.35, 5.7, 1.95, T.CARD, radius=True)
    d.text(s, M + 0.32, 4.55, 5.1, 0.3, "Also integrated", size=13, bold=True,
           colour=T.INK, font=T.HEAD)
    d.bullets(s, M + 0.32, 4.95, 5.06, 1.2, [
        f"Station and gate registry — {f('gate_registry')} records",
        f"Hourly station load profile — {f('hourly_profile')} entries",
        f"Origin–destination top pairs — {f('od_origins')} origins",
    ], size=11.5, space_after=7)
    d.rect(s, M + 6.1, 4.35, 5.83, 1.95, T.CARD_WARN, radius=True)
    d.text(s, M + 6.42, 4.55, 5.2, 0.3,
           "Escalators: not present in the approved data", size=13, bold=True,
           colour=T.WARN_HEAD, font=T.HEAD)
    d.text(s, M + 6.42, 4.95, 5.19, 1.2,
           f"All five normalized OTD artifacts contain {f('escalators')} "
           "escalator records. MetroPulse therefore makes no escalator claim "
           "anywhere in the product. Escalator inventory is on the list of "
           "data requested from DMRC.", size=11, colour=T.WARN_TEXT)
    d.foot(s, "Counts read directly from the loaded artifacts, not estimated.")

    # ------------------------------------------ 07 today vs DMRC realtime
    s = d.slide()
    d.header(s, "Today vs with DMRC realtime",
             "One missing input, six different answers", "07")
    compare = [
        ("Train position", "Interpolated from the timetable",
         "Actual position from the feed"),
        ("Arrival time", "Scheduled, labelled SCHEDULE",
         "Predicted, and labelled LIVE"),
        ("Disruption", "Rider reports only",
         "Detected from the feed within seconds"),
        ("Journey tracking", "GPS above ground, stop-count below",
         "Confirmed against the train the rider is on"),
        ("Crowd guidance", "A generic prior, the same everywhere",
         "Measured loading, per line and hour"),
        ("Interchange advice", "Static walking allowance",
         "Timed against the connecting train"),
    ]
    colw = (W - M * 2 - 0.24) / 2
    d.rect(s, M, 1.95, colw, 0.44, T.CARD, radius=True)
    d.text(s, M + 0.24, 1.95, colw - 0.48, 0.44, "TODAY — SCHEDULE ONLY",
           size=11, bold=True, colour=T.MUTED, font=T.HEAD, anchor=MIDDLE)
    d.rect(s, M + colw + 0.24, 1.95, colw, 0.44, T.INK, radius=True)
    d.text(s, M + colw + 0.48, 1.95, colw - 0.48, 0.44,
           "WITH A DMRC REALTIME FEED", size=11, bold=True, colour="7FE3D2",
           font=T.HEAD, anchor=MIDDLE)
    for i, (row, now, later) in enumerate(compare):
        y = 2.56 + i * 0.6
        d.text(s, M + 0.24, y, 2.3, 0.3, row, size=11, bold=True, colour=T.INK,
               font=T.HEAD)
        d.text(s, M + 2.6, y, colw - 2.84, 0.42, now, size=10.5, colour=T.MUTED)
        d.text(s, M + colw + 0.48, y, colw - 0.72, 0.42, later, size=10.5,
               colour=T.INK)
    d.pill(s, M, 6.26, "REQUIRES DMRC DATA")
    d.text(s, M + 2.45, 6.26, 9.4, 0.3,
           "Nothing on the right needs a new application. Each one is a "
           "different value on the same screen.",
           size=11.5, colour=T.INK, anchor=MIDDLE)
    d.foot(s, "The interface does not change when the feed arrives — the "
              "provenance label and the number behind it do.")

    # ------------------------------------------------ 08 realtime architecture
    s = d.slide()
    d.header(s, "Realtime architecture",
             "The adapter boundary already exists and is tested", "08")
    blocks = [("DMRC realtime", T.VIOLET), ("Adapter", T.PRIMARY),
              ("Validation", T.PRIMARY), ("ID mapping", T.PRIMARY),
              ("Normalized\nposition", T.INK), ("Redis", T.INK),
              ("WebSocket", T.INK), ("Flutter app", T.TEAL)]
    bw, gap = 1.35, 0.155
    for i, (label, col) in enumerate(blocks):
        x = M + i * (bw + gap)
        d.step(s, x, 2.05, bw, 1.18, label, "", col, light=True)
        if i < len(blocks) - 1:
            d.arrow(s, x + bw + 0.012, 2.56, gap - 0.024)
    d.pill(s, M, 3.45, "REQUIRES DMRC DATA")
    d.pill(s, M + 2.6, 3.45, "IMPLEMENTED")
    d.text(s, M + 4.55, 3.45, 7.4, 0.3,
           "Only the first block is missing. Everything downstream is built "
           "and held to a conformance suite.", size=11.5, anchor=MIDDLE)
    guards = [
        ("VALIDATION", "Impossible positions are rejected — null-island, "
         "out-of-range and NaN coordinates never reach the store."),
        ("STALENESS", "Past the threshold a position is dropped and the app "
         "falls back to SCHEDULE and says so."),
        ("CONFORMANCE", "tests/test_adapter_conformance.py holds every "
         "position source to the same contract, including the shipped one."),
    ]
    for i, (lab, txt) in enumerate(guards):
        d.labelled(s, M, 4.2 + i * 0.58, W - M * 2, lab, txt, colour=T.TEAL)
    d.rect(s, M, 6.0, W - M * 2, 0.5, T.CARD_WARN, radius=True)
    d.text(s, M + 0.24, 6.0, W - M * 2 - 0.48, 0.5,
           "Public realtime feed investigated — verified as Delhi's bus GPS, "
           "not Metro — ingestion intentionally disabled. Full measurement in "
           "the Realtime Data Request and the proposal appendix.",
           size=11, colour=T.WARN_TEXT, anchor=MIDDLE)
    d.foot(s, "Connecting an official feed is an adapter and configuration "
              "task, not a rebuild.")

    # ------------------------------------------------------- 09 AI + voice
    s = d.slide()
    d.header(s, "AI and voice", "What runs today, and what is waiting on data",
             "09")
    d.rect(s, M, 2.0, 5.7, 3.05, T.CARD, radius=True)
    d.text(s, M + 0.32, 2.18, 5.1, 0.3, "Implemented", size=14, bold=True,
           colour=T.TEAL, font=T.HEAD)
    d.bullets(s, M + 0.32, 2.6, 5.06, 2.1, [
        "On-device voice assistant — speech in, spoken answer out",
        "Deterministic intent classifier: route, when to leave, which coach, "
        "fare, next station, running late",
        "Offline station search across names, aliases and landmarks",
        "Coach recommendation ranking crowding against exit alignment",
    ], size=11, space_after=8)
    d.pill(s, M + 0.32, 4.55, "IMPLEMENTED")
    d.rect(s, M + 6.1, 2.0, 5.83, 3.05, T.CARD_WARN, radius=True)
    d.text(s, M + 6.42, 2.18, 5.2, 0.3, "Constrained by data, not by code",
           size=14, bold=True, colour=T.WARN_HEAD, font=T.HEAD)
    d.bullets(s, M + 6.42, 2.6, 5.19, 2.1, [
        "Crowd prediction falls back to a generic prior — there are no "
        "occupancy observations to learn from",
        "The prediction interfaces are already pluggable: a model implements "
        "the same port with no schema change",
        "The assistant answers only Delhi Metro questions and declines "
        "everything else by design",
    ], size=11, colour=T.WARN_TEXT, space_after=8)
    d.pill(s, M + 6.42, 4.55, "REQUIRES DMRC DATA")
    d.text(s, M, 5.4, 11.9, 0.8,
           "No large language model is used and no rider utterance leaves the "
           "device. The assistant is a deterministic classifier over "
           "MetroPulse's own data, which is why it runs offline and cannot "
           "invent an answer.", size=11.5, colour=T.INK)
    d.foot(s, "Voice is a convenience layer over the same guidance, not a "
              "separate product surface.")

    # ---------------------------------------------------- 10 accessibility
    s = d.slide()
    d.header(s, "Accessibility",
             "Step-free guidance, with its evidence attached", "10")
    for i, (title, col) in enumerate([("DMRC pathway\ngraph", T.PRIMARY),
                                      ("Gate → lift →\nplatform chain", T.PRIMARY),
                                      ("Reachability\ncheck", T.INK),
                                      ("Named gate\nguidance", T.TEAL)]):
        x = M + i * 2.53
        d.step(s, x, 2.0, 2.2, 1.28, title, "", col, light=True)
        if i < 3:
            d.arrow(s, x + 2.21, 2.56, 0.31)
    tiers = [("Confirmed", "DMRC's graph connects this gate to a lift-served "
                           "platform", T.TEAL),
             ("Not mapped", "The station has lifts, but no mapped path from "
                            "this gate", T.AMBER),
             ("No data", "Nothing is claimed at all", T.SLATE)]
    for i, (label, body, col) in enumerate(tiers):
        y = 3.55 + i * 0.84
        d.rect(s, M, y, 8.9, 0.72, T.CARD, radius=True)
        d.rect(s, M + 0.24, y + 0.14, 0.16, 0.44, col, radius=True)
        d.text(s, M + 0.62, y + 0.05, 2.2, 0.3, label, size=12, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, M + 0.62, y + 0.35, 8.0, 0.32, body, size=10.5)
    d.img(s, "accessibility.png", 9.95, 3.4, h=3.0)
    d.text(s, M, 6.16, 8.9, 0.34,
           f"{f('acc_stepfree')} of {f('stations')} stations currently have a "
           "graph-confirmed step-free gate. The app never presents "
           "\"unmapped\" as \"inaccessible\".",
           size=11.5, bold=True, colour=T.INK)
    d.foot(s, "Where the path is unknown the app says so and offers DMRC's own "
              "lift helpline rather than guessing.")

    # ------------------------------------------------- 11 crowd management
    s = d.slide()
    d.header(s, "Crowd intelligence",
             "Guidance before the crowd forms", "11")
    inputs = ["Official DMRC\ndata", "Station\ninfrastructure",
              "Historical\npatterns", "Events", "Aggregated rider\nobservations"]
    iw2 = 2.24
    for i, lab in enumerate(inputs):
        x = M + i * (iw2 + 0.15)
        col = T.PRIMARY if i == 0 else (T.SLATE if i < 4 else T.AMBER)
        d.step(s, x, 1.92, iw2, 0.92, lab, "", col, light=True)
    d.rect(s, W / 2 - 0.035, 2.9, 0.07, 0.26, T.RULE)
    d.rect(s, M + 3.0, 3.2, W - M * 2 - 6.0, 0.62, T.INK, radius=True)
    d.text(s, M + 3.0, 3.2, W - M * 2 - 6.0, 0.62, "CROWD INTELLIGENCE",
           size=14, bold=True, colour="7FE3D2", font=T.HEAD, align=CENTER,
           anchor=MIDDLE)
    d.rect(s, W / 2 - 0.035, 3.88, 0.07, 0.26, T.RULE)
    for i, (lab, sub) in enumerate([("Detect", "where crowding is building"),
                                    ("Predict", "where it will build next"),
                                    ("Recommend", "one action, not a dashboard")]):
        x = M + 1.6 + i * 3.2
        d.rect(s, x, 4.18, 2.9, 0.7, T.CARD, radius=True)
        d.text(s, x + 0.2, 4.25, 2.5, 0.3, lab, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.2, 4.55, 2.5, 0.3, sub, size=9.5, colour=T.MUTED)
    outs = ['"Use Gate 3 instead"', '"Leave 8 minutes earlier"',
            '"Use the next interchange"', '"Lift route preferred today"']
    ow = (W - M * 2 - 0.15 * 3) / 4
    for i, lab in enumerate(outs):
        x = M + i * (ow + 0.15)
        d.rect(s, x, 5.1, ow, 0.58, T.CARD_GOOD, radius=True)
        d.text(s, x, 5.1, ow, 0.58, lab, size=11, bold=True,
               colour=T.GOOD_TEXT, font=T.HEAD, align=CENTER, anchor=MIDDLE)
    d.rect(s, M, 5.86, W - M * 2, 0.62, T.CARD, radius=True)
    d.text(s, M + 0.24, 5.86, W - M * 2 - 0.48, 0.62,
           "Guide the passenger before they enter the bottleneck — "
           "passenger-flow optimisation, not a crowd alert. MetroPulse "
           "complements DMRC's operational crowd management: control-room "
           "detection, staffing and station regulation remain DMRC's.",
           size=11, bold=True, colour=T.INK, anchor=MIDDLE)
    d.foot(s, "Crowd prediction today falls back to a generic prior — no "
              "occupancy observations exist yet. A data gap, not an "
              "architectural one.")

    # ------------------------------------------------- 13 why MetroPulse
    s = d.slide()
    d.header(s, "Why MetroPulse",
             "Route-centric planning vs contextual journey intelligence", "12")
    colw = (W - M * 2 - 0.24) / 2
    d.rect(s, M, 2.0, colw, 3.4, T.CARD, radius=True)
    d.text(s, M + 0.32, 2.2, colw - 0.64, 0.34, "Route-centric planning",
           size=14, bold=True, colour=T.MUTED, font=T.HEAD)
    d.bullets(s, M + 0.32, 2.68, colw - 0.64, 2.4, [
        "Answers one question, before the journey starts",
        "The same answer for every rider on the platform",
        "No provenance — the rider cannot tell schedule from live",
        "Accessibility is an afterthought or absent",
        "Ends at the destination station name",
    ], size=11.5, space_after=9)
    d.rect(s, M + colw + 0.24, 2.0, colw, 3.4, T.INK, radius=True)
    d.text(s, M + colw + 0.56, 2.2, colw - 0.64, 0.34,
           "Contextual journey intelligence", size=14, bold=True,
           colour="7FE3D2", font=T.HEAD)
    d.bullets(s, M + colw + 0.56, 2.68, colw - 0.64, 2.4, [
        "Answers the next question, at the moment it is asked",
        "Adapts to gate, platform, coach, interchange and exit",
        "Every claim carries the level it came from",
        "Step-free routing built on DMRC's own pathway graph",
        "Ends at the street, with the right exit and the walk beyond it",
    ], size=11.5, colour="D7E0F2", space_after=9)
    d.text(s, M, 5.7, W - M * 2, 0.6,
           "Both start from the same timetable. The difference is what happens "
           "in the forty minutes after the rider stops looking at a route.",
           size=12.5, bold=True, colour=T.INK)
    d.foot(s, "MetroPulse is not a competitor to journey planning. It is the "
              "layer that begins where planning stops.")

    # -------------------------------------------- 14 real-world validation
    s = d.slide()
    d.header(s, "Real-world validation",
             f"{f('beta_users')} commuters found what no test suite would",
             "13")
    defects = [
        ("Station names could not be found",
         f"Matching was literal, so {f('hyphenated_stops')} hyphenated names "
         "never matched what riders type"),
        ("The assistant would not give a route",
         "Only the literal phrase \"route to\" triggered planning"),
        ("\"Set up a new journey\" did nothing",
         "No matching intent existed; it answered but acted on nothing"),
        ("A home station could not be set",
         "The picker opened search but never returned the chosen station"),
        ("No way back from a saved-stations screen",
         "A pushed route with a custom header and no back control"),
        ("The app sat on \"connecting\"",
         "Release builds defaulted to a developer machine address"),
    ]
    for i, (what, why) in enumerate(defects):
        col, row = i % 2, i // 2
        x = M + col * (4.86 + 0.21)
        y = 1.95 + row * 1.16
        d.rect(s, x, y, 4.86, 1.0, T.CARD, radius=True)
        d.text(s, x + 0.24, y + 0.1, 3.7, 0.3, what, size=11.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.24, y + 0.42, 4.4, 0.5, why, size=10, colour=T.BODY)
        d.text(s, x + 3.95, y + 0.1, 0.67, 0.3, "FIXED", size=9, bold=True,
               colour=T.TEAL, font=T.HEAD, align=RIGHT)
    d.img(s, "search_hyphen_fix.png", 10.95, 1.95, h=3.55)
    d.text(s, M, 5.62, 9.9, 0.7,
           "Every one of these was diagnosed, fixed and verified, and each fix "
           "is traceable in the repository. That is why the trial is stronger "
           "evidence than a satisfaction score: each item can be independently "
           "checked.", size=11.5, colour=T.INK)
    d.foot(s, "The trial was defect-driven, not instrumented — so completion "
              "and retention are reported as [DATA REQUIRED], not estimated.")

    # ---------------------------------------------------- 12 data trust
    s = d.slide()
    d.header(s, "Data trust and privacy",
             "Five levels of certainty, one privacy path", "14")
    levels = [
        ("LEVEL 1", "Official DMRC information", T.PRIMARY,
         "Advisories and operational facts published by DMRC",
         "REQUIRES DMRC DATA"),
        ("LEVEL 2", "Official OTD / static data", T.PRIMARY,
         "GTFS timetable, pathways, gates — loaded and served today",
         "APPROVED DATA"),
        ("LEVEL 3", "MetroPulse calculation", T.TEAL,
         "Routing, fares, interchange timing — derived from level 2",
         "IMPLEMENTED"),
        ("LEVEL 4", "AI prediction", T.AMBER,
         "Delay and coach models — shown as estimates, never as fact",
         "IMPLEMENTED"),
        ("LEVEL 5", "Crowdsourced observation", T.SLATE,
         "Rider reports — used only after independent confirmation",
         "IMPLEMENTED"),
    ]
    for i, (lv, name, col, why, status) in enumerate(levels):
        y = 1.95 + i * 0.78
        d.rect(s, M, y, 9.1, 0.66, T.CARD, radius=True)
        d.rect(s, M, y, 0.16, 0.66, col, radius=True)
        d.text(s, M + 0.4, y + 0.05, 1.1, 0.3, lv, size=9.5, bold=True,
               colour=T.MUTED, font=T.HEAD)
        d.text(s, M + 1.55, y + 0.03, 3.5, 0.32, name, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, M + 1.55, y + 0.35, 7.3, 0.3, why, size=10, colour=T.BODY)
        d.pill(s, M + 5.35, y + 0.05, status)
    d.text(s, 10.05, 1.95, 2.6, 0.26, "PRIVACY BY DESIGN", size=9.5,
           bold=True, colour=T.MUTED, font=T.HEAD)
    priv = ["Rider location", "Opt-in, per journey", "Minimum processing",
            "Journey intelligence", "Aggregated where possible",
            "No individual tracking"]
    for i, lab in enumerate(priv):
        y = 2.28 + i * 0.62
        dark = i in (0, len(priv) - 1)
        d.rect(s, 10.05, y, 2.58, 0.5, T.INK if dark else T.CARD, radius=True)
        d.text(s, 10.05, y, 2.58, 0.5, lab, size=10, bold=dark,
               colour="FFFFFF" if dark else T.INK, font=T.HEAD,
               align=CENTER, anchor=MIDDLE)
        if i < len(priv) - 1:
            d.rect(s, 11.3, y + 0.5, 0.07, 0.12, T.RULE)
    d.text(s, M, 5.96, 9.1, 0.5,
           "A lower level never silently overwrites a higher one, and no level "
           "is displayed without its label. Official, calculated and "
           "rider-generated data are stored separately, so one can never be "
           "mistaken for another.", size=11.5, colour=T.INK)
    d.foot(s, "Rider observations require agreement from multiple independent "
              "riders before they are shown to anyone.")

    # ---------------------------------------------------- 15 90-day pilot
    s = d.slide()
    d.header(s, "Proposed MICE pilot",
             "Ninety days, five stages, three possible endings", "15")
    phases = [
        ("DAYS 0–15", "Technical integration",
         "Adapter connected to a DMRC feed; identifiers mapped", T.PRIMARY,
         "Feed successfully consumed and mapped"),
        ("DAYS 16–30", "Data validation",
         "Freshness, completeness and accuracy measured", T.PRIMARY,
         "Agreed freshness and completeness thresholds achieved"),
        ("DAYS 31–60", "Controlled commuter pilot",
         "A predefined cohort rides selected routes, analytics opt-in",
         T.TEAL, "Cohort completes its test journeys"),
        ("DAYS 61–75", "Crowd + accessibility",
         "Selected guidance scenarios run and measured", T.TEAL,
         "Selected scenarios validated"),
        ("DAYS 76–90", "Evaluation",
         "Joint review, written up including negative findings", T.INK,
         "MICE receives the final performance report"),
    ]
    pw = (W - M * 2 - 0.18 * 4) / 5
    for i, (day, title, body, col, _exit) in enumerate(phases):
        x = M + i * (pw + 0.18)
        d.rect(s, x, 1.95, pw, 2.0, T.CARD, radius=True)
        d.rect(s, x, 1.95, pw, 0.4, col, radius=True)
        d.text(s, x, 1.95, pw, 0.4, day, size=10.5, bold=True,
               colour="FFFFFF", font=T.HEAD, align=CENTER, anchor=MIDDLE)
        d.text(s, x + 0.18, 2.48, pw - 0.36, 0.56, title, size=11.5,
               bold=True, colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.18, 3.1, pw - 0.36, 0.8, body, size=9.5)
        if i < 4:
            d.arrow(s, x + pw + 0.015, 2.9, 0.15)
    d.text(s, M, 4.08, 3.0, 0.22, "EXIT CRITERION", size=8, bold=True,
           colour=T.MUTED, font=T.HEAD)
    for i, (_d, _t, _b, _c, exit_) in enumerate(phases):
        x = M + i * (pw + 0.18)
        d.rect(s, x, 4.3, pw, 0.72, T.CARD_GOOD, radius=True)
        d.text(s, x + 0.14, 4.3, pw - 0.28, 0.72, exit_, size=9,
               colour=T.GOOD_TEXT, anchor=MIDDLE)
    d.text(s, M, 5.18, 3.0, 0.22, "PILOT OUTCOMES", size=8, bold=True,
           colour=T.MUTED, font=T.HEAD)
    outcomes = [("GO", "extend beyond the pilot lines", T.TEAL),
                ("ITERATE", "revise and re-run the failing stage", T.AMBER),
                ("STOP", "wind down; findings delivered anyway", T.SLATE)]
    ow2 = (W - M * 2 - 0.24 * 2) / 3
    for i, (word, sub, col) in enumerate(outcomes):
        x = M + i * (ow2 + 0.24)
        d.rect(s, x, 5.4, ow2, 0.6, T.CARD, radius=True)
        d.rect(s, x + 0.18, 5.53, 0.16, 0.34, col, radius=True)
        d.text(s, x + 0.48, 5.4, 1.35, 0.6, word, size=13, bold=True,
               colour=T.INK, font=T.HEAD, anchor=MIDDLE)
        d.text(s, x + 1.8, 5.4, ow2 - 2.0, 0.6, sub, size=10, anchor=MIDDLE)
    d.pill(s, M, 6.2, "PROPOSED")
    d.text(s, M + 2.45, 6.2, 9.4, 0.3,
           "All three endings are defined in advance, so stopping is a normal "
           "outcome rather than an admission.", size=11.5, anchor=MIDDLE)
    d.foot(s, "No commercial terms are proposed and no funding is requested "
              "in this submission.")

    # --------------------------------------------------------- 16 pilot KPIs
    s = d.slide()
    d.header(s, "Pilot KPIs",
             "One headline number, measured at the moment of use", "16")
    d.rect(s, M, 1.9, W - M * 2, 1.0, T.INK, radius=True)
    d.text(s, M + 0.3, 2.02, 6.0, 0.3,
           "HEADLINE — PASSENGER DECISION SUCCESS RATE", size=11.5, bold=True,
           colour="7FE3D2", font=T.HEAD)
    d.text(s, M + 0.3, 2.36, 11.3, 0.5,
           "Did MetroPulse give the correct actionable instruction at the "
           "moment the passenger needed it? Correct gate · platform · "
           "interchange · accessibility route · exit · realtime status — "
           "measured by in-app confirmation.", size=11, colour="D7E0F2")
    groups = [
        ("PASSENGER", T.TEAL, [
            ("Journey completion rate", "opt-in analytics"),
            ("Step-free journeys completed", "accessibility-mode sessions"),
            ("Rider-reported usefulness", "in-app survey at journey end"),
        ]),
        ("SYSTEM", T.PRIMARY, [
            ("Arrival-time error vs ground truth", "seconds, per line and hour"),
            ("Feed availability and staleness", "adapter conformance metrics"),
            ("Crash-free session rate", "crash reporting, once configured"),
        ]),
        ("CROWD", T.AMBER, [
            ("Congestion detected vs observed", "against DMRC station reports"),
            ("Guidance acted on", "alternative gate or time selected"),
            ("False-positive warnings", "reviewed jointly with DMRC"),
        ]),
    ]
    gw = (W - M * 2 - 0.24 * 2) / 3
    for i, (name, col, rows_) in enumerate(groups):
        x = M + i * (gw + 0.24)
        d.rect(s, x, 3.15, gw, 2.85, T.CARD, radius=True)
        d.rect(s, x, 3.15, gw, 0.42, col, radius=True)
        d.text(s, x, 3.15, gw, 0.42, name, size=11, bold=True,
               colour="FFFFFF", font=T.HEAD, align=CENTER, anchor=MIDDLE)
        for j, (kpi, how) in enumerate(rows_):
            y = 3.76 + j * 0.75
            d.text(s, x + 0.24, y, gw - 0.48, 0.34, kpi, size=11, bold=True,
                   colour=T.INK, font=T.HEAD)
            d.text(s, x + 0.24, y + 0.32, gw - 0.48, 0.32, how, size=9.5,
                   colour=T.MUTED)
    d.text(s, M, 6.18, W - M * 2, 0.34,
           "None of these is measured today. Baselines are set jointly in the "
           "first pilot week — a target set without a baseline is a guess.",
           size=11.5, bold=True, colour=T.INK)
    d.foot(s, "Decision success is the product proposition made measurable: "
              "the right single fact at the right minute.")

    # ----------------------------------------------------------- 19 risks
    s = d.slide()
    d.header(s, "Risks and mitigations",
             "Named, with the mitigation already built where possible", "17")
    risks = [
        ("Realtime feed fails or goes stale",
         "Staleness thresholds already enforced; the app falls back to "
         "SCHEDULE and says so rather than showing a frozen train.", T.TEAL),
        ("A prediction is wrong",
         "Predictions are labelled as estimates at every level, never as "
         "fact, so a wrong estimate misleads no one about its status.", T.TEAL),
        ("Privacy concern",
         "Location is opt-in and per-journey, rider-stoppable; analytics is "
         "consent-gated and cannot carry a query or a station pair.", T.TEAL),
        ("Stale static data",
         "Loaders replace each table wholesale inside one transaction, so a "
         "re-run cannot leave a mix of old and new rows.", T.TEAL),
        ("API load during a pilot",
         "Diff-based WebSocket fan-out and a Redis snapshot; rate limiting is "
         "named as hardening still to do before any public pilot.", T.AMBER),
        ("Identifier mapping errors",
         "A configurable mapping chain plus a conformance suite that fails the "
         "build when a source violates the contract.", T.TEAL),
    ]
    for i, (risk, mit, col) in enumerate(risks):
        col_i, row = i % 2, i // 2
        x = M + col_i * (6.06 + 0.21)
        y = 1.95 + row * 1.42
        d.rect(s, x, y, 6.06, 1.26, T.CARD, radius=True)
        d.rect(s, x, y, 0.13, 1.26, col, radius=True)
        d.text(s, x + 0.34, y + 0.1, 5.5, 0.3, risk, size=11.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.34, y + 0.44, 5.5, 0.72, mit, size=10, colour=T.BODY)
    d.text(s, M, 6.3, W - M * 2, 0.34,
           "Five of the six mitigations are already implemented and tested. "
           "The sixth is named as hardening still to do.",
           size=11.5, bold=True, colour=T.INK)
    d.foot(s, "A risk with no mitigation is listed as a risk, not quietly left "
              "out.")

    # ------------------------------------------------------ 17 value to DMRC
    s = d.slide()
    d.header(s, "Value to DMRC", "Five areas, none of them operational", "18")
    areas = [
        ("Passenger experience",
         "Guidance at the moment of each decision, in the rider's pocket"),
        ("Accessibility",
         "Step-free guidance on DMRC's own pathway data, with evidence tiers"),
        ("Crowd management",
         "Passenger-facing guidance that complements control-room systems"),
        ("Digital innovation",
         "A working application demonstrating what open transit data enables"),
        ("Data utilisation",
         "Approved OTD datasets turned into daily commuter value"),
    ]
    for i, (title, body) in enumerate(areas):
        col, row = i % 3, i // 3
        x = M + col * (4.06 + 0.21)
        y = 2.1 + row * 2.0
        d.rect(s, x, y, 4.06, 1.78, T.CARD, radius=True)
        d.rect(s, x + 0.26, y + 0.24, 0.42, 0.42, T.PRIMARY, radius=True)
        d.text(s, x + 0.26, y + 0.24, 0.42, 0.42, str(i + 1), size=13,
               bold=True, colour="FFFFFF", font=T.HEAD, align=CENTER,
               anchor=MIDDLE)
        d.text(s, x + 0.84, y + 0.28, 3.0, 0.34, title, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, x + 0.26, y + 0.86, 3.56, 0.8, body, size=10.5)
    d.rect(s, M + 4.27 * 2, 4.1, 4.06, 1.78, T.INK, radius=True)
    d.text(s, M + 4.27 * 2 + 0.26, 4.4, 3.56, 1.2,
           "MetroPulse is a commuter-facing layer. It seeks no role in "
           "signalling, operations or station control.",
           size=12, colour="C3D2EC")
    d.foot(s, "Nothing proposed here touches a safety-critical or operational "
              "system.")

    # ------------------------------------------ 18 what we need from DMRC
    s = d.slide()
    d.header(s, "What MetroPulse needs from DMRC",
             "Five requests, in priority order", "19")
    asks = [
        ("1", "Realtime Metro data", T.VIOLET,
         "Train positions or movement, ETA / trip updates, and service "
         "alerts — in a test environment first."),
        ("2", "Operational station data", T.VIOLET,
         "Facility operational status, gate closures, accessibility changes, "
         "and escalator inventory and status."),
        ("3", "Passenger-flow data", T.VIOLET,
         "Station occupancy, gate throughput, or aggregated crowd "
         "indicators — whichever DMRC can share."),
        ("4", "Technical collaboration", T.PRIMARY,
         "Feed specification, identifier mapping, refresh expectations, and "
         "a named pilot technical contact."),
        ("5", "A controlled ninety-day pilot", T.PRIMARY,
         "Selected stations and routes, evaluated against the KPIs defined "
         "in this submission."),
    ]
    for i, (num, title, col, body) in enumerate(asks):
        y = 1.95 + i * 0.88
        d.rect(s, M, y, W - M * 2, 0.76, T.CARD, radius=True)
        d.rect(s, M + 0.24, y + 0.14, 0.16, 0.48, col, radius=True)
        d.text(s, M + 0.62, y + 0.08, 0.4, 0.3, num, size=14, bold=True,
               colour=col, font=T.HEAD)
        d.text(s, M + 1.06, y + 0.08, 3.55, 0.3, title, size=12.5, bold=True,
               colour=T.INK, font=T.HEAD)
        d.text(s, M + 4.75, y + 0.08, 7.1, 0.6, body, size=10.5)
    d.text(s, M, 6.45, W - M * 2, 0.32,
           "No funding or exclusivity is requested at this stage.",
           size=12.5, bold=True, colour=T.INK)
    d.foot(s, "Items 4 and 5 cost nothing but time, and remove most of the "
              "risk from items 1–3.")

    # ----------------------------------------------------------- 20 close
    s = d.slide(dark=True)
    d.text(s, M, 1.9, 9.2, 2.0, "MetroPulse is ready\nfor the next stage.",
           size=44, bold=True, colour="FFFFFF", font=T.HEAD, spacing=1.2)
    ready = [
        ("The product exists", "and runs against a deployed backend today"),
        ("The data is official", "approved OTD, loaded and matched"),
        ("The pilot is scoped", "ninety days, an exit check at each stage"),
    ]
    for i, (a, b) in enumerate(ready):
        x = M + i * 3.05
        d.rect(s, x, 4.15, 2.85, 1.12, T.INK_SOFT, radius=True)
        d.text(s, x + 0.24, 4.3, 2.4, 0.3, a, size=12, bold=True,
               colour="7FE3D2", font=T.HEAD)
        d.text(s, x + 0.24, 4.62, 2.4, 0.6, b, size=10, colour="9DB4DC")
    d.rect(s, 10.15, 1.6, 2.5, 2.5, "FFFFFF", radius=True)
    d.img(s, "qr_repo.png", 10.37, 1.82, h=2.06)
    d.text(s, 10.15, 4.2, 2.5, 0.3, "Try MetroPulse", size=13, bold=True,
           colour="FFFFFF", font=T.HEAD, align=CENTER)
    d.text(s, 10.15, 4.52, 2.5, 0.55,
           "Source, APK and demo\ngithub.com/Beware2707/Metropulse",
           size=8.5, colour="9DB4DC", align=CENTER)
    d.text(s, 10.15, 5.15, 2.5, 0.3,
           "Working release build — no account required.", size=8.5,
           colour="6E86B4", align=CENTER)
    d.text(s, M, 5.75, 8.0, 0.36, f"MetroPulse  ·  {f('founder')}", size=15,
           colour="9DB4DC")
    d.text(s, M, 6.19, 8.0, 0.32, f"Contact: {f('contact')}", size=12,
           colour="6E86B4")

    render_pptx(d.rec, out_path)
    render_pdf(d.rec, out_path.replace('.pptx', '.pdf'))
    return out_path
