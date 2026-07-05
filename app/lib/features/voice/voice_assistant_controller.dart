import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/formatters.dart';
import '../../domain/fare.dart';
import '../../domain/journey_progress.dart';
import '../../domain/models/station.dart';
import '../../domain/search_index.dart';
import '../../domain/voice_intent.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
import '../journey_mode/journey_mode_providers.dart';

/// Turns a classified [VoiceIntent] into a spoken answer, using only the
/// app's existing repositories and providers — no separate backend endpoint,
/// no language model. This is what keeps the assistant "an experienced Delhi
/// Metro commuter" rather than a generic chatbot: every answer is a real
/// number or station name pulled from the same data the rest of the app
/// shows, phrased as a sentence.
class VoiceAssistantController {
  VoiceAssistantController(this._ref);

  final Ref _ref;

  static const _declineOffTopic =
      'I can only help with your Delhi Metro journey — try asking when to '
      'leave, which coach to board, or how to reach a station.';

  Future<String> answer(VoiceIntent intent) {
    switch (intent.kind) {
      case VoiceIntentKind.routeTo:
        return _answerRouteTo(intent.stationQuery!);
      case VoiceIntentKind.whenToLeave:
        return _answerWhenToLeave();
      case VoiceIntentKind.whichCoach:
        return _answerWhichCoach();
      case VoiceIntentKind.nextStation:
        return _answerNextStation();
      case VoiceIntentKind.fareQuery:
        return _answerFare();
      case VoiceIntentKind.onTrack:
        return _answerOnTrack();
      case VoiceIntentKind.unknown:
        return Future.value(_declineOffTopic);
    }
  }

  Future<String> _answerRouteTo(String query) async {
    final bundle = await _ref.read(offlineBundleProvider.future);
    if (bundle == null || bundle.stations.isEmpty) {
      return "I don't have station data yet — connect once to download it.";
    }
    final hits = searchStations(stations: bundle.stations, exits: bundle.exits, query: query);
    if (hits.isEmpty) {
      return 'I couldn\'t find a station matching "$query" — try the exact station name.';
    }
    final destination = hits.first.station;
    final origin = await _resolveOrigin();
    if (origin == null) {
      return "I'm not sure where you're starting from yet — set your Home "
          "station in Favourites and I'll be able to route you.";
    }
    if (origin.stopId == destination.stopId) {
      return "You're already at ${destination.name}.";
    }
    try {
      final plan = await _ref.read(journeyRepositoryProvider).plan(origin.stopId, destination.stopId);
      final firstRide = plan.legs.where((leg) => leg.isRide).firstOrNull;
      final lineName = firstRide?.routeLongName ?? 'the metro';
      final minutes = (plan.expectedTravelSeconds / 60).round();
      final changes = plan.interchangeCount;
      final changeText = changes == 0 ? 'no changes' : '$changes ${changes == 1 ? 'change' : 'changes'}';
      final fare = estimateFare(plan);
      return 'Take the $lineName from ${origin.name} to ${destination.name}. '
          "It's about $minutes minutes with $changeText, and should cost around "
          '₹${fare.rupees}.';
    } on Exception {
      return "I couldn't find a route to ${destination.name} right now.";
    }
  }

  Future<String> _answerWhenToLeave() async {
    final card = await _ref.read(commuteCardProvider.future);
    if (card != null && card.leaveBy != null) {
      final minutes = ((card.leaveInSeconds ?? 0) / 60).round();
      if (minutes <= 0) {
        return 'Leave right now to catch your usual train.';
      }
      return 'Leave by ${clockTime(card.leaveBy)} — that gives you about $minutes minutes.';
    }
    final prediction = await _ref.read(commutePredictionProvider.future);
    if (prediction != null) {
      return 'Based on your recent trips, you usually leave around '
          '${clockTime(prediction.predictedDepartureAt)}.';
    }
    return "I don't have enough information yet — set up your Home and Work "
        "stations in Favourites and I'll be able to tell you when to leave.";
  }

