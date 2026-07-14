import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/section_header.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart' show activeAlertsProvider, alertsRepositoryProvider;
import '../shared/station_search_sheet.dart';
import 'disruptions_providers.dart';

/// How a report is submitted — injectable so the screen can be tested without
/// a network. Mirrors [AlertsRepository.postRiderReport]; returns true when
/// the backend accepted it.
typedef PostReportFn = Future<bool> Function({
  String? stopId,
  String? routeId,
  required String message,
  String? category,
});

/// How the optional station picker is opened — injectable so tests don't
/// depend on the offline bundle. Returns the chosen station, or null if the
/// commuter dismisses the picker.
typedef PickStationFn = Future<Station?> Function(BuildContext context);

/// The four report categories the fixed API accepts, in the order shown.
const _categories = <(String, String, IconData)>[
  ('delay', 'Delay', Icons.schedule_rounded),
  ('crowding', 'Crowding', Icons.groups_rounded),
  ('closure', 'Closure', Icons.do_not_disturb_on_rounded),
  ('other', 'Other', Icons.more_horiz_rounded),
];

/// The Disruption Board: two clearly-separated sources of "is something
/// wrong right now" — authoritative operator alerts from DMRC (via
/// [activeAlertsProvider]) and community-sourced rider reports (via
/// [riderReportsProvider], always labelled unverified). Riders can add their
/// own report; MetroPulse never presents a commuter report as an operator
/// alert, and the banner says so up top.
class DisruptionsScreen extends ConsumerWidget {
  const DisruptionsScreen({super.key, this.postReport, this.pickStation});

  /// Test seam — see [PostReportFn]. Null means the real repository.
  final PostReportFn? postReport;

