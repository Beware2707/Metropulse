import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/commute_timeline.dart';
import 'package:metropulse_app/domain/models/commute_card.dart';
import 'package:metropulse_app/domain/models/journey.dart';

JourneyStop _stop(String id, String name) => JourneyStop(stopId: id, name: name);

CommuteCard _card({
  required DateTime leaveBy,
  required DateTime nextDepartureAt,
  required DateTime expectedArrivalAt,
  String? routeLongName = 'Blue Line',
}) {
  return CommuteCard(
    greeting: 'Good morning',
    originStopId: 'S1',
    originName: 'Dwarka',
    destinationStopId: 'S4',
    destinationName: 'Office',
    crowding: 'low',
    routeLongName: routeLongName,
    leaveBy: leaveBy,
    nextDepartureAt: nextDepartureAt,
    expectedArrivalAt: expectedArrivalAt,
  );
}

void main() {
  group('resolveCommuteTimelineStatus', () {
    final leaveBy = DateTime(2026, 1, 1, 8, 14);

    test('a negligible delay is always on time, regardless of slack', () {
      final status = resolveCommuteTimelineStatus(
        now: leaveBy.add(const Duration(minutes: 10)), // already well past leaveBy
        leaveBy: leaveBy,
        delaySeconds: 30, // below the 120s "worth mentioning" cutoff
      );
      expect(status.urgency, CommuteUrgency.onTime);
      expect(status.headline, 'Everything is on time.');
      expect(status.subline, isNull);
    });

    test('a real delay with ample remaining slack is still on time', () {
      final status = resolveCommuteTimelineStatus(
        now: leaveBy.subtract(const Duration(minutes: 10)), // 10 min before leaveBy
        leaveBy: leaveBy,
        delaySeconds: 180, // 3 min delay, comfortably absorbed by 10 min slack
      );
      expect(status.urgency, CommuteUrgency.onTime);
    });

    test('a delay just within the comfortable margin still says leave now', () {
      final status = resolveCommuteTimelineStatus(
        now: leaveBy.subtract(const Duration(seconds: 60)), // 60s slack left
        leaveBy: leaveBy,
        delaySeconds: 180, // net = 60 - 180 = -120s -> exactly the boundary
      );
      expect(status.urgency, CommuteUrgency.leaveNow);
      expect(status.headline, 'Leave now.');
      expect(status.subline, "You'll still make it.");
    });

    test('real remaining slack that cannot absorb the delay quantifies both numbers', () {
      final status = resolveCommuteTimelineStatus(
        now: leaveBy.subtract(const Duration(minutes: 3)), // 180s slack
        leaveBy: leaveBy,
        delaySeconds: 900, // 15 min delay -> net = 180 - 900 = -720s (12 min late)
      );
      expect(status.urgency, CommuteUrgency.actSoon);
      expect(status.headline, 'Leave within 3 min.');
      expect(status.subline, "Otherwise you'll arrive about 12 min late.");
    });

    test('already past leaveBy with a real delay reads as overdue', () {
      final status = resolveCommuteTimelineStatus(
        now: leaveBy.add(const Duration(minutes: 5)),
        leaveBy: leaveBy,
        delaySeconds: 600, // 10 min delay
      );
      expect(status.urgency, CommuteUrgency.overdue);
      expect(status.headline, "You're already running late.");
      // net = slack(-300) - delay(600) = -900s -> 15 min late
      expect(status.subline, 'Expect to arrive about 15 min late.');
    });

    test('a negative (early-running) delay estimate is clamped to zero, never a promised early arrival', () {
      final status = resolveCommuteTimelineStatus(
        now: leaveBy.subtract(const Duration(minutes: 1)),
        leaveBy: leaveBy,
        delaySeconds: -300, // an "early" signal must not read as extra slack
      );
      expect(status.urgency, CommuteUrgency.onTime);
    });
  });

  group('buildCommuteTimelineSteps', () {
    test('returns no steps at all when the card lacks real anchor times', () {
      const card = CommuteCard(
        greeting: 'Hi',
        originStopId: 'S1',
        originName: 'Dwarka',
        destinationStopId: 'S4',
        destinationName: 'Office',
        crowding: 'low',
      );
      expect(buildCommuteTimelineSteps(card: card, plan: null), isEmpty);
    });

    test('with no plan, still produces Leave Home / Board / Destination from the card alone', () {
      final leaveBy = DateTime(2026, 1, 1, 8, 14);
      final boardAt = DateTime(2026, 1, 1, 8, 28);
      final arriveAt = DateTime(2026, 1, 1, 9, 2);
      final steps = buildCommuteTimelineSteps(
        card: _card(leaveBy: leaveBy, nextDepartureAt: boardAt, expectedArrivalAt: arriveAt),
        plan: null,
      );
      expect(steps, hasLength(3));
      expect(steps[0].title, 'Leave Home');
      expect(steps[0].time, leaveBy);
      expect(steps[1].title, 'Board Blue Line');
      expect(steps[1].time, boardAt);
      expect(steps[1].isInterchange, isFalse);
      expect(steps[2].title, 'Office');
      expect(steps[2].time, arriveAt);
    });

    test('an interchange leg is placed in time using the plan, anchored at the real boarding time', () {
      final leaveBy = DateTime(2026, 1, 1, 8, 14);
      final boardAt = DateTime(2026, 1, 1, 8, 28);
      final arriveAt = DateTime(2026, 1, 1, 9, 2);
      final plan = JourneyPlan(
        origin: _stop('S1', 'Dwarka'),
        destination: _stop('S4', 'Office'),
        departureAt: DateTime(2026, 1, 1, 7, 55), // re-planned "from now" — deliberately different from boardAt
        expectedArrivalAt: DateTime(2026, 1, 1, 8, 29),
        expectedTravelSeconds: 2040,
        interchangeCount: 1,
        interchangeStopIds: const ['S2'],
        walkingDistanceM: 100,
        remainingStations: const [],
        legs: [
          JourneyLeg(
            kind: 'ride',
            board: _stop('S1', 'Dwarka'),
            alight: _stop('S2', 'Rajiv Chowk'),
            seconds: 600,
            waitSeconds: 300, // must be re-zeroed since boardAt is already the real departure
            routeId: 'R1',
            stations: [_stop('S1', 'Dwarka'), _stop('S2', 'Rajiv Chowk')],
          ),
          JourneyLeg(
            kind: 'walk',
            board: _stop('S2', 'Rajiv Chowk'),
            alight: _stop('S2', 'Rajiv Chowk'),
            seconds: 120,
            distanceM: 80,
          ),
          JourneyLeg(
            kind: 'ride',
            board: _stop('S2', 'Rajiv Chowk'),
            alight: _stop('S4', 'Office'),
            seconds: 840,
            waitSeconds: 180,
            routeId: 'R2',
            stations: [_stop('S2', 'Rajiv Chowk'), _stop('S4', 'Office')],
          ),
        ],
      );

      final steps = buildCommuteTimelineSteps(
        card: _card(leaveBy: leaveBy, nextDepartureAt: boardAt, expectedArrivalAt: arriveAt),
        plan: plan,
      );

      expect(steps.map((s) => s.title), ['Leave Home', 'Board Blue Line', 'Rajiv Chowk', 'Office']);
      expect(steps[2].isInterchange, isTrue);
      // First leg's wait is zeroed (already anchored at the real boardAt), so
      // the interchange lands exactly 600s (the ride itself) after boardAt —
      // not 900s (which would double-count the original 300s platform wait).
      expect(steps[2].time, boardAt.add(const Duration(seconds: 600)));
      expect(steps[3].time, arriveAt); // the destination always uses the card's own arrival, never the plan's
    });
  });
}
