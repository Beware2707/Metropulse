import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Plus Jakarta Sans type scale — bold, large, confident. Hero numbers
/// (ETA, minutes-until) lean on `displaySmall`/`headlineLarge`; overlines
/// use the wide-tracked `labelSmall`.
abstract final class AppTypography {
  AppTypography._();

  static TextTheme textTheme({required Color primary, required Color secondary}) {
    final base = GoogleFonts.plusJakartaSansTextTheme();
    return base.copyWith(
      displayLarge: base.displayLarge?.copyWith(
        fontSize: 52, fontWeight: FontWeight.w800, letterSpacing: -1.5, height: 1.02, color: primary,
      ),
      displayMedium: base.displayMedium?.copyWith(
        fontSize: 42, fontWeight: FontWeight.w800, letterSpacing: -1, height: 1.04, color: primary,
      ),
      displaySmall: base.displaySmall?.copyWith(
        fontSize: 34, fontWeight: FontWeight.w800, letterSpacing: -0.5, height: 1.05, color: primary,
      ),
      headlineLarge: base.headlineLarge?.copyWith(
        fontSize: 30, fontWeight: FontWeight.w800, letterSpacing: -0.5, color: primary,
      ),
      headlineMedium: base.headlineMedium?.copyWith(
        fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -0.25, color: primary,
      ),
      headlineSmall: base.headlineSmall?.copyWith(
        fontSize: 22, fontWeight: FontWeight.w700, color: primary,
      ),
      titleLarge: base.titleLarge?.copyWith(
        fontSize: 19, fontWeight: FontWeight.w700, color: primary,
      ),
      titleMedium: base.titleMedium?.copyWith(
        fontSize: 16, fontWeight: FontWeight.w600, color: primary,
      ),
      titleSmall: base.titleSmall?.copyWith(
        fontSize: 14, fontWeight: FontWeight.w600, color: primary,
      ),
      bodyLarge: base.bodyLarge?.copyWith(
        fontSize: 16, fontWeight: FontWeight.w500, color: primary, height: 1.35,
      ),
      bodyMedium: base.bodyMedium?.copyWith(
        fontSize: 14, fontWeight: FontWeight.w500, color: secondary, height: 1.35,
      ),
      bodySmall: base.bodySmall?.copyWith(
        fontSize: 12, fontWeight: FontWeight.w500, color: secondary, height: 1.3,
      ),
      labelLarge: base.labelLarge?.copyWith(
        fontSize: 14, fontWeight: FontWeight.w700, color: primary,
      ),
      labelMedium: base.labelMedium?.copyWith(
        fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.4, color: secondary,
      ),
      labelSmall: base.labelSmall?.copyWith(
        fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.8, color: secondary,
      ),
    );
  }
}
