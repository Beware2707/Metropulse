# Play Store listing draft

Grounded only in features that actually ship in this app today — nothing
here describes a planned or aspirational feature. Treat this as a first
draft: proofread it yourself before submitting, and update it if features
change before launch.

## App title (30 char limit)

```
MetroPulse: Delhi Metro
```
(23 characters.)

## Short description (80 char limit)

```
Live Delhi Metro tracking, journey planning, and smart coach recommendations.
```
(77 characters.)

## Full description (4000 char limit)

```
MetroPulse is a companion app for riding the Delhi Metro — plan your
journey, track your train, and know which coach to board before you're
even on the platform.

It's an independent app, built by commuters, and is not operated by or
officially affiliated with the Delhi Metro Rail Corporation (DMRC).

LIVE TRAIN TRACKING, HONESTLY LABELLED
See trains move on a live map of the network. When a live GPS feed is
available for a line, you're watching the real thing; when it isn't,
MetroPulse tells you plainly that you're seeing a schedule-based estimate
instead of quietly guessing. You'll always know which one you're looking
at.

JOURNEY PLANNING
Search any two stations and get a clear route — interchanges, line
colours, and timing — built from the same official timetable data DMRC
publishes.

JOURNEY MODE
Once you're travelling, MetroPulse becomes a real-time companion: it
tracks which phase of the trip you're in — heading to the station,
boarding, riding, changing lines — so you always know what's next without
having to check.

COACH & EXIT RECOMMENDATIONS
Get a coach suggestion based on real crowding data and whichever exit is
closest to where you're headed at your destination. The women-reserved
coach is never recommended — full stop.

SMART COMMUTE ALERTS
Save your regular places (like Home and Work) and MetroPulse learns your
usual commute over time, nudging you with a "leave now" alert instead of
making you check the app out of habit.

COMMUTE REPLAY
A quiet, honest look back at how your recent trips actually went — not a
wall of statistics, just what happened and why.

VOICE ASSISTANT
Ask MetroPulse when your train's coming, or tell it you're running late,
hands-free.

WORKS OFFLINE
Core station and timetable data is cached on your device, so journey
planning still works even when your connection doesn't.

PRIVACY, BUILT IN
MetroPulse identifies your device with a random anonymous ID — not your
name, phone number, or email. Your location is used on-device to show
what's nearby and is never sold or used for ads, because there are no ad
SDKs in this app at all. Full details are in the in-app Privacy Policy.

Have feedback? There's a feedback form built right into Settings — we
read every one.
```
(≈2,150 characters — well under the 4,000 limit, leaving room to grow.)

## Category

Primary: **Maps & Navigation**
Alternative if that's rejected: **Travel & Local**

## Content rating questionnaire notes

- Target audience: Everyone / PEGI 3.
- No violence, gambling, user-generated public content, or chat between
  users (the feedback form is private, one-way to the developer).
- Declare **location access** (on-device only, used for "nearby" features
  and never transmitted for ads/tracking — matches the Data safety
  section below).
- No account sign-up with personal info is required to use the app (see
  [privacy_policy.md](legal/privacy_policy.md) — identity is an anonymous
  device ID).

## Data safety section (Play Console form)

Fill this in directly from [privacy_policy.md](legal/privacy_policy.md) —
don't let it drift from what that document says. As of this draft:

| Data type | Collected? | Shared? | Purpose |
|---|---|---|---|
| Approximate/precise location | Yes, on-device | No | App functionality (nearby stations, map) |
| Device or other IDs | Yes (random anonymous ID, not tied to identity) | No | App functionality, analytics |
| App interactions / crash logs | Yes (once Firebase Crashlytics is configured — see [firebase_setup.md](firebase_setup.md)) | With Firebase (Google), for crash diagnosis only | Analytics |
| Name, email, phone number | No | — | — |
| Financial info, health, contacts, photos | No | — | — |

Data is encrypted in transit (HTTPS). No self-serve in-app data deletion
exists yet — the privacy policy already discloses this honestly; Play
Console's Data safety form has a field for "how to request deletion,"
which should point to the feedback form until a self-serve flow ships.

## Still needed before submission (tracked separately)

- App icon — see task for a proposed concept (docs will note the file
  once generated).
- Screenshots — captured from the live preview once available.
- Feature graphic (1024×500) — not yet created.
- Real Android `applicationId` / iOS bundle ID — currently placeholders
  (`com.metropulse.metropulse_app` / `com.metropulse.metropulseApp`); see
  [firebase_setup.md](firebase_setup.md) for why these must be finalized
  before Firebase registration and Play Store submission, since package
  names can't change after publishing.
