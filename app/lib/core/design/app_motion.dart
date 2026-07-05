import 'package:flutter/animation.dart';

/// Animation timing/curve tokens. Micro-interactions use `fast`; screen-level
/// entrances use `medium`/`slow`; the splash/hero moment uses `hero`.
abstract final class AppMotion {
  AppMotion._();

  static const Duration fast = Duration(milliseconds: 150);
  static const Duration medium = Duration(milliseconds: 280);
  static const Duration slow = Duration(milliseconds: 450);
  static const Duration hero = Duration(milliseconds: 700);

  static const Curve standard = Curves.easeOutCubic;
  static const Curve playful = Curves.easeOutBack;
  static const Curve spring = Curves.elasticOut;
  static const Curve enter = Curves.easeOutQuint;
}
