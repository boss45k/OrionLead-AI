"""
Fix all empty-looking pages throughout the document by:
1. Reducing space_before on level-1 section headings: 16pt -> 8pt
2. Reducing space_before on level-2 section headings: 10pt -> 6pt
3. Reducing body paragraph space_after from 8pt -> 5pt
4. Allowing table rows to break across pages (prevents whole tables jumping to next page)
Content is NOT changed — only spacing/layout.
"""
import sys, io, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRC    = r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx'
BACKUP = r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report_BACKUP5.docx'

shutil.copy(SRC, BACKUP)
doc = Document(SRC)

fixes = {'headings_L1': 0, 'headings_L2': 0, 'body': 0, 'tables': 0}

# ── 1. Fix section heading spacing ─────────────────────────────────────────────
# Level-1 headings (x.x  Title) have sb=16pt → reduce to 8pt
# Level-2 headings (x.x.x  Title) have sb=10pt → reduce to 6pt
# Chapter headings (CHAPTER X) have sb=10pt → keep (they're after explicit page breaks)

import re
L1_pattern = re.compile(r'^\d+\.\d+\s+\S')   # e.g. "1.1  Background..."
L2_pattern = re.compile(r'^\d+\.\d+\.\d+\s')  # e.g. "1.5.1  In Scope"

for para in doc.paragraphs:
    t = para.text.strip()
    pf = para.paragraph_format
    sb = pf.space_before.pt if pf.space_before else 0

    if L1_pattern.match(t) and abs(sb - 16) < 1:
        pf.space_before = Pt(8)
        fixes['headings_L1'] += 1

    elif L2_pattern.match(t) and abs(sb - 10) < 1:
        pf.space_before = Pt(6)
        fixes['headings_L2'] += 1

# ── 2. Reduce body paragraph spacing (sa=8pt → 5pt) ──────────────────────────
# Only paragraphs that are clearly body text (not headings, not empty, not in front matter)
# Body text starts after para [188] (CHAPTER 1) based on earlier scan.

chapter1_idx = None
for i, para in enumerate(doc.paragraphs):
    if para.text.strip() == 'CHAPTER 1':
        chapter1_idx = i
        break

if chapter1_idx:
    for para in doc.paragraphs[chapter1_idx:]:
        t = para.text.strip()
        if not t:
            continue
        pf = para.paragraph_format
        sa = pf.space_after.pt if pf.space_after else 0
        sb = pf.space_before.pt if pf.space_before else 0
        # Body text: sa=8, sb=0 (not a heading)
        if abs(sa - 8) < 1 and sb < 8:
            pf.space_after = Pt(5)
            fixes['body'] += 1

# ── 3. Allow table rows to break across pages ─────────────────────────────────
for table in doc.tables:
    for row in table.rows:
        trPr = row._tr.find(qn('w:trPr'))
        if trPr is None:
            trPr = OxmlElement('w:trPr')
            row._tr.insert(0, trPr)
        # Remove any cantSplit element (which prevents row from breaking)
        for cs in trPr.findall(qn('w:cantSplit')):
            trPr.remove(cs)
        fixes['tables'] += 1

doc.save(SRC)

print(f"Fixes applied:")
print(f"  Level-1 section headings (16pt→8pt): {fixes['headings_L1']}")
print(f"  Level-2 section headings (10pt→6pt): {fixes['headings_L2']}")
print(f"  Body paragraphs (8pt→5pt sa):        {fixes['body']}")
print(f"  Table rows (allow page break):        {fixes['tables']}")
print(f"\nDocument saved. Close and reopen in Word to see the result.")
