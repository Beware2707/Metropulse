import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/confidence_dots.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/section_header.dart';
import '../../domain/place_suggestions.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart'
    show favouriteStationsProvider, inferredPlacesProvider, pinnedJourneysProvider;

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
    final inferredPlaces = ref.watch(inferredPlacesProvider).valueOrNull ?? const [];

    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: Stack(
            children: [
              favourites.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (error, _) => const Center(child: Text("We couldn't load your favourites. Pull to try again.")),
                data: (rows) => ListView(
                  padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 180),
                  children: [
                    // Favourites is a PUSHED route, not one of the four tabs,
                    // so nothing else on screen offers a way back — and with
                    // a custom header instead of an AppBar there was no
                    // automatic one either. Gesture-back still worked, which
                    // is exactly why this stayed invisible for so long.
                    Row(
                      children: [
                        IconPillButton(
                          icon: Icons.arrow_back_rounded,
                          tooltip: 'Back',
                          onPressed: () => context.pop(),
                        ),
                        const SizedBox(width: AppSpacing.md),
                        Text('Saved', style: Theme.of(context).textTheme.displaySmall),
                      ],
                    ),
                    for (final suggestion in placeSuggestions(rows, inferredPlaces))
                      Padding(
                        padding: const EdgeInsets.only(top: AppSpacing.md),
                        child: _PlaceSuggestionCard(
                          suggestion: suggestion,
                          onChoose: (label) => _onStationAction(
                            context,
                            ref,
                            {'stop_id': suggestion.place.stopId, 'position': rows.length},
                            'label:$label',
                          ),
                        ),
                      ),
                    const SectionHeader(title: 'Stations', padding: EdgeInsets.only(top: AppSpacing.xl)),
                    if (rows.isEmpty)
                      const EmptyState(
                        icon: Icons.home_work_rounded,
                        message: "Add your Home and Work stations and we'll build your commute card for you.",
                      )
                    else
                      MomentList(
                        children: [
                          for (final row in rows)
                            _FavouriteRow(
                              row: row,
                              name: stations['${row['stop_id']}']?.name ?? '${row['stop_id']}',
                              onAction: (choice) => _onStationAction(context, ref, row, choice),
                              onTap: () => context.push('/station/${row['stop_id']}'),
                            ),
                        ],
                      ),
                    SectionHeader(
                      title: 'Pinned journeys',
                      trailing: TextButton.icon(
                        onPressed: () => context.push('/planner'),
                        icon: const Icon(Icons.add_rounded, size: 18),
                        label: const Text('New'),
                      ),
                    ),
                    if (pinnedJourneys.isEmpty)
                      const EmptyState(
                        icon: Icons.push_pin_rounded,
                        message: "Save a route from the planner and it'll be one tap away.",
                      )
                    else
                      MomentList(
                        children: [
                          for (var i = 0; i < pinnedJourneys.length; i++)
                            MomentRow(
                              leading: const IconBadge(icon: Icons.push_pin_rounded),
                              title: Text('${pinnedJourneys[i]['label']}', style: Theme.of(context).textTheme.titleMedium),
                              subtitle: Text(
                                '${stations['${pinnedJourneys[i]['origin_stop_id']}']?.name ?? pinnedJourneys[i]['origin_stop_id']}'
                                ' → '
                                '${stations['${pinnedJourneys[i]['destination_stop_id']}']?.name ?? pinnedJourneys[i]['destination_stop_id']}',
                                style: Theme.of(context).textTheme.bodyMedium,
                              ),
                              trailing: IconButton(
                                icon: const Icon(Icons.close_rounded, size: 18),
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
                        ],
                      ),
                  ],
                ),
              ),
              Positioned(
                right: AppSpacing.lg,
                bottom: 108,
                child: PrimaryButton(
                  label: 'Add a station',
                  icon: Icons.add_rounded,
                  onPressed: () => context.push('/search'),
                ),
              ),
            ],
          ),
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
          title: const Text('Give it a name'),
          content: TextField(controller: controller, autofocus: true),
          actions: [
            TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('Cancel')),
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

class _PlaceSuggestionCard extends StatelessWidget {
  const _PlaceSuggestionCard({required this.suggestion, required this.onChoose});

  final PlaceSuggestion suggestion;
  final ValueChanged<String> onChoose;

  @override
  Widget build(BuildContext context) {
    final place = suggestion.place;
    final question = suggestion.labelOptions.length == 1
        ? 'Is ${place.stopName} your ${suggestion.labelOptions.single}?'
        : "What's ${place.stopName} to you?";
    return GlassSurface(
      child: Row(
        children: [
          IconBadge(
            icon: place.role == 'home' ? Icons.home_rounded : Icons.work_rounded,
            gradient: AppColors.heroGradientFor(),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(question, style: Theme.of(context).textTheme.titleMedium),
                Row(
                  children: [
                    Expanded(child: Text(place.rationale, style: Theme.of(context).textTheme.bodySmall)),
                    const SizedBox(width: AppSpacing.sm),
                    ConfidenceDots(confidence: place.confidence),
                  ],
                ),
              ],
            ),
          ),
          for (final label in suggestion.labelOptions)
            TextButton(onPressed: () => onChoose(label), child: Text(label)),
        ],
      ),
    );
  }
}

class _FavouriteRow extends StatelessWidget {
  const _FavouriteRow({required this.row, required this.name, required this.onAction, required this.onTap});

  final Map<String, dynamic> row;
  final String name;
  final ValueChanged<String> onAction;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final label = '${row['label'] ?? ''}'.toLowerCase();
    final icon = switch (label) {
      'home' => Icons.home_rounded,
      'work' => Icons.work_rounded,
      'college' => Icons.school_rounded,
      _ => Icons.star_rounded,
    };
    return MomentRow(
      leading: IconBadge(icon: icon, gradient: AppColors.heroGradientFor()),
      title: Text(name, style: Theme.of(context).textTheme.titleMedium),
      subtitle: row['label'] != null ? Text('${row['label']}', style: Theme.of(context).textTheme.bodySmall) : null,
      trailing: PopupMenuButton<String>(
        onSelected: onAction,
        itemBuilder: (_) => [
          for (final label in FavouritesScreen._quickLabels)
            PopupMenuItem(value: 'label:$label', child: Text('Label as $label')),
          const PopupMenuItem(value: 'custom', child: Text('Custom name…')),
          const PopupMenuItem(value: 'remove', child: Text('Remove')),
        ],
      ),
      onTap: onTap,
    );
  }
}
