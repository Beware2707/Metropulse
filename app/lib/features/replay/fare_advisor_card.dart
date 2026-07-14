import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_spacing.dart';
import '../../core/widgets/glass_surface.dart';
import '../../providers/core_providers.dart';

/// The authenticated 30-day fare estimate behind the Commute Replay surface.
/// Auto-disposed so it re-fetches when the history screen is revisited.
final fareAdvisorProvider = FutureProvider.autoDispose<Map<String, dynamic>?>(
  (ref) => ref.watch(replayRepositoryProvider).fareAdvisor(),
);

/// A small Commute Replay card: "this month you took N trips, roughly this
/// much, and a smart card / off-peak riding would have saved this much".
/// Every figure is an estimate and the copy says so. Renders nothing at all
/// when there's no trip history yet (trips == 0) or the call didn't land —
/// an all-zero fare card would read as broken, not honest.
class FareAdvisorCard extends ConsumerWidget {
  const FareAdvisorCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final advisor = ref.watch(fareAdvisorProvider).valueOrNull;
    if (advisor == null) return const SizedBox.shrink();

    final trips = (advisor['trips'] as num?)?.toInt() ?? 0;
    if (trips <= 0) return const SizedBox.shrink();

    final spend = (advisor['estimated_spend_inr'] as num?)?.toInt() ?? 0;
    final cardSaving = (advisor['card_saving_inr'] as num?)?.toInt() ?? 0;
    final offpeakSaving =
        (advisor['offpeak_extra_saving_inr'] as num?)?.toInt() ?? 0;
    final note = advisor['note'] as String?;

    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
      child: GlassSurface(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('FARE ADVISOR', style: theme.textTheme.labelMedium),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'This month: $trips trips, about ₹$spend. A smart card would have '
              'saved about ₹$cardSaving — off-peak riding another ₹$offpeakSaving.',
              style: theme.textTheme.headlineSmall,
            ),
            if (note != null && note.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                note,
                style: theme.textTheme.labelSmall
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
