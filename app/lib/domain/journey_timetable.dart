import 'models/journey.dart';

/// One simulated stop along a journey's estimated timetable.
class TimetableStop {
  const TimetableStop({
    required this.stopId,
    required this.name,
    required this.scheduledAt,
    required this.isInterchangeBoundary,
  });

  final String stopId;
  final String name;
  final DateTime scheduledAt;

  /// True when this stop is where the rider alights to change lines (an
  /// alight-point of a non-final ride leg) — the interchange-reminder signal.
  final bool isInterchangeBoundary;
}

/// The current simulated position within a [JourneyTimetable].
class TimetableSnapshot {
  const TimetableSnapshot({
    required this.current,
    required this.next,
    required this.remainingCount,
    required this.arrived,
    required this.etaToDestination,
  });

  final TimetableStop? current;
  final TimetableStop? next;
  final int remainingCount;
  final bool arrived;
  final Duration etaToDestination;
}

/// A simulated, GTFS-timetable-derived progress model for a journey.
///
/// This is the fallback progress source used whenever no live vehicle is
/// bound to the journey (see the `journeyProgressProvider` in the app layer,
/// which prefers a live WS-tracked train and falls back to this). Every
/// number here comes from real schedule-derived leg durations already
/// computed by the server-side planner — ride time is prorated evenly across
/// a leg's intermediate stops only because the plan does not carry per-stop
/// offsets, exactly the same kind of honest estimate as [estimateFare].
///
/// The simulation is anchored to [startedAt] (the moment the rider actually
/// tapped Start Journey), not the plan's original `departureAt` — so it
/// stays accurate even if boarding happens later than planned.
class JourneyTimetable {
  JourneyTimetable._(this.stops, this.startedAt, this.estimatedArrivalAt);

  /// Every real station passed after boarding, in order (excludes the
  /// origin, which is already "reached" at [startedAt]).
  final List<TimetableStop> stops;
  final DateTime startedAt;
  final DateTime estimatedArrivalAt;

  factory JourneyTimetable.fromPlan(JourneyPlan plan, {required DateTime startedAt}) {
    final stops = <TimetableStop>[];
    var cursor = startedAt;
    for (var legIndex = 0; legIndex < plan.legs.length; legIndex++) {
      final leg = plan.legs[legIndex];
      if (leg.isRide) {
        cursor = cursor.add(_secondsToDuration(leg.waitSeconds ?? 0));
        final stations = leg.stations ?? const [];
        final hops = stations.length - 1;
        if (hops <= 0) continue;
        final perHop = leg.seconds / hops;
        final isFinalLeg = legIndex == plan.legs.length - 1;
        for (var i = 1; i < stations.length; i++) {
          cursor = cursor.add(_secondsToDuration(perHop));
          stops.add(
            TimetableStop(
              stopId: stations[i].stopId,
              name: stations[i].name,
              scheduledAt: cursor,
              isInterchangeBoundary: !isFinalLeg && i == stations.length - 1,
            ),
          );
        }
      } else {
        cursor = cursor.add(_secondsToDuration(leg.seconds));
      }
    }
    return JourneyTimetable._(stops, startedAt, cursor);
  }

  /// The simulated position at [now]: last stop reached, next stop ahead,
  /// how many remain, and whether the destination has been reached.
  TimetableSnapshot at(DateTime now) {
    if (stops.isEmpty) {
      return TimetableSnapshot(
        current: null,
        next: null,
        remainingCount: 0,
        arrived: !now.isBefore(estimatedArrivalAt),
        etaToDestination: Duration.zero,
      );
    }
    TimetableStop? current;
    TimetableStop? next;
    var passed = 0;
    for (final stop in stops) {
      if (stop.scheduledAt.isAfter(now)) {
        next = stop;
        break;
      }
      current = stop;
      passed++;
    }
    final eta = next == null
        ? Duration.zero
        : estimatedArrivalAt.difference(now).isNegative
            ? Duration.zero
            : estimatedArrivalAt.difference(now);
    return TimetableSnapshot(
      current: current,
      next: next,
      remainingCount: stops.length - passed,
      arrived: next == null,
      etaToDestination: eta,
    );
  }
}

Duration _secondsToDuration(double seconds) =>
    Duration(milliseconds: (seconds * 1000).round());
