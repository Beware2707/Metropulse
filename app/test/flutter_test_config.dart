// Runs before every test file in this package.
//
// Two things, both in service of goldens that mean something:
//
// 1. No network. `google_fonts` will happily reach for fonts.gstatic.com when
//    a requested weight isn't in the asset bundle. A test that depends on the
//    network is flaky by construction, and worse, it hides the very bug it
//    should surface — a missing bundled weight looks fine on a machine with
//    wifi and breaks on a plane. Turning fetching off makes tests resolve
//    fonts exactly the way a cold-started app on the tarmac does.
//
// 2. Real glyphs. Goldens are only useful if the rendered text is the app's
//    real text. Loading the bundled faces here means a golden can actually
//    catch truncated copy, a mislabelled pill, or a stretched button —
//    the class of bug they exist for.
import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  GoogleFonts.config.allowRuntimeFetching = false;
  await _loadAppFonts();
  await _loadMaterialIcons();
  return testMain();
}

/// Registers Material's icon font.
///
/// Without this, every `Icon` renders as an empty tofu box — and a golden
/// taken that way would happily record "the tourist marker is a blank square"
/// and go green forever. Icons carry real meaning in this app (the tourist
/// marker, the SCHEDULE pill's neighbours), so the goldens have to see them.
///
/// The font ships with the SDK rather than the app, so it's resolved from
/// FLUTTER_ROOT — which `flutter test` sets — instead of a hardcoded path.
Future<void> _loadMaterialIcons() async {
  final root = Platform.environment['FLUTTER_ROOT'];
  if (root == null) {
    throw StateError('FLUTTER_ROOT is unset; cannot locate the Material icon font.');
  }
  final file = File(
    '$root/bin/cache/artifacts/material_fonts/materialicons-regular.otf',
  );
  if (!file.existsSync()) {
    throw StateError('Material icon font not found at ${file.path}.');
  }
  await (FontLoader('MaterialIcons')
        ..addFont(Future.value(ByteData.sublistView(file.readAsBytesSync()))))
      .load();
}

/// Registers the Plus Jakarta Sans faces the app bundles, under the family
/// name `GoogleFonts.plusJakartaSans` resolves to.
///
/// Deliberately strict: if a face is missing we throw rather than let the test
/// run render Roboto and quietly produce a golden of the wrong typeface.
Future<void> _loadAppFonts() async {
  const paths = [
    'assets/google_fonts/PlusJakartaSans-Medium.ttf',
    'assets/google_fonts/PlusJakartaSans-SemiBold.ttf',
    'assets/google_fonts/PlusJakartaSans-Bold.ttf',
    'assets/google_fonts/PlusJakartaSans-ExtraBold.ttf',
  ];
  final loader = FontLoader('PlusJakartaSans');
  for (final path in paths) {
    final file = File(path);
    if (!file.existsSync()) {
      throw StateError(
        'Missing bundled font $path. app_typography.dart only requests weights '
        'that live in assets/google_fonts/; if you added a weight, add its file.',
      );
    }
    loader.addFont(Future.value(ByteData.sublistView(file.readAsBytesSync())));
  }
  await loader.load();
}
