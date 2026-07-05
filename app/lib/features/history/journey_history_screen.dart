import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/shimmer_skeleton.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';

/// The full journey history (as opposed to Home's short "recent" preview),
/// offline-cached so it remains browsable without connectivity.
final journeyHistoryFullProvider = FutureProvider<List<Journey>>(
  (ref) => ref.watch(journeyRepositoryProvider).history(limit: 100),
);

class JourneyHistoryScreen extends ConsumerWidget {
  const JourneyHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journeys = ref.watch(journeyHistoryFullProvider);
    final stations = ref.watch(stationIndexProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Where you\'ve been')),
      body: AmbientBackground(
        intensity: 0.4,
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: () async => ref.invalidate(journeyHistoryFullProvider),
            child: journeys.when(
              loading: () => ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: const [
                  ShimmerBlock(height: 72),
                  SizedBox(height: AppSpacing.sm),
                  ShimmerBlock(height: 72),
                  SizedBox(height: AppSpacing.sm),
                  ShimmerBlock(height: 72),
                ],
              ),
              error: (error, _) => ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: [
                  const SizedBox(height: 64),
                  EmptyState(
                    icon: Icons.cloud_off_rounded,
                    message: "We couldn't load your trips.",
                    actionLabel: 'Try again',
                    onAction: () => ref.invalidate(journeyHistoryFullProvider),
                  ),
                ],
              ),
              data: (data) => data.isEmpty
                  ? ListView(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      children: const [
                        SizedBox(height: 96),
                        EmptyState(icon: Icons.history_rounded, message: 'Your trips will show up here once you take one.'),
                      ],
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      itemCount: data.length,
                      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                      itemBuilder: (_, index) {
                        final journey = data[index];
                        return GlassSurface(
                          child: Row(
                            children: [
                              IconBadge(
                                icon: switch (journey.status) {
                                  'completed' => Icons.check_circle_rounded,
                                  'missed' => Icons.error_rounded,
                                  'abandoned' => Icons.remove_circle_rounded,
                                  _ => Icons.pending_rounded,
                                },
                              ),
                              const SizedBox(width: AppSpacing.md),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      '${stations[journey.originStopId]?.name ?? journey.originStopId}'
                                      ' → '
                                      '${stations[journey.destinationStopId]?.name ?? journey.destinationStopId}',
                                      style: Theme.of(context).textTheme.titleMedium,
                                    ),
                                    Text('${journey.status} · ${clockTime(journey.startedAt)}',
                                        style: Theme.of(context).textTheme.bodySmall),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
