"""PDF解析 — 内置目录 > Kimi TOC"""
import re
from collections import Counter
from pathlib import Path
import fitz


class PDFParser:
    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        self.doc = fitz.open(self.pdf_path)
        self.total_pages = len(self.doc)

    def extract_text(self) -> str:
        text = ""
        for page in self.doc:
            text += page.get_text() + "\n"
        return text

    def extract_text_by_page(self) -> list[str]:
        return [page.get_text() for page in self.doc]

    def extract_chapters(self, toc_page_range: str = "") -> list[dict]:
        """优先级: 用户指定页码 > 内置目录 > 文本目录 > 字体分析 > Kimi扫描"""

        # 1. 用户指定页码（最高优先级）
        if toc_page_range:
            try:
                parts = toc_page_range.replace("-", ",").replace("，", ",").split(",")
                toc_start = int(parts[0].strip())
                toc_end = int(parts[-1].strip())
                if 1 <= toc_start <= toc_end <= self.total_pages:
                    print(f"[TOC] 用户指定 p{toc_start}-{toc_end}", flush=True)
                    return self._kimi_ocr_toc_pages(toc_start, toc_end)
            except (ValueError, IndexError):
                pass

        # 2. 内置目录
        toc = self.doc.get_toc()
        if toc:
            return self._chapters_from_toc(toc)

        # 文本目录页
        chapters = self._find_toc_page_and_parse()
        if chapters:
            return chapters

        # 字体分析
        chapters = self._chapters_from_font_analysis()
        if len(chapters) >= 2:
            return chapters

        return self._kimi_toc_scan()

    # ----- Kimi TOC（主力方案）-----

    def _kimi_ocr_toc_pages(self, start_page: int, end_page: int) -> list[dict]:
        """直接 OCR 已知目录页码（跳过搜索，快）"""
        return self._extract_chapters_via_kimi(start_page - 1, end_page)

    def _kimi_toc_scan(self) -> list[dict]:
        """完整 Kimi 流程：搜目录 → OCR"""
        import base64, json
        from config import get_llm_client, get_model_role_config

        model_config = get_model_role_config("vision")
        client = get_llm_client("vision")
        if client is None or not model_config.credential_configured:
            return self._fallback_single_chapter()
        scan = min(20, self.total_pages)

        print(f"[TOC-Kimi] 扫描前{scan}页...", flush=True)
        images = []
        for i in range(scan):
            pix = self.doc[i].get_pixmap(dpi=80)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        resp = client.chat.completions.create(
            model=model_config.model,
            messages=[{"role": "user", "content": [{
                "type": "text",
                "text": "Find the TOC pages. Return JSON: {\"toc_start\": int, \"toc_end\": int}"
            }] + images}],
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"): text = text.split("\n", 1)[-1].rsplit("\n", 1)[0]
        try:
            loc = json.loads(text)
            toc_start = int(loc.get("toc_start", 0) or 0)
            toc_end = int(loc.get("toc_end", 0) or 0)
        except json.JSONDecodeError:
            return self._fallback_single_chapter()

        if toc_start < 1:
            return self._fallback_single_chapter()

        return self._extract_chapters_via_kimi(toc_start - 1, toc_end)

    def _extract_chapters_via_kimi(self, toc_start_0b: int, toc_end: int) -> list[dict]:
        """Kimi OCR 目录页并解析为章节列表"""
        import base64, json
        from config import get_llm_client, get_model_role_config

        model_config = get_model_role_config("vision")
        client = get_llm_client("vision")
        if client is None or not model_config.credential_configured:
            return self._fallback_single_chapter()
        print(f"[TOC-Kimi] OCR p{toc_start_0b+1}-p{toc_end}...", flush=True)

        toc_imgs = []
        for i in range(toc_start_0b, min(toc_end, self.total_pages)):
            pix = self.doc[i].get_pixmap(dpi=100)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            toc_imgs.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        resp = client.chat.completions.create(
            model=model_config.model,
            messages=[{"role": "user", "content": [{
                "type": "text",
                "text": (
                    "Extract ALL chapters and sections with page numbers. "
                    "Return JSON: [{\"title\":\"Ch1 Title\",\"page\":int,\"subs\":[{\"title\":\"1.1\",\"page\":int}]}]"
                ),
            }] + toc_imgs}],
        )
        result = resp.choices[0].message.content.strip()
        if result.startswith("```"): result = result.split("\n", 1)[-1].rsplit("\n", 1)[0]

        try: structure = json.loads(result)
        except json.JSONDecodeError: return self._fallback_single_chapter()

        chapters = []
        for item in structure:
            pg = item.get("page") or 0
            if isinstance(pg, str):
                try: pg = int(pg)
                except ValueError: pg = 0
            title = item.get("title") or f"Ch{len(chapters)+1}"
            if pg < 1 or pg > self.total_pages: continue
            chapters.append({"title": title, "page_number": pg, "subsections": item.get("subs", [])})

        if len(chapters) < 2: return self._fallback_single_chapter()

        for idx, ch in enumerate(chapters):
            end = chapters[idx + 1]["page_number"] - 1 if idx + 1 < len(chapters) else self.total_pages
            ch["end_page"] = end
            ch["text"] = "".join(self.doc[p].get_text() + "\n" for p in range(ch["page_number"] - 1, end))

        print(f"[TOC-Kimi] {len(chapters)}章", flush=True)
        return chapters
        name = self.pdf_path.stem
        text = self.extract_text()[:10000]
        return [{"title": f"{name} (全文)", "text": text, "page_number": 1}]

    # ----- 内置目录 -----

    def _chapters_from_toc(self, toc: list) -> list[dict]:
        chapters = []
        for idx, (level, title, page) in enumerate(toc):
            if level != 1:
                continue
            end_page = next((t[2] for t in toc[idx + 1:] if t[0] == 1), self.total_pages + 1)
            text = "".join(self.doc[p].get_text() + "\n" for p in range(page - 1, min(end_page - 1, self.total_pages)))
            chapters.append({"title": title.strip(), "page_number": page, "text": text, "end_page": end_page - 1})
        return chapters

    # ----- 文本目录页 -----

    def _find_toc_page_and_parse(self) -> list[dict]:
        scan = min(20, self.total_pages)
        has_text = any(len(self.doc[i].get_text().strip()) > 50 for i in range(scan))
        if not has_text:
            return []
        return self._toc_from_text()

    def _toc_from_text(self) -> list[dict]:
        scan = min(20, self.total_pages)
        toc_start, toc_end = None, None
        for i in range(scan):
            text = self.doc[i].get_text()
            if re.search(r'目\s*录', text):
                if toc_start is None: toc_start = i
                toc_end = i
            elif toc_start is not None:
                break
        if toc_start is None:
            return []

        toc_text = ""
        for i in range(toc_start, min(toc_end + 3, self.total_pages)):
            toc_text += self.doc[i].get_text() + "\n"
        entries = self._parse_toc_text(toc_text)
        if not entries:
            return []
        return self._build_from_entries(entries)

    # ----- 字体分析 -----

    def _chapters_from_font_analysis(self) -> list[dict]:
        candidates = []
        sample = min(200, self.total_pages)
        for p in range(sample):
            blocks = self.doc[p].get_text("dict")["blocks"]
            for block in blocks:
                if "lines" not in block: continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        size = round(span["size"], 1)
                        txt = span["text"].strip()
                        if txt and size >= 14:
                            candidates.append((p, size, txt))
                    break
                break
        if not candidates:
            return []

        sizes = [s for _, s, _ in candidates]
        big = {s: c for s, c in Counter(sizes).items() if s >= 14}
        if not big:
            return []

        chapter_size = next((s for s, c in big.most_common() if 2 <= c <= 80), max(big.keys()))
        seen = set()
        pages = [(pg, txt) for pg, sz, txt in candidates if sz == chapter_size and txt not in seen and not seen.add(txt)]
        pages.sort()

        filtered = []
        last = -10
        for pg, txt in pages:
            if pg - last >= 3:
                filtered.append((pg, txt))
                last = pg
        if len(filtered) < 2:
            return []
        return self._build_chapters_from_pages(filtered)

    # ----- 工具 -----

    def _parse_toc_text(self, toc_text: str) -> list[dict]:
        for pat in [
            re.compile(r'(第[一二三四五六七八九十百零\d]+章[^\d]*?)\s*\.*?\s*(\d{1,4})\s*$', re.MULTILINE),
            re.compile(r'(.{0,5}第[一二三四五六七八九十百零\d]+章.{0,60})\s+(\d{1,4})$', re.MULTILINE),
        ]:
            m = pat.findall(toc_text)
            if len(m) >= 2:
                return [{"title": x[0].strip(), "page": int(x[1])} for x in m]
        return []

    def _build_chapters_from_pages(self, pages):
        chs = []
        for idx, (pg, title) in enumerate(pages):
            end = pages[idx + 1][0] if idx + 1 < len(pages) else self.total_pages
            t = "".join(self.doc[p].get_text() + "\n" for p in range(pg, end))
            chs.append({"title": title, "page_number": pg + 1, "text": t, "end_page": end})
        return chs

    def _build_from_entries(self, entries):
        chs = []
        for idx, e in enumerate(entries):
            page = e["page"] - 1
            if page < 0 or page >= self.total_pages: continue
            end = entries[idx + 1]["page"] - 1 if idx + 1 < len(entries) else self.total_pages
            t = "".join(self.doc[p].get_text() + "\n" for p in range(page, end))
            chs.append({"title": e["title"], "page_number": e["page"], "text": t, "end_page": end})
        return chs

    def close(self):
        self.doc.close()

import os
