import 'package:flutter/widgets.dart';

import '../l10n/gen/app_localizations.dart';

/// `context.t.homeYourCommute` — terse access to generated localizations.
/// The `lib/l10n/gen/` sources are produced by `flutter gen-l10n`, which the
/// tool runs automatically on every build (pubspec has `generate: true`).
extension L10nX on BuildContext {
  AppLocalizations get t => AppLocalizations.of(this);
}
