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

  // -- Tickets & recharge hand-off channels ---------------------------------
  //
  // DMRC's official purchase channels. MetroPulse deliberately hands off to
  // these rather than processing payments itself — no payment SDKs, no wallet,
  // no order state; the user pays DMRC directly on DMRC's own rails. These are
  // DMRC's published channels as of mid-2026 and may need updating if DMRC
  // moves them (each is overridable at build time via its MP_* define).

  /// DMRC's official WhatsApp QR-ticketing bot (+91 96508 55800, all lines).
  /// Opening the link starts a chat; sending "Hi" kicks off the menu-driven
  /// bot. We deliberately prefill nothing beyond "Hi" — the bot drives its
  /// own flow.
  static const String dmrcWhatsAppTicketsUrl = String.fromEnvironment(
    'MP_DMRC_WHATSAPP_TICKETS',
    defaultValue: 'https://wa.me/919650855800?text=Hi',
  );

  /// DMRC's official web QR-ticket portal.
  static const String dmrcQrPortalUrl = String.fromEnvironment(
    'MP_DMRC_QR_PORTAL',
    defaultValue: 'https://qrticket.dmrc.org/qrapp/',
  );

  /// Play Store link for DMRC's official Momentum 2.0 app (QR tickets,
  /// wallet, card recharge). A search URL on purpose: we don't hardcode a
  /// package id we haven't verified from an official DMRC source.
  static const String dmrcMomentumStoreUrl = String.fromEnvironment(
    'MP_DMRC_MOMENTUM_STORE',
    defaultValue: 'https://play.google.com/store/apps/search?q=DMRC%20Momentum%202.0',
  );

  /// DMRC's official smart-card online recharge site. An online top-up only
  /// becomes usable after the card is tapped on an Add Value Machine (AVM)
  /// at a station — the UI copy must carry that caveat honestly.
  static const String dmrcCardRechargeUrl = String.fromEnvironment(
    'MP_DMRC_CARD_RECHARGE',
    defaultValue: 'https://www.dmrcsmartcard.com/',
  );

  /// Autope — the only DMRC-authorised private issuer offering auto top-up
  /// (recharges automatically at the AFC gate when the balance runs low).
  static const String autopeUrl = String.fromEnvironment(
    'MP_AUTOPE_URL',
    defaultValue: 'https://autope.in/',
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
