import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/formatters.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../shared/async_section.dart';

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
      appBar: AppBar(title: const Text('Journey history')),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(journeyHistoryFullProvider),
        child: journeys.when(
          loading: () => ListView(
            padding: const EdgeInsets.all(16),
            children: const [
              SkeletonBlock(height: 64),
              SizedBox(height: 8),
              SkeletonBlock(height: 64),
              SizedBox(height: 8),
              SkeletonBlock(height: 64),
            ],
          ),
          error: (error, _) => ListView(
            children: [
              const SizedBox(height: 64),
              Icon(Icons.cloud_off, size: 48, color: Theme.of(context).colorScheme.outline),
              const SizedBox(height: 12),
              const Center(child: Text('Could not load journey history.')),
              Center(
                child: TextButton(
                  onPressed: () => ref.invalidate(journeyHistoryFullProvider),
                  child: const Text('Retry'),
                ),
              ),
            ],
          ),
          data: (data) => data.isEmpty
              ? ListView(
                  children: const [
                    SizedBox(height: 96),
                    Icon(Icons.history, size: 48),
                    SizedBox(height: 12),
                    Center(child: Text('No journeys yet.')),
                    Center(child: Text('Journeys you take will appear here.')),
                  ],
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: data.length,
                  itemBuilder: (_, index) {
                    final journey = data[index];
                    return Card(
                      child: ListTile(
                        leading: Icon(switch (journey.status) {
                          'completed' => Icons.check_circle_outline,
                          'missed' => Icons.error_outline,
                          'abandoned' => Icons.remove_circle_outline,
                          _ => Icons.pending_outlined,
                        }),
                        title: Text(
                          '${stations[journey.originStopId]?.name ?? journey.originStopId}'
                          ' → '
                          '${stations[journey.destinationStopId]?.name ?? journey.destinationStopId}',
                        ),
                        subtitle: Text(
                          '${journey.status} · ${clockTime(journey.startedAt)}',
                        ),
                      ),
                    );
                  },
                ),
        ),
      ),
    );
  }
}
