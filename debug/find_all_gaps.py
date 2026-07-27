"""
Find ALL paragraphs across the document that have large space_before (>= 10pt),
which push themselves to a new page and leave the previous page partially empty.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

doc = Document(r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx')
paras = doc.paragraphs

print("Paragraphs with space_before >= 8pt (section headings / figure refs):")
print("=" * 70)

for i, para in enumerate(paras):
    pf = para.paragraph_format
    sb = pf.space_before.pt if pf.space_before else 0
    sa = pf.space_after.pt if pf.space_after else 0
    text = para.text.strip()[:60]

    if sb >= 8 and text:
        print(f"  [{i:3d}] sb={sb:5.1f}pt sa={sa:4.1f}pt | '{text}'")
