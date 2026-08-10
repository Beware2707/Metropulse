# MetroPulse — Release Audit

**Role:** Principal Release Engineer · **Type:** Evidence-based integration & release audit
**Date:** 2026-07-15 · **Scope:** repo at `C:\Users\riddl\Downloads\Metro`; live backend `http://13.206.122.235:8000`
**Method:** commands executed locally + code read at `file:line` + live-backend probes. No claim below is made without code, a test, or an actual run behind it.

> **Bottom line: NO-GO for public store release. Conditional GO for an Android internal/closed beta** once the Live Map basemap is set. iOS is releasable once the store listing/legal review completes. Full rationale in §9.

---

## POST-AUDIT FIX PASS (2026-07-15) — status update

A follow-up fix pass addressed every code-fixable finding; all changes independently verified (ruff clean, mypy strict clean, **pytest 431**, **flutter analyze 0**, **flutter test 209**).

**FIXED & verified:**
- **B1 legal** — placeholder support/data-deletion email → real contact `riddlesforeverbiz@gmail.com`; governing law set to a real India/Delhi default (no user-visible "Placeholder"/"draft"); lawyer-review note kept as a code comment. *(Legal sign-off on jurisdiction still advised before public launch.)*
- **B2 iOS permissions** — added `NSLocationWhenInUseUsageDescription`, `NSMicrophoneUsageDescription`, `NSSpeechRecognitionUsageDescription`; no background modes.
- **B3 "LIVE" mislabels** — Station Detail & Train Detail now honor `isEstimated`/`isStale` and show the schedule/stale caveat (mirroring the Live Map); the tautological on-time pill is suppressed for estimated trains. No estimated data reads as bare "LIVE".
- **Android mic** — `RECORD_AUDIO` added (voice now functional).
- **Last-Mile copy** — flexible e-rickshaw now "roughly every N min", not a fixed timetable.
- **Latent `source` mislabel** — decoder sets `source="realtime_gps"` explicitly; domain default → `"unknown"`.
- **Lint hygiene** — 3 unused imports removed (ruff/analyze fully clean).
- **Disruptions** — feature-flagged off (`AppConfig.disruptionsEnabled`, default false).

**REMAINS OWNER-ACTION (deliberately NOT faked):**
- ~~**Live Map basemap = MapLibre demotiles**~~ — **RESOLVED for release builds.** Now wired to **MapTiler Streets** (`streets-v2`) via `--dart-define=MP_MAP_STYLE=https://api.maptiler.com/maps/streets-v2/style.json?key=...` — verified compiled into the APK snapshot. Key is passed at build time (NOT committed to git; the `config.dart` default stays demotiles for open-source safety). **Action for owner:** restrict the key by allowed origins + keep the free-tier cap in the MapTiler dashboard, since the key ships inside the APK binary (unavoidable for client-side maps).
- ~~**Exit guidance empty for all 262 stations**~~ — **RESOLVED (partial coverage).** Populated from OpenStreetMap (`tools/build_station_exits.py` → `load-station-exits`): **506 gates across 150/262 stations, 1,069 nearby landmarks incl. tourist places** (e.g. Chandni Chowk → Red Fort museums, Central Secretariat → Parliament Museum), tourist-flagged in the UI with © OpenStreetMap attribution. Loaded on EC2 and verified live. Remaining ~112 stations have no OSM entrance nodes yet (outer/newer lines) — honest partial coverage, not zero; improves as OSM does or via curation.
- **Journey Mode is schedule-simulated** — honest today; becomes live only when a DMRC feed is wired (architecture is ready, §6).
- **Governing-law legal substance** — lawyer confirmation before public launch.

---

## ON-DEVICE PASS (2026-07-17) — findings the code could not reveal

An Android 14 emulator (Pixel 6, `adb` screencap + input) was set up and the release APK
driven through the app for the first time. **647 passing tests, mypy-strict, and a clean
analyzer had all missed the following** — every one found by looking at a real screen:

**Fixed & verified on-device:**
- **App identified itself as `metropulse_app`** in every OS dialog/app drawer — `android:label`
  was still the Flutter scaffold default. → `MetroPulse`.
- **Green "LIVE" pill over schedule-estimated data on Home** — the *same* B3 mislabel the audit
  fixed on two screens; Home was excused as "the mildest case" and shipped. On a real screen that
  reasoning failed. `LiveIndicator` now takes `dataEstimated` and shows amber **SCHEDULE**;
  wired at all four call sites (Home, Station Detail, Train Detail, Live Map). Verified: Home
  now reads SCHEDULE.
- **Journey tab contradicted itself** — header "You're on your way" over body "You're not on a
  journey right now". Title is now state-aware; the redundant app-bar LIVE pill removed (the body
  already carries the honest source pill).
- **Raw `route_id` in user copy** — "Last train — 2 at 12:42 AM" (`headsign ?? route_id`).
  Now shows the headsign or just the time; never an internal key.
