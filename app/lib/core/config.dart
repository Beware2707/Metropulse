/// Build-time defaults; the API base can be overridden at runtime in Settings.
class AppConfig {
  AppConfig._();

  /// `10.0.2.2` reaches the host machine from the Android emulator.
  static const String defaultApiBase = String.fromEnvironment(
    'MP_API_BASE',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// MapLibre style. The default is the dependency-free demotiles style;
  /// swap for a proper raster/vector style key in production.
  static const String mapStyleUrl = String.fromEnvironment(
    'MP_MAP_STYLE',
    defaultValue: 'https://demotiles.maplibre.org/style.json',
  );

  static const String appVersion = '1.0.0';

  /// Delhi city centre — the initial camera before any data loads.
  static const double initialLat = 28.6139;
  static const double initialLon = 77.2090;
  static const double initialZoom = 10.5;

  static String wsUrlFor(String apiBase) {
    final ws = apiBase.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
    return '$ws/ws/live';
  }
}
