import 'models/station.dart';
import 'station_aliases.dart';

/// Why a station matched a search query, so the UI can show "via CP" or
/// "near AIIMS Gate 2" instead of a bare name.
enum SearchMatchReason { name, alias, landmark }

/// One ranked search result.
class SearchHit {
  const SearchHit({
    required this.station,
    required this.reason,
    required this.score,
    this.matchedText,
  });

  final Station station;
  final SearchMatchReason reason;
  final double score;

  /// The alias or landmark string that matched, when [reason] isn't [SearchMatchReason.name].
  final String? matchedText;
}

/// Roman ordinals attached by a hyphen, e.g. the "-I" in "Mayur Vihar-I".
///
/// Only hyphen-attached numerals are converted. That restriction is the whole
/// point: "Mundka Industrial Area (M.I.A)" tokenises to m/i/a, and a blanket
/// rule would rewrite it as "M 1 A" and start matching it against "1".
/// A hyphen means an ordinal suffix ("Phase-I", "Mayur Vihar-II"); a dot means
/// an acronym.
final _romanOrdinal = RegExp(
  r'-\s*(i{1,3}|iv|v|vi{1,3}|ix|x)\b',
  caseSensitive: false,
);

const _romanValues = {
  'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
  'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
};

/// Words a rider adds that the official name may not carry.
///
/// DMRC calls it "Mayur Vihar-I"; people say "Mayur Vihar Phase 1". Dropped
/// from the QUERY only — never from station names, because "Phase 2 (Rapid
/// Metro)" is itself a station and stripping its name would make it
/// unfindable by its own title.
const _queryFillerWords = {'phase', 'pkt', 'no', 'number', 'metro', 'station'};

/// Canonical form for comparing a station name and a typed/spoken query.
///
/// Punctuation becomes whitespace, so "Dwarka Sector - 10" and
/// "dwarka sector 10" land on the same string — the reason a plain substring
/// test failed on nearly every hyphenated station in the network.
String normalizeStationText(String raw) => raw
    .toLowerCase()
    .replaceAllMapped(_romanOrdinal, (m) => ' ${_romanValues[m.group(1)!.toLowerCase()]}')
    .replaceAll(RegExp(r'[^a-z0-9]+'), ' ')
    .trim();

/// [normalizeStationText] split into tokens, optionally without filler words.
List<String> stationTokens(String raw, {bool dropFiller = false}) {
  final normalized = normalizeStationText(raw);
  if (normalized.isEmpty) return const [];
  final tokens = normalized.split(' ');
  if (!dropFiller) return tokens;
  final kept = [for (final t in tokens) if (!_queryFillerWords.contains(t)) t];
  // Never let filler-stripping empty the query — someone searching literally
  // for "metro" should still get their substring search, not everything.
  return kept.isEmpty ? tokens : kept;
}

/// Ranks [stations] against [query] using name, curated aliases and
/// curated exit landmarks (from the offline bundle's `exits` map) — a fully
/// offline search index requiring no network call.
///
/// Pure and stateless: recency/favourite boosting is layered on top by
/// [rankWithBoosts] so this core scorer stays trivially testable.
List<SearchHit> searchStations({
  required List<Station> stations,
  required Map<String, List<StationExitInfo>> exits,
  required String query,
  int limit = 30,
  // When true, only a station's own name or alias can match -- nearby
  // landmarks are ignored. Used for map-picker searches (e.g. the Explore
  // screen), where the point is to find a named station, not something
  // merely close to one.
  bool namesOnly = false,
}) {
  final trimmed = query.trim().toLowerCase();
  if (trimmed.isEmpty) return const [];

  final normalizedQuery = normalizeStationText(query);
  final queryTokens = stationTokens(query, dropFiller: true);

  final hits = <SearchHit>[];
  for (final station in stations) {
    final hit = _bestHitFor(
      station,
      namesOnly ? const [] : (exits[station.stopId] ?? const []),
      trimmed,
      normalizedQuery,
      queryTokens,
    );
    if (hit != null) hits.add(hit);
  }
  hits.sort((a, b) {
    final byScore = b.score.compareTo(a.score);
    return byScore != 0 ? byScore : a.station.name.compareTo(b.station.name);
  });
  return hits.take(limit).toList(growable: false);
}

