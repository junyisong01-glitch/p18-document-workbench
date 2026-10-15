"""Generate entirely fictional teaching fixtures, never company material."""
import io
from pathlib import Path
import subprocess
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runtime" / "samples"
OUT.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def page(c, title, lines):
    c.setFont("STSong-Light", 22)
    c.drawString(50, 775, title)
    c.setFont("STSong-Light", 11)
    c.drawString(50, 745, "P18 虚构测试资料 · 设备预约系统 · 不含任何企业真实信息")
    y = 705
    for line in lines:
        c.drawString(50, y, line)
        y -= 24


c = canvas.Canvas(str(OUT / "01-虚构设备预约需求.pdf"))
page(c, "设备预约系统需求说明", ["文档编号：DEMO-REQ-001", "一、使用场景", "实验室成员可查看设备并发起预约，管理员负责审批。", "二、预约规则", "每次预约最长 2 小时，预约前需检查设备状态。", "取消预约需要在开始前 30 分钟完成。", "三、异常处理", "设备维修时不能新增预约，已有预约需由管理员通知调整。"])
c.showPage(); c.save()

image = Image.new("RGB", (1100, 1300), "white")
draw = ImageDraw.Draw(image)
draw.text((65, 80), "FICTIONAL SCANNED PAGE / DEMO ONLY", fill="black", font_size=34)
draw.text((65, 180), "Reservation API: POST /api/reservations", fill="black", font_size=30)
draw.text((65, 250), "device_id: required | duration: <= 120 min", fill="black", font_size=28)
draw.text((65, 350), "This page is an image. No OCR in version 1.", fill="black", font_size=28)
buf = io.BytesIO();image.save(buf, format="PNG");buf.seek(0)
image_source = ImageReader(buf)
for filename, mixed, same_page in [("02-虚构混合文档需复核.pdf", True, False), ("03-虚构纯扫描文档.pdf", False, False), ("04-虚构同页图文.pdf", False, True)]:
    c = canvas.Canvas(str(OUT / filename))
    if mixed:
        page(c, "接口说明 · 正文页", ["第一部分为可提取文字，第二页是图片模拟扫描内容。", "测试预期：第 2 页提示未提取到文字，需要人工复核。"])
        c.showPage()
    if same_page:
        page(c, "接口说明 · 图文混合", ["此页标题可提取，下方图片中的参数文字不会被识别。"])
        c.drawImage(image_source, 50, 90, width=460, height=520)
    else:
        c.drawImage(image_source, 30, 50, width=535, height=720)
    c.showPage();c.save()

for complex_table in [False, True]:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "PingFang SC";normal.font.size = Pt(11)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "PingFang SC")
    doc.add_heading("虚构设备预约接口说明", 0)
    doc.add_paragraph("P18 教学测试样例。所有业务、接口和数据均为虚构，不涉及企业资料。")
    doc.add_heading("1 创建预约", 1)
    doc.add_paragraph("POST /api/reservations\n预约时长不得超过 120 分钟。")
    doc.add_heading("2 请求参数", 1)
    t = doc.add_table(rows=1, cols=4);t.style="Table Grid"
    for cell, value in zip(t.rows[0].cells,["参数", "类型", "必填", "说明"]): cell.text=value
    for values in [["device_id","string","是","设备编号"],["duration","integer","是","分钟数，最大 120"],["note","string","否","预约说明"]]:
        for cell, value in zip(t.add_row().cells,values):cell.text=value
    if complex_table:
        merged=t.add_row().cells
        merged[0].merge(merged[3]).text="复杂合并单元格：需要核对行列对应关系。"
    doc.add_heading("3 请求示例", 1)
    doc.add_paragraph('{\n    "device_id": "DEMO-001",\n    "duration": 60\n}')
    doc.add_heading("4 测试预期",1)
    doc.add_paragraph("应提取正文、参数表及示例缩进。" + ("应提示合并单元格复核。" if complex_table else "普通正文与表格不应因格式简单而产生异常提示。"))
    doc.save(OUT / ("06-虚构复杂表格.docx" if complex_table else "05-虚构接口说明.docx"))

binary = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS/soffice"
if binary.exists():
    import tempfile
    with tempfile.TemporaryDirectory(prefix="p18-samples-") as profile:
        subprocess.run([str(binary), f"-env:UserInstallation={Path(profile).as_uri()}", "--headless", "--convert-to", "doc:MS Word 97", "--outdir", str(OUT), str(OUT / "05-虚构接口说明.docx")], check=True, timeout=60)
    old = OUT / "05-虚构接口说明.doc"
    if old.exists():old.rename(OUT / "07-虚构旧版接口说明.doc")

c=canvas.Canvas(str(OUT / "08-空白测试.pdf"));c.showPage();c.save()
(OUT / "09-格式不匹配测试.pdf").write_text("This is not a PDF. Intentionally invalid fixture.")
print(f"已生成虚构样例：{OUT}")
for p in sorted(OUT.iterdir()):print(p.name)
