import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/line_chip.dart';
import '../../data/api_client.dart';
import '../../domain/fare.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../domain/network_map_geometry.dart';
import '../../providers/core_providers.dart';
import '../shared/station_search_sheet.dart';

/// A DMRC-style schematic network diagram: coloured lines through real
/// station geometry, interchanges marked, with a picked journey highlighted on
/// the diagram and broken down in a panel. Deliberately CustomPaint-drawn
/// (not MapLibre tiles) for the clean, offline, basemap-free "map view" look.
///
/// Everything is honest: line colours and geometry come straight from the
/// offline bundle, the route + timing come from the same journey planner the
/// rest of the app uses, and fare is the shared client-side *estimate*. DMRC's
/// own map shows a platform number per leg; that lives only in DMRC's private
/// API (which this app deliberately does not use), so it is omitted entirely
/// rather than faked.
class NetworkMapScreen extends ConsumerStatefulWidget {
  const NetworkMapScreen({super.key, this.initialOriginId, this.initialDestinationId});

  final String? initialOriginId;
  final String? initialDestinationId;

  @override
  ConsumerState<NetworkMapScreen> createState() => _NetworkMapScreenState();
}

class _NetworkMapScreenState extends ConsumerState<NetworkMapScreen> {
  final TransformationController _transform = TransformationController();

  Station? _origin;
  Station? _destination;
  JourneyPlan? _plan;
  bool _loading = false;
  String? _error;
  bool _resolvedInitialStations = false;

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bundle = ref.watch(offlineBundleProvider).valueOrNull;

