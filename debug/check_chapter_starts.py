"""
Show 5 paragraphs before and after each page break so we can see blank page patterns.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

doc = Document(r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx')
paras = doc.paragraphs

# Find all page-break paragraph indices
break_indices = []
for i, para in enumerate(paras):
    for elem in para._element.iter():
        if elem.tag == qn('w:br') and elem.get(qn('w:type'), '') == 'page':
            break_indices.append(i)
            break
        if elem.tag == qn('w:sectPr'):
            break_indices.append(i)
            break

print(f"Page break paragraphs: {break_indices}\n")

def para_info(i, para):
    text = para.text.strip()[:50]
    has_img = any(e.tag in (qn('w:drawing'), qn('w:pict')) for e in para._element.iter())
    pf = para.paragraph_format
    sb = round(pf.space_before.pt, 0) if pf.space_before else 0
    sa = round(pf.space_after.pt, 0) if pf.space_after else 0

    if has_img:
        label = '[IMAGE]'
    elif text:
        label = f"'{text}'"
    else:
        label = '(empty)'

    return f"[{i:3d}] sb={int(sb):3d} sa={int(sa):3d} | {label}"

for bi in break_indices:
    print(f"\n{'='*70}")
    print(f"PAGE BREAK at para [{bi}]")
    print(f"{'='*70}")
    print("  --- BEFORE (end of previous page) ---")
    for j in range(max(0, bi-4), bi):
        print(f"  {para_info(j, paras[j])}")
    print(f"  >>> {para_info(bi, paras[bi])} <<<")
    print("  --- AFTER (start of next page) ---")
    for j in range(bi+1, min(len(paras), bi+6)):
        print(f"  {para_info(j, paras[j])}")
