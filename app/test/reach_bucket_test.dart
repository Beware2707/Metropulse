// Pins the reach-mode bucket cut-offs: every boundary minute must land in the
// bucket the legend promises, and the five buckets must be visibly distinct.
// This is the pure colour function the network-map painter calls, tested with
// no painter or widget in sight.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/network_map/network_map_screen.dart';

void main() {
  for (final dark in [false, true]) {
    final mode = dark ? 'dark' : 'light';

    test('$mode: minutes fall in the right half-open bucket', () {
      Color c(int m) => reachBucketColor(m, dark: dark);

      // Bucket boundaries are lower-inclusive: 0..14 green, 15..29 amber,
      // 30..44 orange, 45..59 red, 60+ deep red.
      final green = c(0);
      final amber = c(15);
      final orange = c(30);
      final red = c(45);
      final deepRed = c(60);

      // Same bucket -> same colour, including the last minute before a cut-off.
      expect(c(0), green);
      expect(c(14), green);
      expect(c(15), amber);
      expect(c(29), amber);
      expect(c(30), orange);
      expect(c(44), orange);
      expect(c(45), red);
      expect(c(59), red);
      expect(c(60), deepRed);
      expect(c(120), deepRed);

      // Crossing a boundary changes the colour.
      expect(c(14), isNot(c(15)));
      expect(c(29), isNot(c(30)));
      expect(c(44), isNot(c(45)));
      expect(c(59), isNot(c(60)));

      // All five buckets are distinct hues.
      final all = {green, amber, orange, red, deepRed};
      expect(all.length, 5);
    });
  }

  test('legend colours match the painter buckets', () {
    final legend = reachLegend(dark: false);
    expect(legend.length, 5);
    expect(legend[0].$2, reachBucketColor(0, dark: false));
    expect(legend[4].$2, reachBucketColor(60, dark: false));
  });
}
