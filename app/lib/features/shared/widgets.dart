import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../data/ws_client.dart';
import '../../providers/live_providers.dart';

/// A coloured pill naming a metro line.
class LineBadge extends StatelessWidget {
  const LineBadge({super.key, required this.label, this.colorHex});

  final String label;
  final String? colorHex;

  @override
  Widget build(BuildContext context) {
    final color = routeColor(colorHex);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 12),
      ),
    );
  }
}

/// Small dot + label reflecting the WebSocket connection state.
class LiveIndicator extends ConsumerWidget {
  const LiveIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status =
        ref.watch(wsStatusProvider).valueOrNull ?? WsStatus.connecting;
    final (color, label) = switch (status) {
      WsStatus.live => (Colors.green, 'LIVE'),
      WsStatus.connecting => (Colors.amber, 'CONNECTING'),
      WsStatus.reconnecting => (Colors.red, 'RECONNECTING'),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(label,
            style: TextStyle(
                fontSize: 11, letterSpacing: 1, color: color,
                fontWeight: FontWeight.w600)),
      ],
    );
  }
}

/// A big-number stat inside cards ("Coach 5", "32 min").
class StatTile extends StatelessWidget {
  const StatTile({super.key, required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label.toUpperCase(),
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.colorScheme.outline, letterSpacing: 1)),
        const SizedBox(height: 2),
        Text(value,
            style: theme.textTheme.titleMedium
                ?.copyWith(fontWeight: FontWeight.w700)),
      ],
    );
  }
}
