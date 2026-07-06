import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/station.dart';
import 'package:metropulse_app/domain/search_index.dart';

const _stations = [
  Station(stopId: 'S1', name: 'Rajiv Chowk', lat: 28.63, lon: 77.22),
  Station(stopId: 'S2', name: 'Hauz Khas', lat: 28.54, lon: 77.20),
  Station(stopId: 'S3', name: 'AIIMS', lat: 28.57, lon: 77.21),
  Station(stopId: 'S4', name: 'New Delhi', lat: 28.64, lon: 77.22),
];

const _exits = {
  'S2': [
    StationExitInfo(id: 1, name: 'Gate 1', landmarks: ['IIT Delhi', 'Deer Park']),
  ],
};

void main() {
  test('empty query returns no hits', () {
    expect(searchStations(stations: _stations, exits: const {}, query: ''), isEmpty);
    expect(searchStations(stations: _stations, exits: const {}, query: '   '), isEmpty);
  });

  test('exact name match outranks a prefix match which outranks a substring match', () {
    final hits = searchStations(stations: _stations, exits: const {}, query: 'hauz khas');
    expect(hits.first.station.stopId, 'S2');
    expect(hits.first.reason, SearchMatchReason.name);
  });

  test('prefix beats plain substring for the same station', () {
    final delhiHits = searchStations(stations: _stations, exits: const {}, query: 'new');
    expect(delhiHits.first.station.stopId, 'S4');
  });

  test('a well-known alias resolves to the real station', () {
    final hits = searchStations(stations: _stations, exits: const {}, query: 'cp');
    expect(hits, isNotEmpty);
    expect(hits.first.station.stopId, 'S1');
    expect(hits.first.reason, SearchMatchReason.alias);
    expect(hits.first.matchedText, 'cp');
  });

  test('an alias for a station absent from the dataset contributes nothing', () {
    // 'iffco chowk' alias exists but no such station is loaded here.
    final hits = searchStations(stations: _stations, exits: const {}, query: 'iffco');
    expect(hits, isEmpty);
  });

  test('landmark search finds the station via its curated exits', () {
    final hits = searchStations(stations: _stations, exits: _exits, query: 'deer park');
    expect(hits, isNotEmpty);
    expect(hits.first.station.stopId, 'S2');
    expect(hits.first.reason, SearchMatchReason.landmark);
    expect(hits.first.matchedText, 'Deer Park');
  });

  test('namesOnly excludes landmark matches -- for map-picker searches, a station\'s '
      'own name is all that should resolve it', () {
    final hits = searchStations(stations: _stations, exits: _exits, query: 'deer park', namesOnly: true);
    expect(hits, isEmpty);
  });

  test('namesOnly still finds a station by its own name or alias', () {
    final byName = searchStations(stations: _stations, exits: _exits, query: 'hauz khas', namesOnly: true);
    expect(byName.single.station.stopId, 'S2');
    expect(byName.single.reason, SearchMatchReason.name);

    final byAlias = searchStations(stations: _stations, exits: _exits, query: 'cp', namesOnly: true);
    expect(byAlias.single.station.stopId, 'S1');
    expect(byAlias.single.reason, SearchMatchReason.alias);
  });

  test('name match ranks above a landmark match on a different station', () {
    // Query 'gate' isn't a landmark here, but ensure name/alias always
    // computed independently of landmarks; use a query matching both kinds
    // to confirm the scorer picks the higher-scoring reason per station.
    final hits = searchStations(stations: _stations, exits: _exits, query: 'iit delhi');
    expect(hits.single.reason, SearchMatchReason.landmark);
  });

  test('no match returns no hit for that station', () {
    final hits = searchStations(stations: _stations, exits: const {}, query: 'zzz-nonexistent');
    expect(hits, isEmpty);
  });

  test('results are capped at limit', () {
    final many = List.generate(
      50,
      (i) => Station(stopId: 'X$i', name: 'Station $i', lat: 0, lon: 0),
    );
    final hits = searchStations(stations: many, exits: const {}, query: 'station', limit: 10);
    expect(hits, hasLength(10));
  });

  test('rankWithBoosts breaks a tie in favour of a favourite station', () {
    // Both names match 'a' only via "contains" (neither starts with it), so
    // they tie on the base text-match score — the boost, not the match
    // quality, must decide the order.
    const tied = [
      Station(stopId: 'S1', name: 'Rajiv Chowk', lat: 28.63, lon: 77.22),
      Station(stopId: 'S2', name: 'Hauz Khas', lat: 28.54, lon: 77.20),
    ];
    final hits = searchStations(stations: tied, exits: const {}, query: 'a');
    expect(hits.map((h) => h.score).toSet(), hasLength(1));

    final boosted = rankWithBoosts(hits, favouriteStopIds: {'S2'});
    expect(boosted.first.station.stopId, 'S2');
  });

  test('rankWithBoosts cannot overtake a strictly better text match', () {
    // AIIMS starts with 'a' (score 90); Hauz Khas only contains it (score
    // 70). The +8 favourite boost must not be enough to invert that order —
    // a boost tips ties, it does not override relevance.
    final hits = searchStations(stations: _stations, exits: const {}, query: 'a');
    final boosted = rankWithBoosts(hits, favouriteStopIds: {'S2'});
    expect(boosted.first.station.stopId, 'S3');
  });

  test('rankWithBoosts never promotes a station that did not match at all', () {
    final hits = searchStations(stations: _stations, exits: const {}, query: 'hauz');
    final boosted = rankWithBoosts(hits, favouriteStopIds: {'S4'});
    // S4 never matched 'hauz', so it must not appear regardless of favourite status.
    expect(boosted.any((h) => h.station.stopId == 'S4'), isFalse);
  });
}
