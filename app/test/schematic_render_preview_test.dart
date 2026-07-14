// Rasterizes the REAL network_schematic.json through the app's actual
// painter and writes a PNG for human inspection — the only check that can
// catch a tool↔renderer contract drift (e.g. label boxes measured with one
// font but painted with another). A real font is loaded so glyphs render as
// text rather than flutter_test's Ahem blocks.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/network_schematic.dart';
import 'package:metropulse_app/features/network_map/network_map_screen.dart';

const _outPath =
    r'C:\Users\riddl\AppData\Local\Temp\claude\C--Users-riddl-Downloads-Metro'
    r'\2fc3ed17-50c8-49e0-b4f4-16d10e109083\scratchpad'
    r'\schematic_flutter_render.png';

void main() {
  testWidgets('real schematic asset renders through the app painter',
      (tester) async {
    final assetFile = File('assets/network_schematic.json');
    expect(assetFile.existsSync(), isTrue,
        reason: 'run tools/schematic_layout.py first');
    final schematic = NetworkSchematic.parse(assetFile.readAsStringSync());
    expect(schematic.stations.length, 262);

    // Register a real font under the family the painter names, when one is
    // available on this machine (Windows Arial); Ahem blocks otherwise.
    final arial = File(r'C:\Windows\Fonts\arial.ttf');
    if (arial.existsSync()) {
      final loader = FontLoader('Roboto')
        ..addFont(Future.value(ByteData.sublistView(arial.readAsBytesSync())));
      await loader.load();
    }

    const outWidth = 1600.0;
    final outHeight =
        outWidth * schematic.canvas.height / schematic.canvas.width;
    await tester.binding.setSurfaceSize(Size(outWidth, outHeight));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final key = GlobalKey();
    await tester.pumpWidget(
      MaterialApp(
        home: RepaintBoundary(
          key: key,
          child: Container(
            color: const Color(0xFFFAFAF7),
            child: FittedBox(
              fit: BoxFit.fill,
              child: SizedBox.fromSize(
                size: schematic.canvas,
                child: buildSchematicPreviewForTest(schematic),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.runAsync(() async {
      final boundary =
          key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      final image = await boundary.toImage();
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      // The inspection PNG is a dev-machine artifact; on other machines the
      // render itself (above) is still the regression check.
      final out = File(_outPath).parent.existsSync()
          ? File(_outPath)
          : File('${Directory.systemTemp.path}/schematic_flutter_render.png');
      out.writeAsBytesSync(bytes!.buffer.asUint8List());
    });
  });
}
