import 'package:flutter/material.dart';

import '../design/app_radius.dart';
import '../theme.dart';

/// A bold, filled pill naming a metro line — the GTFS route colour is used
/// as a solid background (not a faint tint) so lines read instantly, the
/// way real Delhi Metro wayfinding does.
class LineChip extends StatelessWidget {
  const LineChip({super.key, required this.label, this.colorHex, this.dense = false});

  final String label;
  final String? colorHex;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final bg = routeColor(colorHex, label);
    final fg = bg.computeLuminance() > 0.5 ? Colors.black87 : Colors.white;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 10 : 14, vertical: dense ? 5 : 9),
      decoration: BoxDecoration(color: bg, borderRadius: AppRadius.pillR),
      child: Text(
        label,
        style: TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: dense ? 11 : 13),
      ),
    );
  }
}
