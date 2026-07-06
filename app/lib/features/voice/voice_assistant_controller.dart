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

/// One answer from the assistant: the spoken/displayed [text], plus whether
/// the underlying data source was live-vehicle-tracked ([isLive] == true) or
/// timetable-estimated ([isLive] == false) — mirroring Journey Mode's own
/// "LIVE TRACKING" / "SCHEDULED ESTIMATE" distinction (see
/// [JourneyProgressSource] in journey_progress.dart). Null when the answer
/// doesn't come from a tracked-progress source at all (most intents), in
/// which case no live/estimate pill should be shown.
class VoiceAnswer {
  const VoiceAnswer(this.text, {this.isLive});

  final String text;
  final bool? isLive;
}

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

  Future<VoiceAnswer> answer(VoiceIntent intent) {
    switch (intent.kind) {
      case VoiceIntentKind.routeTo:
        return _answerRouteTo(intent.stationQuery!);
      case VoiceIntentKind.whenToLeave:
        return _answerWhenToLeave();
      case VoiceIntentKind.runningLate:
        return _answerRunningLate();
      case VoiceIntentKind.whichCoach:
        return _answerWhichCoach();
      case VoiceIntentKind.nextStation:
        return _answerNextStation();
      case VoiceIntentKind.fareQuery:
        return _answerFare();
      case VoiceIntentKind.onTrack:
        return _answerOnTrack();
      case VoiceIntentKind.unknown:
        return Future.value(const VoiceAnswer(_declineOffTopic));
    }
  }

  Future<VoiceAnswer> _answerRouteTo(String query) async {
    final bundle = await _ref.read(offlineBundleProvider.future);
    if (bundle == null || bundle.stations.isEmpty) {
      return const VoiceAnswer("I don't have station data yet — connect once to download it.");
    }
    final hits = searchStations(stations: bundle.stations, exits: bundle.exits, query: query);
    if (hits.isEmpty) {
      return VoiceAnswer('I couldn\'t find a station matching "$query" — try the exact station name.');
    }
    final destination = hits.first.station;
    final origin = await _resolveOrigin();
    if (origin == null) {
      return const VoiceAnswer(
        "I'm not sure where you're starting from yet — set your Home "
        "station in Favourites and I'll be able to route you.",
      );
    }
    if (origin.stopId == destination.stopId) {
      return VoiceAnswer("You're already at ${destination.name}.");
    }
    try {
      final plan = await _ref.read(journeyRepositoryProvider).plan(origin.stopId, destination.stopId);
      final firstRide = plan.legs.where((leg) => leg.isRide).firstOrNull;
      final lineName = firstRide?.routeLongName ?? 'the metro';
      final minutes = (plan.expectedTravelSeconds / 60).round();
      final changes = plan.interchangeCount;
      final changeText = changes == 0 ? 'no changes' : '$changes ${changes == 1 ? 'change' : 'changes'}';
      final fare = estimateFare(plan);
      return VoiceAnswer(
        'Take the $lineName from ${origin.name} to ${destination.name}. '
        "It's about $minutes minutes with $changeText, and should cost around "
        '₹${fare.rupees}.',
      );
    } on Exception {
      return VoiceAnswer("I couldn't find a route to ${destination.name} right now.");
    }
  }

  Future<VoiceAnswer> _answerWhenToLeave() async {
    final card = await _ref.read(commuteCardProvider.future);
    if (card != null && card.leaveBy != null) {
      final minutes = ((card.leaveInSeconds ?? 0) / 60).round();
      if (minutes <= 0) {
        return const VoiceAnswer('Leave right now to catch your usual train.');
      }
      return VoiceAnswer('Leave by ${clockTime(card.leaveBy)} — that gives you about $minutes minutes.');
    }
    final prediction = await _ref.read(commutePredictionProvider.future);
    if (prediction != null) {
      return VoiceAnswer(
        'Based on your recent trips, you usually leave around '
        '${clockTime(prediction.predictedDepartureAt)}.',
      );
    }
    return const VoiceAnswer(
      "I don't have enough information yet — set up your Home and Work "
      "stations in Favourites and I'll be able to tell you when to leave.",
    );
  }

  /// "I'm running late" — reactive, not a repeat of "when should I leave":
  /// if a journey's already under way, reassure with real progress; otherwise
  /// point straight at the next train that's still catchable.
  Future<VoiceAnswer> _answerRunningLate() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey != null) {
      final snapshot = _ref.read(journeyProgressProvider(journey));
      if (snapshot != null && !snapshot.arrived) {
        final etaSeconds = snapshot.etaToDestination?.inSeconds.toDouble();
        final minutes = etaSeconds == null ? null : (etaSeconds / 60).round();
        return VoiceAnswer(
          minutes == null
              ? "You're already on your way — I'll keep tracking your progress."
              : "You're already on your way — about $minutes minutes left. Sit tight.",
        );
      }
    }

    final card = await _ref.read(commuteCardProvider.future);
    if (card?.nextDepartureAt != null) {
      return VoiceAnswer(
        'The next train to ${card!.destinationName} leaves at '
        '${clockTime(card.nextDepartureAt)} — you can still make it.',
      );
    }
    return const VoiceAnswer(
      "I don't have your usual route yet — set up Home and Work in "
      "Favourites and I'll always know your next best departure.",
    );
  }

  /// Which coach to board — prefers the real recommendation reason captured
  /// for the active journey (or, absent a journey, the same real reason for
  /// the user's usual commute) over a generic caption, so this never states a
  /// "why" the backend didn't actually give.
  Future<VoiceAnswer> _answerWhichCoach() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey != null) {
      final context = _ref.read(journeyContextProvider(journey.id));
      if (context?.recommendedCoach != null) {
        final reason = context!.coachReasons.isNotEmpty
            ? context.coachReasons.first
            : 'it lines up well with your exit and tends to run less crowded';
        return VoiceAnswer('Board coach ${context.recommendedCoach! + 1} — $reason.');
      }
    }
    final card = await _ref.read(commuteCardProvider.future);
    if (card?.recommendedCoach != null) {
      final reasons = await _ref.read(homeCoachReasonsProvider.future);
      if (reasons.isNotEmpty) {
        return VoiceAnswer(
          'For your usual commute, coach ${card!.recommendedCoach! + 1} is your '
          'best bet — ${reasons.first}.',
        );
      }
      return VoiceAnswer('For your usual commute, coach ${card!.recommendedCoach! + 1} is your best bet.');
    }
    return const VoiceAnswer(
      "I don't have a coach recommendation right now — start a journey "
      "and I'll tell you which one to board.",
    );
  }

  Future<VoiceAnswer> _answerNextStation() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey == null) {
      return const VoiceAnswer(
        "You're not on a journey right now — start one from the planner "
        "and I'll keep you posted.",
      );
    }
    final snapshot = _ref.read(journeyProgressProvider(journey));
    if (snapshot == null) {
      return const VoiceAnswer("I can't tell yet — give it a moment after boarding.");
    }
    if (snapshot.arrived) {
      return const VoiceAnswer("You've already arrived at your destination.");
    }
    final next = snapshot.nextStationName;
    if (next == null) {
      return const VoiceAnswer("I don't have your next station yet.");
    }
    final remaining = snapshot.remainingStations;
    final stopsText = remaining == null ? '' : ', $remaining ${remaining == 1 ? 'stop' : 'stops'} to go';
    return VoiceAnswer('Next station is $next$stopsText.');
  }

  Future<VoiceAnswer> _answerFare() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey != null) {
      final context = _ref.read(journeyContextProvider(journey.id));
      if (context?.plan != null) {
        final fare = estimateFare(context!.plan!);
        return VoiceAnswer('Your fare for this trip is about ₹${fare.rupees}.');
      }
    }
    return const VoiceAnswer(
      "Tell me where you're headed and I'll work out the fare — try "
      'asking how to reach a station.',
    );
  }

  /// "Am I on track / going the right way" — the one answer whose honesty
  /// about its data source matters enough to surface in the UI, not just in
  /// the sentence: [VoiceAnswer.isLive] carries the same
  /// [JourneyProgressSource] distinction Journey Mode's "LIVE TRACKING" /
  /// "SCHEDULED ESTIMATE" pill shows, so the screen can render an equivalent
  /// pill next to this specific answer.
  Future<VoiceAnswer> _answerOnTrack() async {
    final journey = await _ref.read(activeJourneyProvider.future);
    if (journey == null) {
      return const VoiceAnswer(
        "You're not on a journey right now, so there's nothing to check "
        '— start one from the planner.',
      );
    }
    final stations = _ref.read(stationIndexProvider);
    final destinationName = stations[journey.destinationStopId]?.name ?? 'your destination';
    final snapshot = _ref.read(journeyProgressProvider(journey));
    if (snapshot == null) {
      return const VoiceAnswer("I'm still figuring out where your train is — hang tight.");
    }
    if (snapshot.arrived) {
      return VoiceAnswer("You've arrived at $destinationName.");
    }
    final isLive = snapshot.source == JourneyProgressSource.liveVehicle;
    final sourceNote = isLive ? 'tracking your train live' : 'estimating from the timetable';
    final stopsLeft = snapshot.remainingStations;
    final stopsText = stopsLeft == null ? '' : ', $stopsLeft ${stopsLeft == 1 ? 'stop' : 'stops'} to go';
    return VoiceAnswer(
      "Yes, you're on track for $destinationName — $sourceNote$stopsText.",
      isLive: isLive,
    );
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
