# Bundled Plus Jakarta Sans weights

`google_fonts` prioritizes a matching font file found here over fetching it
from the network at runtime — this is what avoids the first-paint
font-swap flash on a cold start (see `lib/core/design/app_typography.dart`).

Download these 4 files from https://fonts.google.com/specimen/Plus+Jakarta+Sans
(the "Download family" button gives you the full set — you only need these
four) and drop them in this folder **without renaming them**, since
`google_fonts` matches by the exact filenames Google Fonts itself uses:

- `PlusJakartaSans-Medium.ttf` (weight 500)
- `PlusJakartaSans-SemiBold.ttf` (weight 600)
- `PlusJakartaSans-Bold.ttf` (weight 700)
- `PlusJakartaSans-ExtraBold.ttf` (weight 800)

These are the only four weights `app_typography.dart` actually requests —
every other weight in the downloaded family can be discarded. No code
changes are needed once the files are here; `pubspec.yaml` already declares
this folder as an asset directory.

## The trap

That "only four weights" claim is only true because `app_typography.dart`
builds every style *directly* with `GoogleFonts.plusJakartaSans(fontWeight:
...)`. It is easy to undo by accident.

It previously started from `GoogleFonts.plusJakartaSansTextTheme()` and
`copyWith`'d the weights on afterwards. That reads as equivalent and isn't:
the helper resolves Material's *default* text theme first, and those defaults
are largely Regular (w400) — which we don't bundle. So the app fired an HTTP
request to `fonts.gstatic.com` on every cold start, and offline it silently
fell back to Roboto. Nothing failed loudly; it just quietly wasn't the font.

So: don't reach for the `...TextTheme()` helpers, and only request a weight
that has a file in this folder. `test/flutter_test_config.dart` sets
`GoogleFonts.config.allowRuntimeFetching = false`, so if a stray weight
creeps back in, the tests render it in the fallback font rather than papering
over it with a download.
