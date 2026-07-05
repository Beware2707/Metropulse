import 'package:flutter/material.dart';

const _seed = Color(0xFF1F6FEB);

ThemeData buildLightTheme({bool highContrast = false, ColorScheme? dynamicScheme}) =>
    _base(Brightness.light, highContrast: highContrast, dynamicScheme: dynamicScheme);

ThemeData buildDarkTheme({bool highContrast = false, ColorScheme? dynamicScheme}) =>
    _base(Brightness.dark, highContrast: highContrast, dynamicScheme: dynamicScheme);

ThemeData _base(
  Brightness brightness, {
  required bool highContrast,
  ColorScheme? dynamicScheme,
}) {
  // A device-derived (Material You) scheme takes priority when available and
  // enabled; the seed-based scheme is the fallback everywhere else, with an
  // optional boosted contrast level for the accessibility setting.
  final scheme = dynamicScheme ??
      ColorScheme.fromSeed(
        seedColor: _seed,
        brightness: brightness,
        contrastLevel: highContrast ? 1.0 : 0.0,
      );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    appBarTheme: AppBarTheme(
      centerTitle: false,
      backgroundColor: scheme.surface,
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    visualDensity: VisualDensity.adaptivePlatformDensity,
  );
}

/// Parses a GTFS route colour ('EE1C25') with a line-blue fallback.
Color routeColor(String? hex) {
  if (hex == null || hex.isEmpty) return _seed;
  final cleaned = hex.replaceAll('#', '');
  final value = int.tryParse(cleaned, radix: 16);
  if (value == null) return _seed;
  return Color(0xFF000000 | value);
}
