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

  final hits = <SearchHit>[];
  for (final station in stations) {
    final hit = _bestHitFor(
      station,
      namesOnly ? const [] : (exits[station.stopId] ?? const []),
      trimmed,
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
) {
  final name = station.name.toLowerCase();
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

  if (name == trimmed) {
    consider(100, SearchMatchReason.name, station.name);
  } else if (name.startsWith(trimmed)) {
    consider(90, SearchMatchReason.name, station.name);
  } else if (name.contains(trimmed)) {
    consider(70, SearchMatchReason.name, station.name);
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
