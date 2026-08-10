"""A4 report builder shared by every PDF in the submission.

One typographic system, one status-label system, one cover treatment — so a
reviewer opening any of the nine supporting documents recognises it as part of
the same package. Built on reportlab's platypus so pagination, table splitting
and page numbering are handled rather than hand-placed.
"""

from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable,
                                Frame, Image, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from . import theme as T

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _c(hexstr: str):
    return colors.HexColor("#" + hexstr)


# ------------------------------------------------------------------ styles
def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("body", fontName="Helvetica", fontSize=9.6,
                          leading=14.4, textColor=_c(T.BODY), spaceAfter=6)
    return {
        "body": base,
        "lead": ParagraphStyle("lead", parent=base, fontSize=11, leading=16.5,
                               textColor=_c(T.INK), spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold",
                             fontSize=17, leading=21, textColor=_c(T.INK),
                             spaceBefore=14, spaceAfter=8, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold",
                             fontSize=12, leading=16, textColor=_c(T.INK),
                             spaceBefore=11, spaceAfter=5, keepWithNext=1),
        "kicker": ParagraphStyle("kicker", parent=base,
                                 fontName="Helvetica-Bold", fontSize=8,
                                 textColor=_c(T.PRIMARY), spaceAfter=2),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=11,
                                 bulletIndent=1, spaceAfter=4),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.8, leading=12.4,
                               spaceAfter=0),
        "cellhead": ParagraphStyle("cellhead", parent=base, fontSize=8.6,
                                   leading=12, fontName="Helvetica-Bold",
                                   textColor=colors.white, spaceAfter=0),
        "caption": ParagraphStyle("caption", parent=base, fontSize=8.3,
                                  textColor=_c(T.MUTED), spaceAfter=8),
        "covertitle": ParagraphStyle("ct", parent=base,
                                     fontName="Helvetica-Bold", fontSize=30,
                                     leading=35, textColor=colors.white),
        "coversub": ParagraphStyle("cs", parent=base, fontSize=12.5,
                                   leading=18, textColor=_c("C3D2EC")),
    }


S = _styles()


# ------------------------------------------------------------------ pieces
class StatusPill(Flowable):
    """The package motif — a capability label, inline in the text flow."""

    def __init__(self, label: str, size: float = 7.4):
        super().__init__()
        self.label = label
        self.size = size
        self.pad = 4.5
        self.w = len(label) * size * 0.62 + self.pad * 2
        self.h = size + 6

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        c = self.canv
        c.setFillColor(_c(T.STATUS.get(self.label, T.SLATE)))
        c.roundRect(0, 0, self.w, self.h, self.h / 2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", self.size)
        c.drawCentredString(self.w / 2, self.h / 2 - self.size * 0.36, self.label)


class Rule(Flowable):
    def __init__(self, colour=T.RULE, thickness=0.6, width=CONTENT_W):
        super().__init__()
        self.colour, self.thickness, self.w = colour, thickness, width
        self.h = thickness

    def wrap(self, *_):
        return self.w, self.h

    def draw(self):
        self.canv.setStrokeColor(_c(self.colour))
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.w, 0)


def para(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items, style="bullet"):
    return [Paragraph(f"• {t}", S[style]) for t in items]


def heading(text, level=1):
    """A heading that refuses to be the last thing on a page.

    keepWithNext chains paragraph to paragraph only, so a heading followed by
    a table still stranded itself at the page foot. CondPageBreak reserves the
    space a heading plus a first row or two would need.
    """
    need = 34 * mm if level == 1 else 26 * mm
    return [CondPageBreak(need), para(text, "h1" if level == 1 else "h2")]


def status_row(label: str, text: str):
    """A capability line: label on the left, claim on the right."""
    t = Table([[StatusPill(label), para(text, "cell")]],
              colWidths=[38 * mm, CONTENT_W - 38 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def table(rows, widths=None, head=True, keep=False):
    """A data table that fits the frame and repeats its header across pages."""
    data = [[para(str(c), "cellhead" if (head and r == 0) else "cell")
             for c in row] for r, row in enumerate(rows)]
    if widths is None:
        n = len(rows[0])
        widths = [CONTENT_W / n] * n
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, _c(T.RULE)),
    ]
    if head:
        style += [("BACKGROUND", (0, 0), (-1, 0), _c(T.INK))]
        style += [("ROWBACKGROUNDS", (0, 1), (-1, -1),
                   [colors.white, _c(T.CARD)])]
    else:
        style += [("ROWBACKGROUNDS", (0, 0), (-1, -1),
                   [colors.white, _c(T.CARD)])]
    t.setStyle(TableStyle(style))
    # keep=True for short tables whose last row would otherwise spill alone
    # onto the next page. Not the default: applied globally it pushed whole
    # blocks to fresh pages and grew every document.
    return KeepTogether(t) if keep else t


def callout(title: str, body: str, kind: str = "warn"):
    fill = {"warn": T.CARD_WARN, "good": T.CARD_GOOD, "info": T.CARD}[kind]
    head_col = {"warn": T.WARN_HEAD, "good": T.GOOD_TEXT, "info": T.INK}[kind]
    text_col = {"warn": T.WARN_TEXT, "good": T.GOOD_TEXT, "info": T.BODY}[kind]
    ts = ParagraphStyle("ct2", parent=S["h2"], textColor=_c(head_col),
                        spaceBefore=0, spaceAfter=3)
    bs = ParagraphStyle("cb2", parent=S["body"], textColor=_c(text_col),
                        spaceAfter=0)
    t = Table([[[Paragraph(title, ts), Paragraph(body, bs)]]],
              colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _c(fill)),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 8)])


