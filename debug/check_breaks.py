"""
Check ALL explicit page/section breaks and section types in the document.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

doc = Document(r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx')

print("All explicit breaks and section types:")
print("=" * 70)

page = 1
for i, para in enumerate(doc.paragraphs):
    text = para.text.strip()[:50]
    has_image = any(e.tag in (qn('w:drawing'), qn('w:pict'))
                    for e in para._element.iter())

    # Check for page breaks inside runs
    for elem in para._element.iter():
        if elem.tag == qn('w:br'):
            btype = elem.get(qn('w:type'), 'line')
            if btype == 'page':
                label = text or ('[IMAGE]' if has_image else '(empty)')
                print(f"  [{i:3d}] PAGE BREAK inside para: '{label}'")
                page += 1

        if elem.tag == qn('w:sectPr'):
            # Get section type
            sect_type_elem = elem.find(qn('w:type'))
            stype = sect_type_elem.get(qn('w:val'), 'unknown') if sect_type_elem is not None else 'nextPage'
            label = text or ('[IMAGE]' if has_image else '(empty)')
            print(f"  [{i:3d}] SECTION BREAK type='{stype}' in para: '{label}'")
            if stype in ('evenPage', 'oddPage'):
                print(f"         *** WARNING: '{stype}' section break forces blank page! ***")
            page += 1

# Also check the body-level sectPr
body = doc.element.body
body_sect = body.find(qn('w:sectPr'))
if body_sect is not None:
    sect_type_elem = body_sect.find(qn('w:type'))
    stype = sect_type_elem.get(qn('w:val'), 'unknown') if sect_type_elem is not None else 'nextPage'
    print(f"\n  [BODY] Final section type='{stype}'")

print(f"\nTotal explicit page transitions found: {page - 1}")
print(f"Expected pages: {page}")
