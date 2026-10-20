#!/usr/bin/env python3
"""Convert six openly licensed source texts into non-official test PDF/DOCX variants.
Dependencies: python-docx, reportlab. Never modifies the source files.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import textwrap

ROOT = Path(__file__).resolve().parents[1]

DOCX_ITEMS = [
    ("01_需求说明/prd-template.md", "01_需求说明/PRD_格式转换.docx"),
    ("04_测试计划与测试记录/TEST_CASES.md", "04_测试计划与测试记录/TEST_CASES_格式转换.docx"),
    ("04_测试计划与测试记录/TEST_PLAN.md", "04_测试计划与测试记录/TEST_PLAN_格式转换.docx"),
]
PDF_ITEMS = [
    ("01_需求说明/srs-template-bare.md", "01_需求说明/SRS_格式转换.pdf"),
    ("03_架构与技术决策/0000-use-markdown-architectural-decision-records.md", "03_架构与技术决策/ADR_格式转换.pdf"),
    ("04_测试计划与测试记录/TEST_PLAN.md", "04_测试计划与测试记录/TEST_PLAN_格式转换.pdf"),
]

def convert_docx(source, dest):
    from docx import Document
    from docx.shared import Pt
    document = Document()
    document.add_paragraph("公开原文格式转换件（非来源项目官方 DOCX）", style="Subtitle")
    document.add_paragraph("Source: " + source.as_posix())
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            document.add_heading(line.lstrip("#").strip(), level=min(level, 4))
        else:
            document.add_paragraph(raw)
    dest.parent.mkdir(parents=True, exist_ok=True)
    document.save(dest)

def convert_pdf(source, dest):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    styles = getSampleStyleSheet()
    styles["Normal"].fontSize = 8
    styles["Normal"].leading = 11
    for x in ("Heading1","Heading2","Heading3"):
        styles[x].spaceBefore = 10
        styles[x].spaceAfter = 5
    story = [Paragraph("Public source - format-converted test PDF (not official)", styles["Heading2"]), Spacer(1, 12)]
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        if line.startswith("#"):
            depth = len(line) - len(line.lstrip("#"))
            style = styles["Heading1" if depth == 1 else "Heading2" if depth == 2 else "Heading3"]
            value = line.lstrip("#").strip()
        else:
            style, value = styles["Normal"], line
        # Deliberately plain text for reproducible parser testing.
        value = escape(value)
        if len(value) > 180 and " " not in value:
            value = " ".join(textwrap.wrap(value, 100))
        story.append(Paragraph(value, style))
    dest.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(dest), pagesize=A4, rightMargin=40, leftMargin=40, topMargin=42, bottomMargin=42).build(story)

if __name__ == "__main__":
    for a, b in DOCX_ITEMS:
        convert_docx(ROOT / a, ROOT / b)
        print("DOCX:", b)
    for a, b in PDF_ITEMS:
        convert_pdf(ROOT / a, ROOT / b)
        print("PDF:", b)
