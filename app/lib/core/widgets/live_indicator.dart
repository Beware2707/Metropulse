import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/ws_client.dart';
import '../../providers/live_providers.dart';
import '../design/app_colors.dart';
import '../design/app_motion.dart';
import '../design/app_radius.dart';

/// A pulsing dot + label reflecting the WebSocket connection state, inside a
/// soft pill rather than bare text.
class LiveIndicator extends ConsumerStatefulWidget {
  const LiveIndicator({super.key});

  @override
  ConsumerState<LiveIndicator> createState() => _LiveIndicatorState();
}

class _LiveIndicatorState extends ConsumerState<LiveIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: AppMotion.pulse)..repeat(reverse: true);

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final status = ref.watch(wsStatusProvider).valueOrNull ?? WsStatus.connecting;
    final (color, label) = switch (status) {
      WsStatus.live => (AppColors.live, 'LIVE'),
      WsStatus.connecting => (AppColors.warning, 'CONNECTING'),
      WsStatus.reconnecting => (AppColors.danger, 'RECONNECTING'),
    };
    final dot = Container(
      width: 7,
      height: 7,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: AppRadius.pillR),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (MediaQuery.of(context).disableAnimations)
            dot
          else
            FadeTransition(opacity: Tween(begin: 0.4, end: 1.0).animate(_pulse), child: dot),
          const SizedBox(width: 6),
          Text(label,
              style: TextStyle(fontSize: 11, letterSpacing: 0.6, color: color, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}
