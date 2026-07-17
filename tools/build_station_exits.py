"""Build station exit-gate + nearby-landmark data from OpenStreetMap.

Fetches, via the Overpass API:
  1. Delhi Metro station entrances (``railway=subway_entrance`` nodes), each a
     physical gate with a name/ref and coordinates.
  2. Notable named POIs across the network -- tourist attractions and heritage
     sites (``tourism=*`` AND ``historic=*`` -- Delhi's monuments live under
     both), plus landmarks a commuter navigates to (hospitals, malls, colleges,
     cinemas, markets, stadiums, parks...).

Each POI is assigned to its nearest gate within 700 m; per gate the top ~10
landmarks are kept, tourist places first then nearest. The result is written to
``data/station_exits.json`` for :mod:`metropulse.application.commuter.station_exit_loader`.

Source: OpenStreetMap contributors, ODbL -- attribution required, storable.
Run:  .venv/Scripts/python.exe tools/build_station_exits.py
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "data", "station_exits.json")
# Raw Overpass responses are cached here so re-running only to change the
# ASSIGNMENT logic never needs a re-fetch. The public Overpass API rate-limits
# and times out under repeated use -- three rebuilds failed that way, blocking
# a correctness fix that needed no new data. Delete this file (or pass
# --refresh) to force a fresh fetch.
RAW_CACHE = os.path.join(ROOT, "data", "osm_raw_cache.json")

# Delhi NCR bounding box (S, W, N, E) covering the whole metro incl. Noida,
# Gurgaon, Ghaziabad, Faridabad.
BBOX = (28.30, 76.75, 28.95, 77.70)

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# A POI beyond this from every gate is dropped. Kept tight (350 m ~ a 4-minute
# walk): at 700 m, POIs near a station boundary bled onto the WRONG station's
# gate -- Chandni Chowk's gate listed "Kashmere Gate Campus", a different
# station a kilometre away. A landmark is only useful if it's genuinely at
# this exit.
MAX_GATE_DISTANCE_M = 350.0
MAX_LANDMARKS_PER_GATE = 8

# A POI is only attached if this gate is clearly its closest. When another gate
# is nearly as near, the POI is ambiguous between stations and is dropped
# rather than guessed onto one of them.
AMBIGUITY_MARGIN_M = 80.0

# category tag -> (value set, is_tourist). A POI is "tourist" when it's an
# attraction/heritage site; other landmarks are navigational, not tourist.
_TOURIST_TAGS = {
    "tourism": {
        "attraction", "museum", "gallery", "viewpoint", "artwork",
        "theme_park", "zoo", "aquarium",
    },
    "historic": {
        "monument", "memorial", "fort", "castle", "city_gate",
        "archaeological_site", "ruins", "tomb", "palace",
    },
}
_LANDMARK_TAGS = {
    "amenity": {
        "hospital", "university", "college", "theatre", "cinema",
        "marketplace", "courthouse", "townhall", "library",
    },
    "shop": {"mall", "department_store"},
    "leisure": {"stadium", "park", "garden"},
}


def _overpass(query: str) -> dict:
    """POST a query to Overpass, trying each endpoint; returns parsed JSON."""
    data = urllib.parse.urlencode({"data": query}).encode()
    last_err: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(
                endpoint, data=data,
                headers={"User-Agent": "MetroPulse/1.0 (station-exit builder)"},
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                return json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001 - report and try next endpoint
            last_err = exc
            print(f"  overpass {endpoint} failed: {exc}; retrying...", file=sys.stderr)
            time.sleep(5)
    raise RuntimeError(f"all overpass endpoints failed: {last_err}")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_GATE_SUFFIX_RE = re.compile(
    r"\s*(metro\s*station|metro)?\s*"
    r"(gate|entry|exit|entrance)\s*(no\.?|number|-)?\s*[a-z0-9]+.*$",
    re.IGNORECASE,
)
_METRO_TAIL_RE = re.compile(r"\s*(metro\s*station|metro)\s*$", re.IGNORECASE)
_REF_NUM_RE = re.compile(r"(?:gate|entry|exit|entrance)\s*(?:no\.?|number|-)?\s*([0-9]+)",
                         re.IGNORECASE)


def parse_station_name(gate_name: str) -> str:
    """'Rajiv Chowk Metro Gate No 2' -> 'Rajiv Chowk'."""
    name = _GATE_SUFFIX_RE.sub("", gate_name).strip()
    name = _METRO_TAIL_RE.sub("", name).strip(" -,")
    return name or gate_name.strip()


def parse_gate_ref(tags: dict) -> str | None:
    ref = tags.get("ref")
    if ref:
        return str(ref).strip()
    m = _REF_NUM_RE.search(tags.get("name", ""))
    return m.group(1) if m else None


def _node_bbox() -> str:
    s, w, n, e = BBOX
    return f"({s},{w},{n},{e})"


def fetch_gates() -> list[dict]:
    print("Fetching subway entrances...")
    q = f'[out:json][timeout:180];node["railway"="subway_entrance"]{_node_bbox()};out;'
    els = _overpass(q).get("elements", [])
    gates = []
    for e in els:
        tags = e.get("tags", {})
        name = tags.get("name") or "Metro gate"
        lat, lon = e.get("lat"), e.get("lon")
        if lat is None or lon is None:
            continue
        gates.append({
            "name": name,
            "gate_ref": parse_gate_ref(tags),
            "station_name": parse_station_name(name),
            "lat": float(lat),
            "lon": float(lon),
        })
    print(f"  {len(gates)} gates")
    return gates


def fetch_pois() -> list[dict]:
    print("Fetching notable POIs (tourist + landmark)...")
    # One query PER tag family, not a single union over the whole NCR bbox --
    # the combined query 504s on public Overpass. Each family is lighter.
    els: list[dict] = []
    for tag, values in {**_TOURIST_TAGS, **_LANDMARK_TAGS}.items():
        regex = "|".join(sorted(values))
        q = (f'[out:json][timeout:120];'
             f'nwr["{tag}"~"^({regex})$"]["name"]{_node_bbox()};out center tags;')
        part = _overpass(q).get("elements", [])
        print(f"  {tag}: {len(part)}")
        els.extend(part)
        time.sleep(4)
    pois = []
    for e in els:
        tags = e.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        category = None
        tourist = False
        for tag, values in _TOURIST_TAGS.items():
            if tags.get(tag) in values:
                category, tourist = tags[tag], True
                break
        if category is None:
            for tag, values in _LANDMARK_TAGS.items():
                if tags.get(tag) in values:
                    category = tags[tag]
                    break
        if category is None:
            continue
        pois.append({
            "name": name, "category": category, "tourist": tourist,
            "lat": float(lat), "lon": float(lon),
        })
    print(f"  {len(pois)} POIs ({sum(p['tourist'] for p in pois)} tourist)")
    return pois


def assign(gates: list[dict], pois: list[dict]) -> None:
    """Attach each POI to its nearest gate, when that gate is unambiguous.

    A POI goes to the closest gate within MAX_GATE_DISTANCE_M, but only if no
    gate belonging to a *different station* is within AMBIGUITY_MARGIN_M of
    that distance -- otherwise the POI sits between two stations and we'd be
    guessing. Dropping it is honest; attaching it to the wrong station is not.
    """
    for g in gates:
        g["landmarks"] = []
    for p in pois:
        # distance to every gate, nearest first
        ranked = sorted(
            ((haversine_m(p["lat"], p["lon"], g["lat"], g["lon"]), g) for g in gates),
            key=lambda t: t[0],
        )
        if not ranked or ranked[0][0] > MAX_GATE_DISTANCE_M:
            continue
        best_d, best = ranked[0]
        # Ambiguous if a gate of another station is nearly as close.
        contested = any(
            d - best_d < AMBIGUITY_MARGIN_M
            and g["station_name"].strip().lower() != best["station_name"].strip().lower()
            for d, g in ranked[1:]
        )
        if contested:
            continue
        best["landmarks"].append({
            "name": p["name"], "category": p["category"],
            "tourist": p["tourist"], "distance_m": round(best_d),
        })
    for g in gates:
        # tourist places first, then nearest; cap the list.
        g["landmarks"].sort(key=lambda lm: (not lm["tourist"], lm["distance_m"]))
        g["landmarks"] = g["landmarks"][:MAX_LANDMARKS_PER_GATE]


def main() -> int:
    refresh = "--refresh" in sys.argv
    if not refresh and os.path.exists(RAW_CACHE):
        with open(RAW_CACHE, encoding="utf-8") as f:
            raw = json.load(f)
        gates, pois = raw["gates"], raw["pois"]
        print(f"using cached OSM data ({len(gates)} gates, {len(pois)} POIs); "
              f"pass --refresh to re-fetch")
    else:
        gates = fetch_gates()
        time.sleep(3)
        pois = fetch_pois()
        os.makedirs(os.path.dirname(RAW_CACHE), exist_ok=True)
        with open(RAW_CACHE, "w", encoding="utf-8") as f:
            json.dump({"gates": gates, "pois": pois}, f, ensure_ascii=False,
                      separators=(",", ":"))
        print(f"cached raw OSM data -> {RAW_CACHE}")
    assign(gates, pois)

    with_landmarks = sum(1 for g in gates if g["landmarks"])
    tourist_total = sum(sum(x["tourist"] for x in g["landmarks"]) for g in gates)
    asset = {
        "source": "OpenStreetMap contributors",
        "license": "ODbL",
        "gates": gates,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(asset, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT_JSON}: {len(gates)} gates, "
          f"{with_landmarks} with landmarks, {tourist_total} tourist landmarks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