SearchHit? _bestHitFor(
  Station station,
  List<StationExitInfo> exits,
  String trimmed,
  String normalizedQuery,
  List<String> queryTokens,
) {
  double bestScore = 0;
  SearchMatchReason? bestReason;
  String? matchedText;

  void consider(double score, SearchMatchReason reason, String text) {
    if (score > bestScore) {
      bestScore = score;
      bestReason = reason;
      matchedText = text;
    }
  }

  // Compare on the canonical form, so punctuation and Roman ordinals stop
  // being the difference between a hit and "I couldn't find that station".
  final normalizedName = normalizeStationText(station.name);
  if (normalizedName == normalizedQuery) {
    consider(100, SearchMatchReason.name, station.name);
  } else if (normalizedName.startsWith(normalizedQuery)) {
    consider(90, SearchMatchReason.name, station.name);
  } else if (normalizedName.contains(normalizedQuery)) {
    consider(70, SearchMatchReason.name, station.name);
  }

  // Word-set matching, so the rider's extra words ("phase") and their word
  // ORDER stop mattering. Ranked below the string paths above so a precise
  // name like "Phase 2 (Rapid Metro)" still wins its own title.
  if (queryTokens.isNotEmpty) {
    final nameTokens = stationTokens(station.name);
    if (nameTokens.isNotEmpty &&
        queryTokens.every((token) => nameTokens.contains(token))) {
      // Same words, nothing left over: as good as an exact match to a person.
      consider(
        nameTokens.length == queryTokens.length ? 88 : 64,
        SearchMatchReason.name,
        station.name,
      );
    }
  }

  for (final alias in aliasesFor(station.name)) {
    if (alias == trimmed) {
      consider(85, SearchMatchReason.alias, alias);
    } else if (alias.startsWith(trimmed)) {
      consider(78, SearchMatchReason.alias, alias);
    } else if (alias.contains(trimmed)) {
      consider(60, SearchMatchReason.alias, alias);
    }
  }

  for (final exit in exits) {
    for (final landmark in exit.landmarks) {
      final lower = landmark.toLowerCase();
      if (lower == trimmed) {
        consider(65, SearchMatchReason.landmark, landmark);
      } else if (lower.startsWith(trimmed)) {
        consider(55, SearchMatchReason.landmark, landmark);
      } else if (lower.contains(trimmed)) {
        consider(40, SearchMatchReason.landmark, landmark);
      }
    }
  }

  if (bestReason == null) return null;
  return SearchHit(
    station: station,
    reason: bestReason!,
    score: bestScore,
    matchedText: bestReason == SearchMatchReason.name ? null : matchedText,
  );
}

/// Re-ranks [hits] with a bonus for favourite and recently-visited stations —
/// applied on top of the pure text-match score so user history never causes
/// a clearly-wrong match to outrank a clearly-right one.
List<SearchHit> rankWithBoosts(
  List<SearchHit> hits, {
  Set<String> favouriteStopIds = const {},
  Set<String> recentStopIds = const {},
}) {
  final boosted = [
    for (final hit in hits)
      SearchHit(
        station: hit.station,
        reason: hit.reason,
        score: hit.score +
            (favouriteStopIds.contains(hit.station.stopId) ? 8 : 0) +
            (recentStopIds.contains(hit.station.stopId) ? 4 : 0),
        matchedText: hit.matchedText,
      ),
  ]..sort((a, b) {
      final byScore = b.score.compareTo(a.score);
      return byScore != 0 ? byScore : a.station.name.compareTo(b.station.name);
    });
  return boosted;
}