    if (!_resolvedInitialStations && bundle != null) {
      _resolvedInitialStations = true;
      final byId = {for (final s in bundle.stations) s.stopId: s};
      _origin ??= byId[widget.initialOriginId];
      _destination ??= byId[widget.initialDestinationId];
      if (_origin != null && _destination != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _planJourney());
      }
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Network map')),
      body: bundle == null || bundle.stations.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                Positioned.fill(child: _buildDiagram(bundle)),
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: SafeArea(
                    bottom: false,
                    child: Padding(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      child: _EndpointBar(
                        origin: _origin,
                        destination: _destination,
                        onPickOrigin: () => _pick(isOrigin: true),
                        onPickDestination: () => _pick(isOrigin: false),
                        onSwap: _origin != null && _destination != null ? _swap : null,
                      ),
                    ),
                  ),
                ),
                if (_loading)
                  const Positioned(
                    top: 140,
                    left: 0,
                    right: 0,
                    child: Center(child: _LoadingPill()),
                  ),
                if (_error != null)
                  Positioned(
                    top: 140,
                    left: AppSpacing.lg,
                    right: AppSpacing.lg,
                    child: _ErrorPill(message: _error!),
                  ),
                if (_plan != null)
                  _JourneyPanel(
                    plan: _plan!,
                    onClear: _clearPlan,
                  ),
              ],
            ),
    );
  }

  Widget _buildDiagram(OfflineBundle bundle) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);
        final bounds = GeoBounds.fromStations(bundle.stations);
        if (bounds == null) return const SizedBox.shrink();
        final projection = SchematicProjection(bounds: bounds, size: size, padding: 44);

        final byId = {for (final s in bundle.stations) s.stopId: s};
        final points = {
          for (final s in bundle.stations) s.stopId: projection.projectStation(s),
        };
        final interchanges = detectInterchanges(bundle.routeStations);

        final colorByRoute = {for (final r in bundle.routes) r.routeId: r.color};
        final nameByRoute = {
          for (final r in bundle.routes) r.routeId: r.longName ?? r.shortName,
        };

        final lines = <_LinePolyline>[];
        for (final entry in bundle.routeStations.entries) {
          final sequence = routeDrawSequence(entry.value);
          if (sequence == null) continue;
          final polyline = [
            for (final stopId in sequence)
              if (points[stopId] != null) points[stopId]!,
          ];
          if (polyline.length < 2) continue;
          lines.add(_LinePolyline(
            color: routeColor(colorByRoute[entry.key], nameByRoute[entry.key]),
            points: polyline,
          ));
        }

        final overlay = _plan == null ? null : _buildOverlay(_plan!, byId, points);

        return InteractiveViewer(
          transformationController: _transform,
          minScale: 0.6,
          maxScale: 7,
          boundaryMargin: const EdgeInsets.all(600),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapUp: (details) => _onCanvasTap(details.localPosition, points),
            child: AnimatedBuilder(
              animation: _transform,
              builder: (context, _) {
                final viewScale = _transform.value.getMaxScaleOnAxis();
                return CustomPaint(
                  size: size,
                  painter: _SchematicPainter(
                    lines: lines,
                    stationPoints: points,
                    stationNames: {for (final s in bundle.stations) s.stopId: s.name},
                    interchangeIds: interchanges,
                    overlay: overlay,
                    labelScale: viewScale,
                    labelColor: scheme.onSurface,
                    haloColor: scheme.surface,
                    stationFill: scheme.surface,
                    stationBorder: scheme.onSurface.withValues(alpha: 0.55),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  _RouteOverlay _buildOverlay(
    JourneyPlan plan,
    Map<String, Station> byId,
    Map<String, Offset> points,
  ) {
    final stopIds = <String>{plan.origin.stopId, plan.destination.stopId};
    final highlightLines = <_LinePolyline>[];
    for (final leg in plan.legs) {
      final legStops = leg.stations ?? [leg.board, leg.alight];
      for (final stop in legStops) {
        stopIds.add(stop.stopId);
      }
      if (!leg.isRide) continue;
      final polyline = [
        for (final stop in legStops)
          if (points[stop.stopId] != null) points[stop.stopId]!,
      ];
      if (polyline.length < 2) continue;
      highlightLines.add(_LinePolyline(
        color: routeColor(leg.routeColor, leg.routeLongName),
        points: polyline,
      ));
    }
    return _RouteOverlay(
      stopIds: stopIds,
      boardStopId: plan.origin.stopId,
      alightStopId: plan.destination.stopId,
      interchangeStopIds: plan.interchangeStopIds.toSet(),
      lines: highlightLines,
    );
  }

  void _onCanvasTap(Offset local, Map<String, Offset> points) {
    String? nearest;
    var nearestDistance = double.infinity;
    points.forEach((stopId, point) {
      final distance = (point - local).distance;
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = stopId;
      }
    });
    // A generous but not sloppy hit radius, in canvas (unscaled) pixels.
    if (nearest == null || nearestDistance > 22) return;
    final station = ref.read(stationIndexProvider)[nearest];
    if (station == null) return;

    setState(() {
      if (_origin == null) {
        _origin = station;
      } else if (_destination == null && station.stopId != _origin!.stopId) {
        _destination = station;
      } else {
        // Both set (or the same station tapped twice) — start a new pick.
        _origin = station;
        _destination = null;
        _plan = null;
        _error = null;
      }
    });
    if (_origin != null && _destination != null) _planJourney();
  }

  Future<void> _pick({required bool isOrigin}) async {
    final station = await showAppBottomSheet<Station>(
      context,
      builder: (_) => StationSearchSheet(
        title: isOrigin ? 'Where from?' : 'Where to?',
        isOrigin: isOrigin,
      ),
    );
    if (station == null) return;
    setState(() {
      if (isOrigin) {
        _origin = station;
      } else {
        _destination = station;
      }
      _plan = null;
      _error = null;
    });
    if (_origin != null && _destination != null) await _planJourney();
  }

  void _swap() {
    setState(() {
      final origin = _origin;
      _origin = _destination;
      _destination = origin;
      _plan = null;
      _error = null;
    });
    _planJourney();
  }

  void _clearPlan() {
    setState(() {
      _plan = null;
      _origin = null;
      _destination = null;
      _error = null;
    });
  }

  Future<void> _planJourney() async {
    if (_origin == null || _destination == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final plan = await ref
          .read(journeyRepositoryProvider)
          .plan(_origin!.stopId, _destination!.stopId);
      if (!mounted) return;
      setState(() => _plan = plan);
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = isConnectivityError(error)
            ? "You're offline — we can't plan a trip without a connection right now."
            : "We couldn't find a route between these stations.";
      });
    } on Exception {
      if (!mounted) return;
      setState(() => _error = "We couldn't find a route between these stations.");
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
}

// -- overlay + polyline models ------------------------------------------------

/// One drawable line: a colour and its projected canvas points.
class _LinePolyline {
  const _LinePolyline({required this.color, required this.points});

  final Color color;
  final List<Offset> points;
}

/// The highlighted-route state layered over the base diagram.
class _RouteOverlay {
  const _RouteOverlay({
    required this.stopIds,
    required this.boardStopId,
    required this.alightStopId,
    required this.interchangeStopIds,
    required this.lines,
  });

  final Set<String> stopIds;
  final String boardStopId;
  final String alightStopId;
  final Set<String> interchangeStopIds;
  final List<_LinePolyline> lines;
}

// -- painter ------------------------------------------------------------------

class _SchematicPainter extends CustomPainter {
  _SchematicPainter({
    required this.lines,
    required this.stationPoints,
    required this.stationNames,
    required this.interchangeIds,
    required this.overlay,
    required this.labelScale,
    required this.labelColor,
    required this.haloColor,
    required this.stationFill,
    required this.stationBorder,
  });

  final List<_LinePolyline> lines;
  final Map<String, Offset> stationPoints;
  final Map<String, String> stationNames;
  final Set<String> interchangeIds;
  final _RouteOverlay? overlay;
  final double labelScale;
  final Color labelColor;
  final Color haloColor;
  final Color stationFill;
  final Color stationBorder;

  static const double _dimLine = 0.16;
  static const double _dimDot = 0.20;

  @override
  void paint(Canvas canvas, Size size) {
    final hasOverlay = overlay != null;

    // 1. Base line geometry. When a route is highlighted, everything else
    //    dims — exactly how DMRC greys out the rest of the network.
    for (final line in lines) {
      final opacity = hasOverlay ? _dimLine : 0.9;
      _drawPolyline(canvas, line.points, line.color.withValues(alpha: opacity), 4.5);
    }

    // 2. Highlighted route legs, drawn bold on top.
    if (hasOverlay) {
      for (final line in overlay!.lines) {
        _drawPolyline(canvas, line.points, line.color, 7);
      }
    }

    // 3. Station dots.
    final dotFill = Paint()..style = PaintingStyle.fill;
    final dotStroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    stationPoints.forEach((stopId, point) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      final isInterchange = interchangeIds.contains(stopId);
      final alpha = onRoute ? 1.0 : _dimDot;

      if (isInterchange) {
        // A white-filled ring — the universal "you can change lines here" mark.
        dotFill.color = stationFill.withValues(alpha: alpha);
        dotStroke.color = stationBorder.withValues(alpha: alpha);
        canvas.drawCircle(point, 6, dotFill);
        canvas.drawCircle(point, 6, dotStroke);
      } else {
        dotFill.color = stationFill.withValues(alpha: alpha);
        dotStroke.color = stationBorder.withValues(alpha: alpha);
        canvas.drawCircle(point, 3.5, dotFill);
        canvas.drawCircle(point, 3.5, dotStroke);
      }
    });

    // 4. Board / alight endpoints of the highlighted route, marked distinctly.
    if (hasOverlay) {
      _drawEndpoint(canvas, overlay!.boardStopId, AppColors.success, 'A');
      _drawEndpoint(canvas, overlay!.alightStopId, AppColors.danger, 'B');
    }

    // 5. Labels. Interchanges (and route endpoints) are always named; ordinary
    //    stations only appear once zoomed in, so a low-zoom view stays clean.
    stationPoints.forEach((stopId, point) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      final isInterchange = interchangeIds.contains(stopId);
      final isEndpoint = hasOverlay &&
          (stopId == overlay!.boardStopId || stopId == overlay!.alightStopId);
      final zoomedEnough = labelScale >= 2.3;
      final routeZoom = hasOverlay && onRoute && labelScale >= 1.4;
      final show = isEndpoint || isInterchange || zoomedEnough || routeZoom;
      if (!show) return;
      if (hasOverlay && !onRoute && !zoomedEnough) return;
      _drawLabel(canvas, point, stationNames[stopId] ?? '', onRoute ? 1.0 : 0.5);
    });
  }

  void _drawPolyline(Canvas canvas, List<Offset> points, Color color, double width) {
    if (points.length < 2) return;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (var i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(path, paint);
  }

  void _drawEndpoint(Canvas canvas, String stopId, Color color, String letter) {
    final point = stationPoints[stopId];
    if (point == null) return;
    canvas.drawCircle(point, 9, Paint()..color = Colors.white);
    canvas.drawCircle(point, 8, Paint()..color = color);
    final tp = TextPainter(
      text: TextSpan(
        text: letter,
        style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, point - Offset(tp.width / 2, tp.height / 2));
  }

  void _drawLabel(Canvas canvas, Offset point, String text, double opacity) {
    if (text.isEmpty) return;
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: labelColor.withValues(alpha: opacity),
          fontSize: 10,
          fontWeight: FontWeight.w600,
          shadows: [
            Shadow(color: haloColor, blurRadius: 2),
            Shadow(color: haloColor, blurRadius: 2),
          ],
        ),
      ),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )..layout(maxWidth: 120);
    tp.paint(canvas, point + const Offset(8, -6));
  }

  @override
  bool shouldRepaint(_SchematicPainter old) {
    return old.overlay != overlay ||
        old.labelColor != labelColor ||
        // Only repaint on a zoom change that could cross a label threshold.
        _labelBucket(old.labelScale) != _labelBucket(labelScale) ||
        old.lines != lines;
  }

  int _labelBucket(double scale) {
    if (scale >= 2.3) return 2;
    if (scale >= 1.4) return 1;
    return 0;
  }
}

