# App icon

The launcher icon is generated, not hand-drawn per platform. Source of
truth is the vector at `app/assets/icon/app_icon.svg` — an "M" whose
middle stroke breaks into an ECG pulse blip (Metro + Pulse in one mark),
on the app's existing brand gradient (`AppColors.heroGradientFor()`,
`#3D7FFF → #8B5CF6` — the same gradient behind the splash wordmark and
every onboarding slide icon).

## Why three PNGs, not one

iOS and Android both apply their own icon mask (rounded square, circle,
squircle, ...) at install/display time. A source image with baked-in
corner rounding or transparency is wrong for both — Apple rejects it in
review, and it double-masks or shows square corners through a differently
shaped Android launcher mask. So there are three rasters, all derived from
the same SVG, each full-bleed with no pre-applied rounding:

- `app_icon.png` — flat 1024×1024, opaque, full gradient + glyph. Used for
  iOS and Android's legacy (pre-adaptive-icon) launcher icon.
- `app_icon_background.png` — the gradient alone, no glyph. Android
  adaptive icon background layer.
- `app_icon_foreground.png` — the glyph alone on a transparent 1024×1024
  canvas, positioned inside Android's adaptive-icon safe zone (centered,
  within the inner ~66%, so it isn't clipped by any mask shape). Android
  adaptive icon foreground layer.

These were rasterized from the SVG via a headless-Chromium screenshot
(`msedge --headless=new --window-size=1024,1024 --screenshot=...`), since
this environment has no SVG-to-PNG tool installed (no ImageMagick/
Inkscape/cairosvg). If you edit `app_icon.svg`, regenerate all three the
same way — width/height fixed at 1024×1024, `--default-background-color
=00000000` for the transparent foreground render only.

## Wiring

`pubspec.yaml` has a `flutter_launcher_icons:` config block pointing at
the three PNGs above, plus `flutter_launcher_icons` as a dev dependency.
To regenerate every platform size after changing the source images:

```
cd app
flutter pub get
dart run flutter_launcher_icons
```

This writes the Android `mipmap-*/ic_launcher.png` +
`mipmap-anydpi-v26/launcher_icon.xml` + adaptive-icon drawables, and the
full iOS `Assets.xcassets/AppIcon.appiconset`, and updates
`AndroidManifest.xml`'s `android:icon` to point at the new icon. Run
`flutter analyze` afterwards — the tool only touches generated platform
assets, but it's a cheap check.

## Before Play Store / App Store submission

The icon itself doesn't block anything, but remember the Android
`applicationId` / iOS bundle identifier are still placeholders (see
[firebase_setup.md](firebase_setup.md)) — finalize those first, since
regenerating platform folders after changing them can require re-running
the steps above.
