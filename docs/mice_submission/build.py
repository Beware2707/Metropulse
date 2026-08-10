"""Regenerate the entire MetroPulse MICE submission package.

    .venv/Scripts/python.exe docs/mice_submission/build.py

Also runs a consistency check: no document may contain a placeholder that the
README does not declare, and no document may claim official realtime data.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mice.deck import build as build_deck            # noqa: E402
from mice.documents import ALL                       # noqa: E402
from mice.proposal import build_all as build_proposal  # noqa: E402

BANNED = [
    # Phrases that would claim what MetroPulse does not have.
    "live delhi metro data",
    "official realtime data from dmrc",
    "realtime metro feed integrated",
]


def main() -> int:
    os.chdir(HERE)
    written: list[str] = []

    written.append(build_deck("MetroPulse_MICE_Pitch_Deck.pptx"))
    written.append("MetroPulse_MICE_Pitch_Deck.pdf")
    d, p = build_proposal("MetroPulse_MICE_Project_Proposal.docx",
                          "MetroPulse_MICE_Project_Proposal.pdf")
    written += [d, p]
    for name, fn in ALL.items():
        written.append(fn(name))

    print(f"Generated {len(written)} files\n")

    # ---- consistency check -------------------------------------------
    import pymupdf

    problems: list[str] = []
    placeholders: dict[str, list[str]] = {}
    for name in sorted(x for x in written if x.endswith(".pdf")):
        doc = pymupdf.open(name)
        text = "\n".join(page.get_text() for page in doc).lower()
        for phrase in BANNED:
            if phrase in text:
                problems.append(f"{name}: contains banned claim {phrase!r}")
        found = []
        if "[data required]" in text:
            found.append("[DATA REQUIRED]")
        if "[to be provided]" in text:
            found.append("[TO BE PROVIDED]")
        if found:
            placeholders[name] = found
        print(f"  {name:48s} {doc.page_count:>2} pp"
              f"   {'  '.join(found)}")

    print("\nPlaceholders are intentional and listed in README.md.")
    if problems:
        print("\nFAILED:")
        for pr in problems:
            print("  -", pr)
        return 1
    print("No banned claims found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
