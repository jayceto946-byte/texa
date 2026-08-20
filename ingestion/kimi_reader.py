"""Kimi Vision 按需阅读 — 合并关键词提取为一次调用"""
import base64
import json
from pathlib import Path
from config import BOOKS_PATH, CHAPTERS_PATH, get_llm, get_model_role_config


class KimiReader:
    def __init__(self, book_name: str):
        self.book_name = book_name
        self.cache_dir = Path(CHAPTERS_PATH) / book_name
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.kw_cache_dir = self.cache_dir / "_keywords"
        self.kw_cache_dir.mkdir(parents=True, exist_ok=True)

    def read_pages(self, pdf_path: Path, start_page: int, end_page: int,
                   chapter: str = "", question: str = "",
                   extract_keywords: bool = True) -> tuple[str, list[str]]:
        """Kimi Vision 读取页面，自动分批发避免超时。每批 4 页。"""
        total_text = ""
        all_kws = []
        batch_size = 4

        pos = start_page
        while pos < end_page:
            batch_end = min(pos + batch_size, end_page)
            cache_file = self._cache_path(chapter, pos, batch_end)
            kw_file = self.kw_cache_dir / f"{self._chapter_safe(chapter)}_p{pos+1}-{batch_end}_kw.json"

            if cache_file.exists():
                total_text += cache_file.read_text(encoding="utf-8")
                if kw_file.exists():
                    all_kws += json.loads(kw_file.read_text())
                pos = batch_end
                continue

            text, kws = self._read_batch(pdf_path, pos, batch_end, chapter, question, extract_keywords)
            total_text += text
            all_kws += kws
            pos = batch_end

        return total_text, all_kws

    def _read_batch(self, pdf_path: Path, start: int, end: int,
                    chapter: str, question: str, extract_keywords: bool) -> tuple[str, list[str]]:
        """单批读取 4 页"""
        import fitz
        doc = fitz.open(pdf_path)
        images = []
        actual = []
        for p in range(start, min(end, len(doc))):
            pix = doc[p].get_pixmap(dpi=72)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })
            actual.append(p + 1)
        doc.close()

        if not images:
            return "", []

        client = self._get_client()
        if client is None:
            return "", []

        prompt = (
            f"Transcribe these textbook pages (p{actual[0]}-{actual[-1]}). "
            f"Include ALL math formulas in LaTeX ($...$ or $$...$$). Keep original structure."
        )
        if question:
            prompt += f" Focus on: {question}"
        if extract_keywords:
            prompt += (
                "\n\nAfter transcribing, extract 3-5 KEY technical terms. "
                "Return: {\"keywords\": [\"term1\",\"term2\"]}"
            )

        content = [{"type": "text", "text": prompt}] + images
        resp = client.chat.completions.create(
            model=get_model_role_config("vision").model,
            messages=[{"role": "user", "content": content}],
            timeout=120,
        )
        raw = resp.choices[0].message.content or ""

        text, kws = self._split_keywords(raw)

        cache_file = self._cache_path(chapter, start, end)
        cache_file.write_text(text, encoding="utf-8")
        kw_file = self.kw_cache_dir / f"{self._chapter_safe(chapter)}_p{start+1}-{end}_kw.json"
        if kws:
            kw_file.write_text(json.dumps(kws, ensure_ascii=False))

        return text, kws

        # Kimi Vision
        import fitz
        doc = fitz.open(pdf_path)
        images = []
        pages = min(min(end_page - start_page, 6), 6)
        step = max(1, (end_page - start_page) // pages) if pages > 0 else 1
        actual_pages = []
        for p in range(start_page, min(end_page, len(doc)), step):
            pix = doc[p].get_pixmap(dpi=72)
            b64 = base64.b64encode(pix.tobytes("png")).decode()
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })
            actual_pages.append(p + 1)
        doc.close()

        if not images:
            return "", []

        client = self._get_client()
        if client is None:
            return "", []

        prompt = (
            f"Transcribe these textbook pages (p{actual_pages[0]}-{actual_pages[-1]}). "
            f"Include ALL math formulas in LaTeX ($...$ or $$...$$). "
            f"Keep original structure."
        )
        if question:
            prompt += f" Focus on: {question}"
        if extract_keywords:
            prompt += (
                "\n\nAfter transcribing, extract 5-10 KEY technical terms/concepts "
                "and return them in JSON at the end: "
                '{"keywords": ["term1","term2",...]}'
            )

        content = [{"type": "text", "text": prompt}] + images
        resp = client.chat.completions.create(
            model=get_model_role_config("vision").model,
            messages=[{"role": "user", "content": content}],
        )
        raw = resp.choices[0].message.content or ""

        # 分离关键词和正文
        text, kws = self._split_keywords(raw)

        cache_file.write_text(text, encoding="utf-8")
        if kws:
            kw_file.write_text(json.dumps(kws, ensure_ascii=False))

        return text, kws

    def _split_keywords(self, raw: str) -> tuple[str, list[str]]:
        """从回复尾部提取关键词JSON"""
        kws = []
        # 尝试从末尾找 {"keywords": [...]}
        import re
        m = re.search(r'\{"keywords"\s*:\s*\[(.*?)\]\}', raw, re.DOTALL)
        if m:
            try:
                kws = json.loads(m.group(0)).get("keywords", [])
                text = raw[:m.start()].strip()
                return text, kws
            except json.JSONDecodeError:
                pass
        return raw, []

    def extract_keywords(self, text: str, chapter: str) -> list[str]:
        """独立提取关键词（缓存未命中时才调）"""
        if not text or len(text) < 100:
            return [chapter]
        llm = get_llm()
        prompt = f"Extract 5-10 key concepts from this text. Return JSON array only: [\"term1\",\"term2\"]\n\nChapter:{chapter}\nText:{text[:3000]}"
        resp = llm.invoke(prompt).content.strip()
        if resp.startswith("```"): resp = resp.split("\n", 1)[-1].rsplit("\n", 1)[0]
        try:
            return json.loads(resp)
        except json.JSONDecodeError:
            return [chapter]

    def _cache_path(self, chapter: str, start: int, end: int) -> Path:
        return self.cache_dir / f"{self._chapter_safe(chapter)}_p{start+1}-{end}.txt"

    def _chapter_safe(self, chapter: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in chapter)[:40]

    def _get_client(self):
        from config import get_llm_client

        return get_llm_client("vision")
