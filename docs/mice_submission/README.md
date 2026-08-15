# MetroPulse MICE submission — build directory

The package a reviewer receives is **`MetroPulse_MICE_FINAL/`**. This directory
is how it gets made.

```bash
.venv/Scripts/python.exe docs/mice_submission/build.py
```

That writes all fourteen documents plus `Demo/` and `README.md`, then checks the
result and exits non-zero if a check fails.

## What is here

| Path | Role |
|---|---|
| `mice/facts.py` | Every figure, with its provenance. The single source of truth. |
| `mice/theme.py` | Palette, typography, and the five status colours |
| `mice/scene.py` | Scene graph plus PPTX and PDF renderers for the deck |
| `mice/deck.py` | The 20 slides |
| `mice/report.py` | A4 report framework — cover, tables, callouts, status rows |
| `mice/documents.py` | The ten supporting PDFs |
| `mice/proposal.py` | The proposal, rendered to both DOCX and PDF |
| `assets/` | Product screenshots, captured from the release build |
| `demo_walkthrough.md` | Becomes `MetroPulse_MICE_FINAL/Demo/README.md` |
| `MetroPulse_MICE_FINAL_README.md` | Becomes `MetroPulse_MICE_FINAL/README.md` |
| `MetroPulse.apk` | Signed release build, copied into `Demo/` |
| `MetroPulse_MICE_FINAL/` | Build output. Regenerated wholesale; do not edit by hand. |

Only `mice/`, `assets/`, the two markdown sources, and `build.py` are inputs.
Everything in `MetroPulse_MICE_FINAL/` is derived, so an edit made there is lost
on the next build — change the source and rebuild instead.

## The rules the build enforces

`build.py` reads the rendered text of every PDF — not the source — and fails on:

- any banned claim (official realtime data, DMRC approval or partnership,
  company registration, DPIIT recognition);
- any bracketed placeholder other than the two declared ones.

Reading the rendered text matters: the claim that counts is the one a reviewer
sees, and prose assembled from three f-strings can say something no single
source line does.

`_renumber()` in `mice/proposal.py` numbers the sections at build time. They
used to be literal strings, so inserting a section meant editing every heading
after it, and the appendix cross-references drifted the first time that was
missed.

## Adding or changing a figure

Add it to `mice/facts.py` with a source that can be re-checked, then reference
it with `f("key")`. Nothing should be typed as a literal number in a document —
if a figure appears in two documents it must come from one place, or the two
will disagree eventually.

If a figure cannot be measured, use `DATA_REQUIRED` rather than an estimate, and
list it in `MetroPulse_MICE_FINAL_README.md` so the reviewer knows it is missing
on purpose.

## Screenshots

`assets/` holds twelve screens captured from the release build running against
the deployed backend. They were taken outside Metro operating hours, so
time-dependent panels show their empty state — which is correct behaviour, and
noted in the demo walkthrough. Recapturing during service hours (roughly
08:00–22:00 IST) would show scheduled arrivals in those panels.

To recapture, install the APK on a device or emulator and use
`adb exec-out screencap -p > assets/<name>.png`.
