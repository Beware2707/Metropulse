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
