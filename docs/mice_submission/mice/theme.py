"""Shared visual identity for the MetroPulse MICE submission.

Delhi-Metro-adjacent without imitating DMRC's brand: a metro-night ground, a
signal-indigo primary, and a status colour system that is derived from the
product itself — MetroPulse's whole identity is labelling what it knows and
what it does not, so the status pill is the motif rather than decoration.
"""

from __future__ import annotations

# ------------------------------------------------------------------ colour
INK = "0B1B3A"        # deep metro night — dominant on covers and section leads
INK_SOFT = "16294F"
PAPER = "FFFFFF"
CARD = "F3F6FB"
CARD_WARN = "FBF3E6"
CARD_GOOD = "E6F7F3"
BODY = "3C4A63"
MUTED = "77869F"
RULE = "C6D2E6"

PRIMARY = "1B4FD8"    # signal indigo
TEAL = "00A98F"
AMBER = "E08A1E"
VIOLET = "8B3FBF"
SLATE = "5B6B87"

WARN_TEXT = "7A5416"
WARN_HEAD = "9A6414"
GOOD_TEXT = "11705E"

#: The five capability labels the submission must make visually obvious.
#: Every claim in every document carries exactly one of these.
STATUS = {
    "IMPLEMENTED": TEAL,
    "APPROVED DATA": PRIMARY,
    "IN DEVELOPMENT": AMBER,
    "PROPOSED": SLATE,
    "REQUIRES DMRC DATA": VIOLET,
}

STATUS_MEANING = {
    "IMPLEMENTED": "Built, running, and covered by tests in the repository today.",
    "APPROVED DATA": "Official Delhi Open Transit Data already loaded and served.",
    "IN DEVELOPMENT": "Partially built; not yet complete or not yet verified on a device.",
    "PROPOSED": "Not built. Offered as a plan for discussion.",
    "REQUIRES DMRC DATA": "Cannot be built or validated without data only DMRC holds.",
}

# ------------------------------------------------------------------- type
# Both render true-to-width in QA and ship with Office, so nothing reflows on
# the reviewer's machine.
HEAD = "Arial"
BODYF = "Calibri"


def rgb(hex_str: str) -> tuple[int, int, int]:
    """'1B4FD8' -> (27, 79, 216)."""
    return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
