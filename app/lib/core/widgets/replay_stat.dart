import 'package:flutter/material.dart';

/// One glanceable Commute Replay figure — an icon, a value, and a label.
/// Used in both the per-trip and monthly Commute Replay cards.
class ReplayStat extends StatelessWidget {
  const ReplayStat({super.key, required this.icon, required this.label, required this.value, this.color});

  final IconData icon;
  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      width: 132,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color ?? theme.colorScheme.onSurfaceVariant),
          const SizedBox(height: 4),
          Text(value, style: theme.textTheme.titleLarge?.copyWith(color: color)),
          Text(label, style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}
