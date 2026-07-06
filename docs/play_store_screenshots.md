# Play Store screenshots

Five screens were captured live from the running app (Flutter web preview,
375×812 viewport — phone aspect ratio), each showing a real feature with
real data from the dev backend, not staged/mocked content:

1. **Home** — the "leave now" nudge, coach badge, favourites, nearby
   prompt, and voice CTA all in one glance.
2. **Journey planner** — a real planned route (Dwarka Sector-21 → New
   Delhi): travel time, arrival, fare estimate, stop count, and the
   cleaned-up line name ("Airport Express Line", not the raw
   `ORANGE/AIRPORT_...` GTFS string).
3. **Journey Mode (flagship)** — an in-progress trip: live phase
   ("Entering the station"), coach recommendation (never the
   women-reserved coach), platform direction, and a crowding estimate.
4. **Where you've been** — the Commute Replay narrative summary (real
   trip count, savings vs. ride-hailing, CO2 avoided, with an honest
   "estimated by comparing..." disclosure) plus trip history.
5. **Saved** — Home/Work places and a pinned journey, supporting the
   "save your regular places" pitch in the listing copy.

## What's deliberately not included: Explore / Live map

The live map currently renders against MapLibre's public **demo-tiles**
style (`https://demotiles.maplibre.org/style.json`), a dependency-free
placeholder — see `AppConfig.mapStyleUrl` in
[`app/lib/core/config.dart`](../app/lib/core/config.dart), overridable via
`--dart-define=MP_MAP_STYLE=...`. It shows real train positions and line
paths, but the basemap underneath is just a flat demo fill, not a real
street/terrain map — screenshotting it now would misrepresent what the
map looks like with a real tile provider configured. Capture this
screenshot once a real `MP_MAP_STYLE` (e.g. MapTiler or Mapbox, both
require a free API key/account — your call, not something to sign up for
without asking) is wired in.

## Before actually uploading to Play Console

These are composition/content references at web-preview resolution, not
final device captures. For the real listing, re-capture the same five
flows from an actual Android emulator or device build (once the real
`applicationId` is set — see [firebase_setup.md](firebase_setup.md)) at
Play Console's required sizes (minimum 320px, JPEG/PNG, 16:9–9:16 aspect).
The flows and framing above are exactly what to re-shoot.
