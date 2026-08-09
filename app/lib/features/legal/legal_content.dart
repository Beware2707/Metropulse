/// Structured content for the Privacy Policy / Terms of Use screens.
///
/// Kept as plain Dart data (not a rendered markdown asset) so the in-app
/// screens need no markdown-parsing dependency; the same content is
/// maintained in parallel as hostable markdown at docs/legal/ for Play
/// Store submission and any other public hosting requirement.
library;

sealed class LegalBlock {
  const LegalBlock();
}

/// A section heading.
class LegalHeading extends LegalBlock {
  const LegalHeading(this.text);
  final String text;
}

/// A plain paragraph.
class LegalParagraph extends LegalBlock {
  const LegalParagraph(this.text);
  final String text;
}

/// A bolded lead-in followed by an explanatory sentence, e.g. "**Location,
/// kept on your device.** If you grant..." -- the most common shape in
/// both documents.
class LegalItem extends LegalBlock {
  const LegalItem(this.title, this.body);
  final String title;
  final String body;
}

/// A plain bullet list.
class LegalBullets extends LegalBlock {
  const LegalBullets(this.items);
  final List<String> items;
}

/// The "this is a draft, not legal advice" callout.
class LegalNotice extends LegalBlock {
  const LegalNotice(this.text);
  final String text;
}

const String legalLastUpdated = '9 August 2026';

