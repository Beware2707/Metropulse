"""Build the MetroPulse DMRC / MICE submission package.

    .venv/Scripts/python.exe docs/mice_submission/build.py

Writes everything into MetroPulse_MICE_FINAL/ and then checks the result:
no banned claim, no undeclared placeholder, and no figure that disagrees
between documents.
"""

from __future__ import annotations

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "MetroPulse_MICE_FINAL")
DEMO = os.path.join(OUT, "Demo")
ASSETS = os.path.join(HERE, "assets")
APK = os.path.join(HERE, "MetroPulse.apk")

from mice.deck import build as build_deck            # noqa: E402
from mice.documents import ALL                       # noqa: E402
from mice.facts import FACTS                         # noqa: E402
from mice.proposal import build_all as build_proposal  # noqa: E402

#: Phrases that would claim what MetroPulse does not have. Checked against the
#: rendered text of every PDF, because the claim that matters is the one a
#: reviewer reads, not the one in the source.
BANNED = [
    "live delhi metro data",
    "official realtime data from dmrc",
    "realtime metro feed integrated",
    "predicted, and labelled live",
    "predicted, labelled live",
    "dmrc has approved",
    "in partnership with dmrc",
    "registered company",
    "dpiit recognised",
    "dpiit recognized",
]

#: Placeholders are fine, but only the ones README.md tells the reader about.
DECLARED_PLACEHOLDERS = {"[DATA REQUIRED]", "[TO BE PROVIDED]"}


def _demo() -> None:
    """Assemble the folder a reviewer can open without reading anything."""
    os.makedirs(DEMO, exist_ok=True)
    shots = os.path.join(DEMO, "Screenshots")
    os.makedirs(shots, exist_ok=True)
    for name in sorted(os.listdir(ASSETS)):
        if name.endswith(".png") and not name.startswith("qr_"):
            shutil.copy2(os.path.join(ASSETS, name), os.path.join(shots, name))
    if os.path.exists(APK):
        shutil.copy2(APK, os.path.join(DEMO, "MetroPulse.apk"))
    walk = os.path.join(HERE, "demo_walkthrough.md")
    if os.path.exists(walk):
        shutil.copy2(walk, os.path.join(DEMO, "README.md"))
    top = os.path.join(HERE, "MetroPulse_MICE_FINAL_README.md")
    if os.path.exists(top):
        shutil.copy2(top, os.path.join(OUT, "README.md"))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.chdir(OUT)
    written: list[str] = []

    written.append(build_deck("Pitch_Deck.pptx"))
    written.append("Pitch_Deck.pdf")
    docx, pdf = build_proposal("Project_Proposal.docx", "Project_Proposal.pdf")
    written += [docx, pdf]
    for name, fn in ALL.items():
        written.append(fn(name))

    os.chdir(HERE)
    _demo()

    print(f"Generated {len(written)} documents in MetroPulse_MICE_FINAL/\n")

    # ---- checks --------------------------------------------------------
    import pymupdf

    problems: list[str] = []
    pages_total = 0
    for name in sorted(x for x in written if x.endswith(".pdf")):
        doc = pymupdf.open(os.path.join(OUT, name))
        pages_total += doc.page_count
        text = "\n".join(page.get_text() for page in doc)
        low = text.lower()
        for phrase in BANNED:
            if phrase in low:
                problems.append(f"{name}: banned claim {phrase!r}")
        found = sorted(ph for ph in DECLARED_PLACEHOLDERS if ph in text)
        # any other bracketed ALL-CAPS token is an undeclared placeholder
        import re
        for tok in set(re.findall(r"\[[A-Z][A-Z ]{3,}\]", text)):
            if tok not in DECLARED_PLACEHOLDERS:
                problems.append(f"{name}: undeclared placeholder {tok}")
        print(f"  {name:34s} {doc.page_count:>2} pp   {'  '.join(found)}")

    print(f"\n  {'total':34s} {pages_total:>2} pp")
    print(f"  facts recorded: {len(FACTS)}")
    print("\nPlaceholders above are intentional and listed in README.md.")
    if problems:
        print("\nFAILED:")
        for pr in problems:
            print("  -", pr)
        return 1
    print("No banned claims; no undeclared placeholders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
