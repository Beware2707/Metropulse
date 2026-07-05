/// Well-known colloquial names for a handful of Delhi Metro stations.
///
/// Matched by case-insensitive substring against whatever station names
/// actually exist in the loaded offline bundle — an alias for a station the
/// current dataset doesn't contain simply contributes nothing (no crash, no
/// false match). Kept intentionally small: every entry here is public,
/// stable, uncontroversial knowledge about the DMRC network (not a guess at
/// a specific dataset's exact naming), so it stays correct regardless of
/// which GTFS feed is loaded.
const Map<String, String> kStationAliases = {
  'cp': 'rajiv chowk',
  'connaught place': 'rajiv chowk',
  'aiims': 'aiims',
  'jln stadium': 'jawaharlal nehru stadium',
  'new delhi railway station': 'new delhi',
  'ndls': 'new delhi',
  'kashmiri gate': 'kashmere gate',
  'chandni chowk': 'chandni chowk',
  'iffco chowk': 'iffco chowk',
  'huda city centre': 'millennium city centre',
};

/// Known aliases whose canonical target is a substring of [stationName].
Iterable<String> aliasesFor(String stationName) sync* {
  final lowerName = stationName.toLowerCase();
  for (final entry in kStationAliases.entries) {
    if (lowerName.contains(entry.value)) {
      yield entry.key;
    }
  }
}
