import 'package:freezed_annotation/freezed_annotation.dart';

part 'replay.freezed.dart';
part 'replay.g.dart';

/// The story of one completed trip. Every figure here is a documented
/// estimate (see the backend's application/intelligence/commute_impact.py)
/// — never a live pricing/traffic feed — and should always read to the user
/// as an estimate, not a receipt.
@freezed
class TripReplay with _$TripReplay {
  const factory TripReplay({
    required String originStopId,
    required String originName,
    required String destinationStopId,
    required String destinationName,
    required DateTime startedAt,
    required DateTime endedAt,
    required double durationSeconds,
    required double distanceKm,
    required int metroFareRupees,
    required int estimatedCabFareRupees,
    required int moneySavedRupees,
    required double timeSavedSeconds,
    required double co2SavedKg,
  }) = _TripReplay;

  factory TripReplay.fromJson(Map<String, dynamic> json) => _$TripReplayFromJson(json);
}

/// A rolling-window summary of completed trips — the "This Month" card.
@freezed
class MonthlyReplay with _$MonthlyReplay {
  const factory MonthlyReplay({
    required DateTime periodStart,
    required DateTime periodEnd,
    required int tripCount,
    required double totalDistanceKm,
    required double totalTimeSavedSeconds,
    required int totalMoneySavedRupees,
    required double totalCo2SavedKg,
  }) = _MonthlyReplay;

  factory MonthlyReplay.fromJson(Map<String, dynamic> json) => _$MonthlyReplayFromJson(json);
}
