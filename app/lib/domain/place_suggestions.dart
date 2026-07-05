import 'models/intelligence.dart';

/// One actionable place-tagging suggestion: an inferred place plus the
/// label choices worth offering for it. Home is unambiguous (one choice —
/// there's only one Home). A regular weekday destination could be Work or
/// College — movement data can't tell which, so both are offered and the
/// user picks; the app never guesses on their behalf.
class PlaceSuggestion {
  const PlaceSuggestion({required this.place, required this.labelOptions});

  final InferredPlace place;
  final List<String> labelOptions;
}

const _homeLabelOptions = ['Home'];
const _weekdayAnchorLabelOptions = ['Work', 'College'];

/// Inferred places worth surfacing to the user in Favourites.
///
/// A place is only suggested when:
/// - no existing favourite already covers that role (a "Home" favourite
///   already exists, or a "Work"/"College" one already exists), and
/// - the inferred station isn't already saved as a favourite under some
///   other label — accepting a suggestion must only ever ADD a new
///   favourite, never silently relabel or reorder an existing one.
List<PlaceSuggestion> placeSuggestions(
  List<Map<String, dynamic>> favouriteRows,
  List<InferredPlace> inferredPlaces,
) {
  final existingStopIds = favouriteRows.map((row) => '${row['stop_id']}').toSet();
  final hasHome = favouriteRows.any((row) => '${row['label']}'.toLowerCase() == 'home');
  final hasWeekdayAnchor = favouriteRows.any((row) {
    final label = '${row['label']}'.toLowerCase();
    return label == 'work' || label == 'college';
  });

  return [
    for (final place in inferredPlaces)
      if (!existingStopIds.contains(place.stopId))
        if (place.role == 'home' && !hasHome)
          PlaceSuggestion(place: place, labelOptions: _homeLabelOptions)
        else if (place.role == 'weekday_anchor' && !hasWeekdayAnchor)
          PlaceSuggestion(place: place, labelOptions: _weekdayAnchorLabelOptions),
  ];
}
