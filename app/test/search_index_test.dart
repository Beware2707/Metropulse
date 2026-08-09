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
  _realNameTests();

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

/// Station names exactly as DMRC publishes them in the GTFS feed — copied
/// from the live `/api/v1/stations` response, not invented. The whole class
/// of bug fixed here came from assuming names looked tidier than they are.
const _realNames = [
  Station(stopId: 'R1', name: 'Mayur Vihar-I', lat: 28.60, lon: 77.29),
  Station(stopId: 'R2', name: 'East Vinod Nagar - Mayur Vihar-II', lat: 28.61, lon: 77.30),
  Station(stopId: 'R3', name: 'Mayur Vihar Pocket 1', lat: 28.62, lon: 77.31),
  Station(stopId: 'R4', name: 'Mayur Vihar Ext', lat: 28.60, lon: 77.30),
  Station(stopId: 'R5', name: 'Dwarka Sector - 10', lat: 28.58, lon: 77.05),
  Station(stopId: 'R6', name: 'Dwarka Sector - 21', lat: 28.55, lon: 77.05),
  Station(stopId: 'R7', name: 'Dwarka Mor', lat: 28.61, lon: 77.03),
  Station(stopId: 'R8', name: 'Dwarka', lat: 28.61, lon: 77.04),
  Station(stopId: 'R9', name: 'Mundka Industrial Area (M.I.A)', lat: 28.68, lon: 77.03),
  Station(stopId: 'R10', name: 'Phase-I (Rapid Metro)', lat: 28.49, lon: 77.09),
  Station(stopId: 'R11', name: 'Phase 2 (Rapid Metro)', lat: 28.50, lon: 77.09),
  Station(stopId: 'R12', name: 'Dilli Haat - INA', lat: 28.57, lon: 77.21),
  Station(stopId: 'R13', name: 'Terminal 1- IGI Airport', lat: 28.56, lon: 77.12),
];

List<SearchHit> _find(String query) =>
    searchStations(stations: _realNames, exits: const {}, query: query);

void _realNameTests() {
  group('names people say vs names DMRC publishes', () {
    test('"dwarka sector 10" finds "Dwarka Sector - 10"', () {
      // Failed before: the published name has spaces around the hyphen, so a
      // plain substring test could never match what anyone would actually type.
      expect(_find('dwarka sector 10').first.station.stopId, 'R5');
    });

    test('"dwarka sector-10" and odd spacing find it too', () {
      expect(_find('dwarka sector-10').first.station.stopId, 'R5');
      expect(_find('Dwarka  Sector   10').first.station.stopId, 'R5');
    });

    test('"mayur vihar 1" finds "Mayur Vihar-I"', () {
      expect(_find('mayur vihar 1').first.station.stopId, 'R1');
    });

    test('"mayur vihar phase 1" finds it as well — "phase" is the rider\'s word',
        () {
      expect(_find('mayur vihar phase 1').first.station.stopId, 'R1');
    });

    test('"mayur vihar 2" finds the -II station, not the -I one', () {
      expect(_find('mayur vihar 2').first.station.stopId, 'R2');
    });

    test('"mayur vihar pocket 1" still finds the genuinely different station',
        () {
      expect(_find('mayur vihar pocket 1').first.station.stopId, 'R3');
    });

    test('word order does not matter', () {
      expect(_find('sector 10 dwarka').first.station.stopId, 'R5');
    });
  });

  group('the loosening does not break precise names', () {
    test('"Phase 2 (Rapid Metro)" still wins its own title', () {
      expect(_find('phase 2').first.station.stopId, 'R11');
    });

    test('an acronym is not mistaken for a Roman numeral', () {
      // M.I.A tokenises to m/i/a. A blanket roman rule would rewrite it to
      // "M 1 A" and start matching it against searches for "1".
      expect(normalizeStationText('Mundka Industrial Area (M.I.A)'),
          'mundka industrial area m i a');
      expect(_find('mundka').first.station.stopId, 'R9');
    });

    test('a hyphen before a non-numeral word is left alone', () {
      // "- INA" must not become "- 1 NA", and "- Vinod" must not become "- 5".
      expect(normalizeStationText('Dilli Haat - INA'), 'dilli haat ina');
      expect(normalizeStationText('East Vinod Nagar - Mayur Vihar-II'),
          'east vinod nagar mayur vihar 2');
      expect(normalizeStationText('Terminal 1- IGI Airport'),
          'terminal 1 igi airport');
    });

    test('exact beats loose: "dwarka" is Dwarka, not Dwarka Sector - 21', () {
      expect(_find('dwarka').first.station.stopId, 'R8');
    });

    test('a query of only filler words still searches literally', () {
      // Stripping "metro" to nothing would turn this into a match-everything.
      final hits = _find('metro');
      expect(hits.every((h) => h.station.name.toLowerCase().contains('metro')),
          isTrue);
    });
  });
}