const List<LegalBlock> privacyPolicyBlocks = [
  LegalNotice(
    'This policy accurately describes what the app collects and does as of the date above. It '
    'is provided as-is and may be updated from time to time — always refer to the latest '
    'version shown here in the app.',
  ),
  LegalHeading('The short version'),
  LegalParagraph(
    'MetroPulse knows you only by an anonymous, on-device identifier — never your name, '
    'email, or phone number. Your live location stays on your device, with one exception you '
    'control: if you start "Share my trip", your position is sent to our server every few '
    'seconds so that whoever holds your share link can follow you, until you stop sharing. We '
    'store your favourites, journey history, and notification preferences so the app works the '
    'same way next time you open it, plus anything you choose to send us directly (a crowding '
    'report, a feedback message). Two optional extras, each off unless you switch it on: '
    'anonymous usage data about which features you use, and station details you volunteer '
    'after a trip. That is the whole list.',
  ),
  LegalHeading('What we collect'),
  LegalItem(
    'An anonymous device identifier.',
    'On first launch, the app generates a random identifier and registers it with our server '
        'to create an account. This identifier is not tied to your name, email address, phone '
        'number, or any other contact information — we have no way to identify you personally '
        'from it.',
  ),
  LegalItem(
    'Location, kept on your device — unless you share a trip.',
    "If you grant location permission, the app uses your device's location to show nearby "
        'stations and personalize your home screen. For those purposes it is used entirely on '
        'your device and is not transmitted to or stored on our servers. (A weather forecast '
        'for your area is fetched directly from a third-party weather service, described '
        'below, using your approximate location for that one request.)',
  ),
  LegalItem(
    'Your live position, only while you are sharing a trip.',
    'If you tap "Share my trip", the app sends your position to our server about every 20 '
        'seconds and we store it against that trip, so that anyone holding the share link can '
        'follow you on a map. The link does not require an account or a password: anyone who '
        'has it can see where you are while the trip is being shared. We keep the most recent '
        'position for the life of the share; sharing stops — and the position stops being '
        'served — when you end the trip or the share expires. This is the only situation in '
        'which your live location leaves your device, and it never starts without you asking '
        'for it.',
  ),
  LegalItem(
    'Your favourites, journeys, and notification settings.',
    'Stations you save (like Home or Work), your journey history, and your notification '
        'preferences are stored on our servers, tied to your anonymous device identifier, so '
        "they're there the next time you open the app.",
  ),
  LegalItem(
    'Crowding reports you choose to submit.',
    'If you report how crowded a coach is, that report (route, coach, crowd level, and your '
        'anonymous identifier) is stored to improve crowd predictions for other riders.',
  ),
  LegalItem(
    'Feedback you send us.',
    'If you use the in-app feedback form, we store your message, the category you picked, '
        'your app version, and your device platform (e.g. Android or iOS), tied to your '
        'anonymous identifier, so we can read it and, where useful, follow up on patterns '
        'across reports.',
  ),
  LegalItem(
    'Crash and performance data.',
    'Once crash reporting is enabled, the app sends crash reports to Google Firebase '
        'Crashlytics when it crashes or hits a serious error. These reports can include your '
        'device model, OS version, app version, and the technical details of what went wrong '
        '(a stack trace) — never your name, location, or the content of your journeys.',
  ),
  LegalItem(
    'Station details you choose to contribute — only if you turn it on.',
    'If you switch on "Help improve station info" in Settings, then after a '
        'trip we may ask you one question — which coach you were in, which '
        'exit you used — so we can map things DMRC has not published. Unlike '
        'the usage data below, your answer does include the station it is '
        'about, because that is the whole point of it. We store it with your '
        'anonymous identifier so that several riders reporting the same thing '
        'counts once each. Every question is optional and skippable, nothing '
        'is recorded unless you tap send, and turning the setting off stops '
        'the questions.',
  ),
  LegalItem(
    'Anonymous usage data — only if you turn it on.',
    'If you switch on "Share anonymous usage data" in Settings, the app sends us a record of '
        'which features you use: when you open the app, whether a journey you started was '
        'finished or ended early and how long it took, which kinds of requests you make by '
        'voice, and how long your search text was and which result you picked. We do not '
        'receive what you searched for, what you said out loud, or which stations you '
        'travelled between from this. It is off unless you turn it on, and turning it off '
        'stops it immediately and discards anything not yet sent.',
  ),
  LegalHeading('Third-party services we use'),
  LegalBullets([
    'Google Firebase Crashlytics — crash reporting, described above, governed by Google\'s '
        'Privacy Policy.',
    'Open-Meteo — a free weather API. Your device calls this service directly with your '
        "approximate location to show today's forecast; we don't see or store this request on "
        'our servers.',
    'Map tiles — the live map is drawn from a map tile provider your device fetches tiles '
        'from directly, the same way any map app does.',
  ]),
  LegalParagraph(
    'We do not use advertising SDKs, and we do not sell or share your data with data brokers '
    'or advertisers.',
  ),
  LegalHeading('How long we keep things'),
  LegalBullets([
    'Favourites, journey history, and notification preferences: kept until you delete them '
        'or ask us to (see below).',
    'Train position and feed events (the network\'s, not yours): kept for 90 days, then '
        'automatically deleted.',
    'Anonymous usage data, if you turned it on: kept for 90 days, then automatically '
        'deleted.',
    'Station details you contributed: kept while they remain useful to other riders, since '
        'removing them would undo the map they helped build.',
    'Train position history: kept for 72 hours, then automatically deleted. (This is the '
        "trains' positions, not yours.)",
    'Your position from a shared trip: a share stops being viewable 12 hours after you start '
        'it, or as soon as you stop sharing. Your stored position is then automatically '
        'erased within about a day of that.',
    'Feedback and crowding reports: kept indefinitely so we can track patterns over time, '
        'unless you ask us to delete yours.',
  ]),
  LegalHeading('Your choices'),
  LegalItem(
    'Location',
    'can be turned off at any time in your device settings; the app keeps working without '
        'it, just without nearby-station personalization.',
  ),
  LegalItem('Notifications', "can be turned off in the app's own Settings screen."),
  LegalItem(
    'Deleting your data',
    "the app doesn't yet have a self-serve \"delete my account\" button. Until it does, email "
        "us (see Contact below) and we'll delete your account and everything tied to your "
        'device identifier.',
  ),
  LegalHeading("Children's privacy"),
  LegalParagraph(
    "MetroPulse isn't directed at children and doesn't knowingly collect data from anyone who "
    'identifies as under 13 (or the minimum age in your jurisdiction). Since we never collect '
    'a name, birthdate, or contact detail, we have no way to verify age either way — if you '
    "believe a child has used the app and you'd like their data removed, contact us and we'll "
    'delete it.',
  ),
  LegalHeading('Changes to this policy'),
  LegalParagraph(
    "If what we collect or how we use it changes, we'll update this document and change the "
    '"Last updated" date above.',
  ),
  LegalHeading('Contact'),
  LegalParagraph(
    'Questions about this policy or data-deletion requests: riddlesforeverbiz@gmail.com',
  ),
];

