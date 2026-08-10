# MetroPulse — DMRC / MICE submission package

Everything in this folder is generated from the MetroPulse repository. No figure
appears in any document unless it is recorded in `mice/facts.py` with a source
that can be re-checked, and anything unmeasured is shown as a visible
placeholder rather than an estimate.

Regenerate the whole package:

```bash
.venv/Scripts/python.exe docs/mice_submission/build.py
```

## Files

| File | What it is |
|---|---|
| `MetroPulse_MICE_Pitch_Deck.pptx` | 16-slide deck, editable |
| `MetroPulse_MICE_Pitch_Deck.pdf` | The same deck as PDF |
| `MetroPulse_MICE_Project_Proposal.docx` | Main proposal, editable |
| `MetroPulse_MICE_Project_Proposal.pdf` | The same proposal as PDF |
| `MetroPulse_Technical_Architecture.pdf` | System design and the realtime seam |
| `MetroPulse_OTD_Data_Integration.pdf` | Which official datasets are loaded, and what they omit |
| `MetroPulse_Commuter_Testing_Report.pdf` | Automated coverage and the 25-rider commuter trial |
| `MetroPulse_Crowd_Management_Proposal.pdf` | Data → intelligence → passenger instruction |
| `MetroPulse_Realtime_Data_Request.pdf` | What is requested from DMRC, and why |
| `MetroPulse_MICE_Pilot_Proposal.pdf` | Four phases, each with an exit check |
| `MetroPulse_Founder_Profile.pdf` | Self-reported background, kept separate from project evidence |
| `MetroPulse_Roadmap.pdf` | Ordered by dependency, not by date |
| `MetroPulse_Document_Status.pdf` | Index and honest completion status |
| `MetroPulse.apk` | Installable release build |
| `assets/` | Product screenshots from the release build |
| `qa/` | Rendered page images used for visual checking |

Everything in that table except `assets/` is a build output and is gitignored —
`build.py` reproduces the documents from `mice/`, and the 88 MB APK does not
belong in git. Copy the APK in before sending the package.

## Still to be supplied manually

Three figures do not exist anywhere and have **not** been invented.

| Item | Appears in | Placeholder |
|---|---|---|
| Journey completion rate | Testing Report, Proposal §12 | `[DATA REQUIRED]` |
| Retention | Testing Report, Proposal §12 | `[DATA REQUIRED]` |
| Crash-free rate | Testing Report, Proposal §12 | `[DATA REQUIRED]` |

All three need the same thing: the opt-in analytics build in riders' hands,
which in turn needs the privacy policy amendment published. They cannot be
filled in from the 25-rider trial, because that trial was defect-driven and the
analytics pipeline was switched off.

To supply any of them, edit `mice/facts.py` — every document reads from there —
and regenerate.

### Founder background

Supplied from the founder's résumé on 2026-08-11 and now complete. Those fields
are **self-reported**, unlike everything else in the package, so the Founder
Profile puts them in their own table under a heading that says so and keeps the
repository-verifiable claims separate underneath. Keep that separation if you
edit the document.

## Claims discipline

Applied consistently across all 13 documents:

- **No invented features.** Every capability described is present in the repository.
- **No invented numbers.** Counts come from the loaded data artifacts, the test
  suites, or the deployed backend.
- **No realtime claim.** MetroPulse is never described as having official
  realtime Delhi Metro data. The pitch deck states this on slide 1.
- **No escalator claim.** All five normalized OTD artifacts contain zero
  escalator records, so escalator guidance is absent from the product and from
  these documents. It is listed as data requested from DMRC instead.
- **No fabricated company documents.** MetroPulse is not incorporated and holds
  no DPIIT registration; no financials or certificates exist or are implied.

Every capability carries one of five labels:

| Label | Meaning |
|---|---|
| `IMPLEMENTED` | Built, running, covered by tests today |
| `APPROVED DATA` | Official OTD already loaded and served |
| `IN DEVELOPMENT` | Partially built, or not yet device-verified |
| `PROPOSED` | Not built; offered as a plan |
| `REQUIRES DMRC DATA` | Cannot be built or validated without DMRC |

## How it is built

| Module | Responsibility |
|---|---|
| `mice/facts.py` | Every figure, with its provenance. The single source of truth. |
| `mice/theme.py` | Palette, typography, and the five status colours |
| `mice/scene.py` | Scene graph plus PPTX and PDF renderers for the deck |
| `mice/deck.py` | The 16 slides |
| `mice/report.py` | A4 report framework — cover, tables, callouts, status rows |
| `mice/documents.py` | The nine supporting PDFs |
| `mice/proposal.py` | The proposal, rendered to both DOCX and PDF |

The deck and the proposal are each **defined once and rendered twice**. There is
no LibreOffice in the build environment, so the PDFs cannot be produced by
converting the Office files — and writing each twice would guarantee they drift.
A submission whose slides and PDF disagree is worse than either alone.
