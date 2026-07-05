import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'design/app_colors.dart';
import 'design/app_radius.dart';
import 'design/app_typography.dart';

const _seed = AppColors.brandBlue;

ThemeData buildLightTheme({bool highContrast = false, ColorScheme? dynamicScheme}) =>
    _base(Brightness.light, highContrast: highContrast, dynamicScheme: dynamicScheme);

ThemeData buildDarkTheme({bool highContrast = false, ColorScheme? dynamicScheme}) =>
    _base(Brightness.dark, highContrast: highContrast, dynamicScheme: dynamicScheme);

ThemeData _base(
  Brightness brightness, {
  required bool highContrast,
  ColorScheme? dynamicScheme,
}) {
  final isDark = brightness == Brightness.dark;

  // A device-derived (Material You) scheme is respected verbatim when
  // enabled; otherwise the seed scheme is re-tuned onto our punchier,
  // near-black (or near-white) premium canvas.
  final baseScheme = dynamicScheme ??
      ColorScheme.fromSeed(
        seedColor: _seed,
        brightness: brightness,
        secondary: AppColors.brandViolet,
        tertiary: AppColors.brandPink,
        contrastLevel: highContrast ? 1.0 : 0.0,
      );
  final scheme = dynamicScheme != null
      ? baseScheme
      : baseScheme.copyWith(
          surface: isDark ? AppColors.darkBg : AppColors.lightBg,
          surfaceContainerHighest: isDark ? AppColors.darkSurfaceElevated : AppColors.lightSurfaceElevated,
          surfaceContainerHigh: isDark ? AppColors.darkSurfaceElevated : AppColors.lightSurfaceElevated,
          surfaceContainer: isDark ? AppColors.darkSurface : AppColors.lightSurface,
          outline: isDark ? AppColors.darkTextTertiary : AppColors.lightTextTertiary,
          outlineVariant: isDark ? AppColors.darkBorder : AppColors.lightBorder,
        );

  final textPrimary = isDark ? AppColors.darkTextPrimary : AppColors.lightTextPrimary;
  final textSecondary = isDark ? AppColors.darkTextSecondary : AppColors.lightTextSecondary;
  final textTheme = AppTypography.textTheme(primary: textPrimary, secondary: textSecondary);
  final elevatedSurface = isDark ? AppColors.darkSurfaceElevated : AppColors.lightSurfaceElevated;

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textTheme: textTheme,
    fontFamily: textTheme.bodyMedium?.fontFamily,
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: AppBarTheme(
      centerTitle: false,
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      titleTextStyle: textTheme.headlineSmall,
      iconTheme: IconThemeData(color: textPrimary),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      shape: const RoundedRectangleBorder(borderRadius: AppRadius.xlR),
      color: elevatedSurface,
      margin: EdgeInsets.zero,
    ),
    chipTheme: ChipThemeData(
      shape: const RoundedRectangleBorder(borderRadius: AppRadius.pillR),
      side: BorderSide.none,
      backgroundColor: elevatedSurface,
      selectedColor: scheme.primary,
      labelStyle: textTheme.labelLarge,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.pillR),
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 20),
        textStyle: textTheme.labelLarge,
        minimumSize: const Size(64, 56),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.pillR),
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 20),
        side: BorderSide(color: scheme.outlineVariant, width: 1.5),
        minimumSize: const Size(64, 56),
        textStyle: textTheme.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.pillR),
        textStyle: textTheme.labelLarge,
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(
        backgroundColor: elevatedSurface,
        foregroundColor: textPrimary,
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.pillR),
        minimumSize: const Size(48, 48),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: elevatedSurface,
      border: const OutlineInputBorder(borderRadius: AppRadius.pillR, borderSide: BorderSide.none),
      enabledBorder: const OutlineInputBorder(borderRadius: AppRadius.pillR, borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
          borderRadius: AppRadius.pillR, borderSide: BorderSide(color: scheme.primary, width: 2)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
      hintStyle: textTheme.bodyLarge?.copyWith(color: textSecondary),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: const RoundedRectangleBorder(borderRadius: AppRadius.lgR),
      backgroundColor: isDark ? AppColors.darkSurfaceElevated : AppColors.lightTextPrimary,
      contentTextStyle: textTheme.bodyMedium?.copyWith(color: isDark ? textPrimary : Colors.white),
    ),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1, thickness: 1),
    visualDensity: VisualDensity.adaptivePlatformDensity,
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: CupertinoPageTransitionsBuilder(),
        TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
        TargetPlatform.linux: CupertinoPageTransitionsBuilder(),
        TargetPlatform.windows: CupertinoPageTransitionsBuilder(),
      },
    ),
  );
}

/// Real-world Delhi Metro line colours, keyed by the line name embedded in
/// GTFS `route_long_name`/`route_short_name` (e.g. "RED_Rithala to Dilshad
/// Garden", "R_RD"). DMRC's feed never populates `route_color` itself — every
/// route comes through as `null` — so this name-keyed table is the only
/// source of real line colour, not a decorative fallback.
const Map<String, Color> _lineColors = {
  'RED': Color(0xFFE41F26),
  'YELLOW': Color(0xFFFDD10A),
  'BLUE': Color(0xFF0056A8),
  'GREEN': Color(0xFF00A651),
  'VIOLET': Color(0xFF92278F),
  'PINK': Color(0xFFEC4899),
  'MAGENTA': Color(0xFFA6008C),
  'ORANGE': Color(0xFFF7941D),
  'AIRPORT': Color(0xFFF7941D),
  'AQUA': Color(0xFF00AEEF),
  'GRAY': Color(0xFF8A8D8F),
  'GREY': Color(0xFF8A8D8F),
  'RAPID': Color(0xFF00A99D),
};

/// Resolves a metro line's colour: an explicit GTFS `route_color` hex wins
/// when present, otherwise the line name (long or short name — whichever is
/// on hand) is matched against [_lineColors]; brand blue is the last resort
/// for an unrecognised or entirely-unnamed line.
Color routeColor(String? hex, [String? name]) {
  if (hex != null && hex.isNotEmpty) {
    final cleaned = hex.replaceAll('#', '');
    final value = int.tryParse(cleaned, radix: 16);
    if (value != null) return Color(0xFF000000 | value);
  }
  if (name != null) {
    final upper = name.toUpperCase();
    for (final entry in _lineColors.entries) {
      if (upper.contains(entry.key)) return entry.value;
    }
  }
  return _seed;
}

/// [routeColor] as a `#RRGGBB` string, for contexts that need a wire-format
/// colour (MapLibre GeoJSON feature properties) rather than a [Color].
String routeColorHex(String? hex, [String? name]) {
  final color = routeColor(hex, name);
  return '#${color.toARGB32().toRadixString(16).padLeft(8, '0').substring(2)}';
}
