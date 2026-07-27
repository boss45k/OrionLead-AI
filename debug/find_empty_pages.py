"""
Scan the full document and report page-by-page content summary.
Detects empty or near-empty pages caused by bad spacing or orphan breaks.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.oxml.ns import qn

doc = Document(r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx')

page = 1
page_content = {1: []}   # page -> list of text snippets

for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()
    has_image = any(e.tag in (qn('w:drawing'), qn('w:pict'))
                    for e in para._element.iter())

    # Detect page/section breaks inside this paragraph
    for elem in para._element.iter():
        if elem.tag == qn('w:br'):
            if elem.get(qn('w:type'), '') == 'page':
                page += 1
                page_content[page] = []
        if elem.tag == qn('w:sectPr'):
            page += 1
            page_content[page] = []

    snippet = '[IMAGE]' if has_image else (text[:60] if text else '')
    if snippet:
        page_content.setdefault(page, []).append(snippet)

# Report
print(f"Total pages detected: {page}")
print("=" * 70)
for pg in sorted(page_content.keys()):
    items = page_content[pg]
    status = "EMPTY" if not items else (f"{len(items)} item(s)")
    print(f"\nPage {pg:3d}  [{status}]")
    for item in items:
        print(f"         • {item}")

print("\nDone.")
