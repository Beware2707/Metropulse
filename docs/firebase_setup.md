# Setting up Firebase Crashlytics

The app code is fully wired for crash reporting (`app/lib/core/crash_reporting.dart`,
called from `main()`), and stays completely inert — no crashes, no errors,
just quiet local `debugPrint` — until you complete the steps below. Nothing
breaks if you skip this; it just means you won't get crash reports yet.

## 1. Create a Firebase project

1. Go to the [Firebase console](https://console.firebase.google.com/) and
   create a new project (or use an existing one).
2. Enable **Crashlytics** for the project (Firebase console → Build →
   Crashlytics → Get started).

## 2. Register the app's Android package

The Android app was scaffolded with a placeholder package name:

```
com.metropulse.metropulse_app
```

**Change this before you register it with Firebase** — Play Store package
names are permanent once published, so pick your real one now. It's set in
two places, and both must match:

- `app/android/app/build.gradle` — the `namespace` and `applicationId` lines
- Re-run `flutter create --org <your.reverse.domain> --project-name metropulse_app .`
  from the `app/` directory to regenerate it cleanly, or edit both fields
  by hand.

Then in the Firebase console: **Add app → Android**, enter your final
package name, and download the generated **`google-services.json`**.

Place that file at:

```
app/android/app/google-services.json
```

Then add the Google Services Gradle plugin:

- In `app/android/settings.gradle` (or `build.gradle` at the project root,
  depending on your Flutter/Gradle version), add to the `plugins` block:
  ```
  id "com.google.gms.google-services" version "4.4.2" apply false
  ```
- In `app/android/app/build.gradle`, add near the top (after the Flutter/Kotlin plugins):
  ```
  id "com.google.gms.google-services"
  ```

(`flutterfire configure`, from the [FlutterFire CLI](https://firebase.google.com/docs/flutter/setup),
automates all of the above if you have the Firebase CLI installed and are
logged in — worth using instead of the manual steps if you have it handy.)

## 3. Register the app's iOS bundle ID (if you're shipping iOS too)

Same idea: **Add app → iOS** in the Firebase console with your real bundle
identifier (currently a placeholder: `com.metropulse.metropulseApp`, set in
Xcode under Runner → Signing & Capabilities, or via `ios/Runner.xcodeproj`).
Download **`GoogleService-Info.plist`** and add it to `app/ios/Runner/`
via Xcode (drag it into the Runner target so it's bundled correctly, not
just copied into the folder).

## 4. Verify

Once both config files are in place, a release build will start uploading
crash reports automatically. `kDebugMode` builds are deliberately excluded
from collection (see `crash_reporting.dart`) so your own local development
crashes don't clutter the dashboard — force a test crash from a release
build (Crashlytics' own "force a crash" test button, or a deliberate
`throw` in a button handler) to confirm it shows up in the Firebase
console within a few minutes.
