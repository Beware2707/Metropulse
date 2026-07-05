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

Platform scaffolding (`android/`, `ios/`) is created with
`flutter create --platforms=android,ios .` once, then MapLibre needs no extra
setup on Android; on iOS add `io.flutter.embedded_views_preview` if targeting
older Flutter versions per maplibre_gl docs.

## Tests

```bash
flutter test
```