// -- top endpoint bar ---------------------------------------------------------

class _EndpointBar extends StatelessWidget {
  const _EndpointBar({
    required this.origin,
    required this.destination,
    required this.onPickOrigin,
    required this.onPickDestination,
    required this.onSwap,
  });

  final Station? origin;
  final Station? destination;
  final VoidCallback onPickOrigin;
  final VoidCallback onPickDestination;
  final VoidCallback? onSwap;

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      blur: true,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      child: Row(
        children: [
          Expanded(
            child: Column(
              children: [
                _EndpointField(
                  icon: Icons.trip_origin_rounded,
                  label: 'From',
                  station: origin,
                  onTap: onPickOrigin,
                ),
                const Divider(height: 1),
                _EndpointField(
                  icon: Icons.flag_rounded,
                  label: 'To',
                  station: destination,
                  onTap: onPickDestination,
                ),
              ],
            ),
          ),
          IconPillButton(
            icon: Icons.swap_vert_rounded,
            tooltip: 'Swap From and To',
            onPressed: onSwap,
          ),
        ],
      ),
    );
  }
}

class _EndpointField extends StatelessWidget {
  const _EndpointField({
    required this.icon,
    required this.label,
    required this.station,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Station? station;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: AppRadius.mdR,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.sm),
        child: Row(
          children: [
            Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Text(
                station?.name ?? 'Choose $label station',
                style: station == null
                    ? theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)
                    : theme.textTheme.titleSmall,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Icon(Icons.chevron_right_rounded, size: 18, color: theme.colorScheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}

class _LoadingPill extends StatelessWidget {
  const _LoadingPill();

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      blur: true,
      borderRadius: AppRadius.pillR,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
          const SizedBox(width: AppSpacing.md),
          Text('Finding the best route…', style: Theme.of(context).textTheme.labelMedium),
        ],
      ),
    );
  }
}

