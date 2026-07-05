import 'package:flutter/material.dart';

import '../design/app_colors.dart';
import '../design/app_radius.dart';

/// A small pill naming a recommended coach — "Coach 3" — with a train-car
/// glyph. Used on the commute card and in Journey Mode wherever a coach
/// recommendation exists.
class CoachChip extends StatelessWidget {
  const CoachChip({super.key, required this.coach, this.dense = false});

  final int coach;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 10 : 14, vertical: dense ? 6 : 10),
      decoration: BoxDecoration(
        gradient: AppColors.heroGradientFor(),
        borderRadius: AppRadius.pillR,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.train_rounded, size: dense ? 14 : 16, color: Colors.white),
          const SizedBox(width: 6),
          Text(
            'Coach $coach',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: dense ? 12 : 13),
          ),
        ],
      ),
    );
  }
}
