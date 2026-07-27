"""
theme.py — Central styling for OrionLead AI graduation report.
All fonts, colors, heading styles, table helpers, and header/footer setup live here.
"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ── Palette ────────────────────────────────────────────────────────────────────
NAVY_HEX  = "1E3A5F"
GOLD_HEX  = "C9A02C"
LIGHT_HEX = "EFF3F8"
WHITE_HEX = "FFFFFF"
MID_HEX   = "5A5A5A"

NAVY  = RGBColor(0x1E, 0x3A, 0x5F)
GOLD  = RGBColor(0xC9, 0xA0, 0x2C)
DARK  = RGBColor(0x2D, 0x2D, 0x2D)
MID   = RGBColor(0x5A, 0x5A, 0x5A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED   = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1A, 0x8C, 0x4E)

BODY_FONT = "Times New Roman"
HEAD_FONT = "Arial"

# ── Document factory ───────────────────────────────────────────────────────────
def create_document():
    doc = Document()
    _set_margins(doc.sections[0])
    ns = doc.styles['Normal']
    ns.font.name = BODY_FONT
    ns.font.size = Pt(12)
    ns.font.color.rgb = DARK
    return doc


def _set_margins(sec):
    sec.page_height   = Cm(29.7)
    sec.page_width    = Cm(21.0)
    sec.top_margin    = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    sec.left_margin   = Cm(3.0)
    sec.right_margin  = Cm(2.0)


# ── Run formatter ──────────────────────────────────────────────────────────────
def fr(run, name=BODY_FONT, size=12, bold=False, italic=False, color=None):
    run.font.name   = name
    run.font.size   = Pt(size)
    run.font.bold   = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color


# ── Horizontal rule ────────────────────────────────────────────────────────────
def h_rule(doc, color=NAVY_HEX, thick=12):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(2)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bot  = OxmlElement('w:bottom')
    bot.set(qn('w:val'),   'single')
    bot.set(qn('w:sz'),    str(thick))
    bot.set(qn('w:space'), '1')
    bot.set(qn('w:color'), color)
    pBdr.append(bot)
    pPr.append(pBdr)
    return p


# ── Cover-page helper ──────────────────────────────────────────────────────────
def cover_line(doc, text, size=12, bold=False, color=None,
               before=0, after=6, align=WD_ALIGN_PARAGRAPH.CENTER, italic=False):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before       = Pt(before)
    p.paragraph_format.space_after        = Pt(after)
    p.paragraph_format.line_spacing_rule  = WD_LINE_SPACING.SINGLE
    run = p.add_run(text)
    fr(run, name=HEAD_FONT, size=size, bold=bold, italic=italic,
       color=color if color else DARK)
    return p


# ── Chapter title ──────────────────────────────────────────────────────────────
def chapter_title(doc, num, title):
    doc.add_page_break()
    h_rule(doc, NAVY_HEX, 20)

    lbl = doc.add_paragraph()
    lbl.alignment = WD_ALIGN_PARAGRAPH.LEFT
    lbl.paragraph_format.space_before = Pt(10)
    lbl.paragraph_format.space_after  = Pt(0)
    fr(lbl.add_run(f"CHAPTER {num}"), HEAD_FONT, 10, bold=True, color=GOLD)

    ttl = doc.add_paragraph()
    ttl.alignment = WD_ALIGN_PARAGRAPH.LEFT
    ttl.paragraph_format.space_before = Pt(2)
    ttl.paragraph_format.space_after  = Pt(4)
    fr(ttl.add_run(title.upper()), HEAD_FONT, 16, bold=True, color=NAVY)

    h_rule(doc, GOLD_HEX, 6)
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(12)


# ── Section headings ───────────────────────────────────────────────────────────
def section_h(doc, num, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after  = Pt(4)
    fr(p.add_run(f"{num}  {text}"), HEAD_FONT, 13, bold=True, color=NAVY)
    return p


def subsection_h(doc, num, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(3)
    fr(p.add_run(f"{num}  {text}"), HEAD_FONT, 11, bold=True, color=DARK)
    return p


def subsubsection_h(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(2)
    fr(p.add_run(text), HEAD_FONT, 11, bold=True, italic=True, color=MID)
    return p


# ── Body text ──────────────────────────────────────────────────────────────────
def body(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_before      = Pt(0)
    p.paragraph_format.space_after       = Pt(8)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.first_line_indent = Cm(0.8)
    fr(p.add_run(text), BODY_FONT, 12, color=DARK)
    return p


# ── Bullet list ────────────────────────────────────────────────────────────────
def bullet(doc, text, level=0, bold_prefix=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.left_indent = Cm(1.0 + level * 0.6)
    indent_str = "  " * level
    if bold_prefix:
        fr(p.add_run(f"{indent_str}• {bold_prefix}"), BODY_FONT, 12, bold=True, color=NAVY)
        fr(p.add_run(f" {text}"), BODY_FONT, 12, color=DARK)
    else:
        fr(p.add_run(f"{indent_str}• {text}"), BODY_FONT, 12, color=DARK)
    return p


# ── Numbered list ──────────────────────────────────────────────────────────────
def numbered(doc, n, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.left_indent = Cm(1.0)
    fr(p.add_run(f"{n}. "), BODY_FONT, 12, bold=True, color=NAVY)
    fr(p.add_run(text), BODY_FONT, 12, color=DARK)
    return p


# ── Caption ────────────────────────────────────────────────────────────────────
def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after  = Pt(14)
    fr(p.add_run(text), HEAD_FONT, 10, bold=True, italic=True, color=MID)
    return p


# ── Spacer ─────────────────────────────────────────────────────────────────────
def spacer(doc, pts=12):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after  = Pt(pts)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    return p


# ── Page number (TOC entry) ────────────────────────────────────────────────────
def toc_entry(doc, text, page_str, level=0, bold=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(3)
    p.paragraph_format.left_indent  = Cm(level * 0.7)

    # dot-leader tab at ~14cm from left
    pPr = p._p.get_or_add_pPr()
    tabs_el = OxmlElement('w:tabs')
    tab_el  = OxmlElement('w:tab')
    tab_el.set(qn('w:val'),    'right')
    tab_el.set(qn('w:leader'), 'dot')
    tab_el.set(qn('w:pos'),    '8640')
    tabs_el.append(tab_el)
    pPr.append(tabs_el)

    size = 12 if level == 0 else 11
    c = NAVY if bold else DARK
    fr(p.add_run(text), BODY_FONT, size, bold=bold, color=c)
    fr(p.add_run(f"\t{page_str}"), BODY_FONT, size, bold=bold, color=c)
    return p


# ── Styled table ───────────────────────────────────────────────────────────────
def styled_table(doc, headers, rows, col_widths=None, center_cols=None):
    """
    headers    : list[str]
    rows       : list[list[str]]
    col_widths : list[Cm] or None
    center_cols: set of col indices to center-align in data rows
    """
    center_cols = center_cols or set()
    n_cols = len(headers)
    tbl = doc.add_table(rows=1 + len(rows), cols=n_cols)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    _table_borders(tbl)

    # Header row
    for i, h in enumerate(headers):
        c = tbl.rows[0].cells[i]
        _shade(c, NAVY_HEX)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after  = Pt(4)
        fr(p.add_run(h), HEAD_FONT, 10, bold=True, color=WHITE)

    # Data rows
    for ri, row_data in enumerate(rows):
        fill = LIGHT_HEX if ri % 2 == 0 else WHITE_HEX
        for ci, val in enumerate(row_data):
            c = tbl.rows[ri + 1].cells[ci]
            _shade(c, fill)
            p = c.paragraphs[0]
            p.alignment = (WD_ALIGN_PARAGRAPH.CENTER
                           if ci in center_cols
                           else WD_ALIGN_PARAGRAPH.LEFT)
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after  = Pt(3)
            fr(p.add_run(str(val)), BODY_FONT, 10, color=DARK)

    if col_widths:
        for row in tbl.rows:
            for i, c in enumerate(row.cells):
                if i < len(col_widths):
                    c.width = col_widths[i]

    spacer(doc, 10)
    return tbl


# ── XML helpers ────────────────────────────────────────────────────────────────
def _shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)


def _table_borders(tbl_obj):
    tbl  = tbl_obj._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    borders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'),   'single')
        el.set(qn('w:sz'),    '4')
        el.set(qn('w:space'), '0')
        el.set(qn('w:color'), NAVY_HEX)
        borders.append(el)
    tblPr.append(borders)


def _page_num_field(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    fr(run, HEAD_FONT, 10, color=MID)
    for tag, txt in [('begin', None), (None, ' PAGE '), ('end', None)]:
        if tag:
            el = OxmlElement('w:fldChar')
            el.set(qn('w:fldCharType'), tag)
            run._r.append(el)
        else:
            instr = OxmlElement('w:instrText')
            instr.set(qn('xml:space'), 'preserve')
            instr.text = txt
            run._r.append(instr)


# ── Finalize: headers & footers ────────────────────────────────────────────────
def finalize(doc):
    for i, sec in enumerate(doc.sections):
        _set_margins(sec)

        # ── Header ──
        hdr = sec.header
        hdr.is_linked_to_previous = False
        for p in hdr.paragraphs:
            p.clear()
        hp = hdr.paragraphs[0] if hdr.paragraphs else hdr.add_paragraph()

        if i == 0:
            hp.text = ""          # cover page: blank header
        else:
            hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            fr(hp.add_run("OrionLead AI  ·  Islamic University of Lebanon"),
               HEAD_FONT, 9, color=MID)
            pPr = hp._p.get_or_add_pPr()
            pBdr = OxmlElement('w:pBdr')
            bot  = OxmlElement('w:bottom')
            bot.set(qn('w:val'),   'single')
            bot.set(qn('w:sz'),    '4')
            bot.set(qn('w:space'), '1')
            bot.set(qn('w:color'), NAVY_HEX)
            pBdr.append(bot)
            pPr.append(pBdr)

        # ── Footer ──
        ftr = sec.footer
        ftr.is_linked_to_previous = False
        for p in ftr.paragraphs:
            p.clear()
        fp = ftr.paragraphs[0] if ftr.paragraphs else ftr.add_paragraph()
        if i > 0:
            _page_num_field(fp)
