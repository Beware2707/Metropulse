import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Plus Jakarta Sans type scale — bold, large, confident. Hero numbers
/// (ETA, minutes-until) lean on `displaySmall`/`headlineLarge`; overlines
/// use the wide-tracked `labelSmall`.
///
/// Every style below is built directly at one of the four weights bundled in
/// `assets/google_fonts/` (500/600/700/800), and nothing here asks for any
/// other weight. That is deliberate and load-bearing: `google_fonts` resolves
/// a request from the asset bundle only when a file matching that exact weight
/// is present, and otherwise fetches it from `fonts.gstatic.com` at runtime.
///
/// This used to start from `GoogleFonts.plusJakartaSansTextTheme()` and
/// `copyWith` the weights afterwards, which looked equivalent but wasn't: that
/// helper resolves Material's *default* text theme first, and those defaults
/// are largely Regular (w400) — a weight we don't bundle. So the app fired a
/// network request for PlusJakartaSans-Regular on every cold start, and fell
/// back to Roboto for a beat (or entirely, offline) before our overrides ever
/// applied. Building each style explicitly keeps every request inside the
/// bundle. If you add a style here, use a weight that has a file in that
/// folder, or add the file.
abstract final class AppTypography {
  AppTypography._();

  static TextTheme textTheme({required Color primary, required Color secondary}) {
    return TextTheme(
      displayLarge: GoogleFonts.plusJakartaSans(
        fontSize: 52, fontWeight: FontWeight.w800, letterSpacing: -1.5, height: 1.02, color: primary,
      ),
      displayMedium: GoogleFonts.plusJakartaSans(
        fontSize: 42, fontWeight: FontWeight.w800, letterSpacing: -1, height: 1.04, color: primary,
      ),
      displaySmall: GoogleFonts.plusJakartaSans(
        fontSize: 34, fontWeight: FontWeight.w800, letterSpacing: -0.5, height: 1.05, color: primary,
      ),
      headlineLarge: GoogleFonts.plusJakartaSans(
        fontSize: 30, fontWeight: FontWeight.w800, letterSpacing: -0.5, color: primary,
      ),
      headlineMedium: GoogleFonts.plusJakartaSans(
        fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -0.25, color: primary,
      ),
      headlineSmall: GoogleFonts.plusJakartaSans(
        fontSize: 22, fontWeight: FontWeight.w700, color: primary,
      ),
      titleLarge: GoogleFonts.plusJakartaSans(
        fontSize: 19, fontWeight: FontWeight.w700, color: primary,
      ),
      titleMedium: GoogleFonts.plusJakartaSans(
        fontSize: 16, fontWeight: FontWeight.w600, color: primary,
      ),
      titleSmall: GoogleFonts.plusJakartaSans(
        fontSize: 14, fontWeight: FontWeight.w600, color: primary,
      ),
      bodyLarge: GoogleFonts.plusJakartaSans(
        fontSize: 16, fontWeight: FontWeight.w500, color: primary, height: 1.35,
      ),
      bodyMedium: GoogleFonts.plusJakartaSans(
        fontSize: 14, fontWeight: FontWeight.w500, color: secondary, height: 1.35,
      ),
      bodySmall: GoogleFonts.plusJakartaSans(
        fontSize: 12, fontWeight: FontWeight.w500, color: secondary, height: 1.3,
      ),
      labelLarge: GoogleFonts.plusJakartaSans(
        fontSize: 14, fontWeight: FontWeight.w700, color: primary,
      ),
      labelMedium: GoogleFonts.plusJakartaSans(
        fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.4, color: secondary,
      ),
      labelSmall: GoogleFonts.plusJakartaSans(
        fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.8, color: secondary,
      ),
    );
  }
}
