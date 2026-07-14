import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/section_header.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../shared/station_search_sheet.dart';

/// How the screen fetches fair meeting points for two starting stops.
/// Injectable so tests can feed fixed candidates without a live backend;
/// defaults to `JourneyRepository.meet`.
typedef MeetFetcher = Future<List<Map<String, dynamic>>> Function(
    String a, String b);

/// Meet in the middle: pick where you and a friend are each starting, and the
/// backend ranks stations by fairness — smallest worst-case travel time
/// first, then smallest combined time — so neither of you carries the whole
/// trip. Times are whole-minute estimates from the published timetable, not
/// live running.
class MeetScreen extends ConsumerStatefulWidget {
  const MeetScreen({
    super.key,
    this.fetchCandidates,
    this.initialYou,
    this.initialFriend,
  });

  /// Test seam — see [MeetFetcher]. Null means the real repository.
  final MeetFetcher? fetchCandidates;

  /// Test seams — pre-selected starting stations. When both are provided the
  /// screen fetches candidates immediately, without driving the picker.
  final Station? initialYou;
  final Station? initialFriend;

  @override
  ConsumerState<MeetScreen> createState() => _MeetScreenState();
}

class _MeetScreenState extends ConsumerState<MeetScreen> {
  Station? _you;
  Station? _friend;
  List<Map<String, dynamic>>? _candidates;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _you = widget.initialYou;
    _friend = widget.initialFriend;
    if (_you != null && _friend != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _fetch());
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final candidates = _candidates;
    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 48),
            children: [
              Row(
                children: [
                  IconPillButton(
                      icon: Icons.arrow_back_rounded,
                      onPressed: () => context.pop()),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child:
                        Text('Meet in the middle', style: theme.textTheme.displaySmall),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Text(
                'Pick where each of you is starting and we\'ll find the stations '
                'that are fairest to reach — sorted so the longer trip is as '
                'short as it can be.',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.xl),
              _PickerRow(
                label: 'YOU',
                icon: Icons.person_rounded,
                station: _you,
                placeholder: 'Where are you starting?',
                onTap: () => _pick(isYou: true),
              ),
              const SizedBox(height: AppSpacing.md),
              _PickerRow(
                label: 'YOUR FRIEND',
                icon: Icons.person_outline_rounded,
                station: _friend,
                placeholder: 'Where are they starting?',
                onTap: () => _pick(isYou: false),
              ),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.xxl),
                  child: Center(child: CircularProgressIndicator()),
                ),
              if (!_loading && candidates != null) ...[
                if (candidates.isEmpty)
                  const Padding(
                    padding: EdgeInsets.only(top: AppSpacing.xl),
                    child: EmptyState(
                      icon: Icons.handshake_rounded,
                      message:
                          "We couldn't find a fair meeting point for those two "
                          'stops. Try a different pair.',
                    ),
                  )
                else ...[
                  const SectionHeader(title: 'Fairest to meet'),
                  for (final candidate in candidates)
                    Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                      child: _CandidateCard(candidate: candidate),
                    ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    'Times are estimates from the published timetable, not live '
                    'running, and ignore the walk to and from each station.',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.outline),
                  ),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pick({required bool isYou}) async {
    final station = await showAppBottomSheet<Station>(
      context,
      builder: (_) => StationSearchSheet(
        title: isYou ? 'Where are you starting?' : 'Where is your friend?',
        isOrigin: true,
      ),
    );
    if (station == null || !mounted) return;
    setState(() {
      if (isYou) {
        _you = station;
      } else {
        _friend = station;
      }
      _candidates = null;
    });
    await _fetch();
  }

  Future<void> _fetch() async {
    final you = _you;
    final friend = _friend;
    if (you == null || friend == null) return;
    setState(() {
      _loading = true;
      _candidates = null;
    });
    final fetch = widget.fetchCandidates ??
        (String a, String b) => ref.read(journeyRepositoryProvider).meet(a, b);
    final candidates = await fetch(you.stopId, friend.stopId);
    if (!mounted) return;
    setState(() {
      _loading = false;
      _candidates = candidates;
    });
  }
}

/// One of the two "where are you starting" slots.
class _PickerRow extends StatelessWidget {
  const _PickerRow({
    required this.label,
    required this.icon,
    required this.station,
    required this.placeholder,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final Station? station;
  final String placeholder;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return GlassSurface(
      onTap: onTap,
      child: Row(
        children: [
          IconBadge(icon: icon, gradient: AppColors.heroGradientFor()),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: theme.textTheme.labelSmall),
                Text(
                  station?.name ?? placeholder,
                  style: theme.textTheme.titleLarge,
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded),
        ],
      ),
    );
  }
}

/// One ranked meeting station: name (tap through to its detail), and the two
/// honest travel times side by side in the fairness order the API returned.
class _CandidateCard extends StatelessWidget {
  const _CandidateCard({required this.candidate});

  final Map<String, dynamic> candidate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final stopId = '${candidate['stop_id']}';
    final name = '${candidate['name'] ?? stopId}';
    final minutesYou = (candidate['minutes_a'] as num?)?.round();
    final minutesThem = (candidate['minutes_b'] as num?)?.round();

    return GlassSurface(
      onTap: () => context.push('/station/$stopId'),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: theme.textTheme.titleMedium),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'You: ${minutesYou ?? '—'} min · '
                  'Them: ${minutesThem ?? '—'} min',
                  style: theme.textTheme.bodyMedium,
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded),
        ],
      ),
    );
  }
}