const List<LegalBlock> termsOfUseBlocks = [
  LegalNotice(
    'These terms are provided as-is and may be updated from time to time — always refer to the '
    'latest version shown here in the app.',
  ),
  LegalHeading('Acceptance'),
  LegalParagraph(
    "By using MetroPulse, you agree to these terms. If you don't agree, please don't use the "
    'app.',
  ),
  LegalHeading('What MetroPulse is'),
  LegalParagraph(
    'MetroPulse is a companion app for the Delhi Metro: journey planning, live train '
    'tracking, coach and exit recommendations, and commute predictions. It is an independent '
    'app and is not operated by, or officially affiliated with, the Delhi Metro Rail '
    'Corporation (DMRC).',
  ),
  LegalHeading('Accuracy of information — please read this one'),
  LegalParagraph(
    'We build every estimate in this app from real data — the official static timetable, '
    'historical journey durations, and (when a licensed live feed is available) live vehicle '
    "positions — and we label each one honestly, e.g. whether a train's position on the map "
    'is live GPS or estimated from the schedule. But:',
  ),
  LegalBullets([
    'Real-time information may be delayed, unavailable, or wrong. Train positions, delay '
        'estimates, and crowding levels are best-effort predictions, not guarantees.',
    'Always follow official DMRC signage, staff instructions, and announcements over anything '
        'shown in this app, especially for safety information, service disruptions, fare '
        'rules, or coach reservations (e.g. women-reserved coaches).',
    "Don't rely on this app as your only source of information for time-critical travel.",
  ]),
  LegalHeading('Your responsibilities'),
  LegalBullets([
    'Use the app for its intended purpose: planning and following your metro journeys.',
    "Don't submit false, abusive, or misleading crowding reports or feedback.",
    "Don't attempt to interfere with, reverse-engineer, or overload the service.",
    "You're responsible for your own safety on the platform and in the train — the app is a "
        'companion, not a substitute for attention to your surroundings.',
  ]),
  LegalHeading('Accounts'),
  LegalParagraph(
    'Your account is anonymous, identified only by a device-generated token (see the Privacy '
    "Policy for what that means). You're responsible for anything associated with your "
    "device's account.",
  ),
  LegalHeading('Beta status'),
  LegalParagraph(
    'MetroPulse is in beta. Features may change, break, or be removed without notice, and we '
    'may reset data during this period if needed to fix a serious issue. We\'ll try to avoid '
    'this, but it\'s a real possibility during beta and you should not treat the app as '
    'production-stable yet.',
  ),
  LegalHeading('No warranty'),
  LegalParagraph(
    'The app is provided "as is," without warranties of any kind, express or implied, '
    'including accuracy, availability, or fitness for a particular purpose.',
  ),
  LegalHeading('Limitation of liability'),
  LegalParagraph(
    "To the maximum extent permitted by law, MetroPulse's developers are not liable for any "
    'indirect, incidental, or consequential damages arising from your use of the app, '
    'including missed trains, delays, or reliance on an estimate that turned out to be wrong.',
  ),
  LegalHeading('Changes to these terms'),
  LegalParagraph(
    'We may update these terms as the app changes. Continuing to use the app after an update '
    'means you accept the revised terms.',
  ),
  LegalHeading('Governing law'),
  // NOTE (not user-visible): a lawyer should confirm the correct governing law and
  // jurisdiction before public launch; India / Delhi is a sensible default given the
  // app's subject matter and user base.
  LegalParagraph(
    'These terms are governed by the laws of India, and any disputes are subject to the '
    'exclusive jurisdiction of the courts of Delhi.',
  ),
  LegalHeading('Contact'),
  LegalParagraph('Questions about these terms: riddlesforeverbiz@gmail.com'),
];