class _ErrorPill extends StatelessWidget {
  const _ErrorPill({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      blur: true,
      color: AppColors.danger.withValues(alpha: 0.14),
      borderRadius: AppRadius.lgR,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Text(
        message,
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ),
    );
  }
}

// -- journey result panel -----------------------------------------------------

/// The DMRC-style breakdown, in a draggable bottom panel: totals up top, then
/// each ride leg (line, direction, board -> alight, time, expandable station
/// list) with interchange markers between them.
class _JourneyPanel extends StatelessWidget {
  const _JourneyPanel({required this.plan, required this.onClear});

  final JourneyPlan plan;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DraggableScrollableSheet(
      initialChildSize: 0.42,
      minChildSize: 0.16,
      maxChildSize: 0.9,
      snap: true,
      snapSizes: const [0.16, 0.42, 0.9],
      builder: (context, scrollController) {
        return DecoratedBox(
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(AppRadius.xxl)),
            border: Border(top: BorderSide(color: scheme.outlineVariant)),
          ),
          child: ClipRRect(
            borderRadius: const BorderRadius.vertical(top: Radius.circular(AppRadius.xxl)),
            child: ListView(
              controller: scrollController,
              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.xxl),
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: AppSpacing.md),
                    decoration: BoxDecoration(
                      color: scheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                _PanelHeader(plan: plan, onClear: onClear),
                const SizedBox(height: AppSpacing.lg),
                ..._buildLegs(context),
              ],
            ),
          ),
        );
      },
    );
  }

  List<Widget> _buildLegs(BuildContext context) {
    final widgets = <Widget>[];
    JourneyLeg? previousRide;
    for (final leg in plan.legs) {
      if (leg.isRide) {
        // A change is a boarding that follows an earlier ride — never the very
        // first boarding, whose wait is just the initial platform wait.
        if (previousRide != null) {
          widgets.add(_InterchangeRow(atStation: leg.board.name, waitSeconds: leg.waitSeconds));
        }
        widgets.add(_LegCard(leg: leg));
        previousRide = leg;
      } else {
        widgets.add(_WalkRow(leg: leg));
      }
      widgets.add(const SizedBox(height: AppSpacing.sm));
    }
    return widgets;
  }
}

class _PanelHeader extends StatelessWidget {
  const _PanelHeader({required this.plan, required this.onClear});