def flow_diagram(steps: list[tuple[str, str]], per_row: int = 3):
    """A boxed step-flow, drawn as a table so it paginates like text."""
    cells, row = [], []
    for i, (title, sub) in enumerate(steps):
        ts = ParagraphStyle(f"fd{i}", parent=S["cell"],
                            fontName="Helvetica-Bold", textColor=colors.white,
                            alignment=TA_CENTER, spaceAfter=2)
        bs = ParagraphStyle(f"fb{i}", parent=S["cell"], fontSize=8,
                            leading=10.5, textColor=_c("D7E0F2"),
                            alignment=TA_CENTER)
        row.append([Paragraph(title, ts), Paragraph(sub, bs)] if sub
                   else [Paragraph(title, ts)])
        if len(row) == per_row:
            cells.append(row)
            row = []
    if row:
        while len(row) < per_row:
            row.append("")
        cells.append(row)
    t = Table(cells, colWidths=[CONTENT_W / per_row] * per_row)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _c(T.INK)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("INNERGRID", (0, 0), (-1, -1), 2.5, colors.white),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 8)])


def picture(path: str, width_mm: float):
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        w, h = im.size
    w_pt = width_mm * mm
    return Image(path, width=w_pt, height=w_pt * h / w)


# --------------------------------------------------------------- document
class Report(BaseDocTemplate):
    def __init__(self, path: str, title: str, subtitle: str, doc_kind: str):
        super().__init__(path, pagesize=A4, leftMargin=MARGIN,
                         rightMargin=MARGIN, topMargin=MARGIN,
                         bottomMargin=MARGIN + 6 * mm, title=title,
                         author="MetroPulse")
        self.doc_title = title
        self.doc_subtitle = subtitle
        self.doc_kind = doc_kind
        frame = Frame(MARGIN, MARGIN + 6 * mm, CONTENT_W,
                      PAGE_H - 2 * MARGIN - 6 * mm, id="body")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[Frame(0, 0, PAGE_W, PAGE_H,
                                                   id="cover")],
                         onPage=self._cover_bg),
            PageTemplate(id="body", frames=[frame], onPage=self._chrome),
        ])

    def _cover_bg(self, canv, doc):
        canv.setFillColor(_c(T.INK))
        canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    def _chrome(self, canv, doc):
        canv.saveState()
        canv.setFont("Helvetica", 7.4)
        canv.setFillColor(_c(T.MUTED))
        canv.drawString(MARGIN, MARGIN - 1 * mm,
                        f"MetroPulse — {self.doc_kind}")
        canv.drawRightString(PAGE_W - MARGIN, MARGIN - 1 * mm,
                             f"Page {canv.getPageNumber() - 1}")
        canv.setStrokeColor(_c(T.RULE))
        canv.setLineWidth(0.4)
        canv.line(MARGIN, MARGIN + 3 * mm, PAGE_W - MARGIN, MARGIN + 3 * mm)
        canv.restoreState()

    def cover(self, meta: list[tuple[str, str]]) -> list:
        """The dark cover page, identical across the package."""
        out = [Spacer(1, 48 * mm)]
        pad = ParagraphStyle("pad", parent=S["covertitle"],
                             leftIndent=MARGIN, rightIndent=MARGIN)
        sub = ParagraphStyle("psub", parent=S["coversub"],
                             leftIndent=MARGIN, rightIndent=MARGIN)
        small = ParagraphStyle("psm", parent=S["coversub"], fontSize=9.4,
                               leading=14, textColor=_c("7C93BE"),
                               leftIndent=MARGIN, rightIndent=MARGIN)
        kick = ParagraphStyle("pk", parent=S["coversub"], fontSize=8.6,
                              textColor=_c("7FE3D2"), leftIndent=MARGIN,
                              fontName="Helvetica-Bold")
        mark = ParagraphStyle("pmark", parent=S["coversub"], fontSize=17,
                              leading=21, textColor=_c("FFFFFF"),
                              fontName="Helvetica-Bold", leftIndent=MARGIN)
        out.append(Paragraph("MetroPulse", mark))
        out.append(Spacer(1, 9 * mm))
        # The kicker repeated the title on every document; the packet name is
        # the useful thing to carry on a page that may be read alone.
        out.append(Paragraph("DMRC / MICE SUBMISSION", kick))
        out.append(Spacer(1, 5 * mm))
        out.append(Paragraph(self.doc_title, pad))
        out.append(Spacer(1, 4 * mm))
        out.append(Paragraph(self.doc_subtitle, sub))
        out.append(Spacer(1, 26 * mm))
        for k, v in meta:
            out.append(Paragraph(f"<b>{k}</b>  {v}", small))
        out.append(NextPageTemplate("body"))
        out.append(PageBreak())
        return out



def build(path: str, title: str, subtitle: str, kind: str,
          meta: list[tuple[str, str]], story: list) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    doc = Report(path, title, subtitle, kind)
    flat: list = []
    for item in story:
        flat.extend(item) if isinstance(item, list) else flat.append(item)
    doc.build(doc.cover(meta) + flat)
    return path
