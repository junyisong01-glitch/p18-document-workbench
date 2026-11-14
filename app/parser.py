"""Bounded, local-only document extraction; no OCR or model calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

import pymupdf as fitz
import olefile
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree
from app.word_structure import table_structure, table_text, associate_preview, compatibility_copy, normalized, PARSER_VERSION

MAX_TEXT = 2_000_000
MAX_PAGES = 200


def soffice_path():
    explicit = os.environ.get("SOFFICE_PATH")
    if explicit:
        return explicit
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/LibreOfficeDev.app/Contents/MacOS/soffice"
    return str(bundled) if bundled.exists() else shutil.which("soffice")


def validate(path, ext):
    header = path.read_bytes()[:8]
    if ext == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise ValueError("扩展名与实际文件格式不一致，请上传有效的 PDF。")
        with fitz.open(path) as doc:
            if doc.needs_pass:
                raise ValueError("文件需要密码，请自行解密后重新上传。")
            if doc.page_count > MAX_PAGES:
                raise ValueError(f"PDF 超过 {MAX_PAGES} 页限制。")
    elif ext == ".docx":
        if header.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ValueError("文件可能已加密或格式不匹配，请解密并另存为 DOCX 后上传。")
        try:
            with zipfile.ZipFile(path) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("文件不是有效的 Word DOCX。")
                if sum(i.file_size for i in archive.infolist()) > 100_000_000:
                    raise ValueError("DOCX 解压内容超过 100 MB 安全限制，请拆分文档。")
        except zipfile.BadZipFile:
            raise ValueError("DOCX 已损坏或格式不匹配，请重新导出。")
    elif ext == ".xlsx":
        try:
            with zipfile.ZipFile(path) as archive:
                if "xl/workbook.xml" not in archive.namelist(): raise ValueError("文件不是有效的 XLSX。")
                if len(archive.infolist()) > 10000 or sum(i.file_size for i in archive.infolist()) > 100_000_000:
                    raise ValueError("XLSX 解压内容超过安全限制，请拆分文件。")
                if any('vbaProject' in n for n in archive.namelist()): raise ValueError("不支持带宏的工作簿，请另存为无宏 XLSX。")
        except zipfile.BadZipFile: raise ValueError("XLSX 已损坏、加密或格式不匹配，请重新导出。")
    elif ext == ".doc":
        if not olefile.isOleFile(path):
            raise ValueError("扩展名与实际格式不一致，请上传 Word 97–2003 DOC 文件。")
        with olefile.OleFileIO(path) as ole:
            if not ole.exists("WordDocument"):
                raise ValueError("文件不是可读取的 DOC，可能加密或格式不匹配。")
            fib = ole.openstream("WordDocument").read(12)
            if len(fib) >= 12 and int.from_bytes(fib[10:12], "little") & 0x8100:
                raise ValueError("DOC 文件已加密，请自行解密后重新上传。")
    else:
        raise ValueError("当前支持 PDF、DOCX、DOC 和 XLSX。")


def convert(source, target_dir, fmt):
    binary = soffice_path()
    if not binary:
        raise ValueError("未配置 LibreOffice 转换服务；原文件已保留，请配置后重试。")
    target_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    # The bundled macOS headless build needs an explicit fontconfig location
    # to discover system CJK fonts. Keep caller-provided configuration intact.
    fontconfig = Path(binary).resolve().parent.parent / "Resources" / "fontconfig"
    if (fontconfig / "fonts.conf").is_file():
        env.setdefault("FONTCONFIG_FILE", str(fontconfig / "fonts.conf"))
        env.setdefault("FONTCONFIG_PATH", str(fontconfig))
    with tempfile.TemporaryDirectory(prefix="p18-office-") as profile:
        result = subprocess.run(
            [binary, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless", "--convert-to", fmt,
             "--outdir", str(target_dir), str(source)], capture_output=True, timeout=60, env=env,
        )
    output = target_dir / (source.stem + "." + fmt.split(":")[0])
    if result.returncode or not output.exists() or not output.stat().st_size:
        raise ValueError("文件转换失败，请检查文件是否损坏或受密码保护，或重新导出后重试。")
    return output


def issue(kind, message, page=None, block=None):
    return {"kind": kind, "message": message, "page": page, "block": block}


def parse_pdf(path):
    blocks, issues, pages = [], [], []
    total = 0
    with fitz.open(path) as doc:
        for number, page in enumerate(doc, 1):
            text = page.get_text("text", sort=True).strip()
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError("提取内容超过 200 万字符，请拆分文档。")
            image_info = page.get_image_info()
            pages.append({"page": number, "characters": len(text), "images": len(image_info)})
            if not text:
                if image_info:
                    issues.append(issue("no_text", "未提取到文字，可能包含扫描内容；当前未进行图片文字识别。", number))
                elif page.get_drawings():
                    issues.append(issue("no_text", "此页包含图形但未提取到文字，请核对是否遗漏内容。", number))
                else:
                    pages[-1]["blank"] = True
            elif any(fitz.Rect(i["bbox"]).get_area() > page.rect.get_area() * .10 for i in image_info):
                issues.append(issue("image", "本页包含较大图片，图片文字未识别，请核对内容是否完整。", number))
            if "\ufffd" in text or "\x00" in text:
                issues.append(issue("characters", "检测到异常字符，请与原文核对。", number))
            tables = []
            try:
                found = page.find_tables()
                for index, table in enumerate(found.tables, 1):
                    rows = table.extract()
                    tables.append({"rows": rows, "index": index})
                    if any(c is None for row in rows for c in row):
                        issues.append(issue("table", f"表格 {index} 可能包含合并或缺失单元格，请核对行列对应关系。", number))
            except Exception:
                issues.append(issue("table", "本页表格结构检查未完成，请人工核对。", number))
            blocks.append({"id": f"page-{number}", "kind": "page", "label": f"第 {number} 页", "page": number,
                           "text": text, "tables": tables})
    return {"blocks": blocks, "issues": issues, "pages": pages, "characters": total}


def parse_word(path):
    doc = Document(path)
    blocks, issues = [], []
    section = "正文"
    paragraph_count = table_count = total = 0
    for node in doc.element.body:
        if node.tag == qn("w:p"):
            p = Paragraph(node, doc)
            paragraph_count += 1
            text = p.text
            style = p.style.name if p.style else ""
            if style.startswith("Heading") and text.strip():
                section = text.strip()
            bid = f"paragraph-{paragraph_count}"
            label = f"{section} · 段落 {paragraph_count}"
            blocks.append({"id": bid, "kind": "paragraph", "label": label, "text": text, "tables": [], "section": section, "style": style,
                           "has_objects": bool(node.xpath(".//w:drawing | .//w:pict | .//w:object | .//m:oMath")),
                           "heading_level": int(style.split()[-1]) if style.startswith("Heading ") and style.split()[-1].isdigit() else None})
            if node.xpath(".//w:drawing | .//w:pict"):
                issues.append(issue("image", f"{label} 含图片，图片文字未识别，请核对内容完整性。", block=bid))
            if node.xpath(".//m:oMath | .//m:oMathPara"):
                issues.append(issue("formula", f"{label} 含公式对象，请查看原文；当前不保证公式还原。", block=bid))
            if "\ufffd" in text or "\x00" in text:
                issues.append(issue("characters", f"{label} 存在异常字符，请核对。", block=bid))
            total += len(text)
        elif node.tag == qn("w:tbl"):
            table_count += 1
            table = Table(node, doc)
            bid = f"table-{table_count}"
            structure = table_structure(table, bid)
            text = table_text(structure)
            total += len(text)
            blocks.append({"id": bid, "kind": "table", "label": f"{section} · 表格 {table_count}",
                           "text": text, "section": section, "tables": [{**structure, "index": table_count}]})
            if node.xpath(".//w:gridSpan | .//w:vMerge | ./w:tr/w:tc/w:tbl"):
                issues.append(issue("table", f"表格 {table_count} 存在合并单元格或嵌套结构，请核对行列对应关系。", block=bid))
            if node.xpath(".//w:drawing | .//w:pict | .//m:oMath"):
                issues.append(issue("objects", f"表格 {table_count} 含图片或公式对象，请核对未提取内容。", block=bid))
        elif node.tag != qn("w:sectPr"):
            issues.append(issue("structure", "文档包含当前未直接解析的结构，请核对原文。"))
        if total > MAX_TEXT:
            raise ValueError("提取内容超过 200 万字符，请拆分文档。")
    if doc.element.xpath(".//w:txbxContent | .//w:object | .//w:ins | .//w:del"):
        issues.append(issue("objects", "文档含文本框、嵌入对象或修订内容，提取可能不完整，请核对原文。"))
    with zipfile.ZipFile(path) as archive:
        if any(any(note.get(qn('w:type'), 'normal') == 'normal' and (''.join(note.itertext()).strip() or note.xpath('.//w:drawing | .//w:object', namespaces={'w': qn('w:p').split('}')[0][1:]}))
                   for note in etree.fromstring(archive.read(name)))
               for name in ('word/footnotes.xml', 'word/endnotes.xml') if name in archive.namelist()):
            issues.append(issue("notes", "文档包含脚注或尾注，当前正文提取不覆盖这些内容，请核对。"))
    return {"blocks": blocks, "issues": issues, "pages": [], "characters": total}


def parse_word_selected(path, ext):
    """DOCX/DOC extraction; the Docling backend is opt-in and never silent.

    Default remains parse_word. P18_PARSER=docling switches backends for this
    process only; a missing package fails the parse rather than changing quality
    without telling the reviewer.
    """
    if ext in {".docx", ".doc"} and os.environ.get("P18_PARSER", "").strip().lower() == "docling":
        from app.docling_word import available, extract
        if not available():
            raise ValueError("已配置 Docling 解析（P18_PARSER=docling），但当前环境未安装 docling；"
                             "请安装后重试，或去掉该环境变量。")
        return extract(path)
    return parse_word(path)


def process(folder, ext):
    source = folder / ("original" + ext)
    validate(source, ext)
    result = {"preview": {}, "preview_warnings": [], "parser_version": PARSER_VERSION}
    word = source
    if ext == ".doc":
        word = convert(source, folder / "converted", "docx")
        result["converted"] = str(word.relative_to(folder))
    if ext == '.xlsx':
        from app.excel_parser import parse_excel
        result.update(parse_excel(source))
        result['parser_version']=result['excel_parser_version']
        if not result['characters']: result['error']='工作簿没有可提取的单元格内容。'
        return result
    result.update(parse_pdf(source) if ext == ".pdf" else parse_word_selected(word, ext))
    if ext == ".pdf":
        result["preview"]["original"] = source.name
    else:
        for variant, target in [("original", source)] + ([("converted", word)] if ext == ".doc" else []):
            try:
                preview_copy = folder / ('preview-source-' + variant + '.docx')
                compatibility_copy(word, preview_copy)
                preview = convert(preview_copy, folder / ("preview-" + variant), "pdf")
                result['preview_font'] = 'Arial Unicode MS（仅临时预览副本）'
                result["preview"][variant] = str(preview.relative_to(folder))
                pages = associate_preview(result['blocks'], preview, variant)
                expected = [b['text'] for b in result['blocks'] if b['kind'] == 'paragraph'] + [c['text'] for b in result['blocks'] for t in b.get('tables', []) for c in t.get('cells', [])]
                if any(len(normalized(text)) >= 8 and normalized(text) not in ''.join(pages) for text in expected):
                    result['preview_warnings'].append('Word 转换预览可能不完整，请下载原文件核对；系统转换预览页码可能与 Word 分页不同。')
            except Exception:
                result["preview_warnings"].append(f"{variant} 的转换预览未生成，可下载文件核对；预览失败不等于正文解析失败。")
    if not result["characters"]:
        result["error"] = "未提取到可用于检索的文字。可能是扫描内容、空白文档或特殊对象；当前不进行 OCR。"
    return result
