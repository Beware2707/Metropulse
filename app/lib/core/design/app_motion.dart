import 'package:flutter/animation.dart';

/// Animation timing/curve tokens. Micro-interactions use `fast`; screen-level
/// entrances use `medium`/`slow`; the splash/hero moment uses `hero`.
abstract final class AppMotion {
  AppMotion._();

  static const Duration fast = Duration(milliseconds: 150);
  static const Duration medium = Duration(milliseconds: 280);
  static const Duration slow = Duration(milliseconds: 450);
  static const Duration hero = Duration(milliseconds: 700);

  /// The one cadence every "still alive" pulse uses — the live dot, the
  /// shimmer skeleton, the mic button, the loading bar. Previously each of
  /// these picked its own value (1100–1400ms); one shared rhythm reads as a
  /// single heartbeat for the whole app rather than four unrelated ticks.
  static const Duration pulse = Duration(milliseconds: 1200);

  /// A value gliding to its new position — the journey progress dot moving
  /// along the rail. Distinct from `hero` (a one-time entrance moment):
  /// this repeats every time the underlying value changes.
  static const Duration glide = Duration(milliseconds: 900);

  static const Curve standard = Curves.easeOutCubic;
  static const Curve playful = Curves.easeOutBack;
  static const Curve spring = Curves.elasticOut;
  static const Curve enter = Curves.easeOutQuint;
}
