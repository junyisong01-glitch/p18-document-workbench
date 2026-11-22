"""Local OCR with bounded execution; cached macOS Vision or optional Linux Tesseract."""
import hashlib
import fcntl
import tempfile
import csv
import io
import shutil
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pymupdf as fitz


class OcrError(ValueError):
    pass


class PdfOcr:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.configured_binary = os.environ.get("P18_PDF_OCR_HELPER")
        source=Path(__file__).with_name('pdf_ocr.swift')
        cache=Path(os.environ.get('P18_DATA_DIR', str(source.resolve().parents[1]/'runtime')))/'ocr-tools'
        self.binary = Path(self.configured_binary) if self.configured_binary else cache/('vision-'+hashlib.sha256(source.read_bytes()).hexdigest()[:16])
        self.image = self.directory / "page.png"
        self.deadline = time.monotonic() + 100
        self.unavailable = False
        self.backend = os.environ.get('P18_OCR_BACKEND', 'auto')
        if self.backend == 'auto':self.backend = 'vision' if sys.platform == 'darwin' else 'tesseract'


    def recognize(self, page):
        if self.backend == 'tesseract':return self.tesseract(page)
        if self.backend != 'vision':raise OcrError('OCR 引擎配置无效，请检查 P18_OCR_BACKEND。')
        if self.unavailable or sys.platform != "darwin":
            raise OcrError("此环境的本地 OCR 不可用。")
        if self.configured_binary and not (self.binary.is_absolute() and self.binary.is_file()
                                           and os.access(self.binary, os.X_OK)):
            raise OcrError("已配置的本地 OCR 程序不可用。")
        if not self.binary.is_file():
            try:
                self.binary.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                with (self.binary.parent/'compile.lock').open('a') as lock:
                    # Only one worker compiles; others poll within the same bounded budget.
                    while True:
                        try:
                            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                        except BlockingIOError:
                            if time.monotonic()>self.deadline:raise OcrError('OCR 初始化等待超时，请重试。')
                            time.sleep(.1)
                    if not self.binary.is_file():
                        with tempfile.TemporaryDirectory(dir=self.binary.parent) as build:
                            binary=Path(build)/'recognize-text'
                            subprocess.run(['/usr/bin/swiftc','-module-cache-path',str(Path(build)/'modules'),
                                str(Path(__file__).with_name('pdf_ocr.swift')),'-o',str(binary)],
                                check=True,capture_output=True,timeout=30)
                            os.replace(binary,self.binary)
            except (OSError, subprocess.SubprocessError):
                self.unavailable = True
                raise OcrError("此环境的本地 OCR 不可用。") from None

        remaining = self.deadline - time.monotonic()
        if remaining < 1:
            raise OcrError("已达到单文件 OCR 时间上限，请拆分后重试。")
        scale = min(3, 2400 / max(page.rect.width, page.rect.height))
        try:
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB,
                            alpha=False, annots=False).save(self.image)
            result = subprocess.run(
                [str(self.binary), str(self.image)], check=True, capture_output=True,
                timeout=min(30, remaining),
            )
            lines = json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            raise OcrError("本页 OCR 超时。") from None
        except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError):
            raise OcrError("本页 OCR 未完成。") from None
        return [line for line in lines if line["text"].strip()]

    def tesseract(self, page):
        """Optional Linux CPU engine. Never install/download models during an upload."""
        binary = shutil.which('tesseract')
        if not binary:raise OcrError('本机未安装 OCR 引擎，请安装 Tesseract 及简体中文、英文语言包后重试。')
        remaining = self.deadline-time.monotonic()
        if remaining<1:raise OcrError('已达到单文件 OCR 时间上限，请拆分后重试。')
        scale=min(3,2400/max(page.rect.width,page.rect.height))
        try:
            page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False,annots=False).save(self.image)
            result=subprocess.run([binary,str(self.image),'stdout','-l','chi_sim+eng','tsv'],
                check=True,capture_output=True,timeout=min(30,remaining),
                env={**os.environ,'OMP_THREAD_LIMIT':'1'})
            groups={}
            for word in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')),delimiter='\t'):
                if word.get('level')!='5' or not word.get('text','').strip():continue
                key=tuple(word[k] for k in ('page_num','block_num','par_num','line_num'))
                line=groups.setdefault(key,{'text':'','confidence':1.0})
                line['text']+=(' ' if line['text'] else '')+word['text']
                line['confidence']=min(line['confidence'],float(word['conf'])/100)
            return list(groups.values())
        except subprocess.TimeoutExpired:
            raise OcrError('本页 OCR 超时。') from None
        except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, KeyError):
            raise OcrError('本页 OCR 未完成，请检查图片和本机 OCR 中文、英文语言包。') from None
