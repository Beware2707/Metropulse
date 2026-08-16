# MetroPulse — DMRC / MICE submission

A working Delhi Metro journey companion, submitted as a MICE pre-application /
innovation proposal.

**MetroPulse does not have official realtime Delhi Metro data.** That is stated
on the first slide, in the product itself, and throughout these documents. What
it has is a working application on approved Open Transit Data, a realtime
architecture with only the feed missing, and 25 commuters who used it and
reported defects that were then fixed.

## Read in this order

| # | File | Read it for |
|---|---|---|
| 1 | `Pitch_Deck.pdf` | The whole case in twenty slides |
| 2 | `Project_Proposal.pdf` | The detail behind every slide |
| 3 | `Demo/` | The APK, and a five-minute walkthrough |
| 4 | `Realtime_Data_Request.pdf` | Exactly what is asked of DMRC, and why |
| 5 | `Pilot_Proposal.pdf` | The ninety-day pilot and how it would be judged |

## Everything in the folder

| File | What it is |
|---|---|
| `Pitch_Deck.pptx` / `.pdf` | 20 slides, editable and as PDF |
| `Project_Proposal.docx` / `.pdf` | 24 sections, editable and as PDF |
| `Technical_Architecture.pdf` | System design and the realtime seam |
| `OTD_Data_Integration.pdf` | Which official datasets are loaded, and what they omit |
| `Commuter_Validation.pdf` | Automated coverage and the 25-rider trial |
| `Crowd_Management.pdf` | Data → intelligence → one passenger instruction |
| `Realtime_Data_Request.pdf` | What is requested from DMRC, and the evidence for why |
| `Pilot_Proposal.pdf` | Five stages, five exit checks, and the KPIs |
| `Risk_and_Mitigation.pdf` | Every foreseeable risk and what handles it |
| `Founder_Profile.pdf` | Self-reported background, kept separate from project evidence |
| `Roadmap.pdf` | Ordered by dependency, not by date |
| `Document_Status.pdf` | Index and honest completion status |
| `Demo/` | Release APK, screenshots, and a walkthrough |

## Claims discipline

Every capability in every document carries exactly one of five labels:

| Label | Meaning |
|---|---|
| `IMPLEMENTED` | Built, running, covered by tests today |
| `APPROVED DATA` | Official OTD already loaded and served |
| `IN DEVELOPMENT` | Partially built, or not yet device-verified |
| `PROPOSED` | Not built; offered as a plan |
| `REQUIRES DMRC DATA` | Cannot be built or validated without DMRC |

And the rules that produced them:

- **No invented numbers.** Every figure comes from a loaded data artifact, a
  test suite, or the deployed backend. Anything unmeasured is shown as
  `[DATA REQUIRED]` rather than estimated.
- **No realtime claim.** MetroPulse is never described as having official
  realtime Delhi Metro data.
- **No escalator claim.** All five normalized OTD artifacts contain zero
  escalator records, so escalator guidance is absent from the product and from
  these documents. It is requested from DMRC instead.
- **No company claims.** MetroPulse is not incorporated and holds no DPIIT or
  startup registration. No financials, certificates or client references exist
  or are implied.
- **No claimed DMRC relationship.** Nothing here implies approval, partnership
  or endorsement.

The build checks the last four automatically against the rendered text of every
PDF, so a claim cannot creep back in through an edit.

## The public feed question, settled

The Open Transit Data `VehiclePositions` endpoint is the obvious place to get
Metro positions, and it would have been easy to present it as such. It was
measured instead. In one capture:

| Measurement | Result |
|---|---|
| Vehicles reporting | 3,476, within an 11-minute window |
| Identifiers matching an Indian road number plate | 3,476 of 3,476 |
| Vehicles resolving to a Metro route | 0 |
| Median distance to the nearest Metro station | 720 m |
| Within 50 m of any Metro station | 1.0% |
| Furthest vehicle from the network | 30.5 km |
| Distinct route IDs vs the DMRC GTFS feed | 1,107 vs 36 |

It is Delhi's citywide bus GPS. MetroPulse ships with realtime ingestion
disabled rather than showing buses as trains.

## Still to be supplied

Three figures do not exist anywhere and have not been invented:

| Item | Placeholder |
|---|---|
| Journey completion rate | `[DATA REQUIRED]` |
| Retention | `[DATA REQUIRED]` |
| Crash-free rate | `[DATA REQUIRED]` |

All three need the same thing: the opt-in analytics build in riders' hands. They
cannot be filled in from the 25-rider trial, because that trial was
defect-driven and the analytics pipeline was switched off. Measuring them is the
purpose of the commuter-pilot stage.

Founder background is self-reported, unlike everything else here, and the
Founder Profile keeps it in its own section under a heading that says so.

The QR codes on the closing slide and in the Technical Architecture document
point to `github.com/Beware2707/Metropulse`, which is public and was verified
reachable at build time. The signed APK is also published there as release
`v1.0.0-mice`, so a reviewer who scans the QR is one click from installing.

## Contact

Jai Pratap Singh · +91 91037 52190 · riddlesforeverbiz@gmail.com

---

*Regenerate this package with* `.venv/Scripts/python.exe docs/mice_submission/build.py`
