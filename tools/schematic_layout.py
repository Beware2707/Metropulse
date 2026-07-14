#!/usr/bin/env python3
"""Compute an octilinear schematic layout for the DMRC network from GTFS data.

Reads data/dmrc_gtfs.zip, derives per-line ordered stop sequences, runs a
Stott-style hill-climbing schematization (octilinearity + edge-length
uniformity + geographic fidelity + node repulsion + line straightness),
snaps near-octilinear edges exact, inserts mid-edge elbows where a direct
octilinear edge is impossible, places non-overlapping labels, and emits:

  app/assets/network_schematic.json   (renderer contract -- do not change schema)
  <scratch>/schematic_preview.png     (visual ground truth)

The layout is derived purely from GTFS coordinates + this algorithm; no
coordinates are taken from DMRC's published map artwork.
"""

import argparse
import csv
import io
import json
import math
import random
import zipfile
from collections import defaultdict

# ---------------------------------------------------------------- constants

ROOT = r"C:\Users\riddl\Downloads\Metro"
GTFS_ZIP = ROOT + r"\data\dmrc_gtfs.zip"
OUT_JSON = ROOT + r"\app\assets\network_schematic.json"

# Must match app/lib/core/theme.dart _lineColors exactly.
LINE_COLORS = {
    "RED": "#E41F26",
    "YELLOW": "#FDD10A",
    "BLUE": "#0056A8",
    "GREEN": "#00A651",
    "VIOLET": "#92278F",
    "PINK": "#EC4899",
    "MAGENTA": "#A6008C",
    "ORANGE/AIRPORT": "#F7941D",
    "ORANGE": "#F7941D",
    "AIRPORT": "#F7941D",
    "AQUA": "#00AEEF",
    "GRAY": "#8A8D8F",
    "RAPID": "#00A99D",
}

CANVAS_W = 2400.0
CANVAS_H = 2800.0
PADDING = 160.0

CHAR_W = 6.2       # label metrics at font size 11
LABEL_H = 14.0
DOT_R = 6.0
INTER_R = 9.0
MIN_NODE_DIST = 34.0   # repulsion radius (overridable via --rep-radius)
HARD_MIN_DIST = 30.0   # quantitative check threshold


# ---------------------------------------------------------------- gtfs parse

def read_csv(z, name):
    return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig")))


def line_key(long_name):
    name = (long_name or "").strip()
    u = name.find("_")
    if u > 0:
        return name[:u].strip().upper()
    return name.upper()


def parse_gtfs():
    z = zipfile.ZipFile(GTFS_ZIP)
    stops = {s["stop_id"]: {
        "name": s["stop_name"].strip(),
        "lat": float(s["stop_lat"]),
        "lon": float(s["stop_lon"]),
    } for s in read_csv(z, "stops.txt")}
    routes = read_csv(z, "routes.txt")
    trips = read_csv(z, "trips.txt")
    stop_times = read_csv(z, "stop_times.txt")

    # representative trip per route: prefer direction_id 0, else first seen
    rep = {}
    for t in trips:
        rid = t["route_id"]
        cur = rep.get(rid)
        if cur is None or (t.get("direction_id") == "0" and cur[1] != "0"):
            rep[rid] = (t["trip_id"], t.get("direction_id"))
    trip_to_route = {v[0]: rid for rid, v in rep.items()}

    raw = defaultdict(list)
    for row in stop_times:
        rid = trip_to_route.get(row["trip_id"])
        if rid is not None:
            raw[rid].append((int(row["stop_sequence"]), row["stop_id"]))
    seqs = {rid: [sid for _, sid in sorted(v)] for rid, v in raw.items()}

    key_for = {r["route_id"]: line_key(r["route_long_name"]) for r in routes}

    # dedupe direction pairs: same line key + same stop SET = one drawn line
    drawn = {}
    order = []
    for r in routes:
        rid = r["route_id"]
        k = key_for[rid]
        fs = frozenset(seqs[rid])
        dk = (k, fs)
        if dk not in drawn:
            drawn[dk] = {"lineKey": k, "routeIds": [rid], "stopIds": seqs[rid]}
            order.append(dk)
        else:
            drawn[dk]["routeIds"].append(rid)
    lines = [drawn[k] for k in order]
    # longest branch of each key first (nicer draw order), stable otherwise
    lines.sort(key=lambda L: (L["lineKey"], -len(L["stopIds"])))

    # interchanges: stops served by >= 2 distinct line keys
    keys_by_stop = defaultdict(set)
    for rid, s in seqs.items():
        for sid in s:
            keys_by_stop[sid].add(key_for[rid])
    interchanges = {sid for sid, ks in keys_by_stop.items() if len(ks) >= 2}

    return stops, lines, interchanges, seqs, key_for


# ---------------------------------------------------------------- geometry

OCT_DIRS = [(math.cos(math.radians(a)), math.sin(math.radians(a)))
            for a in range(0, 360, 45)]


def edge_angle_dev(dx, dy):
    """Angular distance (degrees, 0..22.5) to the nearest multiple of 45."""
    ang = math.degrees(math.atan2(dy, dx)) % 45.0
    return min(ang, 45.0 - ang)


def nearest_oct_dir(dx, dy):
    ang = math.degrees(math.atan2(dy, dx))
    snapped = round(ang / 45.0) * 45.0
    r = math.radians(snapped)
    return math.cos(r), math.sin(r)


# ---------------------------------------------------------------- layout

