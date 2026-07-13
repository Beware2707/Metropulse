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

  /// DMRC's official, publicly-downloadable network-map PDF, hosted on DMRC's
  /// own server. We link out to it (opened in the browser / downloaded from
  /// DMRC directly) rather than bundling the file — the map artwork is DMRC's
  /// copyright; linking to their official public download is fine, hosting a
  /// copy of it ourselves is not. The URL carries a content hash, so it needs
  /// updating whenever DMRC republishes a new edition (check the "Download
  /// Map" button on https://delhimetrorail.com/map for the current link).
  static const String dmrcNetworkMapUrl = String.fromEnvironment(
    'MP_DMRC_MAP_URL',
    defaultValue:
        'https://delhimetrorail.com/static/media/DMRC-NMRC-NCRTC-Network-Map-02.07.2026.06f70dd2.pdf',
  );

  /// Delhi city centre — the initial camera before any data loads.
  static const double initialLat = 28.6139;
  static const double initialLon = 77.2090;
  static const double initialZoom = 10.5;

  static String wsUrlFor(String apiBase) {
    final ws = apiBase.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
    return '$ws/ws/live';
  }
}
