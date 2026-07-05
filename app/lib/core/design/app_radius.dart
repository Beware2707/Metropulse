import 'package:flutter/widgets.dart';

/// Corner radius scale. Nothing in this app uses the old 12-16dp Material
/// default — floating surfaces read as soft, bold shapes, not boxes.
abstract final class AppRadius {
  AppRadius._();

  static const double sm = 16;
  static const double md = 20;
  static const double lg = 24;
  static const double xl = 28;
  static const double xxl = 32;
  static const double pill = 999;

  static const BorderRadius smR = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdR = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgR = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius xlR = BorderRadius.all(Radius.circular(xl));
  static const BorderRadius xxlR = BorderRadius.all(Radius.circular(xxl));
  static const BorderRadius pillR = BorderRadius.all(Radius.circular(pill));
}
