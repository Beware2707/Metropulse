# Beta analytics: what's built, what's off, and what you have to decide

## The short version

The analytics pipeline is complete and **collecting nothing**. It stays that
way until two things happen, both of which are yours to authorise:

1. The privacy policy is amended (draft text below).
2. A rider turns on **Settings → Privacy → Share anonymous usage data**, which
   defaults to off.

Nothing here starts collecting on its own, and no existing installed user is
opted in by the change.

## Why it was off in the first place

Sprint 7 asked for five beta metrics. Measured against the code, exactly one
of them worked:

| Metric | Before | Why |
|---|---|---|
| Journey completion | **Yes** | `/complete` and `/abandon` are called from Journey Mode |
| Daily usage | No | the app emitted no events at all |
| Voice usage | No | speech, intent parsing and answers are all on-device |
| Search behaviour | No | `searchStations()` is pure Dart over a cached list; the server never sees a query |
| Crash reports | No | Crashlytics is wired but `google-services.json` is absent, so `_crashlyticsReady` stays false and nothing uploads |

The backend half had existed for a while — the `analytics_events` table, the
batched `POST /api/v1/analytics/events` endpoint, an admin summary, retention
pruning. The client half had never been written.

The reason it could not simply be switched on is the published privacy policy.
It enumerates what MetroPulse collects and closes that list with **"That's the
whole list."** Product analytics is not on it. (The "analytics events kept for
90 days" line under retention refers to *vehicle/feed* events — train
positions — not to anything about a rider.) Collecting usage data under a
document that says we don't would be the exact failure this project is built
to avoid, just pointed at users instead of at train data.

## What it collects, precisely

Nine event types, and the payloads are the whole of it:

| Event | Payload |
|---|---|
| `app_opened` | — |
| `journey_started` | `leg_count`, `step_free_preferred` |
| `journey_completed` / `journey_abandoned` | `elapsed_minutes` |
| `voice_intent` | `intent` (e.g. `planJourney`) |
| `voice_intent_unrecognised` | — |
| `search_selected` | `query_length`, `result_rank`, `result_count` |
| `search_abandoned` | `query_length`, `result_count` |

Plus a `session_id` that is random per app run and never persisted, so it
cannot become a stable identifier outliving the anonymous account id the
policy already discloses.

**What cannot be collected, by construction.** The recording methods take no
free text. `recordSearch*` accepts a query *length*; there is no parameter for
the query. `recordVoiceIntent` accepts an intent *name*; there is no parameter
for the transcript. This is deliberate: on a transit app the search query *is*
the destination, and a destination is the most sensitive thing a rider hands
us. A future contributor cannot leak it by accident, because there is nowhere
to put it.

## Draft privacy policy amendment

Add to **"What we collect"**:

> **Anonymous usage data — only if you turn it on.**
> If you switch on "Share anonymous usage data" in Settings, the app sends us
> a record of which features you use: when you open the app, whether a journey
> you started was finished or ended early and how long it took, which kinds of
> requests you make by voice, and how long your search text was and which
> result you picked. We do not receive what you searched for, what you said,
> or which stations you travelled between from this. It is off unless you turn
> it on, and turning it off stops it immediately and discards anything not yet
> sent. Nothing else in this policy changes if you leave it off.

Add to **"How long we keep things"**:

> Anonymous usage data: kept for 90 days, then automatically deleted.

The existing retention line should also be clarified, since it currently reads
as though it might already cover this:

> ~~Vehicle/feed analytics events: kept for 90 days~~
> **Train position and feed events (not yours): kept for 90 days, then
> automatically deleted.**

## Turning it on

1. ~~Amend the privacy policy text and bump the "as of" date.~~ **Done,
   9 August 2026** — approved by the owner. Applied to both
   `app/lib/features/legal/legal_content.dart` (the in-app screens) and
   `docs/legal/privacy_policy.md` (the hosted copy for Play Store), which are
   maintained in parallel and must not drift.
2. Ship that build. The Settings toggle is already present and still defaults
   to off — the policy says "off unless you turn it on", so the default is now
   a promise, not just a preference.
3. For beta riders, ask them directly — a toggle nobody knows about is not
   consent, it is just a defensible default. This is the remaining step.

### What the amendment changed

* "That's the whole list" now reads "One optional extra, off unless you switch
  it on: anonymous usage data about which features you use. That is the whole
  list." That sentence was the specific reason collection could not be turned
  on, so it had to be the specific thing that changed.
* A new **"Anonymous usage data — only if you turn it on"** item under *What
  we collect*, stating what is sent and — as plainly — that searches, speech,
  and travelled-between stations are not.
* Retention: a new 90-day line for usage data, and the old
  "Vehicle/feed analytics events" bullet reworded to "Train position and feed
  events (the network's, not yours)", because that phrasing was ambiguous
  enough to look like it already covered rider analytics when it never did.

The 90-day promise is kept by code that already runs: `purge_analytics` is
scheduled every 24 hours in `cli.py` against `analytics_retention_days`
(default 90). Verified rather than assumed — a retention promise with no job
behind it would be worse than no promise.

## Crash reports need something only you can do

Crashlytics is already disclosed in the current privacy policy ("Once crash
reporting is enabled..."), so no policy change is needed. What's missing is
`app/android/app/google-services.json` from your own Firebase project. Until
that file exists, `initializeCrashReporting()` catches the failure and the app
runs with crash reporting silently inert — which is the correct behaviour for
a developer without Firebase set up, and the wrong behaviour for a 30–50
person beta where crash reports are one of your five metrics.
