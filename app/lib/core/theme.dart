import 'package:flutter/material.dart';

const _seed = Color(0xFF1F6FEB);

ThemeData buildLightTheme() => _base(Brightness.light);

ThemeData buildDarkTheme() => _base(Brightness.dark);

ThemeData _base(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(seedColor: _seed, brightness: brightness);
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
