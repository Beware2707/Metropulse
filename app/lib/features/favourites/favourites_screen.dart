import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/core_providers.dart';
import '../home/home_providers.dart' show favouriteStationsProvider, pinnedJourneysProvider;

export '../home/home_providers.dart' show favouriteStationsProvider;

/// Favourite stations (Home/Work/College/custom labels — which power the
/// commute card) and pinned journeys (local shortcuts straight into the
/// planner).
class FavouritesScreen extends ConsumerWidget {
  const FavouritesScreen({super.key});

  static const _quickLabels = ['Home', 'Work', 'College'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final favourites = ref.watch(favouriteStationsProvider);
    final stations = ref.watch(stationIndexProvider);
    final pinnedJourneys = ref.watch(pinnedJourneysProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Favourites')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/search'),
        icon: const Icon(Icons.add),
        label: const Text('Add station'),
      ),
      body: favourites.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) =>
            Center(child: Text('Could not load favourites: $error')),
        data: (rows) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
          children: [
            Text('Stations', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (rows.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'Add your Home and Work stations to unlock the commute '
                    'card on the home screen.',
                  ),
                ),
              )
            else
              for (final row in rows)
                Card(
                  child: ListTile(
                    leading: Icon(switch ('${row['label']}'.toLowerCase()) {
                      'home' => Icons.home_outlined,
                      'work' => Icons.work_outline,
                      'college' => Icons.school_outlined,
                      _ => Icons.star_outline,
                    }),
                    title: Text(
                      stations['${row['stop_id']}']?.name ?? '${row['stop_id']}',
                    ),
                    subtitle: row['label'] == null ? null : Text('${row['label']}'),
                    trailing: PopupMenuButton<String>(
                      onSelected: (choice) => _onStationAction(context, ref, row, choice),
                      itemBuilder: (_) => [
                        for (final label in _quickLabels)
                          PopupMenuItem(value: 'label:$label', child: Text('Label as $label')),
                        const PopupMenuItem(value: 'custom', child: Text('Custom label…')),
                        const PopupMenuItem(value: 'remove', child: Text('Remove')),
                      ],
                    ),
                    onTap: () => context.push('/station/${row['stop_id']}'),
                  ),
                ),
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: Text('Pinned journeys', style: Theme.of(context).textTheme.titleMedium),
                ),
                TextButton.icon(
                  onPressed: () => context.push('/planner'),
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('New'),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (pinnedJourneys.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text(
                    'Pin a journey from the planner for one-tap access to '
                    'routes you take often.',
                  ),
                ),
              )
            else
              for (var i = 0; i < pinnedJourneys.length; i++)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.push_pin_outlined),
                    title: Text('${pinnedJourneys[i]['label']}'),
                    subtitle: Text(
                      '${stations['${pinnedJourneys[i]['origin_stop_id']}']?.name ?? pinnedJourneys[i]['origin_stop_id']}'
                      ' → '
                      '${stations['${pinnedJourneys[i]['destination_stop_id']}']?.name ?? pinnedJourneys[i]['destination_stop_id']}',
                    ),
                    trailing: IconButton(
                      icon: const Icon(Icons.close, size: 18),
                      onPressed: () async {
                        await ref.read(localStoreProvider).removePinnedJourneyAt(i);
                        ref.invalidate(pinnedJourneysProvider);
                      },
                    ),
                    onTap: () => context.push(
                      '/planner?origin=${pinnedJourneys[i]['origin_stop_id']}'
                      '&destination=${pinnedJourneys[i]['destination_stop_id']}',
                    ),
                  ),
                ),
          ],
        ),
      ),
    );
  }

  Future<void> _onStationAction(
    BuildContext context,
    WidgetRef ref,
    Map<String, dynamic> row,
    String choice,
  ) async {
    final repository = ref.read(favouritesRepositoryProvider);
    final stopId = '${row['stop_id']}';
    final position = (row['position'] as num?)?.toInt() ?? 0;

    if (choice == 'remove') {
      await repository.remove(stopId);
    } else if (choice == 'custom') {
      final controller = TextEditingController(text: '${row['label'] ?? ''}');
      final label = await showDialog<String>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Custom label'),
          content: TextField(controller: controller, autofocus: true),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(controller.text.trim()),
              child: const Text('Save'),
            ),
          ],
        ),
      );
      if (label != null && label.isNotEmpty) {
        await repository.save(stopId, label: label, position: position);
      }
    } else if (choice.startsWith('label:')) {
      final label = choice.substring('label:'.length);
      await repository.save(stopId, label: label, position: position);
    }
    ref.invalidate(favouriteStationsProvider);
  }
}
