// Phase-aware station guidance: the same station facts mean different things
// depending on where the rider is in their journey.
//
// A gate is an ENTRANCE while you're walking in at the origin, a TRANSFER
// point at an interchange, and an EXIT when you're arriving. The DMRC
// pathways and OSM exit datasets don't distinguish those roles — the journey
// does. This turns "here is some station data" into "here is what to do
// next", which is the whole difference between a database and a companion.
//
// Honesty rules baked in:
//   * Escalators are NEVER mentioned. No approved dataset contains a single
//     escalator node (667 gates, 845 lifts, 355 platforms, 566 concourse
//     nodes, zero escalators), so any escalator claim would be invented.
//   * A step-free gate is one DMRC's own pathway graph connects to a
//     lift-served platform. When no gate qualifies, the guidance says the
//     path isn't mapped — never that the station is inaccessible.
//   * Nothing is emitted from an empty dataset. Absent data yields no row,
//     not a confident-sounding guess.

/// Where the rider is, which decides what a gate means to them.
enum JourneyPhase {
  /// Walking into the origin station, before boarding.
  enteringOrigin,

  /// On board, approaching a station where they change lines.
  approachingInterchange,

  /// On board, approaching the final destination.
  arriving,

  /// On board mid-journey, with nothing station-specific to act on.
  riding,
}

/// Actionable station guidance, as separate facts rather than one blurred
/// sentence — so the UI can give each its own weight and its own icon.
///
/// The shape is deliberate. "Exit Gate 4" alone is a location; "Exit Gate 4 /
/// lift to the platform / closest to Connaught Place" is a decision already
/// made for the rider. Each line is a different KIND of claim, with a
/// different evidence base, so each is nullable independently: a gate with no
/// landmark still earns its lift line, and vice versa.
class StationGuidance {
  const StationGuidance({
    required this.headline,
    this.liftNote,
    this.landmarkNote,
    this.platformNote,
    this.stepFree = false,
    this.stepFreeUnmapped = false,
  });

  /// The action: "Enter at Gate No. 2", "Leave by Gate No. 4".
  final String headline;

  /// What the lift evidence supports — and only that. A gate DMRC's graph
  /// connects to a lift-served platform earns the strong line; a station that
  /// merely has lifts somewhere earns the weak one; no lift data earns
  /// silence.
  final String? liftNote;

  /// "Closest to Red Fort" — how people actually navigate out of a station.
  final String? landmarkNote;

  /// Which platforms this station has, from DMRC's own pathway nodes. NOT
  /// which platform your train leaves from: no dataset maps a platform to a
  /// direction, so claiming one would be invention.
  final String? platformNote;

  /// True only when DMRC's graph connects this gate to a lift-served
  /// platform. Drives the accessible badge; never set on a guess.
  final bool stepFree;

  /// True when the rider asked for step-free and the data cannot confirm one.
  /// Surfaced as "not mapped", never as "not accessible".
  final bool stepFreeUnmapped;

  /// Every supporting line, in reading order, for compact surfaces.
  List<String> get detailLines =>
      [liftNote, landmarkNote, platformNote].whereType<String>().toList();

  @override
  String toString() => 'StationGuidance($headline, ${detailLines.join(" / ")}, '
      'stepFree: $stepFree, unmapped: $stepFreeUnmapped)';
}

/// Names of gates DMRC's pathway graph links to a lift-served platform.
List<String> stepFreeGateNames(Map<String, dynamic>? accessibility) => [
      for (final g in (accessibility?['step_free_gates'] as List? ?? const []))
        if (g is Map && g['name'] != null) '${g['name']}',
    ];

/// The gate number in a name, or null. Datasets name gates differently
/// ("Chandni Chowk Metro Gate No. 3" vs "Gate No. 3"); the number is the only
/// reliable join, and a wrong join here sends a wheelchair user to stairs.
int? gateNumber(String name) {
  final m = RegExp(r'gate\s*(?:no\.?|number|-)?\s*(\d+)', caseSensitive: false)
      .firstMatch(name);
  return m == null ? null : int.tryParse(m.group(1)!);
}

/// Whether an exit's name matches one of the mapped step-free gates, by exact
/// gate number only.
bool exitIsStepFree(String exitName, Map<String, dynamic>? accessibility) {
  final n = gateNumber(exitName);
  if (n == null) return false;
  return stepFreeGateNames(accessibility).any((g) => gateNumber(g) == n);
}

/// Build the guidance for one moment of a journey.
///
/// [exits] are the station's curated exits (OSM/official). [accessibility] is
/// DMRC's pathway graph for the station. Both may be null/empty — that is the
/// normal case for most stations and yields no guidance rather than filler.
/// How many lifts DMRC's graph lists at this station.
int liftCount(Map<String, dynamic>? accessibility) =>
    (accessibility?['lifts'] as List?)?.length ?? 0;

/// The station's platform names, e.g. ["Platform 1", "Platform 2"].
List<String> platformNames(Map<String, dynamic>? accessibility) => [
      for (final p in (accessibility?['platforms'] as List? ?? const []))
        if (p is Map && p['name'] != null) '${p['name']}',
    ];

