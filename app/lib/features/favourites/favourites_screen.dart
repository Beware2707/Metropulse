import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/core_providers.dart';

final favouritesProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(favouritesRepositoryProvider).list(),
);

/// Favourite stations with Home/Work labels (which power the commute card).
class FavouritesScreen extends ConsumerWidget {
  const FavouritesScreen({super.key});

  static const _labels = ['Home', 'Work', 'Other'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final favourites = ref.watch(favouritesProvider);
    final stations = ref.watch(stationIndexProvider);

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
        data: (rows) => rows.isEmpty
            ? const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: Text(
                    'No favourites yet.\n\nAdd your Home and Work stations to '
                    'unlock the commute card on the home screen.',
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  for (final row in rows)
                    Card(
                      child: ListTile(
                        leading: Icon(switch ('${row['label']}'.toLowerCase()) {
                          'home' => Icons.home_outlined,
                          'work' => Icons.work_outline,
                          _ => Icons.star_outline,
                        }),
                        title: Text(
                          stations['${row['stop_id']}']?.name ??
                              '${row['stop_id']}',
                        ),
                        subtitle:
                            row['label'] == null ? null : Text('${row['label']}'),
                        trailing: PopupMenuButton<String>(
                          onSelected: (choice) =>
                              _onAction(ref, row, choice),
                          itemBuilder: (_) => [
                            for (final label in _labels)
                              PopupMenuItem(
                                  value: 'label:$label',
                                  child: Text('Label as $label')),
                            const PopupMenuItem(
                                value: 'remove', child: Text('Remove')),
                          ],
                        ),
                        onTap: () =>
                            context.push('/station/${row['stop_id']}'),
                      ),
                    ),
                ],
              ),
      ),
    );
  }

  Future<void> _onAction(
      WidgetRef ref, Map<String, dynamic> row, String choice) async {
    final repository = ref.read(favouritesRepositoryProvider);
    final stopId = '${row['stop_id']}';
    if (choice == 'remove') {
      await repository.remove(stopId);
    } else if (choice.startsWith('label:')) {
      final label = choice.substring('label:'.length);
      await repository.save(
        stopId,
        label: label == 'Other' ? null : label,
        position: (row['position'] as num?)?.toInt() ?? 0,
      );
    }
    ref.invalidate(favouritesProvider);
  }
}
