import json
import sys
from pathlib import Path
from app.parser import process

folder = Path(sys.argv[1])
try:
    result = process(folder, sys.argv[2])
except Exception as exc:
    message = str(exc) if isinstance(exc, ValueError) else "文件解析或转换未完成，请检查格式或重新导出后重试。"
    result = {"error": message, "blocks": [], "issues": [], "pages": [], "characters": 0}
(folder / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