  /// Test seam — see [PickStationFn]. Null means the real station picker.
  final PickStationFn? pickStation;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final alerts = ref.watch(activeAlertsProvider).valueOrNull ?? const [];
    final reports = ref.watch(riderReportsProvider).valueOrNull ?? const [];
    final stations = ref.watch(stationIndexProvider);

    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: () async {
              ref
                ..invalidate(activeAlertsProvider)
                ..invalidate(riderReportsProvider);
              await Future.wait([
                ref.read(activeAlertsProvider.future),
                ref.read(riderReportsProvider.future),
              ]);
            },
            child: ListView(
              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 48),
              children: [
                Row(
                  children: [
                    IconPillButton(icon: Icons.arrow_back_rounded, onPressed: () => context.pop()),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(child: Text('Disruptions', style: theme.textTheme.displaySmall)),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),

                // Honesty banner: the whole reason the two sections are kept
                // apart — operator alerts are authoritative, rider reports are
                // not, and the board says so before either list.
                GlassSurface(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Row(
                    children: [
                      const IconBadge(icon: Icons.verified_user_outlined),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Text(
                          'Commuter reports are unverified — official alerts come from DMRC.',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                    ],
                  ),
                ),

                // -- Official alerts (authoritative) --------------------------
                const SectionHeader(title: 'Official alerts'),
                if (alerts.isEmpty)
                  const _QuietSection(
                    icon: Icons.check_circle_outline_rounded,
                    message: 'No service alerts from DMRC right now.',
                  )
                else
                  MomentList(children: [for (final alert in alerts) _OfficialAlertRow(alert: alert)]),

                // -- Reported by commuters (community-sourced) ----------------
                const SectionHeader(title: 'Reported by commuters'),
                if (reports.isEmpty)
                  const _QuietSection(
                    icon: Icons.forum_outlined,
                    message: 'No commuter reports in the last couple of hours.',
                  )
                else
                  MomentList(children: [
                    for (final report in reports)
                      _RiderReportRow(report: report, stationName: _stationLabel(report, stations)),
                  ]),

                const SizedBox(height: AppSpacing.xxl),
                PrimaryButton(
                  label: 'Report a delay',
                  icon: Icons.add_comment_rounded,
                  expand: true,
                  onPressed: () => _openReportForm(context, ref),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// The station/line label for a rider report: prefer a known station name,
  /// fall back to the raw stop id, then the route id, then "Network-wide" when
  /// the report is pinned to neither.
  static String? _stationLabel(Map<String, dynamic> report, Map<String, Station> stations) {
    final stopId = report['stop_id'] as String?;
    if (stopId != null) return stations[stopId]?.name ?? stopId;
    final routeId = report['route_id'] as String?;
    if (routeId != null) return routeId;
    return null;
  }

  Future<void> _openReportForm(BuildContext context, WidgetRef ref) async {
    final effectivePost = postReport ??
        ({String? stopId, String? routeId, required String message, String? category}) =>
            ref.read(alertsRepositoryProvider).postRiderReport(
                  stopId: stopId,
                  routeId: routeId,
                  message: message,
                  category: category,
                );
    final effectivePick = pickStation ??
        (ctx) => showAppBottomSheet<Station>(
              ctx,
              builder: (_) => const StationSearchSheet(title: 'Which station?', isOrigin: true),
            );

    final posted = await showAppBottomSheet<bool>(
      context,
      builder: (sheetContext) => _ReportForm(postReport: effectivePost, pickStation: effectivePick),
    );
    if (posted != true || !context.mounted) return;
    ref.invalidate(riderReportsProvider);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Thanks — your report is now visible to other commuters.')),
    );
  }
}

/// A section that has nothing to report right now — a calm, honest line
/// rather than a hidden section, so the commuter knows the board is working
/// and simply quiet.
class _QuietSection extends StatelessWidget {
  const _QuietSection({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: EmptyState(icon: icon, message: message, compact: true),
    );
  }
}

class _OfficialAlertRow extends StatelessWidget {
  const _OfficialAlertRow({required this.alert});

  final Map<String, dynamic> alert;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final severity = '${alert['severity']}';
    return MomentRow(
      leading: IconBadge(
        icon: switch (severity) {
          'severe' => Icons.error_rounded,
          'warning' => Icons.warning_rounded,
          _ => Icons.info_rounded,
        },
        color: switch (severity) {
          'severe' => AppColors.danger.withValues(alpha: 0.16),
          'warning' => AppColors.warning.withValues(alpha: 0.16),
          _ => null,
        },
        foreground: switch (severity) {
          'severe' => AppColors.danger,
          'warning' => AppColors.warning,
          _ => null,
        },
      ),
      title: Text('${alert['title']}', style: theme.textTheme.titleMedium),
      subtitle: Text(
        '${alert['description']}',
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
        style: theme.textTheme.bodyMedium,
      ),
    );
  }
}

class _RiderReportRow extends StatelessWidget {
  const _RiderReportRow({required this.report, required this.stationName});

  final Map<String, dynamic> report;
  final String? stationName;

  static (String, IconData) _categoryFor(String? category) => switch (category) {
        'delay' => ('Delay', Icons.schedule_rounded),
        'crowding' => ('Crowding', Icons.groups_rounded),
        'closure' => ('Closure', Icons.do_not_disturb_on_rounded),
        _ => ('Report', Icons.forum_rounded),
      };

  static String _reportedAgo(Object? iso) {
    final time = DateTime.tryParse('$iso');
    if (time == null) return 'just now';
    final mins = DateTime.now().difference(time.toLocal()).inMinutes;
    if (mins <= 0) return 'just now';
    if (mins < 60) return 'reported $mins min ago';
    final hrs = mins ~/ 60;
    return 'reported $hrs hr ago';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (categoryLabel, icon) = _categoryFor(report['category'] as String?);
    final count = (report['count'] as num?)?.toInt() ?? 1;
    final where = stationName == null ? categoryLabel : '$categoryLabel · $stationName';

    // The corroboration line is the honest headline fact — how many people
    // said it — and, when it's a lone report, states plainly it's a single
    // unconfirmed commuter rather than dressing one voice up as consensus.
    final corroboration = count > 1 ? '$count commuters reported this' : 'reported by one commuter, unconfirmed';

    return MomentRow(
      leading: IconBadge(icon: icon, color: AppColors.warning.withValues(alpha: 0.16), foreground: AppColors.warning),
      title: Text('${report['message']}', style: theme.textTheme.bodyLarge),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 2),
          Text(
            '$where · ${_reportedAgo(report['reported_at'])}',
            style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          const SizedBox(height: 4),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.warning.withValues(alpha: 0.15),
                  borderRadius: AppRadius.pillR,
                ),
                child: Text(
                  corroboration,
                  style: theme.textTheme.labelSmall?.copyWith(color: AppColors.warning),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// The report sheet: an optional station, a category chip row, and a message
/// (max 280, matching the API's bound). Submits via the injected
/// [postReport] and pops true only when the backend actually accepted it.
class _ReportForm extends StatefulWidget {
  const _ReportForm({required this.postReport, required this.pickStation});

  final PostReportFn postReport;
  final PickStationFn pickStation;

  @override
  State<_ReportForm> createState() => _ReportFormState();
}

class _ReportFormState extends State<_ReportForm> {
  final _controller = TextEditingController();
  String _category = 'delay';
  Station? _station;
  bool _submitting = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _pickStation() async {
    final station = await widget.pickStation(context);
    if (station != null && mounted) setState(() => _station = station);
  }

  Future<void> _submit() async {
    final message = _controller.text.trim();
    if (message.isEmpty || _submitting) return;
    setState(() => _submitting = true);
    final ok = await widget.postReport(
      stopId: _station?.stopId,
      message: message,
      category: _category,
    );
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      setState(() => _submitting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Couldn't send that — check your connection and try again.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Report a delay', style: theme.textTheme.titleLarge),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Seen something other commuters should know? Your report shows up as unverified — DMRC alerts stay separate.',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpacing.lg),

            // Category chips.
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                for (final (value, label, icon) in _categories)
                  ChoiceChip(
                    avatar: Icon(icon, size: 18, color: _category == value ? Colors.white : theme.colorScheme.onSurface),
                    label: Text(label),
                    selected: _category == value,
                    onSelected: (_) => setState(() => _category = value),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),

            // Optional station.
            MomentRow(
              leading: const IconBadge(icon: Icons.place_outlined),
              title: Text(_station?.name ?? 'Add a station (optional)', style: theme.textTheme.bodyLarge),
              subtitle: _station == null
                  ? null
                  : Text('Tap to change', style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              onTap: _pickStation,
            ),
            const SizedBox(height: AppSpacing.md),

            // Message.
            TextField(
              controller: _controller,
              autofocus: true,
              maxLength: 280,
              maxLines: 3,
              minLines: 2,
              textInputAction: TextInputAction.newline,
              decoration: const InputDecoration(
                hintText: 'What are you seeing? e.g. "Trains held at platform for 10+ min"',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: AppSpacing.md),
            PrimaryButton(
              label: _submitting ? 'Sending…' : 'Post report',
              icon: Icons.send_rounded,
              expand: true,
              onPressed: _controller.text.trim().isEmpty || _submitting ? null : _submit,
            ),
          ],
        ),
      ),
    );
  }
}
