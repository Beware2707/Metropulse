import 'package:flutter/material.dart';

/// MetroPulse colour system. Dark is the primary canvas the whole app is
/// designed against; light is a faithful secondary derivation, not an
/// afterthought, but every hero surface is tuned for dark first.
abstract final class AppColors {
  AppColors._();

  // Brand gradient — deliberately distinct from any single GTFS line colour
  // (routeColor() in theme.dart stays 100% data-driven from the feed).
  static const Color brandBlue = Color(0xFF3D7FFF);
  static const Color brandViolet = Color(0xFF8B5CF6);
  static const Color brandPink = Color(0xFFFF5DA2);

  static const List<Color> heroGradient = [brandBlue, brandViolet];
  static const List<Color> heroGradientWide = [brandBlue, brandViolet, brandPink];

  // Semantic accents, shared by both brightnesses. Chosen to read as
  // unambiguous blue/purple/green/orange — no washed-out "dashboard" tones.
  static const Color live = Color(0xFF2DD4BF);
  static const Color success = Color(0xFF30D158);
  static const Color warning = Color(0xFFFF9500);
  static const Color danger = Color(0xFFFF3B30);
  static const Color night = Color(0xFFFF8A5B);

  // Dark canvas — true OLED black, not a tinted near-black. Surfaces lift by
  // just enough luminance to read as floating, never a flat grey.
  static const Color darkBg = Color(0xFF000000);
  static const Color darkSurface = Color(0xFF0C0C0C);
  static const Color darkSurfaceElevated = Color(0xFF161616);
  static const Color darkSurfaceGlass = Color(0xB0161616);
  static const Color darkBorder = Color(0x1FFFFFFF);
  static const Color darkTextPrimary = Color(0xFFF5F6FA);
  static const Color darkTextSecondary = Color(0xFFA6A8B8);
  static const Color darkTextTertiary = Color(0xFF6B6D80);

  // Light canvas — warm white, not cool lavender-grey.
  static const Color lightBg = Color(0xFFFBF8F3);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightSurfaceElevated = Color(0xFFFFFFFF);
  static const Color lightSurfaceGlass = Color(0xD9FFFFFF);
  static const Color lightBorder = Color(0x14000000);
  static const Color lightTextPrimary = Color(0xFF1C1B19);
  static const Color lightTextSecondary = Color(0xFF615D56);
  static const Color lightTextTertiary = Color(0xFF9C978E);

  static LinearGradient heroGradientFor({Alignment begin = Alignment.topLeft, Alignment end = Alignment.bottomRight}) =>
      LinearGradient(begin: begin, end: end, colors: heroGradient);
}
