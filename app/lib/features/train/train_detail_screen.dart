import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_motion.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/stat_pill.dart';
import '../../domain/models/eta.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';

final _etaProvider = FutureProvider.autoDispose.family<VehicleEta?, String>((ref, vehicleId) async {
  return ref.watch(trainsRepositoryProvider).eta(vehicleId);
});

/// Full train detail: live state plus per-station ETAs down the line.
class TrainDetailScreen extends ConsumerWidget {
  const TrainDetailScreen({super.key, required this.vehicleId});

  final String vehicleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final train = ref.watch(liveTrainProvider(vehicleId));
    final etaAsync = train == null ? null : ref.watch(_etaProvider(vehicleId));
    final eta = etaAsync?.valueOrNull;
    final etaLoading = etaAsync != null && etaAsync.isLoading && !etaAsync.hasValue;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(train?.lineLabel ?? 'Train'),
        actions: const [Padding(padding: EdgeInsets.only(right: 16), child: Center(child: LiveIndicator()))],
      ),
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: train == null
              ? Center(
                  child: EmptyState(
                    icon: Icons.train_rounded,
                    message: "We've lost track of this train — it may have finished its trip.",
                    actionLabel: 'Back to map',
                    onAction: () => context.go('/explore'),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, AppSpacing.xxl),
                  children: [
                    GlassSurface(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          LineChip(label: train.lineLabel, colorHex: train.routeColor),
                          const SizedBox(height: AppSpacing.md),
                          if (train.headsign != null)
                            Text('Towards ${train.headsign}', style: Theme.of(context).textTheme.headlineSmall),
                          const SizedBox(height: AppSpacing.lg),
                          Wrap(
                            spacing: AppSpacing.md,
                            runSpacing: AppSpacing.md,
                            children: [
                              _AnimatedStatPill(
                                icon: Icons.train_rounded,
                                label: 'Status',
                                value: train.atStation
                                    ? 'At ${train.currentStation?.name ?? '…'}'
                                    : train.nextStation != null
                                        ? 'Toward ${train.nextStation!.name}'
                                        : 'Moving',
                              ),
                              if (train.destination != null && train.destination!.name != train.headsign)
                                StatPill(icon: Icons.flag_rounded, label: 'Destination', value: train.destination!.name),
                              if (eta?.delaySeconds != null)
                                _AnimatedStatPill(
                                  icon: Icons.schedule_rounded,
                                  label: 'Schedule',
                                  value: eta!.delaySeconds! > 60 ? '${minutesLabel(eta.delaySeconds)} late' : 'On time',
                                ),
                              if (eta?.delaySeconds != null)
                                _AnimatedStatPill(
                                  icon: Icons.verified_rounded,
                                  label: 'Confidence',
                                  value: eta!.confidence,
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SectionHeader(title: 'Upcoming stations'),
                    if (etaLoading)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: AppSpacing.lg),
                        child: Center(child: CircularProgressIndicator()),
                      )
                    else if (eta == null || eta.stations.isEmpty)
                      const EmptyState(icon: Icons.info_rounded, message: "We don't have arrival times for this train yet.")
                    else
                      MomentList(
                        children: [
                          for (var i = 0; i < eta.stations.length; i++)
                            _StationRow(
                              station: eta.stations[i],
                              isNext: i == 0,
                              accent: routeColor(train.routeColor, train.lineLabel),
                              onTap: () => context.push('/station/${eta.stations[i].stopId}'),
                            ),
                        ],
                      ),
                  ],
                ),
        ),
      ),
    );
  }
}

/// A [StatPill] whose value cross-fades rather than snaps whenever the
/// underlying fact (status/delay) changes.
class _AnimatedStatPill extends StatelessWidget {
  const _AnimatedStatPill({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return AnimatedSwitcher(
      duration: reduceMotion ? Duration.zero : AppMotion.fast,
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (child, animation) => FadeTransition(opacity: animation, child: child),
      child: StatPill(key: ValueKey(value), icon: icon, label: label, value: value),
    );
  }
}

/// A single upcoming-station row. The very next station (`isNext`) gets an
/// accent-tinted background and a bolder, larger ETA to stand out from the
/// rest of the list; every other row stays exactly as plain as before.
class _StationRow extends StatefulWidget {
  const _StationRow({required this.station, required this.isNext, required this.accent, required this.onTap});

  final StationEta station;
  final bool isNext;
  final Color accent;
  final VoidCallback onTap;

  @override
  State<_StationRow> createState() => _StationRowState();
}

class _StationRowState extends State<_StationRow> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final reduceMotion = MediaQuery.of(context).disableAnimations;

    final row = MomentRow(
      leading: Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: widget.accent, shape: BoxShape.circle),
      ),
      title: Text(widget.station.stopName, style: theme.textTheme.titleMedium),
      trailing: Text(
        minutesLabel(widget.station.etaSeconds),
        style: widget.isNext
            ? theme.textTheme.headlineLarge?.copyWith(color: widget.accent, fontWeight: FontWeight.w700)
            : theme.textTheme.titleMedium,
      ),
      onTap: widget.onTap,
    );

    final content = widget.isNext
        ? Container(
            decoration: BoxDecoration(
              color: widget.accent.withValues(alpha: 0.12),
              borderRadius: AppRadius.mdR,
            ),
            child: row,
          )
        : row;

    final scale = reduceMotion ? 1.0 : (_pressed ? 0.97 : 1.0);
    // No `onTap` here: MomentRow's own InkWell (above) already fires
    // widget.onTap — adding it here too would double-push the route on
    // every tap. This GestureDetector exists only to drive the press-scale.
    return GestureDetector(
      onTapDown: reduceMotion ? null : (_) => setState(() => _pressed = true),
      onTapUp: reduceMotion ? null : (_) => setState(() => _pressed = false),
      onTapCancel: reduceMotion ? null : () => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: scale,
        duration: AppMotion.fast,
        curve: AppMotion.standard,
        child: content,
      ),
    );
  }
}
