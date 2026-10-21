#!/usr/bin/env python3
"""Convert public FastAPI Chinese MD sources to unofficial DOCX/PDF reading copies."""
import csv,re
from pathlib import Path
from xml.sax.saxutils import escape
from docx import Document
from docx.shared import Inches,Pt
from docx.oxml.ns import qn
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
ROOT=Path(__file__).resolve().parents[1]
def clean(s):
    s=re.sub(r"\s*\{\s*#[\w\-]+\s*\}\s*$","",s)
    s=re.sub(r"\[([^\]]+)\]\([^)]+\)",r"\1",s)
    s=re.sub(r"<[^>]*>","",s)
    for mark in ("**","__",chr(96),"~~"):
        s=s.replace(mark,"")
    return s.strip()
def parse(src):
    code=False
    for line in src.read_text(encoding="utf-8").splitlines():
        s=line.strip()
        if s.startswith(chr(96)*3):
            code=not code
            continue
        if code:
            if s:yield "code",s
            continue
        if s.startswith("{*") and s.endswith("*}"):
            yield "notice","【官网此处引用独立代码示例；离线阅读版不展开，详见原网页。】"
        elif s.startswith("///"):
            if s!="///": yield "notice",clean(s.strip("/ "))
        elif not s or s.startswith("<!--"):
            yield "space",""
        elif re.match(r"^#{1,6}\s",s):
            yield "h"+str(min(len(s)-len(s.lstrip("#")),3)),clean(s.lstrip("# "))
        elif re.match(r"^([-*]|\d+[.)])\s+",s):
            yield "bullet",clean(re.sub(r"^([-*]|\d+[.)])\s+","",s))
        else:
            yield "body",clean(s)
def to_docx(src,dst,title,url):
    d=Document()
    d.sections[0].top_margin=Inches(.75)
    style=d.styles["Normal"]
    style.font.name="PingFang SC"
    style.font.size=Pt(10.5)
    if style.element.rPr.rFonts is not None:
        style.element.rPr.rFonts.set(qn("w:eastAsia"),"PingFang SC")
    d.add_heading(title,0)
    d.add_paragraph("FastAPI 官方中文教程 · 非官方 Word 阅读版")
    d.add_paragraph("原文："+url)
    for typ,s in parse(src):
        if typ.startswith("h") and len(typ)==2:d.add_heading(s,int(typ[1]))
        elif typ=="bullet":d.add_paragraph(s,style="List Bullet")
        elif typ!="space":d.add_paragraph(s)
    d.save(dst)
def to_pdf(src,dst,title,url):
    fonts=list(Path("/usr/share/fonts").rglob("gbsn00lp.ttf"))
    if not fonts:raise RuntimeError("Missing Chinese TTF font")
    pdfmetrics.registerFont(TTFont("P18ZH",str(fonts[0])))
    styles={}
    for typ,size in [("h1",17),("h2",13),("h3",11),("body",10),("bullet",10),("code",9),("notice",9)]:
        styles[typ]=ParagraphStyle("zh"+typ,fontName="P18ZH",fontSize=size,leading=size*1.7,
            spaceBefore=9 if typ.startswith("h") else 0,spaceAfter=6,wordWrap="CJK",
            leftIndent=10 if typ in ("code","bullet") else 0)
    story=[Paragraph(escape(title),styles["h1"]),
           Paragraph("FastAPI 官方中文教程 · 非官方 PDF 阅读版",styles["notice"]),
           Paragraph(escape("原文："+url),styles["notice"]),Spacer(1,12)]
    for typ,s in parse(src):
        if typ=="space":story.append(Spacer(1,4))
        else:story.append(Paragraph(escape(("• " if typ=="bullet" else "")+s),styles.get(typ,styles["body"])))
    SimpleDocTemplate(str(dst),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=42).build(story)
def main():
    with (ROOT/"00_说明与题库"/"原始来源.csv").open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    for i,row in enumerate(rows,1):
        folder=ROOT/row["类别"]
        title=row["标题"]
        src=folder/(title+".md")
        to_docx(src,folder/(title+"_阅读版.docx"),title,row["原始网页"])
        to_pdf(src,folder/(title+"_阅读版.pdf"),title,row["原始网页"])
        print(i,len(rows),title)
    print("Created",len(rows)*2,"reading docs")
if __name__=="__main__":
    main()
