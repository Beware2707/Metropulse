import 'package:flutter/material.dart';

import '../design/app_radius.dart';
import '../theme.dart';

/// A bold, filled pill naming a metro line — the GTFS route colour is used
/// as a solid background (not a faint tint) so lines read instantly, the
/// way real Delhi Metro wayfinding does.
class LineChip extends StatelessWidget {
  const LineChip({super.key, required this.label, this.subtitle, this.colorHex, this.dense = false});

  final String label;

  /// An optional second line inside the same pill — e.g. "New Delhi to
  /// Dwarka Sector - 21" under the line name — shown smaller and slightly
  /// dimmer than [label].
  final String? subtitle;
  final String? colorHex;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final bg = routeColor(colorHex, label);
    final fg = bg.computeLuminance() > 0.5 ? Colors.black87 : Colors.white;
    final nameText = Text(
      label,
      style: TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: dense ? 11 : 13),
    );
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 10 : 14, vertical: dense ? 5 : 9),
      decoration: BoxDecoration(color: bg, borderRadius: AppRadius.pillR),
      child: subtitle == null
          ? nameText
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                nameText,
                const SizedBox(height: 2),
                Text(
                  subtitle!,
                  style: TextStyle(
                    color: fg.withValues(alpha: 0.85),
                    fontWeight: FontWeight.w500,
                    fontSize: dense ? 9 : 11,
                  ),
                ),
              ],
            ),
    );
  }
}
