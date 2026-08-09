// "Which coach were you in?" — asked once, at the only moment the rider
// actually knows the answer.
//
// This is the whole crowdsourcing surface, and it is deliberately small. The
// rider has just stepped off a train and is walking; they are not here to fill
// in a form. Two taps, or none at all.
//
// Design rules that are not negotiable:
//   * It appears ONLY with explicit contribution consent (see
//     LocalStore.contributionConsent, which is separate from analytics
//     consent for a reason the privacy policy spells out).
//   * It is skippable at every step, and skipping is not a failure state.
//   * It never blocks the end of a journey. The journey ends first; this is
//     an afterthought by construction.
//   * A failed submission is silent. A contribution is a gift, not a task.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_spacing.dart';
import '../../core/widgets/icon_badge.dart';
import '../../providers/core_providers.dart';

/// One exit a rider could have used, as the sheet needs it.
class ExitChoice {
  const ExitChoice({required this.id, required this.name});

  final int id;
  final String name;
}

/// Asks which coach the rider was in and which exit they used, then reports
/// it. Returns without submitting if they close or skip.
///
/// Shown only when [exits] is non-empty — with no gates to choose from there
/// is no question worth asking.
Future<void> showCoachExitPrompt(
  BuildContext context, {
  required WidgetRef ref,
  required String stopId,
  required String stationName,
  required List<ExitChoice> exits,
  required int coachCount,
  String? routeId,
  int? directionId,
}) async {
  if (exits.isEmpty || coachCount <= 0) return;

  final answer = await showModalBottomSheet<({int coach, int exitId})>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (sheetContext) => _CoachExitSheet(
      stationName: stationName,
      exits: exits,
      coachCount: coachCount,
    ),
  );
  if (answer == null) return;

  final result = await ref.read(contributionRepositoryProvider).reportCoachExit(
        stopId: stopId,
        exitId: answer.exitId,
        coachIndex: answer.coach,
        routeId: routeId,
        directionId: directionId,
      );
  if (!context.mounted || result == null) return;

  // Thank them for what actually happened, not for a generic "submitted".
  final message = switch (result) {
    _ when !result.wasNew => 'You had already told us that — thank you.',
    _ when result.confirmed =>
      "That's confirmed by enough riders now — it'll help everyone here.",
    _ => 'Thanks. A couple more riders and this becomes a tip for everyone.',
  };
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}

class _CoachExitSheet extends StatefulWidget {
  const _CoachExitSheet({
    required this.stationName,
    required this.exits,
    required this.coachCount,
  });

  final String stationName;
  final List<ExitChoice> exits;
  final int coachCount;

  @override
  State<_CoachExitSheet> createState() => _CoachExitSheetState();
}

class _CoachExitSheetState extends State<_CoachExitSheet> {
  int? _coach;
  int? _exitId;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final ready = _coach != null && _exitId != null;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.lg),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  const IconBadge(icon: Icons.volunteer_activism_rounded),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text('Help the next rider',
                        style: theme.textTheme.titleLarge),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                // Says plainly what it is for. Nobody taps twice for "improve
                // our service"; people do help a specific person.
                'Nobody has mapped which coach stops nearest which exit at '
                '${widget.stationName}. You just did it — which coach were you in?',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.lg),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  for (var i = 0; i < widget.coachCount; i++)
                    ChoiceChip(
                      label: Text('Coach ${i + 1}'),
                      selected: _coach == i,
                      onSelected: (_) => setState(() => _coach = i),
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Text('And which exit did you use?',
                  style: theme.textTheme.titleSmall),
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  for (final exit in widget.exits)
                    ChoiceChip(
                      label: Text(exit.name),
                      selected: _exitId == exit.id,
                      onSelected: (_) => setState(() => _exitId = exit.id),
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl),
              Row(
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Not now'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: ready
                        ? () => Navigator.of(context)
                            .pop((coach: _coach!, exitId: _exitId!))
                        : null,
                    child: const Text('Send'),
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
