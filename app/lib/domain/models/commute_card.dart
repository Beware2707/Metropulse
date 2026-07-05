import 'package:freezed_annotation/freezed_annotation.dart';

part 'commute_card.freezed.dart';
part 'commute_card.g.dart';

/// The personalised home-screen card.
@freezed
class CommuteCard with _$CommuteCard {
  const factory CommuteCard({
    required String greeting,
    required String originStopId,
    required String originName,
    required String destinationStopId,
    required String destinationName,
    required String crowding,
    String? routeLongName,
    String? routeColor,
    String? platformHint,
    DateTime? nextDepartureAt,
    DateTime? leaveBy,
    double? leaveInSeconds,
    int? recommendedCoach,
    @Default(<String>[]) List<String> interchangeNames,
    double? travelSeconds,
    DateTime? expectedArrivalAt,
    int? stationsRemaining,
  }) = _CommuteCard;

  factory CommuteCard.fromJson(Map<String, dynamic> json) =>
      _$CommuteCardFromJson(json);
}
