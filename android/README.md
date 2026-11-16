# Kotsu for Android

Native Kotlin + Jetpack Compose app. The PC version stays in Python.

- `core/` is a pure Kotlin copy of the Python domain rules (quick line, currency,
  installment dates, recurrence, stamps, merge, check code, exchange file) plus `Book`, the
  phone's database (D43). Its tests run the shared cases in `../vectors/*.json`, generated from
  the Python domain by `tools/generate_vectors.py`. If a rule changes in Python, regenerate
  the vectors and the Kotlin tests will fail until `core/` matches.
- `app/` is the Compose UI: the main screen in the Cotton Candy theme (night and light,
  ⋯ menu or `t`), the quick line with a live preview, and the dialogs. Data is saved in
  `kotsu.json` in the app's private folder after every change.

## Exchange with the PC

On the phone: ⋯ → export exchange file, save it (e.g. to Drive), then on the PC
`kotsu --import FILE`. The other way: `kotsu --export FILE` on the PC, ⋯ → import exchange
file on the phone. ⋯ → check code must equal the PC's (key `v`).

Deleted entries stay deleted when you import (the deletion is newer than the file). To get
them back from an older file or backup, import it: the phone counts what the file has that
was deleted here and offers **restore**. Restored entries get a new stamp, so the next
exchange brings them back on the PC too.

To delete an account, long-press it in the accounts area: it goes with all its entries
(after asking), and the next exchange removes it from the PC too.

Tap the month at the top to pick any month and year (‹ › change the year; **today** goes
back to the current month).

To see one category in the month, tap **# category ▾** above the entries (or ⋯ → filter
by category, or tap the category on an entry).

Locally, the core tests need only the JVM and Maven Central:
`gradle -p android :core:test` (the app needs the Android SDK and Google Maven).

## Release APK

Signed release APKs are attached to the [Releases](https://github.com/Sera-DAI/kotsu/releases)
page with `android-vX.Y.Z` tags. They are signed with one fixed key kept by the maintainer
(never in this repository), so each version installs as an update and keeps your data.
Debug APKs from CI are for tests only: each one has a different throwaway key.

## Build

The `android` workflow runs the core tests and builds a debug APK on every push that
touches `android/` or `vectors/`. Download it from the run's **Artifacts**
(`kotsu-android-debug`) and install it on the phone (allow installs from unknown sources).

Locally, with JDK 17, Gradle 8.11 and the Android SDK:

```
gradle -p android :core:test :app:assembleDebug
```
