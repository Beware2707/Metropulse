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
