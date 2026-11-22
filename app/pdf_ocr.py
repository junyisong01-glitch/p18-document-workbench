"""Run Apple's local text recognizer only for PDF pages that need it."""
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
        self.binary = Path(self.configured_binary) if self.configured_binary else self.directory / "recognize-text"
        self.image = self.directory / "page.png"
        self.deadline = time.monotonic() + 100
        self.unavailable = False

    def recognize(self, page):
        if self.unavailable or sys.platform != "darwin":
            raise OcrError("此环境的本地 OCR 不可用。")
        if self.configured_binary and not (self.binary.is_absolute() and self.binary.is_file()
                                           and os.access(self.binary, os.X_OK)):
            raise OcrError("已配置的本地 OCR 程序不可用。")
        if not self.binary.is_file():
            try:
                subprocess.run(
                    ["/usr/bin/swiftc", "-module-cache-path", str(self.directory / "modules"),
                     str(Path(__file__).with_name("pdf_ocr.swift")), "-o", str(self.binary)],
                    check=True, capture_output=True, timeout=30,
                )
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