- **`GhostButton` design-system bug** — `Container(alignment:)` with no width constraint expands
  to fill loose constraints, so *every* `expand:false` GhostButton silently stretched full-width
  (onboarding's "Skip" was the most prominent control on the screen). Fixed in the shared widget.
- **Home greeting truncated mid-word** ("…explore nearby pl…") → shortened copy.
- **Live Map train markers** — cluster circles at radius 16/opacity .85 rendered as opaque blobs
  swallowing the network, and their count labels silently failed to draw (symbol layer had no
  font from the style's glyph set). Smaller, ringed, with an explicit `Noto Sans Regular`.

- **Cross-station landmark bleed — FIXED & verified live.** Chandni Chowk's gate listed
  "Kashmere Gate Campus" (a different station ~1 km away): the 700 m nearest-gate assignment had
  no station awareness. Radius tightened to 350 m (~4-min walk) + an ambiguity margin (a POI
  contested between two stations is dropped, not guessed). Applied to the live data offline using
  the `distance_m` already stored — the bleeding entries were all >350 m (Kashmere Gate Campus
  490 m, Sushila Mohan Park 445 m, Bagh Diwar 517 m) while genuine ones were <350 m. Landmarks
  1,169 → 489 across 150 stations; every remaining Chandni Chowk landmark verified as genuinely
  local. *Trade-off: precision over volume — fewer landmarks, but each one true.*
- **OSM tool now caches raw Overpass responses** (`data/osm_raw_cache.json`, `--refresh` to
  re-fetch). Three rebuilds failed to rate-limits/timeouts while trying to apply an assignment
  fix that needed **no new data** — re-fetching everything to change local logic was a design
  flaw in the tool.

**Still open (unchanged):** Home's duplicate search affordances ("Where to?" field vs "Where are
you going?" button), Home's fresh-install dead zone, no pre-prompt rationale before the location
dialog, and the absence of golden tests (the reason this class of bug survives).

---

## 1. Commands actually executed

| Command | Result |
|---|---|
| `python -m pytest -q` (backend) | **431 passed**, 1 deprecation warning, exit 0 |
| `mypy src/metropulse` (strict) | **clean — 119 source files**, exit 0 |
| `ruff check src tests` | **2 errors** (both unused imports) |
| `ruff format --check src tests` | 102/177 "would reformat" — **not a gate** (project configures only `line-length=100`, not ruff-format) |
| `flutter analyze` (app) | **1 warning** (unused import, `test/locale_hi_test.dart:11`) |
| `flutter test` (app) | **209 passed**, exit 0 |
| `dart format --set-exit-if-changed lib test` | 107/151 "would change" — **not enforced** by the project |
| Live probes | `GET /api/v1/trains` → 294 trains, **100% `source:"schedule_estimate"`**; `/journey/plan`, `/journeys/meet`, `/park-and-ride`, `/alerts` (count 0), `/alerts/reports` ([]), `/stations/{id}/exits` (12 stations → all `[]`) |

### Test / static-analysis findings
- **Passing:** backend 431/431; Flutter 209/209; mypy strict clean.
- **Failing:** none.
- **Lint (non-blocking):** `ruff` — unused `dataclass` import at `src/metropulse/application/intelligence/commute_impact.py:21` (production); unused import at `tests/test_intelligence.py:30`. `flutter analyze` — unused import `test/locale_hi_test.dart:11`. All three are `--fix`-able hygiene items, not functional defects.
- **Formatting not enforced:** neither `ruff format` nor `dart format` is wired as a gate; the tree is not auto-format-clean. Recommend adding a `dart format`/`ruff format` CI check post-release, but it does not affect correctness.

---

## 2. TODO / placeholder / mock / fake / fallback classification

There are **zero literal `TODO`/`FIXME`/`XXX`/`HACK` comments** in the tree (verified: `grep -n '\b(TODO|FIXME|XXX|HACK)\b'` → 0; earlier "TODO" hits were `toDouble()` substrings). No synthetic/random data generators exist in any backend production path.

| Bucket | Count | Representative evidence |
|---|---|---|
| **1. Legitimate test infra** | many | `tests/*` fakes: `StubFeed`/`StubPositionSource` `tests/test_realtime_engine.py:23,246`; `StubTravelTimePredictor` `test_eta_engine.py:136`; `FakeDmrcClient` `test_gtfs_static_updater.py:33`; `fakeredis` fixtures. Flutter: `_StubAdapter` `app/test/journey_share_repository_test.dart:18`, fake fetchers in park-&-ride/meet/disruptions tests. |
| **2. Legitimate UI placeholder/skeleton** | few | `shimmer_skeleton.dart:6`; text-field hints `meet_screen.dart:101`; admin dashboard input hint `api/dashboard.py:42`; sample voice prompts `voice_assistant_screen.dart:341` (trigger the real pipeline). |
| **3. Generated code** | many | `app/lib/domain/models/*.g.dart`, `app/lib/l10n/gen/*`, `alembic/versions/*` headers. |
| **4. Development fallback (acceptable, honestly labeled)** | several | Schedule-estimated positions `schedule_position_source.py` (tagged `source="schedule_estimate"`); Crashlytics inert-until-configured `crash_reporting.dart:18-39` (release-only, no PII); accessibility "no wheelchair guarantee" disclosure `journey_plan.py:33`; delay predictor's unused `direction_id` `delay_predictor.py:59` (disclosed, real data). |
| **5. Incomplete production implementation** | **1** | **MapLibre style defaults to `demotiles`** — `app/lib/core/config.dart:15`. See §5-blockers. |
| **6. Release blocker** | **1 (3 lines)** | **Placeholder legal text shipped in-app** — `app/lib/features/legal/legal_content.dart:157,233,238`. See below. |

**Bucket 6 detail — legal placeholders (CONFIRMED by direct read):**
- `legal_content.dart:157` (Privacy Policy → Contact): `'[support email placeholder — replace before publishing]'` — this is the address the policy names for **data-deletion requests**, so the promised deletion mechanism has no working contact.
- `legal_content.dart:238` (Terms → Contact): same placeholder.
- `legal_content.dart:233` (Terms → Governing law): `'Placeholder — a lawyer should confirm the right governing law and jurisdiction…'`.
These strings render on the in-app Privacy/Terms screens and self-declare "replace before publishing." → **Release blocker (compliance).**

---

## 3. User-visible data-source audit

Legend — **Official?**: DMRC/govt vs third-party vs computed-by-us vs crowdsourced. **Live?**: realtime telemetry vs schedule-derived vs static.

| Feature | Source | Official? | Live? | Estimated? | Freshness | Offline | Fallback |
|---|---|---|---|---|---|---|---|
| Live Map / train positions | `schedule_position_source.py:46` interpolates static GTFS shapes | Computed from DMRC **static** schedule | **Schedule-derived, NOT GPS** | Yes | worker polls 5 s; WS diffs | not cached | banner "estimated from the schedule, not live GPS" (`live_map_screen.dart:229`) |
| ETA per station | `eta_engine.py:77` from position+shape+stop_times | Computed | derived from estimate | Yes (speed/dwell) | per poll | none | `confidence` graded; null if unusable |
| "On time / late" | `eta_engine.py:155` | Computed | — | Yes (≈0 delay under schedule mode) | per poll | none | null if implausible |
| Journey plan times | `journey_planner.py` Dijkstra over stop_times | DMRC static | Schedule | duration real; wait/walk heuristic | static until reload | offline bundle | 404 |
| Fares | `fare.dart`, `_slab_fare` | Computed from DMRC **published** slabs (no fare API) | n/a | Yes | static table | client-side | honest note |
| Next-train / last-train | `journey_tools.py`, `last_train.py` | DMRC static (⚠ manual `end_date` override 2025→2030, `data/raw_gtfs/OVERRIDE_NOTES.md`) | Schedule | no | static | offline bundle | 404 |
| Station facilities | Delhi Transport Stack xlsx, name/coord match | Third-party curated | Static snapshot | no | manual load | station cache | unmatched reported |
| Park & ride | facilities + planner time | Curated + computed | Static | Yes (straight-line dist; capacity ≠ live) | static | — | 404 |
| Last-mile e-rickshaw | `shared_mobility_gtfs_v1.zip` | Third-party curated | Static (frequencies) | no | manual load | station cache | absent → hidden |
| Weather | Open-Meteo (device) | Third-party | Third-party live | n/a | 6 s fetch | none → null | self-labeled "decorative" |
| Air quality | Open-Meteo air-quality (device) | Third-party | Third-party live | n/a | 6 s fetch | none → null | attributed, errors→null |
| Fare advisor | user journeys + slabs | Computed | historical | Yes | 30-day window | — | empty note at 0 trips |
| Commute replay | stored journeys | Computed | historical | Yes | per request | — | hidden at 0 trips |
| Reach / Meet | planner `travel_seconds_from` | Schedule | Schedule | no | static | — | 404 |
| Disruptions — official | admin `POST /admin/alerts` only | **Admin-entered — NO DMRC feed** | not ingested | no | on admin action | — | empty |
| Disruptions — rider | `POST /alerts/reports` `source='rider'` | Crowdsourced, unverified | recent window | no | 120 min | — | deduped |
| Crowding / coach | `HistoricalCrowdPredictor` over rider `CrowdObservation` | Crowdsourced + prior | historical avg | Yes | 28-day | — | prior when sparse |
| Journey sharing pos. | sharer **device GPS** | User device | live (device) | no | on report; 12 h TTL | — | ETA null if underivable; **no PII** |
| Network schematic map | bundled `assets/network_schematic.json` | Static designed asset | static | no | app bundle | **fully offline** | lenient anchor |

**Is there ANY official DMRC realtime feed today? — No.** `config.py:52 gtfs_rt_enabled=False` (default); the configured OTD URL is Delhi's **city bus** GPS, not metro (documented `config.py:43-51`); the deployed backend serves 100% `schedule_estimate` positions (verified live). The GTFS-RT ingestion path exists but is dormant.

**Sources presented as more live/authoritative than they are** (→ §7):
1. **Station Detail "Arriving now" + green "LIVE" pill** with no estimate caveat (`station_detail_screen.dart:109,116`).
2. **Train Detail green "LIVE" pill** + no `isEstimated`/`isStale` check anywhere in the file (`train_detail_screen.dart:43`).
3. **Disruptions "official alerts come from DMRC"** while no DMRC alert feed is connected (`disruptions_screen.dart:104,117`).
4. **`VehiclePosition.source` defaults to `"realtime_gps"`** (`domain/entities.py:49`, `train.dart:39`) — latent mislabel-by-default (inactive today, since the schedule source always sets `schedule_estimate` explicitly).

---

## 4. Core commuter flow audit (priority over all secondary features)

Open → Search → Plan → Start → Companion → Interchange → Destination → Exit.

| Hop | Status | Evidence |
|---|---|---|
| 1 Open / splash / onboarding | **works** | `/splash` initial, offline-tolerant boot, 4 real onboarding slides (`splash_screen.dart:48-60`, `onboarding_screen.dart`) |
| 2 Search destination | **works (caveat)** | fully offline over cached bundle; picking a result opens **Station Detail**, and the search→plan bridge is the "Directions" button → `/planner?destination=` (`search_screen.dart:154`, `station_detail_screen.dart:124`). Two-step handoff, not search→plan direct. |
| 3 Plan journey | **works (verified live)** | `GET /journey/plan` returns real multi-leg plans with interchanges/fare; `57→227` → `interchange_count:1` (`journey_planner_screen.dart`, live probe) |
| 4 Start journey | **works, defining caveat** | `repository.start()` is called with **no `vehicleId`** (`journey_planner_screen.dart:418-423`, the only call site) → backend stores `vehicle_id=null` |
| 5 Journey Mode / Companion | **works, never "live"** | because `vehicleId==null`, `journeyProgressProvider` always uses `fromTimetable(...)`, a **1-second clock simulation** over prorated schedule (`journey_mode_providers.dart:112-142`). The "LIVE TRACKING" pill is unreachable in this flow; it is always "SCHEDULED ESTIMATE" (**honestly labeled**). Server-side interchange/delay/arrival push notifications never fire (`journey_session.py:75 if not journey.vehicle_id: return None`). |
| 6 Interchange | **works (simulated)** | real interchange ids from the plan; "Time to change trains" banner fires on the sim clock (`journey_timetable.dart:79`, `companion_messages.dart:59`) |
| 7 Destination arrival | **works, simulated** | arrival = sim clock past last stop, user taps "I've arrived" to close; can announce "You're here" before a delayed train actually arrives (`journey_mode_screen.dart:255,369`) |
| 8 Exit guidance | **empty in production** | exit row renders only `if (exitName != null)`; endpoint 404s when no curated exits. **Verified live: 0 of 262 stations have exits** (`/stations/{id}/exits` → `[]` for all 12 probed; bundle `stations-with-exits: 0`). Onboarding promises "the exit closest to where you're headed — every time" (`onboarding_screen.dart:34`) → produces **nothing** for any station. Fails silently (no fabricated data). |

**Weakest link:** Journey Mode is a schedule replay, not live tracking — it will drift on any delayed/held train and can declare arrival early. It is labeled honestly, so it is not deceptive, but the flagship "live companion" is not live in the shipped configuration. **Second:** exit guidance is non-functional at every station.

**Core-flow verdict:** production-ready **as an honest schedule-based planner + guide** (boot, search, real planning, coach/platform/interchange prompts, manual arrival, post-trip replay all work). **Not** production-ready as the advertised **live** companion, and two promoted promises (live tracking, exit-to-landmark) do not function.

---

## 5. Secondary-feature audit + feature-flag decisions

No pre-existing boolean feature-flag system existed; config is build-time `String.fromEnvironment` in `AppConfig`. All nine features are pushed routes (none is a bottom-tab), so **none competes with the 4-tab core navigation**.

| Feature | Complete E2E? | Prod-data dependency | Misleading? | Decision |
|---|---|---|---|---|
| Meet | Yes (live-verified) | static GTFS (available) | No | **SHIP** |
| Park & Ride | Yes (live-verified) | facilities seeded | No | **SHIP** |
| Tickets | Yes (external hand-off) | none | No | **SHIP** |
| Air Quality | Yes | Open-Meteo; hides on error | No (attributed) | **SHIP** |
| Weather | Yes | Open-Meteo | No ("decorative") | **SHIP** |
| Journey Sharing | Yes, PII-free | active journey; ⚠ prod must set public `MP_API_BASE` for share links | No | **SHIP** |
| Replay | Yes, data-gated | empty until user has trips; hides at 0 | No | **SHIP** |
| Last Mile | Yes, partial coverage | curated subset | **Mild** — renders flexible e-rickshaw as "every 5 min" (`station_detail_screen.dart:320`), overstating a demand-based service | **SHIP-WITH-COPY-FIX** |
| **Disruptions** | Structurally wired, **hollow in prod** | **both lists empty** (no DMRC alert ingestion — admin-only `create`; rider needs volume; live `/alerts`→0, `/alerts/reports`→[]) | **Yes** — "No service alerts from DMRC right now" implies a DMRC feed that isn't connected | **FLAG (implemented)** |

**Action taken (the one authorized change):** Disruptions is now gated behind `AppConfig.disruptionsEnabled` (`bool.fromEnvironment('MP_ENABLE_DISRUPTIONS', defaultValue: false)`):
- `app/lib/core/config.dart` — the flag, documented, default **off**.
- `app/lib/core/router.dart:/disruptions` — `redirect` to `/` when disabled (stray deep-link can't reach the empty board).
- `app/lib/features/notifications/notifications_screen.dart` — the entry button is wrapped in `if (AppConfig.disruptionsEnabled)`.
Verified: `flutter analyze` clean, `flutter test` 209/209 pass. Re-enable with `--dart-define=MP_ENABLE_DISRUPTIONS=true` once a real alert source is wired **or** the "from DMRC" copy is corrected.

**Not flagged, needs copy fix (not implemented — flagged for owner):** Last-Mile "every N min" for flexible routes.

---

## 6. Realtime architecture — DMRC feed readiness

**Verdict: adapter-pluggable — an official DMRC feed can be added WITHOUT rewriting the core.**

- The engine depends on **Protocol ports**, not concretes: `FeedSource` (raw protobuf) and `PositionSource` (decoded), plus an injectable `Decoder` (`realtime_engine.py:37-58`). `RealtimeEngine.__init__` accepts either and branches in `poll_once` (`:148-153`). Tests exercise both (`tests/test_realtime_engine.py:236,259`).
- The current schedule source **is itself a `PositionSource` implementation** (`schedule_position_source.py:26`) — proof the seam already carries a second, non-feed source in production.
- `source` is a **data field** carried end-to-end into Flutter (`entities.py:49` → `train.dart:39`, `isEstimated` getter `:44`); live-vs-schedule is a value on the payload, not a code path.

| Surface | Rewrite needed to add DMRC live? | Why |
|---|---|---|
| Journey Mode | **No** | already branches live-vehicle vs timetable (`journey_mode_providers.dart:112-143`) |
| Live Map | **No** | banner toggles off `t.isEstimated` (`live_map_screen.dart:225-229`) |
| ETA presentation | **No** | `EtaEngine.compute` takes any `VehiclePosition`; real `speed_mps` just upgrades speed source (`eta_engine.py:244`) |
| WebSocket consumers | **No** | frames are source-agnostic diffs (`realtime_engine.py:195-216`, `ws/live.py`) |
| Flutter state mgmt | **No** | `LiveTrainsNotifier` fed purely by snapshot+diff (`live_providers.dart:35-68`) |

**Files a DMRC adapter touches:** if DMRC emits standard GTFS-RT protobuf → likely *none* (reuse `gtfs_rt/client.py` + `decoder.py`), just config (`config.py` flag/URL/key, `cli.py:226-238` selection). If a non-GTFS-RT shape → **one new file** implementing `FeedSource`+`Decoder` or `PositionSource`. **Untouched:** `realtime_engine.py`, `snapshot.py`, vehicle store, `eta_engine.py`, `ws/live.py`, and **all Flutter**.

**One precise caveat (do not overstate readiness):** the source is chosen once at worker start (config-time XOR — `cli.py:226-238`). There is **no in-process automatic "use DMRC live, fall back to schedule when the feed is stale"** switch today. That needs a thin **composite `PositionSource`** (try DMRC, else `ScheduleEstimatedPositionSource`) — **additive to the existing port, not a core rewrite.** Do NOT invent the DMRC schema; wire it behind these ports when the real feed spec arrives.

---

## 7. Status-label truthfulness

Staleness **is** detected server-side (time-based, 90 s default: `entities.py:51-53`, `config.py:74`, `snapshot.py:55-61` → client `isStale` `live_providers.dart:56`). The five canonical states all exist as **concepts** but are **ad-hoc**: three disjoint enums (`WsStatus`, `JourneyProgressSource`, + `isStale`/`isEstimated` booleans), no shared status model, derived per screen — which is exactly why coverage is inconsistent.

**Honest surfaces (verified correct):** Live Map ("estimated from the schedule, not live GPS"), Journey Mode ("SCHEDULED ESTIMATE" vs "LIVE TRACKING", downgrades stale live → estimate), crowd source labels, weather/AQI attribution, Meet/Reach/planner "published timetable" captions, fare "(est.)".

**MISLABELS — must fix before public release (violate the explicit rule "never label schedule interpolation as Live"):**
1. **Station Detail "Arriving now" board** — green "LIVE" pill + concrete ETAs, **no estimate/stale caveat** on the screen; shows interpolated arrivals under "LIVE" when the deployment is in schedule mode (`station_detail_screen.dart:109,116,143`). The `isEstimated` flag is available but unused here.
2. **Train Detail screen** — green "LIVE" pill + status + on-time/late pill + per-station ETAs, and the file **never checks `isEstimated`/`isStale`** (grep-confirmed). The map's bottom sheet labels the *same* train honestly — so this is an inconsistency, not a data limit.
3. **Latent:** `VehiclePosition.source` default `"realtime_gps"` — a position reaching the client without an explicit source is labeled real GPS. Inactive today; recommend defaulting to `schedule_estimate`/`unknown`.

("LIVE" reflects **WebSocket connectivity**, set on any frame including heartbeats — `ws_client.dart:111`, `live_indicator.dart:34`. It is honest where the screen adds a data-source caveat, misleading where it does not.)

---

## 8. Privacy & permissions

Verified against the **packaged release manifest** (`app/build/.../packaged_manifests/release/AndroidManifest.xml`) and `app/ios/Runner/Info.plist`.

| Capability | Declared? | Justified / timing | Graceful denial? | Leak risk |
|---|---|---|---|---|
| Foreground location | Android FINE+COARSE (plugin-merged); **iOS usage string MISSING** | on-demand, low-accuracy, at point of use (`location_service.dart:44`) | Yes (`home_providers.dart:215`, park&ride manual fallback) | none (local) |
| **Background location** | **NOT requested** (verified absent from merged manifest) | correctly unused | n/a | none |
| Microphone (voice) | Android `RECORD_AUDIO` **not declared** → mic init fails; **iOS usage string MISSING** | only during explicit listen toggle, stopped on dispose (`voice_assistant_screen.dart:77-112`) | Yes ("Voice input isn't available" + tappable prompts) | none; never always-on |
| Notifications | `POST_NOTIFICATIONS` (merged) | requested at first use, gated on opt-in | Yes | none |
| Journey sharing | network feature | user-initiated, stoppable | GPS-denied auto-stops | **none — verified PII-free** |
| Rider reports | network feature | auth to post | empty on error | **no identity exposed** |

**Cleared with evidence (NOT blockers):** no background location; public share link/page carry **no PII** (`SharedJourneyPublicOut` = status/names/lat-lon/nearest/eta only; 128-bit token; 12 h TTL; 410-on-expiry; `<meta robots noindex>`; XSS-safe `json.dumps`); rider feed exposes no `user_id` (moderation-only); mic never always-on; Crashlytics release-only, inert in debug, **no `setUserId`/custom keys** (no PII).

**Privacy / permission blockers & gaps:**
- **iOS RELEASE BLOCKER:** `Info.plist` declares **none** of `NSLocationWhenInUseUsageDescription` / `NSMicrophoneUsageDescription` / `NSSpeechRecognitionUsageDescription`. geolocator and speech_to_text hard-crash / App-Store-reject without them. (Android unaffected.)
- **Android mic non-functional (not privacy):** `RECORD_AUDIO` undeclared → voice-by-mic degrades to "unavailable"; add the permission to make the mic feature work on Android.
- **Rider reports:** no rate-limit or content moderation on submit (`alerts.py:185-216`) — add a throttle before scaling the public feed.
- No pre-prompt rationale sheet before the OS location prompt (acceptable given contextual trigger; nice-to-have).

---

## 9. Release readiness & GO / NO-GO

### Release blockers (must clear before a public store submission)
| # | Blocker | Evidence | Platform | Owner action |
|---|---|---|---|---|
| B1 | Placeholder legal text in shipped Privacy/Terms (incl. non-working data-deletion contact) | `legal_content.dart:157,233,238` | Android + iOS | Replace support email + governing law; lawyer review |
| B2 | iOS `Info.plist` missing all permission usage strings (location/mic/speech) | `app/ios/Runner/Info.plist` | iOS only | Add 3 `*UsageDescription` keys |
| B3 | Schedule estimates shown under "LIVE" without caveat (Station Detail, Train Detail) | `station_detail_screen.dart:109-116`; `train_detail_screen.dart:43` (no `isEstimated`) | Android + iOS | Add estimate/stale caveat + honor `isEstimated`/`isStale` |

### Incomplete features (function-degraded, not deceptive)
- **Live Map basemap = MapLibre demotiles** (`config.dart:15`) — demo world map, no streets/stations, demo host with no SLA; shipped APK was built without `MP_MAP_STYLE`. Set a real style key at build (or accept a degraded map). *(Bucket 5.)*
- **Exit guidance empty for all 262 stations** — promoted feature produces nothing in production (verified live). Curate exit data or stop promoting it in onboarding.
- **Journey Mode is schedule-simulated, not live** — flagship "live" guidance drifts on delays; honest labeling holds, but manage the marketing claim until a DMRC feed lands.
- **Android voice-by-mic broken** — `RECORD_AUDIO` undeclared.

### Recommended for feature flag
- **Disruptions — DONE**, gated `AppConfig.disruptionsEnabled=false`. Re-enable when an alert source is wired or copy corrected.

### Copy fixes (not implemented — owner)
- Last-Mile "every N min" for flexible e-rickshaw → soften ("runs ~every N min" / drop for demand-based).
- Disruptions empty-state "from DMRC" (moot while flagged off).
- Default `VehiclePosition.source` to a non-"realtime_gps" value.

### Manual physical-device tests required (cannot be verified from code/CI)
1. Real GPS **share link** opens on a second device and updates live; Stop halts updates; link dies at 12 h.
2. **Location permission** prompt + graceful denial on a real Android device and (once B2 fixed) iOS.
3. **Notification** actually fires for a scheduled last-train reminder at the computed time.
4. **Voice** mic capture on Android after `RECORD_AUDIO` is added.
5. **Live Map** rendering with a real `MP_MAP_STYLE` (confirm streets/stations draw).
6. **Journey Mode** end-to-end on an actual ride — confirm drift on a delayed train and the honesty of the "SCHEDULED ESTIMATE" label in the wild.
7. **Hindi** switch persists across restart; core-flow screens render Devanagari; no layout overflow.
8. Cold-start **offline** behavior (airplane mode) across search/plan/map.

### DMRC realtime integration readiness
**Ready — adapter-pluggable, no core rewrite** (§6). When DMRC provides the feed: wire it behind the existing `FeedSource`/`PositionSource`/`Decoder` ports; if standard GTFS-RT, it's a config flip against `gtfs_rt/client.py` + `decoder.py`; if not, one new adapter file. Add a composite source for automatic live→schedule fallback (additive). Do not invent the DMRC schema. Journey Mode, Live Map, ETA, WS, and all Flutter state remain untouched. **Prerequisite:** once real GPS flows, B3 resolves naturally (`isEstimated` goes false) — but B3 must still be fixed for the current schedule-mode release.

### Verdict
- **Public Play Store / App Store: NO-GO.** Blockers B1 (legal) and B3 ("LIVE" mislabels) apply to both platforms; B2 (iOS permissions) blocks iOS. None is large; all are addressable in a focused pass.
- **iOS: NO-GO** until B2 (+B1, B3).
- **Android internal / closed beta: CONDITIONAL GO** after B3 (label truthfulness) and a real `MP_MAP_STYLE`, with B1 acknowledged as a known pre-public gap and Disruptions flagged off (done). The backend (431 tests, mypy-clean, adapter-ready) and the honest schedule-based core flow are solid enough for controlled testing.

**What is genuinely production-ready today:** the backend and its realtime architecture; the honest schedule-based planner (search → plan → coach/interchange guidance → manual arrival → replay); Meet, Park & Ride, Tickets, Weather, Air Quality, Journey Sharing (with public `MP_API_BASE`), Replay, and partial Last-Mile. **Not production-ready:** anything advertised as *live* train tracking, exit-to-landmark guidance, the demotiles Live Map basemap, Android mic voice, and — for any public submission — the legal text and iOS permission strings.

---
*Every finding above is backed by a `file:line`, a test, or a live-backend probe. No score is assigned; the GO/NO-GO rests on the enumerated, reproducible blockers.*

---

## 10. Golden-test pass (regression net for the visual bugs)

The on-device pass found 8 real bugs that 218 Flutter tests, a clean analyzer
and a mypy-strict backend all missed — because none of them looked at pixels.
Goldens were added over the three surfaces where those bugs actually lived,
rather than over whole screens (screen-level goldens need the entire
provider/network stack and go brittle fast).

`app/test/golden_honesty_test.dart` — 6 goldens, all passing:

| Golden | Guards against |
|---|---|
| `live_indicator_live` / `_schedule` / `_reconnecting` | the pill claiming green **LIVE** over `source="schedule_estimate"` data |
| `ghost_button_compact` / `_expanded` | `expand:false` silently stretching to full width |
| `exit_landmarks_tourist` | a tourist place being indistinguishable from a bank |

**The net was verified, not assumed.** Both original bugs were deliberately
re-introduced; the two corresponding goldens failed and the other four stayed
green (no false positives). `test/failures/live_indicator_schedule_testImage.png`
rendered the green LIVE lie against its amber SCHEDULE master. Both regressions
were then reverted and the suite re-confirmed green.

### Two harness defects found while building the net

Both matter because they are the "blind golden" failure mode — a golden that
passes forever while recording the wrong thing:

1. **Icons rendered as tofu.** The first `exit_landmarks_tourist` baseline
   recorded the tourist marker as an empty box, because Flutter's icon font
   isn't loaded in `flutter test`. Left alone it would have gone green forever
   while proving nothing. `flutter_test_config.dart` now loads
   `materialicons-regular.otf` (resolved via `FLUTTER_ROOT`, not a hardcoded
   path) and throws rather than silently falling back.
2. **`pumpAndSettle` cannot settle** a `LiveIndicator` — its dot pulses forever.
   The goldens advance the fake clock by exactly one 1200 ms pulse instead,
   which is deterministic and lands the dot at full opacity.

### Production bug found: fonts were fetched over the network on every cold start

Not a test artifact — a real shipped defect, surfaced only because goldens
forced the font question.

- **Symptom:** `google_fonts` requested `PlusJakartaSans-Regular` (w400), a
  weight the app does not bundle, and fetched it from `fonts.gstatic.com`.
- **Cause:** `app_typography.dart:11` started from
  `GoogleFonts.plusJakartaSansTextTheme()` and `copyWith`'d weights afterwards.
  The helper resolves Material's *default* text theme first — largely w400 —
  so the fetch fired regardless of the overrides that followed.
- **Impact:** a network request on every cold start; offline, a silent fallback
  to Roboto. Nothing failed loudly. `assets/google_fonts/README.md` asserted
  the opposite ("the only four weights `app_typography.dart` actually
  requests") and was simply wrong.
- **Fix:** every style is now built directly via
  `GoogleFonts.plusJakartaSans(fontWeight: ...)` at only the four bundled
  weights (500/600/700/800).
- **Verified:** with both harness crutches removed (no manual `FontLoader`,
  `allowRuntimeFetching` left **on**), the suite attempts **zero** gstatic
  fetches. The identical command before the fix produced
  `Failed to load font with url: https://fonts.gstatic.com/...`. The README's
  false claim is corrected and the trap documented.

**Status:** `flutter analyze` clean; 218/218 Flutter tests pass.

---

## 11. Deep check + APK rebuild (multi-agent audit, 7 dimensions)

A 61-agent audit across honesty, release-blockers, Flutter/backend correctness,
privacy-security, test-integrity and consistency. Every candidate was
independently verified by two adversarial reviewers (a refuter and a release
engineer); a finding survived only on unanimous non-refutation.

**27 candidates -> 17 confirmed, 10 refuted.** The refuted ten are as important
as the confirmed: they were plausible-sounding claims that did not survive
someone reading the actual file.

**Verification baseline (re-established, not assumed):** `flutter analyze`
clean; mypy strict clean; ruff clean; **673 tests pass** (443 backend + 230
Flutter), up from 653.

### FIXED: the honesty guard failed open in three separate ways

All three are the same underlying mistake — *absence of evidence resolving to
the claim instead of the caveat* — and none was caught by 653 tests, mypy
strict, a clean analyzer, or the golden tests added earlier the same day.

1. **`Vehicle.source` defaulted to `'realtime_gps'`** (`train.dart:39`). Any
   payload missing the field deserialized to "this is real GPS" and lit a green
   LIVE. The comment claimed this was "the honest assumption" — it was the
   dishonest one, since no DMRC realtime feed exists at all. Now defaults to
   `schedule_estimate`.
2. **`isEstimated` was `source == 'schedule_estimate'`** — so any *unknown*
   value (a future backend tag, a typo) counted as live. Found by a test
   written for #1, not by the audit. Now `source != 'realtime_gps'`: only an
   affirmative realtime_gps may claim live.
3. **`.any()` on an empty collection returns `false`** (`live_map_screen.dart:129`,
   `home_screen.dart:183`, `station_detail_screen.dart:68`). An empty train
   table therefore meant "not estimated" -> green LIVE, caveats suppressed, and
   the map pill flipped to the explicit lie *"Dots are trains, moving live"*.
   Not a startup blip: `WsStatus.live` is not gated on train data (it fires on
   any frame, and heartbeats sustain it), so "socket up, table empty" is a
   stable state — a quiet station, or any time after service hours.

The rule now lives in **one** place (`dataEstimatedProvider` /
`arrivalsEstimatedProvider`, `live_providers.dart`) rather than being re-derived
at each call site, because it was re-derived wrongly at three call sites at once.
**Empty means estimated.**

*Verified on-device, not just in tests:* on a fresh install with an empty train
table — the exact state that shipped the lie — Home and Live Map both render an
amber **SCHEDULE** pill plus "Train positions are estimated from the schedule,
not live GPS."

### FIXED: the last train after midnight was invisible

`next_departure()` (`last_train.py`) scanned only today's and tomorrow's service
dates. GTFS stores a post-midnight trip on the day it *started*, with hours past
24 — and the real DMRC feed does this **1,410 times**, running to **25:13**. So a
commuter on a platform at 00:30 was told the next train was tomorrow morning
while a train 15 minutes away was hidden — wrong at the hour the answer matters
most. Now scans `(-1, 0, 1)` and returns the earliest by real `departure_at`.
The default GTFS test fixture has no post-midnight trip, which is exactly why
435 tests missed it; `tests/test_post_midnight_departures.py` adds one.

### FIXED: the privacy policy contradicted the code

`legal_content.dart` stated "Your live location never leaves your device" and
"never transmitted to or stored on our servers", while journey sharing uploads
device GPS every ~20 s to an **unauthenticated public** endpoint. (The in-app
share UI was already honest — it was specifically the legal document, the
artifact regulators and Play's Data Safety form are read against, that was
false.) The policy now carves out sharing explicitly.

### FIXED: shared GPS traces were kept forever

`SHARE_TTL` (12 h) only ever gated *readability* — the row kept `last_lat`/
`last_lon` indefinitely. Every other category had retention (vehicle history
72 h, analytics 90 days); the user's own position, the most sensitive data here,
had none, and the retention list omitted it while reading as complete. Added
`forget_expired_share_positions` (hourly, `share_position_retention_hours`,
default 24 h), which nulls the coordinates and keeps the row as an audit trail.
Retention list updated — including disambiguating "vehicle position history" as
*the trains', not yours*.

### FIXED: the store listing sold "Live Delhi Metro tracking"

`docs/play_store_listing.md` — the copy read by the largest audience the project
has — led with **"Live Delhi Metro tracking"** and offered "when a live GPS feed
is available for a line, you're watching the real thing", a conditional implying
some line has GPS. None does. The whole app was engineered never to show green
LIVE over interpolated data; the listing undid it before install, while
self-certifying "nothing here describes a planned or aspirational feature".
Rewritten to state positions are timetable-estimated. Exit coverage corrected
from an implied "every destination" to the measured **150 of 262 stations**
(counted against the live backend).

### Not fixed — these are owner decisions, not code bugs

- **Release is signed with the Android debug key** (`build.gradle.kts:34`;
  confirmed against the built APK's certificate: `CN=Android Debug`). Play hard-
  rejects debug-signed uploads, and the signing key binds permanently to the
  applicationId on first publish — so this must be a deliberate choice, made
  once, by the owner. Fine for sideloading; fatal for Play.
- **Cleartext HTTP to a bare EC2 IP carrying Bearer tokens**
  (`network_security_config.xml`). The device token is the sole account
  credential and is sniffable on hostile Wi-Fi — i.e. station concourses, where
  this app is used. Needs a domain + TLS, which is infrastructure, not code.

### APK

Rebuilt release, **87.4 MB**. Verified by inspecting the binary rather than
trusting the build log: `MP_API_BASE=http://13.206.122.235:8000` and the real
MapTiler `streets-v2` style are both compiled into `libapp.so`, with **no**
demotiles fallback. The MapTiler key is in neither the repo nor the git folder.
Installed and exercised on the emulator (screenshots above). Backend confirmed
live (`/health` 200; 262 stations; exits serving `landmarks_detail` with real
tourist flags).

**Status: unchanged GO for sideload/internal testing; still NO-GO for Play**
until the signing key and TLS are resolved by the owner.

---

## 12. DMRC Open Transit Data integration (8 new files in Downloads)

Eight files arrived from the OTD portal. Verdicts, from a 5-agent parse +
cross-check pass over every row:

| File | Verdict |
|---|---|
| `pathways.zip` (GTFS-Pathways) | **Integrated** — 220 stations / 9 lines of gate-lift-platform graphs (its own README wrongly claims 3 lines) |
| `dmrc_station_and_gate_locations.xlsx` | **Integrated** — official registry; 258/264 codes resolved; backfills `stops.stop_code`, +531 official gate exits |
| `stationwise_hourly_entry_exit_february_2024.xlsx` | **Integrated** — filename lies: actually Sep 2024–Feb 2025, 181 service days, 741 profiles |
| `od_flow_jan_2021_jan_2025.xlsx` | **Integrated** (Jan 2025 month) — 98.9M journeys, top destinations per origin |
| `dmrc_static_gtfs_v1.zip` | **Skipped** — identical timetable but `calendar.txt` expired 2025-12-31; loading it would kill every departure |
| Shop/Subway `.xlsb` | **Skipped** — third-party crowdsourced points, no station linkage |

### What shipped

Three new curated tables (`station_accessibility`, `station_hourly_load`,
`station_top_destinations`; migration 0012), a 4-stage `load-otd` CLI, three
API endpoints (`/accessibility`, `/busyness`, `/top-destinations`), and three
station-detail sections — every one carrying its source and data vintage
("DMRC ridership data, Sep 2024 – Feb 2025"), because a dated snapshot without
its date is an overclaim. Incomplete pathway coverage reads "partly mapped",
never "not accessible" — a dataset gap is not a missing lift.

### Two integration bugs the adversarial cross-check caught before they shipped

1. **Interchange stations have one code per line** (Kashmere Gate = KGM + KGR
   + KG-6, all one stop). The hourly loader overwrote instead of summing; the
   OD loader would have violated the unique index outright. Both now merge
   onto the resolved stop. Regression tests confirmed failing on the old code.
2. **Placeholder coordinates in the official registry** — clusters of gates
   pinned to single points, including one in Bharatpur, Rajasthan, 127 km
   away. Gates >2 km from their own station keep their name/description but
   lose their coords rather than draw an exit in another state.

### Data quality worth remembering

The parsers reported (not cleaned away): 44 pathway edges whose endpoints are
mangled free-text ("no lift at this gate"), 30 stops with no coordinates, one
station 74.9 km off, gates mostly at station-level precision, 45 unparseable
gate rows, and blank duplicate OD rows per the workbook's own legend. Only
62/220 stations have a strictly connected step-free chain — which is why the
UI's `complete` wording is conservative.

### Verified

- 452 backend tests (9 new loader tests incl. revert-verified regressions),
  236 Flutter tests (6 new section tests); mypy strict, ruff, analyzer clean.
- Real load on local Postgres: 258 codes, 213 accessibility graphs, 228
  busyness profiles, 228 destination sets; unmatched codes (6 stations newer
  than the GTFS network) reported, not guessed.
- Live API spot-check: Rajiv Chowk peaks at 9,095 entries/hr on weekdays and
  sent 2.65M riders in Jan 2025, top destination Chandni Chowk; uncovered
  stations 404. Numbers pass the Delhi smell test.
- APK rebuilt (87.5 MB); new endpoints + attribution strings verified inside
  `libapp.so`; installed on emulator.

**EC2 push: DONE** (after the owner widened the security group to
103.62.92.0/22 — the recurring SSH lockout is the ISP hopping within that
block). Deployed via docker compose rebuild; migration 0012 applied (exit 0);
`load-otd` run with the artifacts mounted: 258 codes, 213 accessibility
graphs, 228 busyness profiles, 228 destination sets, and **151 official
exits added with 380 skipped where OSM already covers** — the OSM-priority
logic doing exactly its job in production. Station exit coverage is now
**223/262** (was 150). Live-verified: all three endpoints answer with real
data, and the emulator (APK pointed at EC2) renders all three sections —
histogram peak "around 7 PM" at Chandni Chowk, top destination New Delhi
95.9k riders, every section attributed and dated. This deploy also shipped
the earlier post-midnight last-train fix and the share-position retention
job, which predated the previous 32-hour-old containers.

---

## 13. Crowd-aware journeys + step-free gate guidance

The two features that turn the OTD datasets from display into decisions.

**Crowd-aware journey planning.** `CrowdForecastService` scores every station
on a planned route against ITS OWN weekly peak (a small station's rush reads
busy for that station) and suggests a nearby quieter departure only when the
route is actually busy AND the shift saves >= 15 points. The planner shows a
one-line advisory ("Rajiv Chowk is usually at its busiest around now —
typically ~51% quieter leaving around 9 PM"), worded "typically", vintage
attributed, hidden entirely on quiet routes.

*Bug caught by probing production, not by tests:* the first deploy suggested
leaving at **1:13 AM** from a quiet 10 PM route — "quieter" because the metro
is CLOSED then; near-zero closed-hours entries read as an improvement. Fixed
by gating suggestions on the busy threshold (which also keeps the search
window inside service hours); the regression test reproduces the exact
production case. Live re-probe: quiet 10 PM -> no suggestion; peak 6 PM ->
"21:00, 51% quieter".

**Step-free gate guidance.** Connected-component reachability over the stored
pathways graph: a gate qualifies when its component contains a lift AND a
platform (concourse nodes participate — most real chains route through them;
self-loops and the feed's mangled free-text endpoints are handled). Exposed as
`step_free_gates` on the accessibility endpoint; the station's Step-free
section names the qualifying gates, and exits get an accessible badge on an
EXACT gate-number match only — fuzzy matching would badge the wrong gate,
the one mistake that costs a wheelchair user a staircase. Live: **58 stations
expose 122 step-free gates.** Verified on-device at Chandni Chowk: Gate No. 2
badged, Gates 1 and 3 correctly not.

**Verified:** 460 backend + 240 Flutter tests (all new logic revert-verified
or reproducing a live failure); mypy/ruff/analyzer clean; deployed to EC2 and
probed live; APK rebuilt (87.5 MB) and exercised on the emulator.

---

## 14. Bus + multimodal via Delhi Transport Stack (licensed API)

The deferred bus integration ("we will add after getting data") — a DTS
Multimodal Journey Planner key was approved 2026-07-24 (expires 2027-07-24).

**License read before writing code.** Transport Stack Schedule 1 permits
modification, separation and compilation into a multi-source app; it requires
**attribution**. Every response carries `attribution` and the UI renders
"Journey options: Delhi Transport Stack" under the options. Perpetual term.

**Key hygiene.** The key lives only in the EC2 `.env` (`DTS_API_KEY`,
`SecretStr` like every other key), passed via an optional compose variable so
an unset key simply turns the feature off (503, stated plainly). Verified
absent from every tracked file, from the git folder, and from the APK binary.

**What shipped.** `MultimodalPlanService` proxies DTS server-side and
normalizes its `data[]/directions.routes[]` shape into ranked options;
`GET /journey/multimodal`; a "Bus + metro, door to door" planner section
showing the top 3 as "44 min · ₹10 · reach by 12:36 / walk 7 min → Yellow Line
→ walk 4 min". Bus route ids are stripped of their `UP`/`DOWN` direction
suffixes ("448DOWN" → "448") — the same rule that bans raw route_id.

**Honesty.** DTS self-declares `response_type` per response; that label passes
through verbatim and the UI appends "timetable-based" when every option is
static. MetroPulse never upgrades DTS's own word for its data.

### Three bugs found by probing production, not by tests

1. **500 on every call**: `MultimodalLeg` is a `slots=True` dataclass, so
   `vars()` in `from_domain` raised TypeError. Fixed with `asdict`; the schema
   seam now has a test (it was the one seam without one).
2. **Section never appeared on-device** despite the API returning 5 options
   and the server logging 3 successful upstream calls. Cause: the DTS upstream
   takes **~20 s**, longer than the client's 15 s default receive timeout —
   and the `autoDispose` provider was cancelled and restarted every time the
   section scrolled out of view, so it never finished for anyone who scrolled
   while waiting. Fixed with a 40 s per-request timeout and `ref.keepAlive()`
   (10-minute cache; a new origin/destination is a different key).
3. **A silent 20-second gap** read as "there are no bus options" — the section
   now shows "Checking bus routes…" while loading.

**Verified:** 467 backend + 242 Flutter tests; mypy/ruff/analyzer clean;
deployed; and confirmed on-device under the exact failure condition — nine
aggressive scrolls during the load, section still populated with DTC 411 and
DTC 423 options and the attribution line.

---

## 15. NCRTC (Namo Bharat / RRTS) + the Road layer

Two datasets arrived. One shipped, one was refused — both on evidence.

### `ncrtc_static_gtfs_v1.zip` — SHIPPED, narrowly

A GTFS feed for the Delhi-Meerut RRTS corridor. Three findings decided the
shape of the feature, each verified independently after a 4-agent assessment:

**1. The interchange inversion — the reason a naive load would lie.** The feed
lists 16 stations but schedules trips to only **7**. The nine unserved include
the whole Delhi extension — and those are precisely the ones sitting on top of
metro stations: **Jangpura 35 m, Anand Vihar 63 m, New Ashok Nagar 105 m,
Sarai Kale Khan 475 m** from their metro namesakes. Every one has **zero
scheduled trips**. Load all 16 and the app tells a rider at Anand Vihar there
is a Namo Bharat train 63 metres away. There is not. Meanwhile the seven that
*do* run are far outside Delhi, with exactly **one** genuine interchange:
Ghaziabad RRTS, **338 m** from Shaheed Sthal (New Bus Adda) on the Red Line.
Proximity to the metro is *inversely* correlated with being usable.

**2. Loading it through `load-gtfs` would have destroyed the app.**
`static_loader.load()` calls `delete_all_static()` (`repositories.py:173`),
which DELETEs every static table. Pointing the normal GTFS command at this zip
would wipe all 262 Delhi Metro stations and leave 16 RRTS stops. A separate
`load-regional-rail` command reads the archive without touching the metro
dataset, and its help text says so.

**3. The timetable is synthesised, and NCRTC did not publish it.** Verified
directly: dwell is **0 s at all 910 stop_times**, there are **2 distinct timing
profiles across 130 trips** (one per direction, byte-identical), and **896
gaps are exactly 900 s** — no peak/off-peak variation anywhere. Real timetables
are never that clean. And `attributions.txt` declares the producer as
**OpenStreetMap contributors**, with NCRTC named only as the operating agency.
So the times are labelled *indicative*, the card credits the actual producer,
and it points riders at ncrtc.in before they travel.

A fourth issue caught in review: the first cut computed headway by merging both
directions, giving "every 9 min" — but a Delhi-bound rider gains nothing from a
Meerut-bound train, so that halved the apparent wait. Now per-direction: **15
min**, which is what the feed actually says.

Shipped as a *connection*, never a route: RRTS never enters the metro planner
and never borrows the metro fare table (its fares are far higher). Live and
verified on-device: Shaheed Sthal shows "Ghaziabad station · Interchange ·
338m walk (about 5 min) · Roughly every 15 min each way, 06:04–22:25
(indicative) · Operated by NCRTC · separate ticket". **Anand Vihar returns an
empty list** — the guarantee that matters.

Re-running the loader with a newer feed lights up the Delhi extension
automatically, on evidence rather than optimism.

### `Data Layer 04_Road.xlsb` — SKIPPED

104,444 crowdsourced road points (paplilabs), same family as the previously
skipped Shop and Subway layers. Evidence: the bounding box covers **central
Delhi only** (28.55–28.68 N), so most of the 262-station network can never be
covered — a sample found nearby points for just **57 stations**. `road_width_ft`
clusters hard around 24.95–24.99 ft, consistent with a ~25 ft default rather
than measurement. Timestamps are time-only (undateable), images live on a
third-party host, and no license statement ships with the file.

The deciding question was the commuter one: knowing the road outside a station
is ~25 ft wide does not tell a rider anything about footpaths, crossings or
safety. It makes nobody's journey better, so it does not ship.

**Verified:** 472 backend + 245 Flutter tests; mypy/ruff/analyzer clean;
migration 0013; deployed to EC2 and loaded there; APK rebuilt and exercised.

---

## 16. Journey Mode: context-aware station guidance, and the ticket-link bug

### The ticket bug: only WhatsApp opened

Root cause found in `AndroidManifest.xml`: the `<queries>` block declared only
Flutter's default `PROCESS_TEXT`. Since **Android 11**, `url_launcher` cannot
resolve a handler it can't see, so of the five Tickets & recharge channels only
`wa.me` opened — WhatsApp claims that host through verified App Links, while
DMRC's QR portal, the Momentum store link, the recharge site and Autope all
silently did nothing.

Fixed in three layers: `VIEW`+`https`/`http` queries in the manifest; a
`platformDefault` fallback after `externalApplication` so a plain web link
still reaches a browser; and honest failure copy. The old message —
"check your connection" — sent people to inspect their wifi over a package
visibility problem that had nothing to do with the network. It now says
"Couldn't open that link on this device" and offers **Copy link**, so a dead
end has a way out.

Verified by dumping the built APK's binary manifest with `aapt2`: both the
`https` and `http` VIEW intents are present. Widget tests cover all four
previously-broken channels reaching the launcher, and assert the word
"connection" no longer appears.

### Escalators: the honest gap

The brief asked for platform, gate, lift **and escalator** context. Platform,
gate and lift shipped. Escalators did not, because **no approved dataset
contains a single escalator**: the pathways graph holds 667 gates, 845 lifts,
355 platforms and 566 concourse nodes, and the facilities sheet has only
`elevated`/`toilet`/`parking` columns. A test asserts no phase or preference
can ever emit the word.

### Context-aware guidance

New pure-Dart `domain/station_guidance.dart`: the same gate means different
things by journey phase — an **entrance** at the origin, a **transfer** at an
interchange, an **exit** on arrival. Journey Mode now derives its phase from
the progress snapshot and fetches only the station the rider is about to act
on; mid-ride it fetches nothing and says nothing.

`JourneyProgressSnapshot` gained `interchangeStopId` — it already knew the
interchange's *name*, but guidance needs the id to look up that station's
gates, and resolving a name back to an id is a guess wherever two stations
share one.

### Accessibility routing

The step-free preference was **local state on the planner screen**: it did not
persist, and Journey Mode never learned it — so the guidance that matters
most, at the moment a wheelchair user is actually standing in the station, was
the one place it could not reach. It is now persisted in `LocalStore` and
exposed as `stepFreePreferredProvider`, read by both screens.

When set, a step-free need outranks landmark convenience: the rider is sent to
the gate DMRC's graph connects to a lift-served platform, not the one with the
best landmarks. Where no gate qualifies, the copy reads **"Step-free entrance
not mapped here"** with the DMRC helpline — never "not accessible", because a
gap in the map is not a verdict on the station.

*Verified on-device end to end:* step-free toggled on in the planner, app
force-stopped and relaunched, and Journey Mode's "ENTERING THE STATION —
Chandni Chowk" leads with **"Enter at Gate No. 2 · Step-free to the platform
in DMRC's map"** — matching exactly what the live API reports as that
station's only step-free gate.

### RRTS behind a flag

`AppConfig.rrtsEnabled` (`MP_ENABLE_RRTS`, default **false**), matching the
disruptions-flag pattern. The provider returns empty without a request when
off, so a disabled feature costs nothing on the wire. Rationale in the flag's
own doc comment: one genuine interchange, and a community-reconstructed
timetable. Flip it when the Delhi extension runs in the feed.

**Verified:** 472 backend + 264 Flutter tests; analyzer clean; APK rebuilt,
installed, and driven through plan -> step-free -> journey.

---

## 17. Sprint 7: the escalator correction, richer guidance, adapter conformance

### The escalator premise was wrong — stated before anything was built on it

The Sprint 7 brief listed official data for "Platform information, Gates,
Lifts, **Escalators**" and asked for an accessible mode that avoids broken
escalators. An exhaustive search of every approved dataset found **zero**
escalators: the pathways graph holds 667 gates, 845 lifts, 355 platforms and
566 concourse nodes, and the facilities sheet carries only
`elevated`/`toilet`/`parking`. The string "escalator" appears 0 times across
all five normalized artifacts.

So escalator features are not blocked on *operational* status data — the
static inventory does not exist either. This belongs in the DMRC data ask
alongside lift status. A test asserts no phase or preference can ever emit
the word, so it cannot drift into the UI by accident.

**Platforms, by contrast, were an unexploited win**: real numbers (Platform 1
through 6, 355 nodes) that the app was not using. Now surfaced — with the
limit that no dataset maps a platform to a *direction*, so the app names a
station's platforms but never claims which one a given train departs from.
A test enforces that too.

### Priority 1 — guidance that earns its place

`StationGuidance` now carries separate, independently-nullable facts rather
than one blurred detail string, so each renders with its own weight:

    Leave by Gate No. 2
    ✓ Lift to the platform
    Closest to Red Fort

The lift line is **tiered to its evidence**, which is the part that matters
to someone who cannot use stairs:

| evidence | line | tick |
|---|---|---|
| gate is graph-connected to a lift-served platform | "Lift to the platform" | ✓ green |
| station has lifts, this gate unconnected in the map | "2 lifts at this station — path from this gate not mapped" | none |
| no lift data | *(silence)* | — |

The tick is a promise, and it is only made on evidence.

### Priority 2 — the "no UI rewrite" claim is now CI-enforced

`tests/test_adapter_conformance.py` turns the DMRC-readiness promise into a
contract every position source must satisfy:

1. emits the one normalized model (`VehiclePosition`);
2. declares `source` **explicitly** — the field defaults to `"unknown"` so an
   adapter that forgets cannot pass as live GPS;
3. timezone-aware UTC timestamps (a naive datetime silently breaks staleness,
   which is what stops the app showing a ghost train);
4. stable, unique, non-empty vehicle ids (the diff engine keys on identity —
   unstable ids turn one train into phantom arrivals);
5. survives an empty cycle (feeds go quiet; the app must not);
6. round-trips through `VehicleOut` **unchanged** — that payload is exactly
   what the Flutter client parses, and it is the half of "no UI rewrite" that
   normally goes untested.

Run against a **reference DMRC GTFS-RT adapter written only to the published
contract** (proving the seam is sufficient) and against **today's real
production source** (proving the contract is satisfiable by real code, not
just a fixture). Four adversarial tests prove the suite REJECTS violations:
a forgetful adapter, naive timestamps, duplicate ids, and the classic 0,0
"no GPS fix" sentinel.

The real-source test carries an explicit anti-vacuity guard: it pins the
clock to 08:05 IST and asserts positions were actually emitted, because a
contract loop over an empty list is a test that goes green while asserting
nothing.

**What this buys:** when DMRC's feed arrives, a new adapter either passes
this suite or CI fails — before the feed reaches production, and long before
a commuter sees a wrong train.

## 18. Sprint 7 (cont.): what the explanations were actually resting on

Two findings, both established by running the deployed system rather than by
reading it.

### 18.1 The coach recommendation was a constant

Probing production (`13.206.122.235:8000`) with three unrelated journeys —
AIIMS→Akshardham, Adarsh Nagar→AIIMS, Akshardham→Adarsh Nagar — returned the
same answer every time: **coach 7, `crowd_source: "prior"`, reason "typically
less crowded"**. Two causes, both confirmed:

* `coach_exit_hints` is **empty**. `exit_alignment` came back `0.5` — the
  neutral no-data constant — for every coach of every journey, and
  `/recommendations/exit?station=88` reported 0 of 3 exits carrying a
  `nearest_coach_index`. There is no loader for that table; rows only ever
  arrive through the admin `add_hint` endpoint, which nothing has called.
* There are no crowd observations, so every occupancy is `_triangular_prior`.

With both signals absent the ranking has no journey-specific input left. The
prior is symmetric (`[0.4, 0.5, 0.6, 0.7, 0.7, 0.6, 0.5, 0.4]`), coach 0 is
excluded as women-reserved, so index 7 wins **always**.

The ranking is not wrong — it is the honest consequence of having no data.
The *explanation* was wrong. "Typically less crowded" reads as a claim about
how this line actually runs, and a rider is entitled to read it that way.

Fixed in `application/commuter/coach.py`:

* `_crowd_reasons` now keys off evidence, not the number. Observed coaches
  keep "typically less crowded"; prior-derived ones say **"end coaches are
  usually lighter — no crowd data for this line yet"**. Silence was rejected
  as its own kind of lie — it implies we had nothing to offer.
* A second, subtler leak: `CrowdForecast.source` is one label for all eight
  coaches, so in a *mixed* forecast (a few coaches reported, the rest prior —
  the normal case) a prior-derived coach inherited the word "observed" from a
  different coach. `CrowdForecast` now carries `observed_coaches`, and the
  wording is decided per coach.
* `_exit_reasons` **names the gate**: "closest to Gate No. 4" instead of the
  unfalsifiable "stops nearest to a destination exit", via a new
  `hint_exit_names_for` join. A rider can check a named gate against the signs
  overhead. This is dormant until hints are curated — it is the mechanism, not
  a live feature, and it is reported as such.

Four tests added. Two fail on the pre-fix code (verified by reverting
`_crowd_reasons`); one pins the constant-recommendation behaviour so it fails
the moment real data changes the answer — which is exactly when the claim it
guards stops being true.

### 18.2 The conformance suite tested the contract, not the shipped decoder

§17 established the adapter contract and ran it against a reference adapter
and the live schedule source. It never ran it against
`decode_vehicle_positions` — the code that actually wakes up when
`gtfs_rt_enabled` flips. Two real defects were sitting in that gap, both
reproduced by execution:

| Defect | Consequence | Status |
|---|---|---|
| Duplicate `vehicle.id` | GTFS-RT guarantees `entity.id` unique, **not** `vehicle.id`. Two entities → two positions → the engine's `{p.vehicle_id: p}` collapsed them to one, and the diff reported the loser as *removed*. A train vanished off the map, no error anywhere. | Fixed: dedupe, first wins, logged at ERROR naming both entity ids |
| `0,0` no-fix sentinel | lat/lon are `required` in GTFS-RT, so a producer with no fix must send *something* — and sends `0,0`. `RouteResolver.locate` projects any position onto the trip shape, so it would not even look wrong: it snaps to the end of the line and shows a confident, fictional train. | Fixed: `_has_fix` drops `0,0`, NaN, and out-of-range |

One correction to the audit that surfaced these: it attributed the `0,0` bug
to proto3 scalar defaults passing `HasField("position")`. That mechanism is
wrong — GTFS-RT is proto2 and lat/lon are `required`, so an unset-coordinate
payload cannot be encoded at all (protobuf raises `EncodeError`). The
reachable bug is an *explicitly set* `0.0, 0.0`, which is valid protobuf and
decoded into a live train. Same defect, different cause; the fix covers it.

Also added: a staleness test with teeth. `is_stale` is structurally dead today
(the schedule source stamps `timestamp=now` every cycle) and becomes the
mechanism that stops a frozen train being drawn as a moving one the day a feed
arrives. The contract now proves it *fires* on a ten-minute-old position, not
merely that it is callable.

Conformance suite: 8 → **12 tests**. Both decoder tests fail on the pre-fix
decoder (verified by reverting the guards).

### 18.3 Known gaps, recorded not fixed

* **No composite source.** `cli.py:341-353` is strictly either/or, so a
  partial DMRC rollout (a few lines live, the rest schedule) has no code path.
  This is a plausible way for DMRC to actually roll out.
* **`vehicle_id` changes meaning at cutover.** Today it is `sched-{trip_id}` —
  one id per *trip*. Real GPS gives one id per *physical train*, persisting
  across trips. `EtaEngine` keys history on it, so the 300 s window will span
  terminal layovers and bias segment speed low right after each trip change.
  Persisted Journey Mode sessions pin a `sched-*` id and will dangle; the app
  degrades to timetable rather than crashing, but it needs an expiry pass.
* **The `Decoder` seam is not config-reachable.** The `decoder=` kwarg exists
  on the engine but `cli.py` never passes it, so a custom decoder requires
  editing `cli.py`.

Verification: backend **487 passed** (was 480), ruff and mypy clean across 125
files; Flutter **272 passed**, `analyze` clean. Git mirror synced and diffed
byte-identical.

## 19. Sprint 7 Priority 5: making the beta measurable, without starting to watch

### 19.1 One of the five metrics worked

Measured against the code rather than assumed:

| Metric | Before | Why |
|---|---|---|
| Journey completion | **Yes** | `/complete` + `/abandon` called from `journey_mode_screen.dart` |
| Daily usage | No | the app emitted no analytics events at all |
| Voice usage | No | speech, intent parsing and answers are entirely on-device |
| Search behaviour | No | `searchStations()` is pure Dart over a cached list — the server never sees a query |
| Crash reports | No | Crashlytics is wired, but `google-services.json` is absent, so `_crashlyticsReady` stays false and nothing uploads |

The backend half had existed for some time — `analytics_events`, the batched
`POST /api/v1/analytics/events`, an admin summary, retention pruning. The
client half had never been written, which is the whole explanation for four
unmeasurable metrics.

### 19.2 Why it could not simply be switched on

The published privacy policy enumerates what MetroPulse collects and closes
that list with **"That's the whole list."** Product analytics is not on it.
The "analytics events kept for 90 days" retention line refers to *vehicle and
feed* events — train positions — not to anything about a rider.

So the pipeline was built **fail-closed** and left off. `docs/analytics_consent.md`
carries the draft policy amendment for the owner to approve; nothing collects
until that ships and a rider opts in.

### 19.3 Privacy enforced structurally, not by discipline

Two properties, both load-bearing:

* **Consent is a gate, not a preference.** `AnalyticsService.record` checks
  consent before buffering, so there is no path that records first and decides
  later. Withdrawal mid-session discards the buffer *unsent* — verified by
  test, because "off" that still leaks the last few minutes is not off.
* **The API cannot express the private thing.** `recordSearchSelected` takes a
  query *length*; there is no query parameter. `recordVoiceIntent` takes an
  intent *name*; there is no transcript parameter. On a transit app the search
  query IS the destination, so this is the one place where making the leak
  impossible beats making it discouraged.

`LocalStore.analyticsConsent` reads `== 'true'` (absent → off), deliberately
the opposite direction from `notificationsEnabled`'s `!= 'false'` (absent →
on). The same shape copied without thought would have silently opted every
already-installed user into collection they were never asked about.

12 new Flutter tests cover the gate, withdrawal, payload shape, offline
retry, oldest-first eviction, and per-run session ids.

### 19.4 Owner actions still outstanding

* Approve and ship the privacy policy amendment (draft in
  `docs/analytics_consent.md`), then ask beta riders directly — a toggle
  nobody knows about is a defensible default, not consent.
* Add `app/android/app/google-services.json` from your own Firebase project.
  Crash reporting is already disclosed in the current policy, so this needs no
  legal change — but until the file exists, crash reports are silently inert,
  which is right for a developer and wrong for a 30–50 person beta.

Verification: Flutter **284 passed** (was 272), `analyze` clean; backend
unchanged at 487. Git mirror synced, 12 files diffed byte-identical.

### 19.5 Policy amendment approved and applied (9 August 2026)

The owner approved the draft. Applied to **both** parallel copies — the in-app
`legal_content.dart` and the hosted `docs/legal/privacy_policy.md` — since
they are maintained separately and a drift between them is exactly the kind of
gap that turns a privacy statement into a false one.

Changes: the blocking sentence "That's the whole list" now names the opt-in
extra; a new *Anonymous usage data — only if you turn it on* item states what
is sent and what is not; a 90-day retention line was added; and the old
"Vehicle/feed analytics events" bullet was reworded to "Train position and
feed events (the network's, not yours)" because it read as though it might
already have covered rider analytics, which it never did.

The 90-day promise was checked against the code, not assumed: `purge_analytics`
is scheduled every 24 h in `cli.py` against `analytics_retention_days`
(default 90).

Collection still does not start on its own. The Settings toggle remains
default-off, which the amended policy now states as a commitment. Asking beta
riders directly is the one remaining step, and it is a product decision, not a
code change.

Verification after the amendment: Flutter **284 passed**, `analyze` clean.
Both legal files synced to the mirror byte-identical.

## 20. Three field-reported bugs, checked on a real device

Verified on the `metropulse_test` emulator (Android, 1080x2400) against the
deployed backend, before and after the fix build.

### 20.1 Station names — FIXED, reproduced and re-verified on device

DMRC publishes **"Dwarka Sector - 10"** (spaces around the hyphen) and
**"Mayur Vihar-I"** (a Roman numeral). There is no "Mayur Vihar Phase-1" in
the feed at all. The matcher compared raw lowercase substrings, so what a
rider actually types could never match. 31 of 262 stations carry a hyphen, so
this broke a large slice of the network — and the voice assistant shares the
same index, which is why it kept answering "try the exact station name".

Before (old build): "dwarka sector 10" -> *"We couldn't find that one."*
After: -> **Dwarka Sector - 10**, single clean hit.
After: "mayur vihar phase 1" -> **Mayur Vihar-I** first, "Mayur Vihar Pocket 1"
second — the loosening did not collapse two genuinely different stations.

Normalisation folds punctuation and converts **hyphen-attached** Roman
ordinals only. That restriction is load-bearing: "Mundka Industrial Area
(M.I.A)" tokenises to m/i/a, and a blanket rule would rewrite it as "M 1 A"
and start matching it against searches for "1". A hyphen means an ordinal
("Phase-I", "Vihar-II"); a dot means an acronym. "Dilli Haat - INA" and
"Terminal 1- IGI Airport" are likewise untouched.

12 tests use names copied from the live `/api/v1/stations` response. 6 fail on
the old matcher (verified by reverting).

### 20.2 Back buttons — FIXED

Favourites/"Saved" was a pushed route with a custom header instead of an
`AppBar`, so it had no back affordance at all. Gesture-back still worked,
which is exactly why it stayed invisible. Journey History and Network Map were
audited too and are fine — they use `AppBar`, which supplies the arrow.

### 20.3 "All options showing as live" — NOT REPRODUCED

Walked every surface on the deployed backend. All read **SCHEDULE**:

| Screen | Badge | Extra caveat shown |
|---|---|---|
| Home | SCHEDULE | — |
| Explore / Live map | SCHEDULE | "Train positions are estimated from the schedule, not live GPS." |
| Journey Mode | SCHEDULED ESTIMATE | — |
| Station detail | SCHEDULE | "Arrival times are estimated from the schedule, not live GPS." |
| Planner | n/a | options are timetable-based, nothing claims live |

Two genuine **fail-open defaults** were found and fixed anyway, because both
resolve absence of evidence to the claim rather than the caveat:

* `LiveIndicator.dataEstimated` defaulted to `false` — a caller who simply
  forgot the argument rendered a green LIVE badge. Now `required`.
* Train detail used `train?.isEstimated ?? false` — a train missing from the
  live map rendered as LIVE. Now `?? true`.

Making the parameter required immediately caught that
`golden_honesty_test.dart` was itself relying on that default: the honesty
golden was asserting the un-honest value.

Separately: production currently serves **zero trains** (`/api/v1/trains` ->
`{"count": 0}`), so the realtime worker appears to be down on EC2. That is its
own defect and worth fixing regardless — but with no trains the badge is
correctly SCHEDULE, so it is not the cause of the report.

The reported symptom remains unexplained and the task stays open pending the
specific screen.

Verification: Flutter **296 passed**, `analyze` clean, release APK built
(87.7 MB) and installed on the emulator; the two fixes confirmed visually.

### 20.4 The real cause: every release APK pointed at a developer's laptop

The "reconnecting" report led to the actual defect, and it is a shipping
blocker rather than a cosmetic one.

`AppConfig.defaultApiBase` defaulted to **`http://10.0.2.2:8000`** — the
Android emulator's alias for the *host machine's* localhost. Any release APK
built without `--dart-define=MP_API_BASE=...` shipped pointing there. On a
real phone that address routes nowhere, so:

```
FATAL: WebSocketChannelException: SocketException: Connection refused
       (OS Error: Connection refused, errno = 111), address = 10.0.2.2
```

repeating on a backoff loop — badge stuck on CONNECTING then RECONNECTING, and
an empty home screen. The Settings override that could have rescued it is
gated behind `kDebugMode`, so a user had no way out.

EC2 was healthy throughout: `/ws/live` returns `101 Switching Protocols`.
Nothing was wrong with the server.

Fixed by making production the default and the emulator address the OVERRIDE —
the safe direction, since a developer can deliberately point at their own
machine but nobody ships a build aimed at one by accident:

    flutter run --dart-define=MP_API_BASE=http://10.0.2.2:8000

**Why nothing caught this.** Every unit and widget test injects its own base
URL, so none of them read the constant. And the emulator used for verification
*can* reach 10.0.2.2 — the single environment where the bug is invisible was
the environment it was checked in. `app/test/config_test.dart` now asserts the
constant itself: not the emulator alias, not loopback, not a private LAN
range, a well-formed absolute URL, and its derived ws/wss form. Three of the
seven fail on the old value (verified by reverting).

This also explains the original "all options showing as live" report better
than any badge bug: with the socket never connecting, the pill never leaves
CONNECTING/RECONNECTING and no screen ever loads data.

**Why the earlier APK worked and this one didn't.** §11 records a build made
with `MP_API_BASE=http://13.206.122.235:8000` passed explicitly. So the
release process was correct only as long as someone remembered the flag — a
plain `flutter build apk --release` silently produced a broken app. That is
the class of defect worth removing outright rather than documenting, which is
why the safe value is now the default. `app/README.md` corrected too; it had
been advertising the emulator address as the default.

Verified on device after the fix: badge reads SCHEDULE, **zero** WebSocket
exceptions in logcat (was one every ~3 s), and server-driven home content
loads. Flutter **303 passed**, `analyze` clean.

## 21. Why the arrivals boards are empty — the timetable has no Sunday

Chased from "/api/v1/trains returns 0". The worker is **not** broken:
`/health` reports `feed_age_seconds: 4.29`, so it is publishing every few
seconds. It is publishing an empty snapshot, correctly, because the data has
nothing to publish.

DMRC's GTFS, counted directly from `data/dmrc_gtfs.zip` (262 stops / 36 routes
— matching production exactly):

| service_id | days | trips |
|---|---|---|
| weekday | Mon–Fri | **5,379** |
| saturday | Sat | **59** |
| sunday | Sun | **0** |

So on Sundays there is no scheduled service in the dataset at all, and
Saturday carries 1.1% of a weekday. Roughly 2/7 of the week, the app can see
nothing. Delhi Metro runs on both days; we are blind, not the network.

### The honesty failure this caused

Every empty board said **"No trains headed this way right now."** To a rider
on a Sunday that reads as *the metro has stopped*. Absence of data was being
presented as absence of trains — the same class of error as labelling a
schedule estimate "Live", pointed the other way.

### The trap in detecting it

The obvious check passes. `active_service_ids` answers from `calendar.txt`,
which *does* contain a `sunday` row with `sunday=1`, so on a Sunday it returns
`{"sunday"}` — non-empty, service apparently exists. Only counting the TRIPS
attached to those services reveals the truth. `ServiceDayService.coverage`
does that, and `GET /api/v1/service-day` exposes it.

The client now distinguishes three states, and the third matters as much as
the second:

* covered day, nothing approaching -> "No trains headed this way right now."
* **uncovered day** -> "Our timetable has no service data for today, so we
  can't show arrivals. Trains may still be running — check DMRC for times."
* **unknown** (offline / still loading) -> the plain wording, because claiming
  "no data for today" when we haven't asked would be inventing a cause. Not
  knowing is not a licence to guess a reason.

A still-connecting socket outranks both — we cannot know what today holds
before we have connected.

4 backend tests (including a `ghost_service` calendar row no trip references —
the exact shape of the real bug) and 4 widget tests covering all three states
plus the connecting case.

### Owner action

This is a **data** gap, not a code one, and the fix is not ours to fabricate:
obtain a GTFS export from DMRC that includes weekend service. Until then the
app is honest about the gap but still cannot show Saturday or Sunday arrivals.

Verification: Flutter **307 passed**, `analyze` clean; ruff and mypy clean
across 127 source files.

## 22. Rider contributions — filling gaps without borrowing DMRC's authority

Owner's call, and the right one: MetroPulse has gaps it cannot close alone,
and riders are standing on the platform holding the answers. Contribution
model chosen: **in-the-moment, per-prompt, opt-in**. Nothing is harvested
passively.

### What riders can and cannot fix (measured, not assumed)

| Gap | Fixable? | The honest limit |
|---|---|---|
| Coach -> exit (`coach_exit_hints`: **0 rows, ever**) | **Yes — best target** | One tap at journey end; directly unlocks the named-gate explanation |
| Lift / toilet status | Yes | Perishable — needs freshness decay, not permanent facts |
| Crowding | Endpoint already exists | 0 observations because nothing prompts for it |
| Step-free paths (56/262 confirmed) | Partly, **asymmetrically** | "I used the lift at Gate 3" is evidence; "I couldn't find one" is not evidence there isn't one. A single negative must never remove a badge |
| Weekend timetable | Weakly | Journey times prove service exists and give rough headways; they cannot reconstruct a trip-level schedule |

### The design, and what each piece is defending against

* **Reports live in their own table.** `coach_exit_reports` never writes into
  `coach_exit_hints`. Curated mapping and eyewitness agreement stay separable
  everywhere downstream, by construction rather than by convention.
* **Confirmation counts PEOPLE.** Three distinct riders, enforced by a unique
  constraint on `(user_id, stop, route, direction, coach, exit)`. One
  enthusiast tapping five times yields one vote — tested directly, because
  without that constraint five taps and five witnesses look identical.
  `route_id`/`direction_id` use `''`/`-1` sentinels rather than NULL, since
  NULL never equals NULL and would have silently voided the constraint.
* **Provenance survives to the screen.** A confirmed rider claim reads
  **"riders say Gate No. 7 is closest"**, never "closest to Gate No. 7".
  Curated hints outrank rider ones where both exist. Blending the two into one
  confident sentence is the small dishonesty that would make every other claim
  in the app suspect.
* **Reports can only add.** Nothing a rider submits removes an existing fact.

8 tests, including: an unconfirmed claim (2 riders) must change neither the
wording nor the ranking; a confirmed one must change both; and a confirmed
claim must leave `coach_exit_hints` still empty.

### Privacy

This needs its own consent and its own policy clause — it must **not** ride on
the analytics toggle shipped in §19, which was scoped deliberately narrowly and
whose policy text states we do not receive which stations a rider travelled
between. A coach-exit report is exactly that. Client prompt, consent, and the
policy clause are the remaining work.

Verification: backend **500 passed** (was 492), ruff and mypy clean across 129
source files, migration 0014 applied cleanly against real Postgres.

### 22.1 The client half — asked once, at the only moment anyone knows

The prompt appears after a rider **arrives** (an abandoned trip proves nothing
about the destination), only with explicit contribution consent, and only when
the destination has gates worth choosing between. Two taps or none: "Not now"
is a first-class answer and skipping is not a failure state. A failed
submission is silent — a contribution is a gift, not a task.

The thank-you is honest about which of three things happened, because
"submitted" would flatten them: *you had already told us that* / *a couple more
riders and this becomes a tip for everyone* / *that's confirmed now*.

**Consent is separate from analytics, and the storage layer enforces it.**
`contributionConsent` is its own key with its own default-false. This is not
tidiness: §19's policy text promises the analytics toggle does not receive
which stations a rider travelled between, and a coach-exit report is exactly
that, about one named station. Wiring them to one key would have silently
opted people into the thing they were told was excluded. 5 tests assert the
two consents move independently in both directions.

### 22.2 A discrepancy found while writing the policy clause

The in-app policy and the hosted `docs/legal/privacy_policy.md` are maintained
in parallel, and they had **drifted**. The hosted copy said *"Your live
location never leaves your device"* and omitted the share-a-trip disclosure
entirely — no collection item, no retention line — while the in-app copy has
carried both for some time. The hosted document was therefore inaccurate about
the one feature that does send a rider's position to the server.

Restored: the share-trip collection item, its 12-hour retention line, and a
corrected short version. Both copies now also carry the new contribution
clause and agree that there are **two** optional extras rather than one.

Worth noting as a process risk: two hand-maintained copies of a legal document
will drift again. A generated hosted copy, or a test diffing the two, would
close it properly.

Verification: Flutter **312 passed** (was 307), `analyze` clean; backend 500,
ruff and mypy clean.

## 23. Deploy: migration 0014 + the Sprint 7 backend, live on EC2

Deployed 9 August 2026. Note that `docker compose up -d --build` necessarily
ships the code with the schema, so this release also carried the decoder
guards (§18.2), evidence-tiered coach reasons (§18.1), `/service-day` (§21)
and `/contributions` (§22).

Pre-flight: DB at 0013, `coach_exit_reports` absent, schema-only `pg_dump`
taken as a rollback reference (1,750 lines). SSH reachable — current IP
103.62.92.187, inside the `103.62.92.0/22` rule, so the lockout trap did not
bite this time.

Result: `metropulse-migrate-1` exit code **0**, log shows
`Running upgrade 0013 -> 0014`, `alembic_version` now **0014**. The table
landed with everything that matters intact — notably
`uq_coach_exit_report_once_per_rider` on
`(user_id, stop_id, route_id, direction_id, coach_index, exit_id)`, which is
the mechanism that makes confirmation count people rather than taps, and both
`ON DELETE CASCADE` foreign keys.

### Production now demonstrates the Sunday finding directly

```
GET /api/v1/service-day
{"service_date":"2026-08-09","has_timetable":false,
 "scheduled_trips":0,"active_service_ids":["sunday"]}
```

That is §21's trap visible in one response: the calendar declares a `sunday`
service as active, and **zero trips reference it**. Anything asking "is there
service today?" from the calendar alone would answer yes.

### Verified after deploy

| Check | Result |
|---|---|
| `/health` | ok; database, redis true; `feed_age_seconds` 3.9 |
| `/api/v1/service-day` | 200, correct for a Sunday |
| `POST /api/v1/contributions/coach-exit` anonymous | **401** — wired and auth-gated |
| `/recommendations/coach` | 200; reason reads "end coaches are usually lighter — no crowd data for this line yet" (the §18.1 wording, live) |
| stations / journey plan / exit / accessibility / trains | all 200 |

The coach recommendation confirms the honesty fix in production: it no longer
claims "typically less crowded" over a triangular prior.

Still outstanding and unchanged by this deploy: the GTFS has no weekend
service (owner action — obtain a feed from DMRC that includes it), and the
client APK carrying the contribution prompt is built but not distributed.

## 24. README overclaim fixed, and one correction to the release brief

### 24.1 README vs .env.example — the owner was right

`README.md` opened with "a 5-second GTFS-Realtime polling engine" and stated
the worker "polls the DMRC VehiclePositions feed every 5 s", while
`.env.example` correctly documented that the same endpoint is Delhi's
**citywide bus** GPS and shipped `GTFS_RT_ENABLED=false`. Two documents in the
repo disagreed about the single most sensitive claim the project makes, and
the README was the one a DMRC official would read first.

Fixed in three places: the opening description now reads "realtime-ready
GTFS/DMRC integration layer with a 5-second polling architecture" and carries
an explicit callout — **MetroPulse does not have live Delhi Metro train GPS**
— with the evidence (registration-plate vehicle ids, ~4,000 simultaneous
vehicles, positions on ordinary roads); the worker bullet says the snapshot is
interpolated from the static timetable; and the "Realtime engine behaviour"
section states it describes a contract that today runs over the
schedule-estimated source.

### 24.2 Correction: there is no escalator data, and there never was

The brief asks the UI to show "⬆ Escalator available" alongside gate and lift.
That cannot be built honestly. Counted again across every approved artifact:

| Artifact | "escalator" occurrences |
|---|---|
| `official_stations_gates.json` | **0** |
| `pathways.json` | **0** |
| `hourly_profile.json` | **0** |
| `od_top_destinations.json` | **0** |
| `ncrtc_assessment.json` | **0** |

`pathways.json` covers 220 stations across 9 lines and its node categories are
exactly: **845 lifts, 667 gates, 355 platforms, 566 others, 1,307 edges**.
There is no escalator category — not an empty one, none. The DMRC facilities
spreadsheet has no escalator column either.

This is the third time this has been checked and reported (§17 corrected the
same premise). Everything else in the requested row is real and buildable:

    Exit Gate 4
    120 m to your destination     <- from exit coordinates
    Lift available                <- graph-confirmed, 56/262 stations

So the row ships without the escalator line, and `station_guidance.dart`
already has a test asserting the word "escalator" can never appear for any
phase or preference.

### 24.3 The HTTPS blocker — and a sequencing trap

Agreed and already listed as an owner action. One caveat on ordering: flipping
`AppConfig.defaultApiBase` to `https://api.metropulse.in` **before** DNS and a
certificate exist would break the app completely — same class of failure as
the `10.0.2.2` default fixed in §20.4, since the release build hides the
Settings override behind `kDebugMode`. The domain, certificate and reverse
proxy must land first; the one-line client change is last, not first.

## 24. Four field-reported bugs, and they were one chain

Reported from real use: the assistant would not give a route, would not set up
a journey, Home station could not be set, and a screen had no back button.

**The root was the third.** Favourites' "Add a station" did
`context.push('/search')` and stopped. Search's normal tap opens station
DETAIL, so the pick was never returned and never saved — the button was
structurally incapable of adding a favourite. Hence no Home station.

That cascaded: `_answerRouteTo` fell back to Home for every rider, so with no
Home it replied *"set your Home station in Favourites"* — advice the app made
impossible to follow. Fixed by using the existing picker mode, awaiting the
station, and asking Home / Work / College / just-save.

**The voice parser** matched only the literal `"route to"`, so
*"best route FROM x TO y"* — the most natural phrasing — was the one
guaranteed to fail. Now matches best/fastest/quickest route, directions and
travel-to, and parses BOTH endpoints (non-greedy, so a multi-word origin like
"dwarka sector 10" is not truncated). Speaking both ends now works with no
Home station at all.

**"Set up a new journey"** matched nothing; a new `planJourney` intent now
opens the planner — answering with a sentence and going nowhere was the bug.
`"plan a trip to Saket"` still routes rather than opening a blank form.

17 tests; 18 assertions fail on the pre-fix parser (verified by reverting).

Also fixed the README overclaim: the "5-second GTFS-Realtime polling engine"
headline and "polls the DMRC VehiclePositions feed" now read realtime-**ready**,
with a block stating plainly that MetroPulse has no live Metro GPS and that the
public OTD endpoint is Delhi's citywide BUS feed. README and `.env.example`
now agree.

## 25. Journey tracking: four sources, and what each may claim

Rider-initiated only, stoppable from the notification and from Journey Mode.
The constraint that shaped it: **63 of 215 stations are underground** (counted
from OTD facilities data), and GPS does not work in a tunnel — satellite
signals arrive weaker than the receiver's own noise floor, so a few metres of
concrete ends them. Station coordinates cannot fill that gap; they say where
stations are, not where the rider is.

| Source | Works underground | May claim |
|---|---|---|
| `gps` | No | Distance, and therefore "get ready to alight" |
| `approximate` (wifi/cell) | Often | Which station, when accuracy beats half the local spacing |
| `stopCount` (accelerometer) | **Yes** | How many stops since boarding |
| `schedule` | Yes | Position only, never proximity |

Design decisions worth keeping:

* **Adaptive accuracy gate.** A fixed 150 m threshold discarded the only
  positioning that survives a tunnel. Android's fused provider falls back to
  wifi APs underground and reports large accuracy — but a 300 m fix is decisive
  where neighbouring stations are 1.2 km apart. Judged against local spacing,
  not a constant.
* **Monotonic progress.** One stray fix cannot rewind the journey and
  re-announce a passed station.
* **"Get ready to alight" requires a distance.** From a timetable it is an
  instruction backed by a guess, and this is the moment that would hurt.
* **The schedule veto is one-directional.** A count exceeding what the elapsed
  time physically allows is impossible, so it is corrected down. A slow journey
  is NEVER revised up: a delayed train and a missed dwell look identical in the
  timing, and revising up would put a rider a station ahead of reality. Note
  also that *agreement* proves nothing — a mid-tunnel hold inflates the count
  AND slows the journey, so both drift together.
* **Schematic, not geographic.** The map is a diagram with straightened lines,
  so plotting a raw coordinate on it would look authoritative and mean nothing.
  The marker is driven by which stations have been passed; with no hop distance
  it sits at the last known platform rather than an invented midpoint.

Play policy: `ACCESS_BACKGROUND_LOCATION` is deliberately **absent**. A
foreground service may read location without it — the ongoing notification is
the user-visible signal that replaces it. That keeps MetroPulse out of the
background-location review entirely, and the manifest says so where someone
would otherwise "helpfully" add the permission.

**Not yet done, and not to be claimed:** nothing has run on a device; the
schematic renderer does not yet consume the computed marker; and every
threshold (stillness cutoff, dwell minimum, minimum run time) is **reasoned,
not measured**. One instrumented ride is required before this ships — a wrong
dwell threshold miscounts, and a miscount is worse than showing nothing.

Verification: Flutter **380 passed**, `analyze` clean.
