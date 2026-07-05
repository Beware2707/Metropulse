import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../domain/models/commute_card.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../shared/widgets.dart';

final commuteCardProvider = FutureProvider<CommuteCard?>(
  (ref) => ref.watch(commuteRepositoryProvider).card(),
);

final activeJourneyProvider = FutureProvider<Journey?>(
  (ref) => ref.watch(journeyRepositoryProvider).current(),
);

/// Home: the commuter's answer screen — commute card first, actions second.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(commuteCardProvider);
    final journey = ref.watch(activeJourneyProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('MetroPulse'),
        actions: [
          const Padding(
            padding: EdgeInsets.only(right: 8),
            child: Center(child: LiveIndicator()),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => context.push('/settings'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(commuteCardProvider);
          ref.invalidate(activeJourneyProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (journey.valueOrNull != null)
              _ActiveJourneyBanner(journey: journey.valueOrNull!),
            card.when(
              data: (data) => data == null
                  ? const _SetupCommuteCard()
                  : _CommuteCardView(card: data),
              loading: () => const Card(
                child: SizedBox(
                  height: 180,
                  child: Center(child: CircularProgressIndicator()),
                ),
              ),
              error: (_, __) => const _SetupCommuteCard(),
            ),
            const SizedBox(height: 16),
            _QuickActions(),
          ],
        ),
      ),
    );
  }
}

class _CommuteCardView extends StatelessWidget {
  const _CommuteCardView({required this.card});

  final CommuteCard card;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(card.greeting, style: theme.textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              '${card.originName} → ${card.destinationName}',
              style: theme.textTheme.headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            if (card.routeLongName != null)
              LineBadge(label: card.routeLongName!, colorHex: card.routeColor),
            const SizedBox(height: 16),
            if (card.leaveInSeconds != null)
              Text(
                'Leave in ${minutesLabel(card.leaveInSeconds)}',
                style: theme.textTheme.titleLarge?.copyWith(
                  color: theme.colorScheme.primary,
                  fontWeight: FontWeight.w800,
                ),
              )
            else
              Text('No upcoming departures',
                  style: theme.textTheme.titleMedium),
            const SizedBox(height: 16),
            Wrap(
              spacing: 24,
              runSpacing: 12,
              children: [
                StatTile(
                    label: 'Next metro',
                    value: clockTime(card.nextDepartureAt)),
                StatTile(label: 'Crowding', value: card.crowding),
                if (card.platformHint != null)
                  StatTile(label: 'Platform', value: card.platformHint!),
                if (card.recommendedCoach != null)
                  StatTile(
                      label: 'Coach', value: '${card.recommendedCoach! + 1}'),
                StatTile(label: 'ETA', value: minutesLabel(card.travelSeconds)),
                if (card.interchangeNames.isNotEmpty)
                  StatTile(
                      label: 'Interchange',
                      value: card.interchangeNames.join(', ')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _SetupCommuteCard extends StatelessWidget {
  const _SetupCommuteCard();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: const Icon(Icons.add_home_work_outlined, size: 36),
        title: const Text('Set up your commute'),
        subtitle: const Text(
            'Add two favourite stations labelled Home and Work to see your '
            'personalised commute card here.'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.push('/favourites'),
      ),
    );
  }
}

class _ActiveJourneyBanner extends StatelessWidget {
  const _ActiveJourneyBanner({required this.journey});

  final Journey journey;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.primaryContainer,
      child: ListTile(
        leading: Icon(Icons.navigation, color: scheme.onPrimaryContainer),
        title: const Text('Journey in progress'),
        subtitle: const Text('Tap to return to live journey mode'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.push('/journey'),
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final actions = [
      ('Live map', Icons.map_outlined, '/map'),
      ('Plan journey', Icons.route_outlined, '/planner'),
      ('Search', Icons.search, '/search'),
      ('Favourites', Icons.star_outline, '/favourites'),
    ];
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 2.4,
      children: [
        for (final (label, icon, path) in actions)
          Card(
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => context.push(path),
              child: Row(
                children: [
                  const SizedBox(width: 16),
                  Icon(icon),
                  const SizedBox(width: 12),
                  Text(label,
                      style: Theme.of(context).textTheme.titleSmall),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