  final JourneyPlan plan;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fare = estimateFare(plan);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('ESTIMATED TRAVEL TIME', style: theme.textTheme.labelSmall),
                  Text(minutesLabel(plan.expectedTravelSeconds),
                      style: theme.textTheme.displaySmall),
                ],
              ),
            ),
            IconPillButton(
              icon: Icons.close_rounded,
              tooltip: 'Clear route',
              onPressed: onClear,
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            _Stat(label: 'Arrive', value: clockTime(plan.expectedArrivalAt)),
            _Stat(label: 'Fare (est.)', value: '₹${fare.rupees}'),
            _Stat(label: 'Stations', value: '${plan.remainingStations.length}'),
            _Stat(label: 'Changes', value: '${plan.interchangeCount}'),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          'Times and fare are estimates from the published schedule, not a live gate charge.',
          style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainer,
        borderRadius: AppRadius.mdR,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label.toUpperCase(), style: theme.textTheme.labelSmall),
          Text(value, style: theme.textTheme.titleMedium),
        ],
      ),
    );
  }
}

/// One ride leg, DMRC-style: the line, its direction ("towards <terminus>"),
/// board -> alight, the leg's time, and an expandable full station list.
class _LegCard extends StatefulWidget {
  const _LegCard({required this.leg});

  final JourneyLeg leg;

  @override
  State<_LegCard> createState() => _LegCardState();
}

class _LegCardState extends State<_LegCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final leg = widget.leg;
    final stations = leg.stations ?? const <JourneyStop>[];
    // Intermediate stops (everything between board and alight).
    final between = stations.length > 2 ? stations.sublist(1, stations.length - 1) : const <JourneyStop>[];

    return GlassSurface(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LineChip(label: cleanLineName(leg.routeLongName), colorHex: leg.routeColor),
          if (leg.platformHint != null && leg.platformHint!.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                Icon(Icons.navigation_rounded, size: 14, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Text(_towardsLabel(leg.platformHint!),
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ),
              ],
            ),
          ],
          const SizedBox(height: AppSpacing.md),
          _StationRow(icon: Icons.trip_origin_rounded, label: leg.board.name, bold: true),
          const _StationRow(icon: Icons.south_rounded, label: '', muted: true),
          _StationRow(icon: Icons.place_rounded, label: leg.alight.name, bold: true),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Text(
                '${stopsLabel((stations.isEmpty ? 1 : stations.length) - 1)} · ${minutesLabel(leg.seconds)}',
                style: theme.textTheme.bodySmall,
              ),
              const Spacer(),
              if (between.isNotEmpty)
                TextButton(
                  onPressed: () => setState(() => _expanded = !_expanded),
                  child: Text(_expanded ? 'Hide stations' : 'Show ${between.length} stations'),
                ),
            ],
          ),
          if (_expanded && between.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final stop in between)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        children: [
                          Icon(Icons.circle, size: 6, color: theme.colorScheme.outline),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(child: Text(stop.name, style: theme.textTheme.bodyMedium)),
                        ],
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _StationRow extends StatelessWidget {
  const _StationRow({required this.icon, required this.label, this.bold = false, this.muted = false});

  final IconData icon;
  final String label;
  final bool bold;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: 16, color: muted ? theme.colorScheme.outline : theme.colorScheme.onSurface),
          const SizedBox(width: AppSpacing.md),
          if (label.isNotEmpty)
            Expanded(
              child: Text(
                label,
                style: bold ? theme.textTheme.titleSmall : theme.textTheme.bodyMedium,
              ),
            ),
        ],
      ),
    );
  }
}

class _InterchangeRow extends StatelessWidget {
  const _InterchangeRow({required this.atStation, this.waitSeconds});

  final String atStation;
  final double? waitSeconds;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final wait = (waitSeconds ?? 0) > 0 ? ' · wait about ${minutesLabel(waitSeconds)}' : '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(Icons.transfer_within_a_station_rounded, size: 18, color: theme.colorScheme.primary),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text('Change at $atStation$wait',
                style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.primary)),
          ),
        ],
      ),
    );
  }
}

class _WalkRow extends StatelessWidget {
  const _WalkRow({required this.leg});

  final JourneyLeg leg;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(Icons.directions_walk_rounded, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              'Walk to ${leg.alight.name} · ${distanceLabel(leg.distanceM)} · about ${minutesLabel(leg.seconds)}',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

/// The GTFS headsign (leg.platformHint) is usually a bare terminus name
/// ("Rithala"), which we prefix with "Towards". But the backend's fallback
/// headsign is already "Towards <terminus>" when a trip has no trip_headsign,
/// so guard against a doubled prefix.
String _towardsLabel(String headsign) {
  final trimmed = headsign.trim();
  return trimmed.toLowerCase().startsWith('towards')
      ? trimmed
      : 'Towards $trimmed';
}
