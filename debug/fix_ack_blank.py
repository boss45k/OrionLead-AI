"""
Fix: Acknowledgments signature paragraph ('Ali Jradeh / Islamic University...')
is being pushed to a new blank page because the body text is too long.
Fix: reduce space_after on each Acknowledgments body paragraph from 8pt → 4pt,
     and set keep_with_next=True on the last two body paragraphs so the signature
     always stays with the preceding text.
"""
import sys, io, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRC    = r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report.docx'
BACKUP = r'C:\AI-Lead-Collection-System\report\OrionLead_AI_Report_BACKUP4.docx'

shutil.copy(SRC, BACKUP)
doc = Document(SRC)
paras = doc.paragraphs

# ── Find the Acknowledgments block ────────────────────────────────────────────
ack_start = None
ack_sig   = None   # 'Ali Jradeh\nIslamic University...'

for i, para in enumerate(paras):
    t = para.text.strip()
    if t == 'ACKNOWLEDGMENTS':
        ack_start = i
    if ack_start and 'Ali Jradeh' in t and 'Islamic University' in t:
        ack_sig = i
        break

if ack_start is None or ack_sig is None:
    print("Could not locate Acknowledgments block.")
    sys.exit(1)

print(f"ACKNOWLEDGMENTS heading at [{ack_start}]")
print(f"Signature paragraph at [{ack_sig}]")

# ── Reduce space_after on all body paragraphs in Acknowledgments block ────────
body_paras = []
for i in range(ack_start + 1, ack_sig):
    para = paras[i]
    if para.text.strip():   # only non-empty paragraphs
        pf = para.paragraph_format
        old = pf.space_after.pt if pf.space_after else 0
        if old >= 6:
            pf.space_after = Pt(4)
            print(f"  [{i}] space_after {old:.0f}pt → 4pt | '{para.text.strip()[:40]}'")
            body_paras.append(i)

# ── Set keep_with_next on the last body paragraph before the signature ────────
# This forces the signature to stay with the last body paragraph on the same page
last_body = None
for i in range(ack_sig - 1, ack_start, -1):
    if paras[i].text.strip():
        last_body = i
        break

if last_body is not None:
    pPr = paras[last_body]._element.find(qn('w:pPr'))
    if pPr is None:
        pPr = OxmlElement('w:pPr')
        paras[last_body]._element.insert(0, pPr)
    kwn = pPr.find(qn('w:keepNext'))
    if kwn is None:
        kwn = OxmlElement('w:keepNext')
        pPr.append(kwn)
    print(f"\nSet keepNext on [{last_body}]: '{paras[last_body].text.strip()[:50]}'")

doc.save(SRC)
print("\nSaved. Reopen the report in Word to verify the blank page is gone.")
