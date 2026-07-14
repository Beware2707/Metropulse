import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
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
import '../tickets/tickets_screen.dart' show ExternalUrlLauncher;

/// How the screen fetches ranked park-and-ride candidates. Injectable so
/// tests can feed fake data without a live backend; defaults to
/// `JourneyRepository.parkAndRide`.
typedef ParkAndRideFetcher = Future<List<Map<String, dynamic>>> Function(
    String destinationStopId, double lat, double lon);

/// How the screen finds where the user is starting from. Injectable for
/// tests; defaults to geolocator (last-known fix first, then a low-accuracy
/// current fix). Returning null means "couldn't locate" and triggers the
/// manual near-which-station fallback.
typedef PositionResolver = Future<({double lat, double lon})?> Function();

/// Park & ride: drive to a metro station that actually has DMRC-published
/// parking, then ride the rest of the way. Candidates come ranked by the
/// backend (straight-line driving proximity + metro time to the
/// destination); this screen is honest that distances are straight-line and
/// capacities are published numbers, not live availability.
class ParkAndRideScreen extends ConsumerStatefulWidget {
  const ParkAndRideScreen({
    super.key,
    this.initialDestinationId,
    this.fetchCandidates,
    this.resolvePosition,
    this.launchExternal,
  });

  final String? initialDestinationId;

  /// Test seam — see [ParkAndRideFetcher]. Null means the real repository.
  final ParkAndRideFetcher? fetchCandidates;

  /// Test seam — see [PositionResolver]. Null means the real geolocator.
  final PositionResolver? resolvePosition;

  /// Test seam for the tap-to-call hand-off. Null means the real launcher.
  final ExternalUrlLauncher? launchExternal;

  @override
  ConsumerState<ParkAndRideScreen> createState() => _ParkAndRideScreenState();
}

class _ParkAndRideScreenState extends ConsumerState<ParkAndRideScreen> {
  Station? _destination;
  ({double lat, double lon})? _position;
  String? _positionLabel;
  List<Map<String, dynamic>>? _candidates;
  bool _loading = false;
  bool _needsManualLocation = false;
  bool _resolvedInitialDestination = false;

  @override
  Widget build(BuildContext context) {
    if (!_resolvedInitialDestination && widget.initialDestinationId != null) {
      final stations = ref.watch(stationIndexProvider);
      if (stations.isNotEmpty) {
        _resolvedInitialDestination = true;
        _destination ??= stations[widget.initialDestinationId];
        if (_destination != null) {
          WidgetsBinding.instance.addPostFrameCallback((_) => _locateAndFetch());
        }
      }
    }

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
                      icon: Icons.arrow_back_rounded, onPressed: () => context.pop()),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text('Park & ride', style: theme.textTheme.displaySmall),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Text(
                'Drive to a station with parking, leave the vehicle there, and '
                'ride the metro the rest of the way.',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: AppSpacing.xl),
              GlassSurface(
                onTap: _pickDestination,
                child: Row(
                  children: [
                    IconBadge(
                        icon: Icons.flag_rounded,
                        gradient: AppColors.heroGradientFor()),
                    const SizedBox(width: AppSpacing.lg),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('DESTINATION', style: theme.textTheme.labelSmall),
                          Text(
                            _destination?.name ?? 'Choose destination station',
                            style: theme.textTheme.titleLarge,
                          ),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right_rounded),
                  ],
                ),
              ),
              if (_needsManualLocation) ...[
                const SizedBox(height: AppSpacing.lg),
                GlassSurface(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("We couldn't get your location.",
                          style: theme.textTheme.titleMedium),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        "Pick the station nearest to where you're starting "
                        "and we'll measure from there instead.",
                        style: theme.textTheme.bodyMedium,
                      ),
                      const SizedBox(height: AppSpacing.lg),
                      GhostButton(
                        label: 'Near which station?',
                        icon: Icons.near_me_rounded,
                        expand: true,
                        onPressed: _pickNearStation,
                      ),
                    ],
                  ),
                ),
              ],
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
                      icon: Icons.local_parking_rounded,
                      message:
                          "We couldn't find a station with parking for this trip.",
                    ),
                  )
                else ...[
                  const SectionHeader(title: 'Where to park'),
                  if (_positionLabel != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.md),
                      child: Text(
                        'Measured from $_positionLabel.',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: theme.colorScheme.outline),
                      ),
                    ),
                  for (final candidate in candidates)
                    Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                      child: _CandidateCard(candidate: candidate, onCall: _call),
                    ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    'Parking numbers are DMRC-published capacity, not live availability.',
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

  Future<void> _pickDestination() async {
    final station = await showAppBottomSheet<Station>(
      context,
      builder: (_) => const StationSearchSheet(
          title: 'Where are you headed?', isOrigin: false),
    );
    if (station == null || !mounted) return;
    setState(() {
      _destination = station;
      _candidates = null;
    });
    await _locateAndFetch();
  }

  Future<void> _pickNearStation() async {
    final station = await showAppBottomSheet<Station>(
      context,
      builder: (_) =>
          const StationSearchSheet(title: 'Near which station?', isOrigin: true),
    );
    if (station == null || !mounted) return;
    setState(() {
      _position = (lat: station.lat, lon: station.lon);
      _positionLabel = 'near ${station.name}';
      _needsManualLocation = false;
    });
    await _fetch();
  }

  /// Location first (device fix, else the manual near-station fallback),
  /// then the ranked candidates.
  Future<void> _locateAndFetch() async {
    if (_destination == null) return;
    if (_position == null) {
      setState(() {
        _loading = true;
        _needsManualLocation = false;
      });
      final position = await (widget.resolvePosition ?? _devicePosition)();
      if (!mounted) return;
      if (position == null) {
        setState(() {
          _loading = false;
          _needsManualLocation = true;
        });
        return;
      }
      _position = position;
      _positionLabel = 'your location';
    }
    await _fetch();
  }

  Future<void> _fetch() async {
    final destination = _destination;
    final position = _position;
    if (destination == null || position == null) return;
    setState(() {
      _loading = true;
      _candidates = null;
    });
    final fetch = widget.fetchCandidates ??
        (String dest, double lat, double lon) => ref
            .read(journeyRepositoryProvider)
            .parkAndRide(destination: dest, lat: lat, lon: lon);
    final candidates =
        await fetch(destination.stopId, position.lat, position.lon);
    if (!mounted) return;
    setState(() {
      _loading = false;
      _candidates = candidates;
    });
  }

  /// The graceful-degradation location ladder: services on → permission →
  /// last-known fix (instant) → one low-accuracy current fix. Any failure
  /// returns null, which hands over to the manual near-station picker
  /// rather than blocking the feature on GPS.
  Future<({double lat, double lon})?> _devicePosition() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) return null;
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }
      final last = await Geolocator.getLastKnownPosition();
      if (last != null) return (lat: last.latitude, lon: last.longitude);
      final current = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.low,
        timeLimit: const Duration(seconds: 10),
      );
      return (lat: current.latitude, lon: current.longitude);
    } on Exception {
      return null;
    }
  }

  Future<void> _call(String contact) async {
    final launch = widget.launchExternal ?? (uri) => launchUrl(uri);
    final ok = await launch(Uri(scheme: 'tel', path: contact));
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Couldn't start a call on this device.")),
      );
    }
  }
}

