import 'package:flutter/material.dart';

/// A quiet honesty indicator — how much real history an estimate rests on,
/// never a marketing "trust us" badge. [confidence] is a real 0..1 value
/// already computed by the backend (e.g. `DelayEstimate.confidence`,
/// `CommutePrediction.confidence`); this only translates it into five small
/// dots, filled proportionally. Deliberately plain circles rather than star
/// icons — Metro Intelligence's brand voice is quiet, not gamified.
class ConfidenceDots extends StatelessWidget {
  const ConfidenceDots({super.key, required this.confidence, this.size = 6});

  final double confidence;
  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final filled = (confidence.clamp(0.0, 1.0) * 5).round().clamp(0, 5);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < 5; i++)
          Padding(
            padding: EdgeInsets.only(right: i < 4 ? 3 : 0),
            child: Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: i < filled ? scheme.primary : scheme.outlineVariant,
              ),
            ),
          ),
      ],
    );
  }
}