  Future<String> _answerWhichCoach() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey != null) {
      final context = _ref.read(journeyContextProvider(journey.id));
      if (context?.recommendedCoach != null) {
        return 'Board coach ${context!.recommendedCoach! + 1} — it lines up '
            'well with your exit and tends to run less crowded.';
      }
    }
    final card = await _ref.read(commuteCardProvider.future);
    if (card?.recommendedCoach != null) {
      return 'For your usual commute, coach ${card!.recommendedCoach! + 1} is your best bet.';
    }
    return "I don't have a coach recommendation right now — start a journey "
        "and I'll tell you which one to board.";
  }

  Future<String> _answerNextStation() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey == null) {
      return "You're not on a journey right now — start one from the planner "
          "and I'll keep you posted.";
    }
    final snapshot = _ref.read(journeyProgressProvider(journey));
    if (snapshot == null) {
      return "I can't tell yet — give it a moment after boarding.";
    }
    if (snapshot.arrived) {
      return "You've already arrived at your destination.";
    }
    final next = snapshot.nextStationName;
    if (next == null) {
      return "I don't have your next station yet.";
    }
    final remaining = snapshot.remainingStations;
    final stopsText = remaining == null ? '' : ', $remaining ${remaining == 1 ? 'stop' : 'stops'} to go';
    return 'Next station is $next$stopsText.';
  }

  Future<String> _answerFare() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey != null) {
      final context = _ref.read(journeyContextProvider(journey.id));
      if (context?.plan != null) {
        final fare = estimateFare(context!.plan!);
        return 'Your fare for this trip is about ₹${fare.rupees}.';
      }
    }
    return "Tell me where you're headed and I'll work out the fare — try "
        'asking how to reach a station.';
  }

  Future<String> _answerOnTrack() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey == null) {
      return "You're not on a journey right now, so there's nothing to check "
          '— start one from the planner.';
    }
    final stations = _ref.read(stationIndexProvider);
    final destinationName = stations[journey.destinationStopId]?.name ?? 'your destination';
    final snapshot = _ref.read(journeyProgressProvider(journey));
    if (snapshot == null) {
      return "I'm still figuring out where your train is — hang tight.";
    }
    if (snapshot.arrived) {
      return "You've arrived at $destinationName.";
    }
    final sourceNote = snapshot.source == JourneyProgressSource.liveVehicle
        ? 'tracking your train live'
        : 'estimating from the timetable';
    final stopsLeft = snapshot.remainingStations;
    final stopsText = stopsLeft == null ? '' : ', $stopsLeft ${stopsLeft == 1 ? 'stop' : 'stops'} to go';
    return "Yes, you're on track for $destinationName — $sourceNote$stopsText.";
  }

  /// Best-effort "where is the user right now": the active journey's current
  /// station if one is tracked, else its stated origin, else the Home
  /// favourite, else the first favourite, else unknown.
  Future<Station?> _resolveOrigin() async {
    final stations = _ref.read(stationIndexProvider);
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey != null) {
      final snapshot = _ref.read(journeyProgressProvider(journey));
      final currentName = snapshot?.currentStationName;
      if (currentName != null) {
        for (final station in stations.values) {
          if (station.name == currentName) return station;
        }
      }
      final origin = stations[journey.originStopId];
      if (origin != null) return origin;
    }
    final favourites = await _ref.read(favouriteStationsProvider.future);
    if (favourites.isEmpty) return null;
    Map<String, dynamic>? home;
    for (final favourite in favourites) {
      if ('${favourite['label']}'.toLowerCase() == 'home') {
        home = favourite;
        break;
      }
    }
    home ??= favourites.first;
    return stations['${home['stop_id']}'];
  }
}

final voiceAssistantControllerProvider =
    Provider<VoiceAssistantController>((ref) => VoiceAssistantController(ref));
