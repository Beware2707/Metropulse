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

  // Semantic accents, shared by both brightnesses.
  static const Color live = Color(0xFF2DD4BF);
  static const Color success = Color(0xFF34D399);
  static const Color warning = Color(0xFFFBBF24);
  static const Color danger = Color(0xFFFF5470);
  static const Color night = Color(0xFFFF8A5B);

  // Dark canvas.
  static const Color darkBg = Color(0xFF0B0B14);
  static const Color darkSurface = Color(0xFF15151F);
  static const Color darkSurfaceElevated = Color(0xFF1D1D29);
  static const Color darkSurfaceGlass = Color(0xB01D1D29);
  static const Color darkBorder = Color(0x1FFFFFFF);
  static const Color darkTextPrimary = Color(0xFFF5F6FA);
  static const Color darkTextSecondary = Color(0xFFA6A8B8);
  static const Color darkTextTertiary = Color(0xFF6B6D80);

  // Light canvas.
  static const Color lightBg = Color(0xFFF6F6FB);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightSurfaceElevated = Color(0xFFFFFFFF);
  static const Color lightSurfaceGlass = Color(0xD9FFFFFF);
  static const Color lightBorder = Color(0x14000000);
  static const Color lightTextPrimary = Color(0xFF15151F);
  static const Color lightTextSecondary = Color(0xFF5B5D70);
  static const Color lightTextTertiary = Color(0xFF9799AA);

  static LinearGradient heroGradientFor({Alignment begin = Alignment.topLeft, Alignment end = Alignment.bottomRight}) =>
      LinearGradient(begin: begin, end: end, colors: heroGradient);
}