/// One ranked station card: name, honest straight-line distance, published
/// capacity chips, the metro continuation when the planner found one, the
/// operator, and tap-to-call when DMRC lists a contact.
class _CandidateCard extends StatelessWidget {
  const _CandidateCard({required this.candidate, required this.onCall});

  final Map<String, dynamic> candidate;
  final void Function(String contact) onCall;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final name = '${candidate['name'] ?? candidate['stop_id']}';
    final distanceKm = (candidate['distance_km'] as num?)?.toDouble();
    final car = candidate['car_capacity'] as int?;
    final motorcycle = candidate['motorcycle_capacity'] as int?;
    final cycle = candidate['cycle_capacity'] as int?;
    final operatorName = candidate['operator'] as String?;
    final contact = candidate['contact'] as String?;
    final metroMinutes = candidate['metro_minutes'] as int?;
    final metroSummary = candidate['metro_summary'] as String?;

    return GlassSurface(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: theme.textTheme.titleMedium),
                if (distanceKm != null)
                  Text(
                    '${distanceKm.toStringAsFixed(1)} km away (straight line)',
                    style: theme.textTheme.bodySmall,
                  ),
                const SizedBox(height: AppSpacing.sm),
                Wrap(
                  spacing: AppSpacing.sm,
                  runSpacing: AppSpacing.sm,
                  children: [
                    if (car != null && car > 0)
                      _CapacityChip(
                          icon: Icons.directions_car_rounded,
                          count: car,
                          label: 'car spots'),
                    if (motorcycle != null && motorcycle > 0)
                      _CapacityChip(
                          icon: Icons.two_wheeler_rounded,
                          count: motorcycle,
                          label: 'motorcycle spots'),
                    if (cycle != null && cycle > 0)
                      _CapacityChip(
                          icon: Icons.pedal_bike_rounded,
                          count: cycle,
                          label: 'cycle spots'),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                if (metroMinutes != null)
                  Text(
                    '~$metroMinutes min by metro'
                    '${metroSummary != null ? ' — $metroSummary' : ''}',
                    style: theme.textTheme.bodyMedium,
                  )
                else
                  Text(
                    'No metro route found from here to your destination.',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.outline),
                  ),
                if (operatorName != null && operatorName.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: Text('Operated by $operatorName',
                        style: theme.textTheme.bodySmall),
                  ),
              ],
            ),
          ),
          if (contact != null && contact.isNotEmpty) ...[
            const SizedBox(width: AppSpacing.md),
            IconPillButton(
              icon: Icons.call_rounded,
              tooltip: 'Call the parking operator',
              onPressed: () => onCall(contact),
            ),
          ],
        ],
      ),
    );
  }
}

/// A small icon + count pill for one published capacity figure.
class _CapacityChip extends StatelessWidget {
  const _CapacityChip(
      {required this.icon, required this.count, required this.label});

  final IconData icon;
  final int count;
  final String label;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: '$count $label',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: scheme.primary.withValues(alpha: 0.1),
          borderRadius: AppRadius.pillR,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: scheme.primary),
            const SizedBox(width: 6),
            Text(
              '$count',
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                  color: scheme.onSurface),
            ),
          ],
        ),
      ),
    );
  }
}