class Layout:
    def __init__(self, stops, lines, interchanges, args):
        self.args = args
        self.stops = stops
        self.lines = lines
        self.interchanges = interchanges
        self.ids = sorted(stops.keys(), key=lambda s: int(s))
        self.idx = {sid: i for i, sid in enumerate(self.ids)}
        n = len(self.ids)

        # --- initial equirectangular projection, fit to canvas w/ padding
        lats = [stops[s]["lat"] for s in self.ids]
        lons = [stops[s]["lon"] for s in self.ids]
        mean_lat = sum(lats) / n
        klon = math.cos(math.radians(mean_lat))
        xs = [(stops[s]["lon"]) * klon for s in self.ids]
        ys = [-(stops[s]["lat"]) for s in self.ids]   # y grows south (screen)
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        sw = (CANVAS_W - 2 * PADDING) / (maxx - minx)
        sh = (CANVAS_H - 2 * PADDING) / (maxy - miny)
        # anisotropic: stretch the minor axis up to 1.45x the major-axis scale
        # so the network actually uses the canvas (schematic maps routinely
        # stretch one axis; relative N/S/E/W arrangement is preserved).
        scale_x = min(sw, min(sw, sh) * 1.45)
        scale_y = min(sh, min(sw, sh) * 1.45)
        offx = PADDING + ((CANVAS_W - 2 * PADDING) - scale_x * (maxx - minx)) / 2
        offy = PADDING + ((CANVAS_H - 2 * PADDING) - scale_y * (maxy - miny)) / 2
        self.pos = [[offx + (x - minx) * scale_x, offy + (y - miny) * scale_y]
                    for x, y in zip(xs, ys)]
        self.orig = [p[:] for p in self.pos]

        # --- unique undirected edges (consecutive stop pairs on any line)
        eset = {}
        self.triples = set()
        for L in lines:
            s = [self.idx[sid] for sid in L["stopIds"]]
            for a, b in zip(s, s[1:]):
                k = (min(a, b), max(a, b))
                eset[k] = eset.get(k, 0) + 1
            for a, b, c in zip(s, s[1:], s[2:]):
                t = (a, b, c) if a < c else (c, b, a)
                self.triples.add(t)
        self.edges = list(eset.keys())
        self.adj_edges = defaultdict(list)     # node -> edge (a,b) list
        for e in self.edges:
            self.adj_edges[e[0]].append(e)
            self.adj_edges[e[1]].append(e)
        self.node_triples = defaultdict(list)
        for t in self.triples:
            for nnode in t:
                self.node_triples[nnode].append(t)
        self.neighbors = defaultdict(set)
        for a, b in self.edges:
            self.neighbors[a].add(b)
            self.neighbors[b].add(a)

        # target edge length
        lens = sorted(self.elen(e) for e in self.edges)
        med = lens[len(lens) // 2]
        self.L = args.target_len if args.target_len else max(52.0, min(75.0, med))

        self.rep_mult = {}   # node -> repulsion radius multiplier (label feedback)

        # spatial grid for repulsion
        self.cell = 64.0
        self.grid = defaultdict(set)
        for i in range(n):
            self.grid[self.gkey(self.pos[i])].add(i)

    # --- helpers
    def gkey(self, p):
        return (int(p[0] // self.cell), int(p[1] // self.cell))

    def elen(self, e):
        a, b = self.pos[e[0]], self.pos[e[1]]
        return math.hypot(b[0] - a[0], b[1] - a[1])

    def near_nodes(self, p, exclude, radius):
        cx, cy = int(p[0] // self.cell), int(p[1] // self.cell)
        r = int(radius // self.cell) + 1
        out = []
        for gx in range(cx - r, cx + r + 1):
            for gy in range(cy - r, cy + r + 1):
                for j in self.grid.get((gx, gy), ()):
                    if j != exclude:
                        out.append(j)
        return out

    # --- cost terms -------------------------------------------------
    def edge_cost(self, e, w):
        a, b = self.pos[e[0]], self.pos[e[1]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return 1e6
        dev = edge_angle_dev(dx, dy)
        c = w["oct"] * (dev / 22.5) ** 2
        c += w["len"] * ((length - self.L) / self.L) ** 2
        short = 0.6 * self.L
        if length < short:
            c += w["short"] * ((short - length) / short) ** 2
        return c

    def triple_cost(self, t, w):
        a, b, c = self.pos[t[0]], self.pos[t[1]], self.pos[t[2]]
        d1 = math.atan2(b[1] - a[1], b[0] - a[0])
        d2 = math.atan2(c[1] - b[1], c[0] - b[0])
        turn = abs(math.degrees(d2 - d1))
        turn = min(turn % 360.0, 360.0 - turn % 360.0)
        return w["str"] * (turn / 90.0) ** 2

    def rep_cost_node(self, i, w):
        p = self.pos[i]
        c = 0.0
        mi = self.rep_mult.get(i, 1.0)
        for j in self.near_nodes(p, i, MIN_NODE_DIST * 2.2):
            q = self.pos[j]
            radius = MIN_NODE_DIST * max(mi, self.rep_mult.get(j, 1.0))
            d = math.hypot(q[0] - p[0], q[1] - p[1])
            if d < radius:
                c += w["rep"] * ((radius - d) / radius) ** 2
        return c

    EDGE_REP_R = 27.0

    def edge_rep_cost_node(self, i, w):
        """Penalise non-incident line segments grazing a station."""
        we = w.get("erep", 0.0)
        if we == 0.0:
            return 0.0
        p = self.pos[i]
        c = 0.0
        radius = self.EDGE_REP_R * self.rep_mult.get(i, 1.0) ** 1.3
        seen = set()
        for j in self.near_nodes(p, i, 130.0):
            for e in self.adj_edges[j]:
                if e in seen or i == e[0] or i == e[1]:
                    continue
                seen.add(e)
                a, b = self.pos[e[0]], self.pos[e[1]]
                abx, aby = b[0] - a[0], b[1] - a[1]
                ll = abx * abx + aby * aby
                if ll < 1e-9:
                    continue
                t = max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / ll))
                dx, dy = p[0] - (a[0] + t * abx), p[1] - (a[1] + t * aby)
                d = math.hypot(dx, dy)
                if d < radius:
                    c += we * ((radius - d) / radius) ** 2
        return c

    def geo_cost_node(self, i, w):
        p, o = self.pos[i], self.orig[i]
        d = math.hypot(p[0] - o[0], p[1] - o[1])
        return w["geo"] * (d / 250.0) ** 2

    def local_cost(self, i, w):
        c = self.geo_cost_node(i, w) + self.rep_cost_node(i, w)
        c += self.edge_rep_cost_node(i, w)
        for e in self.adj_edges[i]:
            c += self.edge_cost(e, w)
        for t in self.node_triples[i]:
            c += self.triple_cost(t, w)
        return c

    def total_cost(self, w):
        c = 0.0
        for e in self.edges:
            c += self.edge_cost(e, w)
        for t in self.triples:
            c += self.triple_cost(t, w)
        n = len(self.pos)
        for i in range(n):
            c += self.geo_cost_node(i, w)
            c += 0.5 * self.rep_cost_node(i, w)   # pairs counted twice
            c += self.edge_rep_cost_node(i, w)
        return c

    # --- optimization ----------------------------------------------
    def candidate_moves(self, i, step):
        cands = []
        for dx, dy in OCT_DIRS:
            cands.append((step * dx, step * dy))
            cands.append((0.5 * step * dx, 0.5 * step * dy))
        # Stott-style: snap onto an exact octilinear ray from each neighbor
        p = self.pos[i]
        for j in self.neighbors[i]:
            q = self.pos[j]
            dx, dy = p[0] - q[0], p[1] - q[1]
            d = math.hypot(dx, dy)
            if d < 1e-9:
                continue
            ux, uy = nearest_oct_dir(dx, dy)
            for dist in (d, self.L):
                tx, ty = q[0] + ux * dist, q[1] + uy * dist
                cands.append((tx - p[0], ty - p[1]))
        return cands

    def optimize(self, w, sweeps, step_hi, step_lo, rng, w_oct_final=None,
                 subset=None):
        n = len(self.pos)
        order = list(subset) if subset is not None else list(range(n))
        for s in range(sweeps):
            frac = s / max(1, sweeps - 1)
            step = step_hi * (step_lo / step_hi) ** frac
            if w_oct_final:
                w = dict(w)
                w["oct"] = w["oct"] * (1 - frac) + w_oct_final * frac
            rng.shuffle(order)
            improved = 0.0
            for i in order:
                base = self.local_cost(i, w)
                best, bestp = 0.0, None
                p0 = self.pos[i][:]
                for mx, my in self.candidate_moves(i, step):
                    nx, ny = p0[0] + mx, p0[1] + my
                    if not (40 <= nx <= CANVAS_W - 40 and 40 <= ny <= CANVAS_H - 40):
                        continue
                    old_key = self.gkey(self.pos[i])
                    self.pos[i][0], self.pos[i][1] = nx, ny
                    new_key = self.gkey(self.pos[i])
                    if new_key != old_key:
                        self.grid[old_key].discard(i)
                        self.grid[new_key].add(i)
                    c = self.local_cost(i, w)
                    # restore
                    if new_key != old_key:
                        self.grid[new_key].discard(i)
                        self.grid[old_key].add(i)
                    self.pos[i][0], self.pos[i][1] = p0
                    if c < base + best - 1e-9:
                        best, bestp = c - base, (nx, ny)
                if bestp is not None:
                    old_key = self.gkey(self.pos[i])
                    self.pos[i][0], self.pos[i][1] = bestp
                    new_key = self.gkey(self.pos[i])
                    if new_key != old_key:
                        self.grid[old_key].discard(i)
                        self.grid[new_key].add(i)
                    improved += -best
            if improved < 0.05 and s > sweeps // 2:
                break
        return self.total_cost(w)

    # --- snap pass ---------------------------------------------------
    def snap(self, tol_deg=10.0):
        snapped = 0
        edges = sorted(self.edges, key=lambda e: edge_angle_dev(
            self.pos[e[1]][0] - self.pos[e[0]][0],
            self.pos[e[1]][1] - self.pos[e[0]][1]))
        for _ in range(3):
            changed = False
            for e in edges:
                a, b = e
                pa, pb = self.pos[a], self.pos[b]
                dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                dev = edge_angle_dev(dx, dy)
                if dev < 0.01 or dev > tol_deg:
                    continue
                length = math.hypot(dx, dy)
                ux, uy = nearest_oct_dir(dx, dy)
                mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
                na = (mx - ux * length / 2, my - uy * length / 2)
                nb = (mx + ux * length / 2, my + uy * length / 2)
                if self.snap_ok(a, na) and self.snap_ok(b, nb, moving_with=a):
                    self.move_to(a, na)
                    self.move_to(b, nb)
                    snapped += 1
                    changed = True
            if not changed:
                break
        return snapped

    def snap_ok(self, i, newp, moving_with=None):
        # no repulsion violation
        for j in self.near_nodes(newp, i, HARD_MIN_DIST + self.cell):
            if j == moving_with:
                continue
            q = self.pos[j]
            if math.hypot(q[0] - newp[0], q[1] - newp[1]) < HARD_MIN_DIST:
                return False
        # do not un-snap an already exact incident edge
        for e in self.adj_edges[i]:
            other = e[0] if e[1] == i else e[1]
            if other == moving_with:
                continue
            p, q = self.pos[i], self.pos[other]
            if edge_angle_dev(q[0] - p[0], q[1] - p[1]) < 0.01:
                if edge_angle_dev(q[0] - newp[0], q[1] - newp[1]) > 0.01:
                    return False
        return True

    def move_to(self, i, newp):
        old_key = self.gkey(self.pos[i])
        self.pos[i][0], self.pos[i][1] = newp
        new_key = self.gkey(self.pos[i])
        if new_key != old_key:
            self.grid[old_key].discard(i)
            self.grid[new_key].add(i)

    # --- metrics ------------------------------------------------------
    def metrics(self):
        devs = []
        for e in self.edges:
            a, b = self.pos[e[0]], self.pos[e[1]]
            devs.append(edge_angle_dev(b[0] - a[0], b[1] - a[1]))
        within5 = sum(1 for d in devs if d <= 5.0) / len(devs)
        exact = sum(1 for d in devs if d <= 0.01) / len(devs)
        mind, minpair = 1e9, None
        n = len(self.pos)
        for i in range(n):
            for j in self.near_nodes(self.pos[i], i, MIN_NODE_DIST + self.cell):
                if j <= i:
                    continue
                p, q = self.pos[i], self.pos[j]
                d = math.hypot(q[0] - p[0], q[1] - p[1])
                if d < mind:
                    mind, minpair = d, (self.ids[i], self.ids[j])
        lens = [self.elen(e) for e in self.edges]
        return {
            "edges": len(self.edges),
            "pct_within_5deg": within5,
            "pct_exact_oct": exact,
            "min_node_dist": mind,
            "min_pair": minpair,
            "edge_len_min": min(lens),
            "edge_len_med": sorted(lens)[len(lens) // 2],
            "edge_len_max": max(lens),
        }


# ---------------------------------------------------------------- elbows

def build_polyline(layout, stop_ids):
    """Station positions + one elbow per non-octilinear edge.
    Returns (points, stop_point_index)."""
    pts, spi = [], []
    idxs = [layout.idx[s] for s in stop_ids]
    for k, i in enumerate(idxs):
        p = layout.pos[i]
        if k > 0:
            a = layout.pos[idxs[k - 1]]
            dx, dy = p[0] - a[0], p[1] - a[1]
            if edge_angle_dev(dx, dy) > 0.01:
                elbow = compute_elbow(a, p, layout, exclude=(idxs[k - 1], i))
                if elbow is not None:
                    pts.append([round(elbow[0], 2), round(elbow[1], 2)])
        spi.append(len(pts))
        pts.append([round(p[0], 2), round(p[1], 2)])
    return pts, spi


def compute_elbow(a, b, layout=None, exclude=()):
    """One intermediate vertex making A->C->B two octilinear segments.
    When both orientations are geometrically valid, prefer the elbow that
    stays farther from other stations (avoids near-tangent grazes)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ang = math.degrees(math.atan2(dy, dx))
    lo = math.floor(ang / 45.0) * 45.0
    hi = lo + 45.0
    options = []
    for d1, d2 in ((lo, hi), (hi, lo)):
        u1 = (math.cos(math.radians(d1)), math.sin(math.radians(d1)))
        u2 = (math.cos(math.radians(d2)), math.sin(math.radians(d2)))
        det = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(det) < 1e-9:
            continue
        rx, ry = b[0] - a[0], b[1] - a[1]
        t = (rx * u2[1] - ry * u2[0]) / det
        s = (u1[0] * ry - u1[1] * rx) / det
        if t > 1.0 and s > 1.0:
            options.append((a[0] + t * u1[0], a[1] + t * u1[1]))
    if not options:
        return None
    if len(options) == 1 or layout is None:
        return options[0]
    def clearance(c):
        best = 1e9
        for j in layout.near_nodes(c, -1, 130.0):
            if j in exclude:
                continue
            q = layout.pos[j]
            best = min(best, math.hypot(q[0] - c[0], q[1] - c[1]))
        return best
    return max(options, key=clearance)


# ---------------------------------------------------------------- labels

SQ2 = math.sqrt(0.5)

_TEXT_W_CACHE = {}


def text_width(name, bold):
    """Measured width of the label as the preview actually renders it
    (8pt at dpi 100 = 11.11px). Falls back to the flat CHAR_W estimate."""
    key = (name, bold)
    if key not in _TEXT_W_CACHE:
        try:
            from matplotlib.textpath import TextPath
            from matplotlib.font_manager import FontProperties
            fp = FontProperties(family="DejaVu Sans",
                                weight="bold" if bold else "normal")
            w = TextPath((0, 0), name, size=11.11, prop=fp).get_extents().width
        except Exception:
            w = CHAR_W * len(name)
        _TEXT_W_CACHE[key] = w + 2.0
    return _TEXT_W_CACHE[key]

# unit offset direction (y-down) for each compass anchor
ANCHOR_OFF = {"e": (1, 0), "w": (-1, 0), "n": (0, -1), "s": (0, 1),
              "ne": (1, -1), "nw": (-1, -1), "se": (1, 1), "sw": (-1, 1)}


class OBB:
    """Oriented box: origin corner + unit axes u (length w) and v (length h)."""

    def __init__(self, origin, u, v, w, h):
        self.o = origin
        self.u, self.v = u, v
        self.w, self.h = w, h
        ox, oy = origin
        self.corners = [
            (ox, oy),
            (ox + u[0] * w, oy + u[1] * w),
            (ox + u[0] * w + v[0] * h, oy + u[1] * w + v[1] * h),
            (ox + v[0] * h, oy + v[1] * h),
        ]

    def project(self, axis):
        vals = [c[0] * axis[0] + c[1] * axis[1] for c in self.corners]
        return min(vals), max(vals)

    def overlaps(self, other, pad=1.0):
        for axis in (self.u, self.v, other.u, other.v):
            a0, a1 = self.project(axis)
            b0, b1 = other.project(axis)
            if a1 + pad < b0 or b1 + pad < a0:
                return False
        return True

    def contains(self, p, pad=0.0):
        rx, ry = p[0] - self.o[0], p[1] - self.o[1]
        tu = rx * self.u[0] + ry * self.u[1]
        tv = rx * self.v[0] + ry * self.v[1]
        return -pad <= tu <= self.w + pad and -pad <= tv <= self.h + pad

    def intersects_segment(self, p, q, pad=4.0):
        if self.contains(p, pad) or self.contains(q, pad):
            return True
        # SAT between segment (degenerate obb) and this box, inflated by pad
        dx, dy = q[0] - p[0], q[1] - p[1]
        ln = math.hypot(dx, dy)
        if ln < 1e-9:
            return self.contains(p, pad)
        su = (dx / ln, dy / ln)
        sv = (-su[1], su[0])
        axes = (self.u, self.v, su, sv)
        for axis in axes:
            a0, a1 = self.project(axis)
            v0 = p[0] * axis[0] + p[1] * axis[1]
            v1 = q[0] * axis[0] + q[1] * axis[1]
            b0, b1 = min(v0, v1), max(v0, v1)
            if a1 + pad < b0 or b1 + pad < a0:
                return False
        return True

    def intersects_circle(self, c, r):
        rx, ry = c[0] - self.o[0], c[1] - self.o[1]
        tu = rx * self.u[0] + ry * self.u[1]
        tv = rx * self.v[0] + ry * self.v[1]
        cu = max(0.0, min(self.w, tu))
        cv = max(0.0, min(self.h, tv))
        return math.hypot(tu - cu, tv - cv) < r


def label_box(pos, anchor, angle, text_w, is_inter, scale=1.0, shift=0.0):
    """OBB for a label candidate. Design space: y grows downward.

    ``shift`` slides the box along its perpendicular axis (v) — legal since
    the asset now carries the exact box origin (labelDx/labelDy), so any
    placement the collision check approves transfers verbatim to the
    renderer.
    """
    x, y = pos
    r = (INTER_R if is_inter else DOT_R) + 4.0 * scale
    rd = r * SQ2 + 1.0
    h = LABEL_H
    if angle == -45:
        u = (SQ2, -SQ2)          # up-right in y-down space
        v = (SQ2, SQ2)
        ax, ay = ANCHOR_OFF[anchor]
        p = (x + ax * (rd if ax and ay else r), y + ay * (rd if ax and ay else r))
        if anchor in ("ne", "e", "n", "se"):   # text starts at p, reads up-right
            origin = (p[0] - v[0] * h / 2, p[1] - v[1] * h / 2)
        else:                              # text ends at p, reads up-right
            origin = (p[0] - u[0] * text_w - v[0] * h / 2,
                      p[1] - u[1] * text_w - v[1] * h / 2)
        origin = (origin[0] + v[0] * shift, origin[1] + v[1] * shift)
        return OBB(origin, u, v, text_w, h)
    u, v = (1.0, 0.0), (0.0, 1.0)
    if anchor == "e":
        origin = (x + r, y - h / 2)
    elif anchor == "w":
        origin = (x - r - text_w, y - h / 2)
    elif anchor == "n":
        origin = (x - text_w / 2, y - r - h)
    elif anchor == "s":
        origin = (x - text_w / 2, y + r)
    elif anchor == "ne":
        origin = (x + rd, y - rd - h + 3)
    elif anchor == "nw":
        origin = (x - rd - text_w, y - rd - h + 3)
    elif anchor == "se":
        origin = (x + rd, y + rd - 3)
    elif anchor == "sw":
        origin = (x - rd - text_w, y + rd - 3)
    else:
        raise ValueError(anchor)
    return OBB((origin[0], origin[1] + shift), u, v, text_w, h)


CAND_LIST = [("e", 0), ("w", 0), ("ne", 0), ("se", 0), ("nw", 0), ("sw", 0),
             ("n", 0), ("s", 0),
             ("ne", -45), ("sw", -45), ("n", -45), ("s", -45),
             ("e", -45), ("w", -45), ("se", -45), ("nw", -45)]


def place_labels(layout, segments, rng):
    """Label placement: per-station statically-valid candidates (no line/dot
    collisions), then conflict-repair local search over label-label overlaps.
    Returns ({stop_id: (anchor, angle, box)}, overlap_count, dead_stations,
    involved_station_ids)."""
    ids = layout.ids
    n = len(ids)
    # segment spatial index
    seg_grid = defaultdict(list)
    cell = 128.0
    for seg in segments:
        (x0, y0), (x1, y1) = seg
        for gx in range(int(min(x0, x1) // cell), int(max(x0, x1) // cell) + 1):
            for gy in range(int(min(y0, y1) // cell), int(max(y0, y1) // cell) + 1):
                seg_grid[(gx, gy)].append(seg)

    def segs_near(box):
        xs = [c[0] for c in box.corners]
        ys = [c[1] for c in box.corners]
        out = set()
        for gx in range(int((min(xs) - 8) // cell), int((max(xs) + 8) // cell) + 1):
            for gy in range(int((min(ys) - 8) // cell), int((max(ys) + 8) // cell) + 1):
                for s in seg_grid.get((gx, gy), ()):
                    out.add(s)
        return out

    def static_ok(i, box, pad):
        if any(c[0] < 6 or c[0] > CANVAS_W - 6 or c[1] < 6 or
               c[1] > CANVAS_H - 6 for c in box.corners):
            return False
        for seg in segs_near(box):
            if box.intersects_segment(seg[0], seg[1], pad=pad):
                return False
        pos = layout.pos[i]
        for j2 in layout.near_nodes(pos, i, 320.0):
            p2 = layout.pos[j2]
            rr = (INTER_R if ids[j2] in layout.interchanges else DOT_R) + 2
            if box.intersects_circle(p2, rr):
                return False
        return True

    def violation(i, box):
        """Score for a fallback candidate: how badly it intrudes on lines.
        Grazing scores low; crossing through a band scores high."""
        if any(c[0] < 6 or c[0] > CANVAS_W - 6 or c[1] < 6 or
               c[1] > CANVAS_H - 6 for c in box.corners):
            return 1e9
        v = 0.0
        for seg in segs_near(box):
            lo, hi = 0.0, 4.5
            if box.intersects_segment(seg[0], seg[1], pad=0.0):
                v += 60.0     # genuine crossing
                continue
            if not box.intersects_segment(seg[0], seg[1], pad=hi):
                continue
            for _ in range(6):
                mid = (lo + hi) / 2
                if box.intersects_segment(seg[0], seg[1], pad=mid):
                    hi = mid
                else:
                    lo = mid
            v += (4.5 - lo) ** 2
        pos = layout.pos[i]
        for j2 in layout.near_nodes(pos, i, 320.0):
            p2 = layout.pos[j2]
            rr = (INTER_R if ids[j2] in layout.interchanges else DOT_R) + 2
            if box.intersects_circle(p2, rr):
                v += 60.0
        return v

    # statically valid candidates per station, in preference order. The asset
    # carries the exact chosen box origin (labelDx/labelDy), so larger offsets
    # and perpendicular slides transfer verbatim to the renderer — the
    # candidate space can be generous.
    cands = []      # i -> list of (anchor, angle, box)
    dead = []       # stations with NO statically valid candidate
    scales = (1.0, 1.45, 2.0, 2.6)
    shifts = (0.0, -8.0, 8.0, -15.0, 15.0, -22.0, 22.0)
    for i in range(n):
        sid = ids[i]
        pos = layout.pos[i]
        is_inter = sid in layout.interchanges
        text_w = text_width(layout.stops[sid]["name"], is_inter)
        good = []
        for pad in (4.5, 3.6, 3.0):   # clean clearance first, then snug
            for scale in scales:
                for shift in shifts:
                    for anchor, angle in CAND_LIST:
                        box = label_box(pos, anchor, angle, text_w, is_inter,
                                        scale, shift)
                        if static_ok(i, box, pad):
                            good.append((anchor, angle, box))
                    if len(good) >= 12:
                        break
                if len(good) >= 12:
                    break
            if good:
                break
        if not good:
            dead.append(sid)
            # least-violation fallbacks: grazing a line band beats crossing it
            scored = []
            for scale in scales:
                for shift in shifts[:3]:
                    for anchor, angle in CAND_LIST:
                        box = label_box(pos, anchor, angle, text_w, is_inter,
                                        scale, shift)
                        scored.append((violation(i, box), (anchor, angle, box)))
            scored.sort(key=lambda t: t[0])
            good = [c for _, c in scored[:3]]
        cands.append(good)

    # initial assignment: first candidate (preference order)
    choice = [0] * n
    # neighbor lists for label-label pruning (label boxes stay near stations)
    near = [[j for j in range(n) if j != i and
             abs(layout.pos[j][0] - layout.pos[i][0]) < 420 and
             abs(layout.pos[j][1] - layout.pos[i][1]) < 300]
            for i in range(n)]

    def conflicts(i, box):
        c = 0
        for j in near[i]:
            if box.overlaps(cands[j][choice[j]][2], pad=1.2):
                c += 1
        return c

    def total_conflicts():
        return sum(conflicts(i, cands[i][choice[i]][2]) for i in range(n))

    order = list(range(n))
    best_choice, best_total = choice[:], total_conflicts()
    for rnd in range(18):
        for sweep in range(60):
            improved = False
            for i in order:
                cur = conflicts(i, cands[i][choice[i]][2])
                if cur == 0:
                    continue
                best_k, best_c = choice[i], cur
                for k, (_, _, box) in enumerate(cands[i]):
                    if k == choice[i]:
                        continue
                    c = conflicts(i, box)
                    if c < best_c:
                        best_c, best_k = c, k
                        if c == 0:
                            break
                if best_k != choice[i]:
                    choice[i] = best_k
                    improved = True
            rng.shuffle(order)
            if not improved:
                break
        # coordinated pair moves: two mutually-overlapping labels often need
        # to move at the same time, which single-label descent cannot do
        for i in range(n):
            bi = cands[i][choice[i]][2]
            for j in near[i]:
                if j <= i or not bi.overlaps(cands[j][choice[j]][2], pad=1.2):
                    continue
                found = None
                for ka in range(len(cands[i])):
                    for kb in range(len(cands[j])):
                        ba, bb = cands[i][ka][2], cands[j][kb][2]
                        if ba.overlaps(bb, pad=1.2):
                            continue
                        ci, cj = choice[i], choice[j]
                        choice[i], choice[j] = ka, kb
                        if conflicts(i, ba) == 0 and conflicts(j, bb) == 0:
                            found = (ka, kb)
                        choice[i], choice[j] = ci, cj
                        if found:
                            break
                    if found:
                        break
                if found:
                    choice[i], choice[j] = found
                    bi = cands[i][choice[i]][2]
        t = total_conflicts()
        if t < best_total:
            best_total, best_choice = t, choice[:]
        if best_total == 0:
            break
        # perturb: conflicting labels AND their neighbors jump around
        choice = best_choice[:]
        shake = set()
        for i in range(n):
            if conflicts(i, cands[i][choice[i]][2]) > 0:
                shake.add(i)
                box = cands[i][choice[i]][2]
                for j in near[i]:
                    if box.overlaps(cands[j][choice[j]][2], pad=1.2):
                        shake.add(j)
        for i in shake:
            choice[i] = rng.randrange(len(cands[i]))
    choice = best_choice

    result = {ids[i]: cands[i][choice[i]] for i in range(n)}
    boxes = {i: cands[i][choice[i]][2] for i in range(n)}
    overlaps = 0
    involved = set()
    pairs = []
    for a in range(n):
        for b in near[a]:
            if b > a and boxes[a].overlaps(boxes[b], pad=0.0):
                overlaps += 1
                involved.add(ids[a])
                involved.add(ids[b])
                pairs.append((layout.stops[ids[a]]["name"],
                              layout.stops[ids[b]]["name"]))
    if pairs:
        print("   conflict pairs:", pairs)
    return result, overlaps, dead, involved


# ---------------------------------------------------------------- output

def render_preview(layout, drawn, labels, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    dpi = 100
    fig = plt.figure(figsize=(CANVAS_W / dpi, CANVAS_H / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, CANVAS_W)
    ax.set_ylim(CANVAS_H, 0)      # y-down like design space
    ax.axis("off")
    fig.patch.set_facecolor("#FAFAF7")

    for L in drawn:
        pts = L["points"]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=L["color"], lw=5, solid_capstyle="round",
                solid_joinstyle="round", zorder=2)

    for i, sid in enumerate(layout.ids):
        x, y = layout.pos[i]
        if sid in layout.interchanges:
            ax.add_patch(Circle((x, y), INTER_R, facecolor="white",
                                edgecolor="#1a1a1a", lw=2.2, zorder=4))
            ax.add_patch(Circle((x, y), INTER_R - 4.5, facecolor="white",
                                edgecolor="#1a1a1a", lw=1.2, zorder=5))
        else:
            ax.add_patch(Circle((x, y), DOT_R, facecolor="white",
                                edgecolor="#333333", lw=1.4, zorder=4))

    # Labels are drawn from the exact collision-checked boxes — the preview
    # shows precisely what the asset ships, not a re-derived approximation.
    for i, sid in enumerate(layout.ids):
        name = layout.stops[sid]["name"]
        angle, box = labels[sid][1], labels[sid][2]
        is_inter = sid in layout.interchanges
        kw = dict(fontsize=8, zorder=6, rotation_mode="anchor",
                  color="#111111",
                  fontweight="bold" if is_inter else "normal")
        h = LABEL_H
        if angle == -45:
            # anchor at the vertical center of the box's starting edge;
            # y-axis inverted -> matplotlib rotation +45 rises to the right
            px = box.o[0] + box.v[0] * h / 2
            py = box.o[1] + box.v[1] * h / 2
            ax.text(px, py, name, ha="left", va="center", rotation=45, **kw)
        else:
            ax.text(box.o[0], box.o[1] + h / 2, name, ha="left", va="center",
                    rotation=0, **kw)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)


# ---------------------------------------------------------------- main

def main():
    global MIN_NODE_DIST
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweeps", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--target-len", type=float, default=0.0)
    ap.add_argument("--w-oct", type=float, default=5.0)
    ap.add_argument("--w-oct-final", type=float, default=14.0)
    ap.add_argument("--w-len", type=float, default=1.4)
    ap.add_argument("--w-short", type=float, default=45.0)
    ap.add_argument("--w-geo", type=float, default=0.9)
    ap.add_argument("--w-rep", type=float, default=70.0)
    ap.add_argument("--w-str", type=float, default=2.2)
    ap.add_argument("--w-erep", type=float, default=16.0)
    ap.add_argument("--rep-radius", type=float, default=MIN_NODE_DIST)
    ap.add_argument("--preview", type=str, required=True)
    args = ap.parse_args()
    MIN_NODE_DIST = args.rep_radius

    rng = random.Random(args.seed)
    stops, lines, interchanges, seqs, key_for = parse_gtfs()
    assert len(stops) == 262, f"expected 262 stops, got {len(stops)}"
    assert len(interchanges) == 23, \
        f"expected 23 interchanges, got {len(interchanges)}"

    layout = Layout(stops, lines, interchanges, args)
    print(f"lines(drawn)={len(lines)} edges={len(layout.edges)} "
          f"triples={len(layout.triples)} target_len={layout.L:.1f}")

    w = {"oct": args.w_oct, "len": args.w_len, "short": args.w_short,
         "geo": args.w_geo, "rep": args.w_rep, "str": args.w_str,
         "erep": args.w_erep}
    cost = layout.optimize(w, args.sweeps, step_hi=44.0, step_lo=2.0, rng=rng,
                           w_oct_final=args.w_oct_final)
    print(f"post-optimize cost={cost:.1f}")
    snapped = layout.snap(tol_deg=10.0)
    print(f"snapped {snapped} edges")
    # short refinement after snapping to relax any tension, then snap again
    w2 = dict(w)
    w2["oct"] = args.w_oct_final
    cost = layout.optimize(w2, 8, step_hi=6.0, step_lo=1.5, rng=rng)
    snapped = layout.snap(tol_deg=10.0)
    print(f"refine cost={cost:.1f}, snapped {snapped} more")

    def build_drawn():
        drawn = []
        for L in lines:
            pts, spi = build_polyline(layout, L["stopIds"])
            color = LINE_COLORS.get(L["lineKey"])
            if color is None:
                for k, v in LINE_COLORS.items():
                    if k in L["lineKey"]:
                        color = v
                        break
            drawn.append({
                "lineKey": L["lineKey"],
                "routeIds": L["routeIds"],
                "color": color or "#0056A8",
                "points": pts,
                "stopIds": L["stopIds"],
                "stopPointIndex": spi,
            })
        segments = []
        for d in drawn:
            p = d["points"]
            for a, b in zip(p, p[1:]):
                segments.append(((a[0], a[1]), (b[0], b[1])))
        return drawn, list({s for s in segments})

    # label placement with geometry feedback: stations whose labels cannot be
    # placed get extra local repulsion, then geometry re-optimizes and labels
    # are re-placed.
    best = None   # (score, pos, drawn, labels, overlaps, failures)
    for feedback_round in range(13):
        drawn, segments = build_drawn()
        labels, overlaps, failures, involved = place_labels(layout, segments, rng)
        mm = layout.metrics()
        score = (3 * len(failures) + overlaps, len(failures),
                 0 if mm["pct_within_5deg"] >= 0.90 else 1)
        print(f"round {feedback_round}: overlaps={overlaps} "
              f"dead={len(failures)} oct5={mm['pct_within_5deg']:.3f} "
              f"mind={mm['min_node_dist']:.1f} {failures[:8]}")
        acceptable = (mm["pct_within_5deg"] >= 0.90 and
                      mm["min_node_dist"] >= HARD_MIN_DIST)
        if best is None or (acceptable and score < best[0]) or \
                (best[0][2] == 1 and acceptable):
            if acceptable or best is None:
                best = (score, [p[:] for p in layout.pos], drawn, labels,
                        overlaps, failures)
        if overlaps == 0 and not failures and acceptable:
            break
        problem = set(failures) | involved
        problem_idx = {layout.idx[sid] for sid in problem}
        for i in list(layout.rep_mult):
            if i not in problem_idx:   # recovered: relax gradually
                layout.rep_mult[i] = max(1.0, layout.rep_mult[i] * 0.85)
        for i in problem_idx:
            layout.rep_mult[i] = min(2.6, layout.rep_mult.get(i, 1.0) + 0.3)
        # only re-optimize the neighborhoods of problem stations so solved
        # regions stay solved
        subset = set()
        for i in problem_idx:
            subset.add(i)
            subset.update(layout.near_nodes(layout.pos[i], i, 190.0))
        layout.optimize(w2, 18, step_hi=12.0, step_lo=1.5, rng=rng,
                        subset=subset)
        layout.snap(tol_deg=10.0)
        layout.optimize(w2, 6, step_hi=4.0, step_lo=1.2, rng=rng,
                        subset=subset)
        layout.snap(tol_deg=10.0)
    # restore the best state seen, then solve labels intensively on the
    # frozen geometry (label search is stochastic; take the best of many)
    score, bpos, drawn, labels, overlaps, failures = best
    for i, p in enumerate(bpos):
        layout.move_to(i, (p[0], p[1]))
    drawn, segments = build_drawn()
    for seed in range(6):
        r2 = random.Random(1000 + seed)
        l2, o2, f2, _ = place_labels(layout, segments, r2)
        if 3 * len(f2) + o2 < 3 * len(failures) + overlaps:
            labels, overlaps, failures = l2, o2, f2
        if overlaps == 0 and not failures:
            break
    print(f"best state: dead={len(failures)} overlaps={overlaps} "
          f"dead-ids={failures}")

    m = layout.metrics()
    print("metrics:", json.dumps(m, indent=1))

    # topology verification: stopIds must equal GTFS-derived sequences
    for d in drawn:
        rid = d["routeIds"][0]
        assert d["stopIds"] == seqs[rid], f"sequence mismatch for route {rid}"
        for k, spi_k in enumerate(d["stopPointIndex"]):
            sid = d["stopIds"][k]
            i = layout.idx[sid]
            px, py = d["points"][spi_k]
            assert abs(px - round(layout.pos[i][0], 2)) < 0.01
            assert abs(py - round(layout.pos[i][1], 2)) < 0.01

    stations = {}
    for i, sid in enumerate(layout.ids):
        anchor, angle, box = labels[sid]
        x, y = layout.pos[i]
        stations[sid] = {
            "x": round(x, 2),
            "y": round(y, 2),
            "label": stops[sid]["name"],
            "labelAnchor": anchor,
            "labelAngle": angle,
            # Exact collision-checked box origin, relative to the station.
            # The renderer places the text box here verbatim, so zero label
            # overlaps in this tool means zero on the device too.
            "labelDx": round(box.o[0] - x, 2),
            "labelDy": round(box.o[1] - y, 2),
            "interchange": sid in interchanges,
        }
    asset = {
        "version": 1,
        "canvas": {"width": CANVAS_W, "height": CANVAS_H},
        "stations": stations,
        "lines": drawn,
    }
    import os
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(asset, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT_JSON} ({os.path.getsize(OUT_JSON)} bytes)")

    render_preview(layout, drawn, labels, args.preview)
    print(f"wrote {args.preview}")

    checks = {
        "min_node_dist_ok": m["min_node_dist"] >= HARD_MIN_DIST,
        "oct_within_5deg_ok": m["pct_within_5deg"] >= 0.90,
        "label_overlaps_ok": overlaps == 0 and not failures,
        "stations_262": len(stations) == 262,
        "interchanges_23": sum(1 for s in stations.values() if s["interchange"]) == 23,
    }
    print("CHECKS:", json.dumps(checks))


if __name__ == "__main__":
    main()
