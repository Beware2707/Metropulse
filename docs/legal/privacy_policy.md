# MetroPulse Privacy Policy

**Last updated: 9 August 2026**

> **This is a draft.** It accurately describes what the app collects and
> does as of the date above, written by the engineering team building it —
> it has not been reviewed by a lawyer. Have it reviewed against India's
> Digital Personal Data Protection Act, 2023 (and any other laws that apply
> to where you operate) before publishing it or submitting the app to an
> app store.

## The short version

MetroPulse knows you only by an anonymous, on-device identifier — never
your name, email, or phone number. Your live location stays on your device,
with one exception you control: if you start "Share my trip", your position
is sent to our server so that whoever holds your share link can follow you,
until you stop sharing. We store your favourites, journey history, and
notification preferences so the app works the same way next time you open
it, plus anything you choose to send us directly (a crowding report, a
feedback message). Two optional extras, each off unless you switch it on:
anonymous usage data about which features you use, and station details you
volunteer after a trip. That is the whole list.

## What we collect

**An anonymous device identifier.** On first launch, the app generates a
random identifier and registers it with our server to create an account.
This identifier is not tied to your name, email address, phone number, or
any other contact information — we have no way to identify you personally
from it.

**Location, kept on your device.** If you grant location permission, the
app uses your device's location to show nearby stations and personalize
your home screen. This location is used entirely on your device and is
never transmitted to or stored on our servers. (A weather forecast for
your area is fetched directly from a third-party weather service,
described below, using your approximate location for that one request.)

**Your live position, only while you are sharing a trip.** If you tap
"Share my trip", the app sends your position to our server about every 20
seconds and we store it against that trip, so that anyone holding the share
link can follow you on a map. The link does not require an account or a
password: anyone who has it can see where you are while the trip is being
shared. Sharing stops — and the position stops being served — when you end
the trip or the share expires. This is the only situation in which your live
location leaves your device, and it never starts without you asking for it.

**Your favourites, journeys, and notification settings.** Stations you
save (like Home or Work), your journey history, and your notification
preferences are stored on our servers, tied to your anonymous device
identifier, so they're there the next time you open the app.

**Crowding reports you choose to submit.** If you report how crowded a
coach is, that report (route, coach, crowd level, and your anonymous
identifier) is stored to improve crowd predictions for other riders.

**Feedback you send us.** If you use the in-app feedback form, we store
your message, the category you picked, your app version, and your device
platform (e.g. Android or iOS), tied to your anonymous identifier, so we
can read it and, where useful, follow up on patterns across reports.

**Crash and performance data.** [Once crash reporting is enabled — see the
setup note in the engineering docs] the app sends crash reports to Google
Firebase Crashlytics when it crashes or hits a serious error. These
reports can include your device model, OS version, app version, and the
technical details of what went wrong (a stack trace) — never your name,
location, or the content of your journeys.

**Station details you choose to contribute — only if you turn it on.**
If you switch on "Help improve station info" in Settings, then after a trip
we may ask you one question — which coach you were in, which exit you used —
so we can map things DMRC has not published. Unlike the usage data below,
your answer does include the station it is about, because that is the whole
point of it. We store it with your anonymous identifier so that several
riders reporting the same thing counts once each. Every question is optional
and skippable, nothing is recorded unless you tap send, and turning the
setting off stops the questions.

**Anonymous usage data — only if you turn it on.** If you switch on "Share
anonymous usage data" in Settings, the app sends us a record of which
features you use: when you open the app, whether a journey you started was
finished or ended early and how long it took, which kinds of requests you
make by voice, and how long your search text was and which result you
picked. We do not receive what you searched for, what you said out loud, or
which stations you travelled between from this. It is off unless you turn
it on, and turning it off stops it immediately and discards anything not
yet sent.

## Third-party services we use

- **Google Firebase Crashlytics** — crash reporting, described above.
  Governed by [Google's Privacy Policy](https://policies.google.com/privacy).
- **Open-Meteo** — a free weather API. Your device calls this service
  directly with your approximate location to show today's forecast; we
  don't see or store this request on our servers.
- **Map tiles** — the live map is drawn from a map tile provider your
  device fetches tiles from directly, the same way any map app does.

We do not use advertising SDKs, and we do not sell or share your data with
data brokers or advertisers.

## How long we keep things

- Favourites, journey history, and notification preferences: kept until
  you delete them or ask us to (see below).
- Train position and feed events (the network's, not yours): kept for 90
  days, then automatically deleted.
- Anonymous usage data, if you turned it on: kept for 90 days, then
  automatically deleted.
- Station details you contributed: kept while they remain useful to other
  riders, since removing them would undo the map they helped build.
- Realtime vehicle position history: kept for 72 hours, then automatically
  deleted.
- Your position from a shared trip: a share stops being viewable 12 hours
  after you start it, or as soon as you stop sharing. Your stored position
  is then automatically erased within about a day of that.
- Feedback and crowding reports: kept indefinitely so we can track
  patterns over time, unless you ask us to delete yours.

## Your choices

- **Location** can be turned off at any time in your device settings; the
  app keeps working without it, just without nearby-station personalization.
- **Notifications** can be turned off in the app's own Settings screen.
- **Deleting your data**: the app doesn't yet have a self-serve "delete my
  account" button. Until it does, email us (see Contact below) and we'll
  delete your account and everything tied to your device identifier.

## Children's privacy

MetroPulse isn't directed at children and doesn't knowingly collect data
from anyone who identifies as under 13 (or the minimum age in your
jurisdiction). Since we never collect a name, birthdate, or contact
detail, we have no way to verify age either way — if you believe a child
has used the app and you'd like their data removed, contact us and we'll
delete it.

## Changes to this policy

If what we collect or how we use it changes, we'll update this document
and change the "Last updated" date above.

## Contact

Questions about this policy or a data deletion request:
**[support email placeholder — replace before publishing]**
