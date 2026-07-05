import 'journey_timetable.dart';
import 'models/eta.dart';
import 'models/train.dart';

/// Where a journey stands right now — a single, source-agnostic shape.
///
/// This is the ONLY thing Journey Mode's UI consumes. It can be built from a
/// live GTFS-Realtime-tracked vehicle ([fromLiveTrain]) or from a
/// GTFS-timetable simulation ([fromTimetable]) when no live vehicle is bound
/// to the journey yet. Swapping which source feeds a given journey — e.g.
/// once reliable realtime-to-journey vehicle matching lands — is a provider
/// wiring change; nothing that renders a [JourneyProgressSnapshot] needs to
/// change.
class JourneyProgressSnapshot {
  const JourneyProgressSnapshot({
    required this.source,
    required this.currentStationName,
    required this.nextStationName,
    required this.remainingStations,
    required this.fractionComplete,
    required this.etaToDestination,
    required this.approachingInterchange,
    required this.interchangeStationName,
    required this.arrivingSoon,
    required this.arrived,
    required this.justBoarded,
    this.delaySeconds,
  });

  final JourneyProgressSource source;
  final String? currentStationName;
  final String? nextStationName;

  /// Stations still ahead including the destination; null when unknowable
  /// (e.g. a live vehicle whose destination isn't on its current leg yet).
  final int? remainingStations;

  /// 0.0 (just boarded) .. 1.0 (arrived); null when unknowable.
  final double? fractionComplete;
  final Duration? etaToDestination;
  final bool approachingInterchange;
  final String? interchangeStationName;
  final bool arrivingSoon;
  final bool arrived;

  /// True near the very start of the journey, before any station has been
  /// passed — the moment to show boarding/coach guidance.
  final bool justBoarded;
  final double? delaySeconds;
}

enum JourneyProgressSource { liveVehicle, timetableEstimate }

/// Builds a snapshot from a live, WS-tracked vehicle.
///
/// [totalStations] is the number of stations from boarding to destination as
/// planned — it is plan-level context the caller must supply (a live train's
/// own remaining-station list is relative to the train's current position,
/// not to where the rider boarded, so it cannot derive this on its own).
JourneyProgressSnapshot fromLiveTrain({
  required Train train,
  required String destinationStopId,
  required Set<String> interchangeStopIds,
  required int? totalStations,
  VehicleEta? eta,
}) {
  final remainingIds = [for (final s in train.remainingStations) s.stopId];
  final remainingToDest = remainingToDestination(remainingIds, destinationStopId);
  final destinationEta =
      eta?.stations.where((s) => s.stopId == destinationStopId).firstOrNull;
  final nextStopId = train.nextStation?.stopId;
  final isInterchange = nextStopId != null && interchangeStopIds.contains(nextStopId);

  return JourneyProgressSnapshot(
    source: JourneyProgressSource.liveVehicle,
    currentStationName: train.currentStation?.name,
    nextStationName: train.nextStation?.name,
    remainingStations: remainingToDest,
    fractionComplete: _fraction(totalStations, remainingToDest),
    etaToDestination: destinationEta == null
        ? null
        : Duration(milliseconds: (destinationEta.etaSeconds * 1000).round()),
    approachingInterchange: isInterchange,
    interchangeStationName: isInterchange ? train.nextStation!.name : null,
    arrivingSoon: remainingToDest == 1,
    arrived: remainingToDest == 0,
    justBoarded: totalStations != null &&
        remainingToDest != null &&
        remainingToDest >= totalStations,
    delaySeconds: eta?.delaySeconds,
  );
}

/// Builds a snapshot from the GTFS-timetable simulation.
JourneyProgressSnapshot fromTimetable(
  JourneyTimetable timetable,
  DateTime now, {
  required Set<String> interchangeStopIds,
}) {
  final snapshot = timetable.at(now);
  final totalStations = timetable.stops.length;
  final passed = totalStations - snapshot.remainingCount;
  final nextId = snapshot.next?.stopId;
  final isInterchange = nextId != null && interchangeStopIds.contains(nextId);

  return JourneyProgressSnapshot(
    source: JourneyProgressSource.timetableEstimate,
    currentStationName: snapshot.current?.name,
    nextStationName: snapshot.next?.name,
    remainingStations: snapshot.remainingCount,
    fractionComplete:
        totalStations == 0 ? null : (passed / totalStations).clamp(0.0, 1.0),
    etaToDestination: snapshot.arrived ? Duration.zero : snapshot.etaToDestination,
    approachingInterchange: isInterchange,
    interchangeStationName: isInterchange ? snapshot.next!.name : null,
    arrivingSoon: snapshot.remainingCount == 1,
    arrived: snapshot.arrived,
    justBoarded: passed == 0,
    delaySeconds: null, // a simulation has no notion of real-world delay
  );
}

double? _fraction(int? total, int? remaining) {
  if (total == null || remaining == null || total <= 0) return null;
  final done = total - remaining;
  return (done / total).clamp(0.0, 1.0);
}

/// Remaining-to-destination from a live train's remaining-station list.
///
/// Returns the 1-based position of [destinationStopId] within [remaining]
/// (so "next station is the destination" == 1), 0 when nothing remains, and
/// null when the destination isn't on this train's current run (e.g. before
/// an interchange, while riding an earlier leg of the plan).
int? remainingToDestination(
  List<String> remainingStopIds,
  String destinationStopId,
) {
  if (remainingStopIds.isEmpty) return 0;
  final index = remainingStopIds.indexOf(destinationStopId);
  return index >= 0 ? index + 1 : null;
}
