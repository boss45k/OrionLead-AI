"""
Smart content-search based fix for the report:
1. Fix Department/Faculty text that may have been reverted by Word
2. Reduce the 120pt spacing on page-2 logo that creates a blank-looking gap
3. Remove any duplicate empty paragraphs on page 1 (Word may have re-inserted them)
"""
import sys, io, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

SRC    = r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx'
BACKUP = r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report_BACKUP3.docx'

shutil.copy(SRC, BACKUP)
doc = Document(SRC)
paras = doc.paragraphs

# ── Helper ─────────────────────────────────────────────────────────────────────

def clear_and_set(para, text, bold=False, size=12,
                  align=WD_ALIGN_PARAGRAPH.CENTER, sb=0, sa=6):
    p = para._element
    pPr = p.find(qn('w:pPr'))
    for child in list(p):
        p.remove(child)
    if pPr is not None:
        p.insert(0, pPr)
    para.alignment = align
    para.paragraph_format.space_before = Pt(sb)
    para.paragraph_format.space_after  = Pt(sa)
    run = para.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = 'Times New Roman'

fixes = 0

# ── Fix 1: Department and Faculty on page 1 (search by current wrong content) ──

for i, para in enumerate(paras):
    t = para.text.strip()
    if t in ('Department of Computer Science', 'Department of Computer Engineering'):
        clear_and_set(para, 'Department of Computer Engineering',
                      bold=False, size=12, sb=0, sa=6)
        print(f"  [FIX] [{i:3d}] Department → 'Department of Computer Engineering'")
        fixes += 1

    if t in ('Faculty of Sciences & Arts', 'Faculty of Sciences and Arts', 'Faculty of Engineering'):
        clear_and_set(para, 'Faculty of Engineering',
                      bold=False, size=12, sb=0, sa=6)
        print(f"  [FIX] [{i:3d}] Faculty → 'Faculty of Engineering'")
        fixes += 1

# ── Fix 2: Reduce 120pt gap on page-2 logo to 60pt ───────────────────────────
# Find the SECOND logo in the document (page 2 logo)

logo_count = 0
for i, para in enumerate(paras):
    has_image = any(e.tag in (qn('w:drawing'), qn('w:pict'))
                    for e in para._element.iter())
    if has_image:
        logo_count += 1
        if logo_count == 2:  # Second logo = page 2
            pf = para.paragraph_format
            current_sa = pf.space_after.pt if pf.space_after else 0
            if current_sa > 80:
                para.paragraph_format.space_after = Pt(60)
                print(f"  [FIX] [{i:3d}] Page-2 logo spacing: {current_sa:.0f}pt → 60pt")
                fixes += 1
            break

# ── Fix 3: Remove extra blank lines on page 1 after the logo (before OrionLead AI) ──
# Pattern on page 1: logo → [empty(s)] → OrionLead AI
# We want at most 1 empty paragraph between logo and OrionLead AI

def delete_para(para):
    para._element.getparent().remove(para._element)

paras = doc.paragraphs  # refresh

logo_idx = None
for i, para in enumerate(paras):
    has_image = any(e.tag in (qn('w:drawing'), qn('w:pict'))
                    for e in para._element.iter())
    if has_image:
        logo_idx = i
        break

if logo_idx is not None:
    # Find 'OrionLead AI' after the logo
    orion_idx = None
    for i in range(logo_idx + 1, min(logo_idx + 15, len(paras))):
        if paras[i].text.strip() == 'OrionLead AI':
            orion_idx = i
            break

    if orion_idx is not None:
        # Count empty paragraphs between logo and OrionLead AI
        gap = orion_idx - logo_idx - 1
        print(f"\n  Logo at [{logo_idx}], OrionLead AI at [{orion_idx}], gap={gap} empty paras")
        if gap > 1:
            # Delete extra empty paragraphs (keep only 1)
            to_delete = gap - 1
            paras = doc.paragraphs
            for _ in range(to_delete):
                target_idx = logo_idx + 1
                if not paras[target_idx].text.strip():
                    delete_para(paras[target_idx])
                    paras = doc.paragraphs
                    fixes += 1
                    print(f"  [FIX] Deleted extra empty para between logo and OrionLead AI")

# ── Verify and save ────────────────────────────────────────────────────────────

print(f"\nTotal fixes applied: {fixes}")

doc.save(SRC)
print("Document saved.")

# Quick verify
doc2 = Document(SRC)
page, pg_content = 1, {1: []}
for para in doc2.paragraphs:
    for elem in para._element.iter():
        if elem.tag == qn('w:br') and elem.get(qn('w:type'), '') == 'page':
            page += 1; pg_content[page] = []
        if elem.tag == qn('w:sectPr'):
            page += 1; pg_content[page] = []
    t = para.text.strip()
    has_img = any(e.tag in (qn('w:drawing'), qn('w:pict')) for e in para._element.iter())
    snippet = '[IMAGE]' if has_img else t
    if snippet:
        pg_content.setdefault(page, []).append(snippet[:50])

print("\nPage 1 content after fix:")
for item in pg_content.get(1, []):
    print(f"  • {item}")
print("\nPage 2 content after fix:")
for item in pg_content.get(2, []):
    print(f"  • {item}")
