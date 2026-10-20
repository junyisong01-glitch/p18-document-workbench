"""Conservative source highlighting. Never infer pages from display labels."""
import re
import pymupdf as fitz


def locate(path, ext, chunk):
    fallback = {"status": "unavailable", "pages": [], "message": "无法精确高亮原文；以下为真实提取片段，页码不作推断。"}
    # Word structure alone is not reliable rendered geometry.
    if ext != ".pdf":
        return fallback
    pages = {s.get("page") for s in chunk.get("sources", []) if type(s.get("page")) is int}
    parts = list(dict.fromkeys(p.strip() for p in chunk["text"].split("\n\n") if len(re.sub(r"\s", "", p)) >= 6))
    normalize = lambda value: re.sub(r"\s", "", value)
    found = []
    with fitz.open(path) as pdf:
        all_text = [normalize(page.get_text()) for page in pdf]
        for number in sorted(pages):
            if not 1 <= number <= len(pdf):
                continue
            page = pdf[number - 1]
            boxes = []
            for part in parts:
                if sum(text.count(normalize(part)) for text in all_text) != 1:
                    continue  # Repeated text is not a trustworthy occurrence.
                for rect in page.search_for(part):
                    rect = rect * page.rotation_matrix
                    box = [rect.x0/page.rect.width, rect.y0/page.rect.height,
                           rect.x1/page.rect.width, rect.y1/page.rect.height]
                    if 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1 and box not in boxes:
                        boxes.append(box)
            if boxes:
                found.append({"page": number, "rects": boxes})
    if not found:
        return fallback
    return {"status": "matched", "pages": found,
            "message": "黄色标记为在可靠物理页中唯一匹配的片段文字；未标记部分请结合提取片段核对。"}
