# MetroPulse — demo

Everything here is the real product. The APK is the signed release build, and
the screenshots are captured from it running against the deployed backend.

## Run it yourself

1. Install `MetroPulse.apk` on any Android 8.0 or newer device — from this
   folder, or downloaded directly from the signed release:
   <https://github.com/Beware2707/Metropulse/releases/download/v1.0.0-mice/MetroPulse.apk>
2. Open it. No account, no sign-up, no permission is required to start.

The app talks to the deployed backend over the internet. Nothing else is
needed.

## A five-minute walkthrough

| Step | What to do | What to notice |
|---|---|---|
| 1 | Open the app | The badge reads **SCHEDULE**, never LIVE. That is the honest state: there is no realtime Metro feed. |
| 2 | Search `dwarka` | `Dwarka Sector - 10` appears even though you did not type the hyphen. This was one of the defects the commuter trial found. |
| 3 | Open any station | During service hours **Arriving now** lists the next trains by line, each carrying *"estimated from the schedule, not live GPS"*. The caveat is on the screen, not buried in a policy. |
| 4 | Scroll to **Step-free access** | Where DMRC's pathway data confirms a lift-served route it says so; where it does not, it says *"partly mapped"* and offers DMRC's lift helpline rather than guessing. |
| 5 | Plan a journey | Four preferences, including **Step-free friendly**. The result shows travel time, fare estimate and interchanges, each labelled as an estimate. |
| 6 | Open **Explore** | The octilinear network schematic, with the same schedule caveat above it. |
| 7 | Tap the microphone | The assistant asks for permission at the point of use, not at install. It answers Delhi Metro questions only, on-device. |

## What you will *not* see, and why

**Live train positions.** There is no DMRC realtime feed, so there are none.
What the app shows instead are positions interpolated from the published
timetable — 293 of them at 22:31 IST on 14 August 2026, which is why the
network map carries train counts and the station screen lists arrivals. Every
one is labelled SCHEDULE.

Outside Metro operating hours those panels are empty, which is correct rather
than broken: the last trains run around 23:00 and nothing is moving at 03:00.

The public Open Transit Data `VehiclePositions` endpoint was tested and is not
Metro data: in one capture, all 3,476 reporting vehicles carried road
registration plates, none resolved to a Metro route, and the median vehicle was
720 m from the nearest Metro station. It is Delhi's citywide bus feed.
MetroPulse ships with realtime ingestion disabled rather than showing buses as
trains. `Realtime_Data_Request.pdf` covers this in full.

**Crowd predictions with real numbers.** No occupancy data exists in the
approved datasets, so crowd guidance falls back to a generic prior and is
labelled as such.

## Source

The implementation lives at `github.com/Beware2707/Metropulse` — architecture,
tests and both applications, open for technical review. The installable build
is published there as release `v1.0.0-mice`.

## Screenshots

In `Screenshots/`, all from the release build:

| File | Screen |
|---|---|
| `home.png` | Home — context, weather and air quality before search |
| `search.png` | Station search |
| `search_hyphen_fix.png` | The hyphen-matching defect, fixed |
| `planner.png` | Journey planner with route preferences |
| `journey_mode.png` | Journey Mode — guidance during the trip |
| `station_detail.png` | Station detail with the schedule caveat |
| `accessibility.png` | Facilities and step-free evidence tiers |
| `network_map.png` | Octilinear network schematic |
| `voice.png` | Metro Assistant |
| `permission_prompt.png` | Microphone permission, asked at point of use |
| `settings_privacy.png` | Privacy settings |
| `tickets.png` | Ticketing links |

Screenshots were captured on 14 August 2026 at around 22:30 IST — inside
service hours — so the arrival and network panels show real scheduled
positions rather than an empty state.