/// The lift line, pitched at exactly what the evidence supports.
///
/// Three tiers, and the difference matters to someone who cannot use stairs:
///   * this gate is graph-connected to a lift-served platform -> a promise;
///   * the station has lifts but this gate is not connected in the map ->
///     a fact about the station, with no claim about this gate;
///   * no lift data -> nothing at all.
String? _liftNote({required bool gateIsStepFree, required int lifts}) {
  if (gateIsStepFree) return 'Lift to the platform';
  if (lifts > 0) {
    return lifts == 1
        ? '1 lift at this station — path from this gate not mapped'
        : '$lifts lifts at this station — path from this gate not mapped';
  }
  return null;
}

/// Build the guidance for one moment of a journey.
///
/// [exits] are the station's curated exits (OSM/official). [accessibility] is
/// DMRC's pathway graph for the station. Both may be null/empty — that is the
/// normal case for most stations and yields no guidance rather than filler.
StationGuidance? buildStationGuidance({
  required JourneyPhase phase,
  required bool stepFreePreferred,
  List<Map<String, dynamic>> exits = const [],
  Map<String, dynamic>? accessibility,
  String? matchedExitName,
  String? matchedLandmark,
}) {
  if (phase == JourneyPhase.riding) return null;

  final stepFree = stepFreeGateNames(accessibility);
  final lifts = liftCount(accessibility);
  final platforms = platformNames(accessibility);

  // Platforms are worth naming only while heading TO a platform. On the way
  // out they are behind the rider, and one more line would just be noise.
  final platformNote = (phase == JourneyPhase.arriving || platforms.isEmpty)
      ? null
      : (platforms.length == 1
          ? platforms.single
          : '${platforms.take(3).join(', ')} at this station');

  // A rider who needs step-free access is answering a different question
  // ("can I get through at all?") than one who wants the handiest exit, so
  // that need outranks landmark convenience at every phase.
  if (stepFreePreferred) {
    if (stepFree.isEmpty) {
      // Only say something when we were asked to and cannot answer. Silence
      // here would read as "no lift"; a wrong claim would be worse.
      if (accessibility == null) return null;
      return StationGuidance(
        headline: switch (phase) {
          JourneyPhase.enteringOrigin => 'Step-free entrance not mapped here',
          JourneyPhase.approachingInterchange =>
            'Step-free transfer not mapped here',
          _ => 'Step-free exit not mapped here',
        },
        liftNote: lifts > 0
            ? '$lifts lift${lifts == 1 ? '' : 's'} here, but no mapped path '
                'from a gate'
            : null,
        landmarkNote: 'Call DMRC on 155370 to check lift service',
        stepFreeUnmapped: true,
      );
    }
    final gates = stepFree.take(2).join(', ');
    return StationGuidance(
      headline: switch (phase) {
        JourneyPhase.enteringOrigin => 'Enter at $gates',
        JourneyPhase.approachingInterchange => 'Change using $gates',
        _ => 'Leave by $gates',
      },
      liftNote: 'Lift to the platform',
      platformNote: platformNote,
      stepFree: true,
    );
  }

  // Arriving: the exit engine already picked a gate, possibly matched to a
  // landmark the rider asked for. Prefer that over anything chosen here.
  if (phase == JourneyPhase.arriving && matchedExitName != null) {
    final isStepFree = exitIsStepFree(matchedExitName, accessibility);
    return StationGuidance(
      headline: 'Leave by $matchedExitName',
      liftNote: _liftNote(gateIsStepFree: isStepFree, lifts: lifts),
      landmarkNote:
          matchedLandmark == null ? null : 'Closest to $matchedLandmark',
      stepFree: isStepFree,
    );
  }

  if (exits.isEmpty) return null;

  // Otherwise lead with the exit that has the most recognisable landmarks —
  // "the one by the Red Fort" is how people actually navigate.
  final best = [...exits]..sort((a, b) =>
      ((b['landmarks'] as List?)?.length ?? 0)
          .compareTo((a['landmarks'] as List?)?.length ?? 0));
  final name = '${best.first['name']}';
  final landmarks = (best.first['landmarks'] as List? ?? const [])
      .whereType<String>()
      .take(2)
      .toList();
  if (landmarks.isEmpty && platformNote == null) return null;

  final isStepFree = exitIsStepFree(name, accessibility);
  return StationGuidance(
    headline: switch (phase) {
      JourneyPhase.enteringOrigin => 'Enter at $name',
      JourneyPhase.approachingInterchange => 'Change at $name',
      _ => 'Leave by $name',
    },
    liftNote: _liftNote(gateIsStepFree: isStepFree, lifts: lifts),
    landmarkNote: landmarks.isEmpty
        ? null
        : (phase == JourneyPhase.arriving
            ? 'Closest to ${landmarks.join(', ')}'
            : 'Near ${landmarks.join(', ')}'),
    platformNote: platformNote,
    stepFree: isStepFree,
  );
}
