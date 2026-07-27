"""
build.py — Assembles the OrionLead AI graduation report.
Add each new section module to SECTIONS in order, then run:
    python build.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import theme as T
from sections import s00_front, s01_intro, s02_literature, s03_analysis, s04_design, s05_implement, s06_testing, s07_ui, s08_conclusion, s09_references

OUT = os.path.join(os.path.dirname(__file__), "OrionLead_AI_Report.docx")

SECTIONS = [
    s00_front,
    s01_intro,
    s02_literature,
    s03_analysis,
    s04_design,
    s05_implement,
    s06_testing,
    s07_ui,
    s08_conclusion,
    s09_references,
]


def build():
    doc = T.create_document()
    for mod in SECTIONS:
        mod.build(doc)
    T.finalize(doc)
    doc.save(OUT)
    print(f"OK  Saved: {OUT}")
    print(f"    Sections built: {len(SECTIONS)}")


if __name__ == "__main__":
    build()
