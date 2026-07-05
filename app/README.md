# MetroPulse Flutter app

Clean-Architecture Flutter client for the MetroPulse backend: live map with
animated trains, journey mode, personalised commute card, offline station
cache, WebSocket-only live updates (no polling).

## Layers

```
lib/
├── core/       config, theme, router, formatters
├── domain/     freezed models (pure, no Flutter imports)
├── data/       Dio API client, WebSocket client, Hive store, repositories
├── providers/  Riverpod wiring (DI + live state)
└── features/   one folder per screen
```

## Setup

```bash
flutter pub get
dart run build_runner build --delete-conflicting-outputs   # freezed/json codegen
flutter run --dart-define=MP_API_BASE=http://10.0.2.2:8000
```

`MP_API_BASE` defaults to `http://10.0.2.2:8000` (Android emulator -> host).
The WebSocket URL is derived from it. Override at runtime in Settings.

Verified against **Flutter 3.44.4 / Dart 3.12.2**: `flutter analyze` reports
zero issues, `flutter test` passes 62/62, and `flutter build web` compiles
the full dependency graph end to end (this also caught a real
`maplibre_gl` incompatibility — see below). Android/iOS/Windows haven't been
built here (no Android SDK or MSVC toolchain in this environment); `web` and
`windows` are otherwise available as run targets once platform scaffolding
exists.

Platform scaffolding (`android/`, `ios/`) is created with
`flutter create --platforms=android,ios .` once (web scaffolding is already
checked in). Then:

- **Location (nearby stations)** — add to `android/app/src/main/AndroidManifest.xml`:
  `<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION"/>`
  and to `ios/Runner/Info.plist`:
  `NSLocationWhenInUseUsageDescription` = "Shows metro stations near you."
- **MapLibre** needs no extra Android setup; offline tile regions are stored
  by the plugin automatically after "Download offline map area" on the map.
- **Localization** — `lib/l10n/gen/` is produced by `flutter gen-l10n`,
  which runs automatically on build (`generate: true`). Add locales by
  dropping `app_<locale>.arb` files next to `app_en.arb`.
- **maplibre_gl must stay on `^0.26.0` or newer** on recent Flutter — `0.20.x`
  calls a `dart:ui` API (`platformViewRegistry`) that no longer exists on the
  web target and fails to compile. Confirmed by building both versions here.

## Quality notes (beta audit)

- Crash handling: all uncaught errors funnel through `_reportError` in
  `main.dart` — swap in Crashlytics/Sentry there.
- Battery: the WebSocket disconnects while backgrounded (resumes with seq
  replay); map animation pauses off-screen; location uses one low-accuracy
  fix on demand.
- Every home section has skeleton / empty / error states via `AsyncSection`;
  skeletons freeze under the OS reduced-motion setting.
- Layouts are responsive: two-column dashboard ≥720 px, content capped at
  1100 px on tablets.
- Known debt: strings outside Home/Journey Mode are not yet in ARB;
  `AsyncSection`'s two internal strings are literals.

## Tests

```bash
flutter test    # 62 tests: pure domain logic (fare, companion messages,
                # GTFS-timetable simulation, search ranking) + widget-level
                # animator tests. No backend or device required.
```
