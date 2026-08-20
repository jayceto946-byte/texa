"""DEPRECATED: legacy Gradio web UI.

This module is retained only for historical reference and is not part of the
supported entry points. The active web backend is ``backend.main:app``; start it
with ``python main.py web`` or ``python -m uvicorn backend.main:app``.
"""
__deprecated__ = True

import warnings

warnings.warn(
    "ui.web is deprecated; use the FastAPI backend instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json, time, io, base64, threading, re
from pathlib import Path
from typing import Optional
import gradio as gr
from config import BOOKS_PATH, PROGRESS_PATH, get_llm
from ingestion.pdf_parser import PDFParser
from ingestion.kimi_reader import KimiReader
from knowledge.keyword_index import KeywordIndex
from knowledge.kg_visualizer import KGVisualizer, generate_kg_html
from ingestion.background_reader import BackgroundReader
from memory.study_memory import StudyMemory
from memory.feedback import FeedbackLoop
from memory.mistake_book import get_mistake_book, MistakeRecord, MISTAKE_TYPES

CSS = """
footer { display: none !important; }
"""

LATEX_DELIMITERS = [
    {"left": "$$", "right": "$$", "display": True},
    {"left": "$", "right": "$", "display": False},
]

_SKIP_CHAPTER_KEYWORDS = {"参考文献", "附录", "目录", "前言"}


def _is_skip_chapter(title: str) -> bool:
    for kw in _SKIP_CHAPTER_KEYWORDS:
        if kw in title:
            return True
    return False


class StudyWebUI:
    def __init__(self):
        self.kimi_reader: Optional[KimiReader] = None
        self.kw_index: Optional[KeywordIndex] = None
        self.memory: Optional[StudyMemory] = None
        self.feedback: Optional[FeedbackLoop] = None
        self.current_book: Optional[str] = None
        self.chapters: list[dict] = []
        self.book_pdf_path: Optional[Path] = None
        self.bg_reader: Optional[BackgroundReader] = None
        self._vector_store = None
        self._kg_cache = None
        self._kg_lock = threading.Lock()
        self._kg_building = False
        self._vs_lock = threading.Lock()
        self._vs_warmup_thread = None

    # === 缓存管理 ===

    def _start_warmup(self):
        """后台静默预加载嵌入模型，避免首问卡顿。"""
        if self._vs_warmup_thread is not None:
            return

        def _warmup():
            try:
                print("[后台] 预加载嵌入模型...", flush=True)
                self._get_vector_store()
                print("[后台] 嵌入模型加载完成", flush=True)
            except Exception as e:
                print(f"[后台] 嵌入模型预加载失败: {e}", flush=True)

        self._vs_warmup_thread = threading.Thread(target=_warmup, daemon=True)
        self._vs_warmup_thread.start()

    def _get_vector_store(self):
        if self._vector_store is None:
            with self._vs_lock:
                # 双重检查，防止多个线程同时创建
                if self._vector_store is None:
                    from ingestion.vector_store import ChapterVectorStore
                    self._vector_store = ChapterVectorStore()
        return self._vector_store

    def _get_kg(self):
        if self._kg_cache is None or self._kg_cache.book_name != (self.current_book or ""):
            from knowledge.knowledge_graph import KnowledgeGraph
            self._kg_cache = KnowledgeGraph(self.current_book or "default")
        return self._kg_cache

    def _invalidate_caches(self):
        self._vector_store = None
        self._kg_cache = None

    # === 教材管理 ===

    def _ensure(self, name):
        if self.current_book != name:
            self.memory = StudyMemory(name)
            self.feedback = FeedbackLoop(name)
            self.kimi_reader = KimiReader(name)
            self.kw_index = KeywordIndex(name)
            self.current_book = name
            self._invalidate_caches()

    def _save_chapters(self):
        if self.current_book and self.chapters:
            f = Path(PROGRESS_PATH) / self.current_book / "_chapters.json"
            f.parent.mkdir(parents=True, exist_ok=True)
            with open(str(f), "w", encoding="utf-8") as fh:
                json.dump(self.chapters, fh, ensure_ascii=False, indent=2)

    def _load_chapters(self, name):
        f = Path(PROGRESS_PATH) / name / "_chapters.json"
        if f.exists():
            with open(str(f), "r", encoding="utf-8") as fh:
                return json.load(fh)
        return []

    def _get_books(self):
        return list(BOOKS_PATH.glob("*.pdf"))

    def list_books(self):
        return [p.stem for p in self._get_books()]

    def switch_book(self, name):
        if not name:
            return "", "", "", "", ""
        self._ensure(name)
        pdfs = {p.stem: p for p in self._get_books()}
        self.book_pdf_path = pdfs.get(name)
        self.chapters = self._load_chapters(name)
        if not self.chapters and self.book_pdf_path:
            p = PDFParser(self.book_pdf_path)
            self.chapters = p.extract_chapters()
            p.close()
            self._save_chapters()
        ch_html = self._format_chapter_list(self.chapters)
        kw = self.kw_index.total_terms() if self.kw_index else 0
        kg_html = self._ensure_kg_plot_html()
        return ch_html, self.pre_read_status(), f"共{len(self.chapters)}章 | {kw}关键词", kg_html, name

    def _format_chapter_list(self, chapters: list) -> str:
        """返回HTML格式的章节目录树 — 固定高度+滚动+深色主题"""
        skip_sections = {"本章学习要点", "本章小结", "习题", "思考题", "参考文献", "附录"}
        if not chapters:
            return (
                "<div style='max-height:480px;overflow-y:auto;padding:8px;color:#e2e8f0;'>"
                "<p style='color:#64748b;'>暂无目录</p></div>"
            )

        lines = [
            "<div style='max-height:480px;overflow-y:auto;padding:8px;"
            "font-family:system-ui,-apple-serif;line-height:1.75;color:#e2e8f0;'>"
        ]

        for ch in chapters:
            ch_title = ch.get("title", "")
            ch_page = ch.get("page_number", 1)
            lines.append(
                f"<div style='font-weight:600;color:#f8fafc;margin-top:10px;font-size:15px;'>"
                f"📖 {ch_title} <span style='color:#64748b;font-size:12px;'>p{ch_page}</span></div>"
            )

            subs = ch.get("subsections", [])
            for sub in subs:
                sub_title = sub.get("title", "")
                if any(skip in sub_title for skip in skip_sections):
                    continue
                sub_page = sub.get("page", "")
                match = re.match(r'第([一二三四五六七八九十\d]+)节\s*(.+)', sub_title)
                if match:
                    cn_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                              '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                    num_str = match.group(1)
                    num = int(num_str) if num_str.isdigit() else cn_nums.get(num_str, 1)
                    sub_display = f"{num}. {match.group(2)}"
                else:
                    sub_display = sub_title
                lines.append(
                    f"<div style='padding-left:18px;color:#94a3b8;font-size:13.5px;margin-top:2px;'>"
                    f"├─ {sub_display} <span style='color:#475569;font-size:12px;'>p{sub_page}</span></div>"
                )
        lines.append("</div>")
        return "\n".join(lines)

    def import_book(self, file, pre_read=False, toc_pages=""):
        try:
            if file is None:
                return "请上传PDF", "", "", "", ""
            p = Path(file.name if isinstance(file, dict) else str(file))
            if not p.exists() or p.suffix.lower() != ".pdf":
                return f"无效: {p}", "", "", "", ""
            dest = BOOKS_PATH / p.name
            if p.resolve() != dest.resolve():
                import shutil
                try:
                    shutil.copy2(p, dest)
                except PermissionError:
                    pass
            name = p.stem
            self._ensure(name)
            self.book_pdf_path = dest
            parser = PDFParser(dest)
            self.chapters = parser.extract_chapters(toc_pages.strip() if toc_pages else "")
            parser.close()
            self._save_chapters()
            if not self.chapters:
                self.chapters = [{"title": f"{name} (全文)", "page_number": 1, "end_page": 0}]
            if pre_read and len(self.chapters) >= 2:
                self.start_pre_read()
            ch_html = self._format_chapter_list(self.chapters)
            kg_html = self._ensure_kg_plot_html()
            return (
                ch_html,
                self.pre_read_status(),
                f"导入完成: {name} | {len(self.chapters)}章",
                kg_html,
                gr.update(choices=self.list_books(), value=name),
                name,
            )
        except Exception as e:
            import traceback
            return traceback.format_exc(), "", "", "", "", ""

    def start_pre_read(self):
        if not self.chapters or len(self.chapters) < 2:
            return "请先导入"
        if not self.book_pdf_path:
            return "无PDF"
        if self.bg_reader and self.bg_reader._running:
            return f"预读中: {self.bg_reader.status['done']}/{self.bg_reader.status['total']}"
        self.bg_reader = BackgroundReader(self.current_book, self.chapters, self.book_pdf_path)
        self.bg_reader.start()
        return f"预读已启动 ({len(self.chapters)}章)"

    def pre_read_status(self):
        if self.bg_reader:
            s = self.bg_reader.status
            if s.get("running"):
                return f"预读 {s['done']}/{s['total']}"
            if s.get("done", 0) > 0:
                return f"[OK] 完成 {s['done']}/{s['total']}"
        return ""

    # === 错题本 ===

    def _get_mb(self):
        book = self.current_book or "default"
        return get_mistake_book(book)

    def mb_add(self, q_text, u_ans, c_ans, src, subj, tags_str, mtypes, diff, img):
        if not q_text.strip():
            return "❌ 题目内容不能为空", self.mb_list(subj, "", 50), self.mb_due(subj), self.mb_stats(subj), self.mb_weak(subj)
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        record = MistakeRecord(
            question_text=q_text.strip(),
            user_answer=u_ans.strip(),
            correct_answer=c_ans.strip(),
            source=src.strip(),
            subject=subj.strip() or (self.current_book or "default"),
            chapter=None,
            tags=tags,
            mistake_type=mtypes,
            difficulty=int(diff),
            image_path=str(img) if img else None,
        )
        mb = self._get_mb()
        mb.add(record)
        subj_filter = subj.strip() or (self.current_book or "")
        return (
            f"✅ 已保存（{record.id}）",
            self.mb_list(subj_filter, "", 50),
            self.mb_due(subj_filter),
            self.mb_stats(subj_filter),
            self.mb_weak(subj_filter),
        )

    def mb_list(self, subject_filter, search_kw, limit):
        mb = self._get_mb()
        records = mb.list_all(subject=subject_filter or None, limit=limit)
        if search_kw.strip():
            kw = search_kw.strip().lower()
            records = [r for r in records if kw in r.question_text.lower() or any(kw in t.lower() for t in r.tags)]
        rows = []
        for r in records:
            rows.append([
                r.id,
                r.question_text[:80] + "..." if len(r.question_text) > 80 else r.question_text,
                ", ".join(r.tags) or "—",
                ", ".join(r.mistake_type) or "—",
                r.difficulty,
                r.sm2.get("next_review", "—") if r.sm2 else "—",
            ])
        return rows

    def mb_due(self, subject_filter):
        mb = self._get_mb()
        records = mb.get_due(subject=subject_filter or None)
        rows = []
        for r in records:
            rows.append([
                r.id,
                r.question_text[:80] + "..." if len(r.question_text) > 80 else r.question_text,
                ", ".join(r.tags) or "—",
                ", ".join(r.mistake_type) or "—",
                r.sm2.get("interval", 1) if r.sm2 else 1,
            ])
        return rows

    def mb_review(self, rid, quality):
        if not rid:
            return "请选择一道错题", self.mb_due("")
        mb = self._get_mb()
        try:
            mb.review(rid.strip(), int(quality))
            return f"✅ 已记录复习（quality={quality}）", self.mb_due("")
        except Exception as e:
            return f"❌ {e}", self.mb_due("")

    def mb_explain(self, rid):
        if not rid:
            return "请选择一道错题后再点击讲题"
        mb = self._get_mb()
        try:
            llm = get_llm()
            # 专业课模式：注入RAG上下文；通用模式：不注入
            def rag_provider(record):
                if not self.current_book:
                    return ""
                try:
                    vs = self._get_vector_store()
                    if vs and record.tags:
                        ch_docs = vs.search_all(record.tags[0], k=3)
                        texts = []
                        for ch, docs in ch_docs.items():
                            texts.append(f"【{ch}】")
                            for d in docs:
                                texts.append(d.page_content[:400])
                        return "\n".join(texts)
                except Exception:
                    pass
                return ""
            result = mb.explain(rid.strip(), lambda prompt: llm.invoke(prompt).content, context_provider=rag_provider)
            return result
        except Exception as e:
            return f"❌ 讲题失败: {e}"

    def mb_detail(self, rid):
        if not rid:
            return ""
        mb = self._get_mb()
        r = mb.get(rid.strip())
        if not r:
            return "未找到该错题"
        md = f"""**题目**
{r.question_text}

**用户答案**
{r.user_answer or '（未提供）'}

**正确答案**
{r.correct_answer or '（未提供）'}

**错因**：{', '.join(r.mistake_type) or '—'}
**标签**：{', '.join(r.tags) or '—'}
**来源**：{r.source or '—'}
**难度**：{'⭐' * r.difficulty}
**下次复习**：{r.sm2.get('next_review', '—') if r.sm2 else '—'}
"""
        return md

    def mb_stats(self, subject_filter):
        mb = self._get_mb()
        stats = mb.get_stats(subject=subject_filter or None)
        lines = [
            f"**总错题数**：{stats['total']}",
            f"**今日待复习**：{stats['due_today']}",
        ]
        if stats.get('by_type'):
            lines.append("\n**错因分布**：")
            for t, c in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
                lines.append(f"- {t}: {c} 道")
        return "\n".join(lines)

    def mb_weak(self, subject_filter):
        mb = self._get_mb()
        weak = mb.get_weak_points(subject=subject_filter or None, top_n=8)
        if not weak:
            return "暂无薄弱点数据，请先录入错题"
        lines = ["**薄弱点 TOP 列表**\n"]
        for i, w in enumerate(weak, 1):
            lines.append(f"{i}. **{w['name']}**（{w['type']}）— {w['count']} 道错题")
        return "\n".join(lines)

    # === Stream 问答 ===

    def ask_stream(self, question, history):
        if not self.current_book:
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": "请先在左侧选择教材"})
            yield history, ""
            return

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": "思考中..."})
        yield history, ""

        # 精确章节号匹配，辅助 graph 定位
        chapter_title, _ = self._resolve_chapter_from_question(question)
        target_chapters = [chapter_title] if chapter_title else []

        from graph.main_graph import run_graph_stream
        import time
        t0 = time.time()
        content_started = False
        source_chapters = []

        for event in run_graph_stream(
            question, self.current_book, target_chapters=target_chapters
        ):
            stage = event["stage"]

            if stage == "plan":
                intent = event["intent"]
                source_chapters = event["chapters"]
                status_map = {
                    "teach": "📖 准备讲解",
                    "summarize": "📋 准备总结",
                    "qa": "🔍 检索中",
                    "quiz": "📝 出题中",
                    "plan": "📅 规划中",
                    "cross_chapter": "🔗 跨章节检索",
                }
                history[-1]["content"] = f"{status_map.get(intent, '思考中')}..."
                yield history, ""

            elif stage == "chapter":
                if event.get("has_teaching"):
                    history[-1]["content"] = "📖 整理讲解内容..."
                    yield history, ""

            elif stage == "generate":
                if event.get("chunk"):
                    if not content_started:
                        history[-1]["content"] = ""
                        content_started = True
                    history[-1]["content"] += event["chunk"]
                    yield history, ""

            elif stage == "done":
                # 附加来源章节
                if source_chapters and source_chapters[0]:
                    ch_label = source_chapters[0]
                    if len(source_chapters) > 1:
                        ch_label += f" 等{len(source_chapters)}个章节"
                    history[-1]["content"] += f"\n\n*— {ch_label}*"
                yield history, ""
                print(
                    f"[graph] 总耗时: {time.time()-t0:.1f}s | "
                    f"intent={event['state'].get('intent')} | chapters={source_chapters}",
                    flush=True,
                )

    # === 以下旧方法已移除，逻辑已收归 graph pipeline ===
    # _fast_answer_stream / _read_and_answer_stream / _detect_intent / _teach_stream

    # === 章节号精确匹配 ===

    def _resolve_chapter_from_question(self, question: str) -> tuple[str | None, bool]:
        """从问题中提取章节号并匹配章节列表。

        Returns:
            (chapter_title, is_exercise_query)
        """
        import re

        q = question.lower()

        # 判断是否是习题查询
        exercise_kw = {"习题", "题目", "练习题", "作业", "题号", "怎么做", "求解"}
        is_exercise = any(k in q for k in exercise_kw) or bool(re.search(r'\d+[-–—.]\d+', question))

        # 提取章节号（支持：第四章、第4章、第4节、4. 开头）
        chapter_num = None
        cn_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                   '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

        # 第X章（中文/阿拉伯数字）
        m = re.search(r'第\s*([一二三四五六七八九十\d]+)\s*[章节]', question)
        if m:
            num_str = m.group(1)
            chapter_num = int(num_str) if num_str.isdigit() else cn_nums.get(num_str)

        # chapter X
        if chapter_num is None:
            m = re.search(r'chapter\s*(\d+)', q)
            if m:
                chapter_num = int(m.group(1))

        # 匹配章节标题
        if chapter_num is not None:
            num_str = str(chapter_num)
            for ch in self.chapters:
                if _is_skip_chapter(ch.get("title", "")):
                    continue
                t = ch.get("title", "")
                if num_str in t:
                    return t, is_exercise

        return None, is_exercise

    # === 知识图谱（懒加载，启动时不触发） ===

    def _ensure_kg_plot_html(self):
        """只读取已有缓存，绝不触发构建"""
        if not self.current_book:
            return ""
        html_path = Path(PROGRESS_PATH) / self.current_book / "kg_graph.html"
        if html_path.exists():
            return self._wrap_kg_iframe(html_path)
        return (
            "<p style='color:#64748b;padding:20px;text-align:center;'>"
            "知识图谱未生成<br><span style='font-size:13px;'>"
            "点击上方 🔄 刷新图谱 手动生成</span></p>"
        )

    def _wrap_kg_iframe(self, html_path: Path) -> str:
        try:
            file_url = html_path.as_uri()
            return f'''<iframe src="{file_url}"
                style="width:100%; height:750px; border:none; border-radius:8px; background:#0d1117;"
                sandbox="allow-scripts allow-same-origin allow-popups"
                title="知识图谱">
            </iframe>'''
        except Exception as e:
            return f"<p style='color:red'>加载图谱失败: {e}</p>"

    def _open_kg_in_browser(self) -> str:
        if not self.current_book:
            return "请先选择教材"
        html_path = Path(PROGRESS_PATH) / self.current_book / "kg_graph.html"
        if not html_path.exists():
            return "知识图谱未生成，请先点击 🔄 刷新图谱"
        import webbrowser
        webbrowser.open(html_path.as_uri())
        return f"已在浏览器中打开: {html_path.name}"

    def _build_kg_plot(self):
        if not self.current_book:
            return ""
        kg = self._get_kg()
        if not kg.graph:
            return "<p style='color:#94a3b8;padding:20px;'>知识图谱为空</p>"
        t0 = time.time()
        viz = KGVisualizer(self.current_book)
        # 从本地章节文本提取摘要（零成本，不加载嵌入模型）
        definitions, _ = viz.enrich_definitions(kg.graph, vector_store=None)
        html = viz.generate_html(kg.graph, definitions, kg_instance=kg)
        html_path = viz.save_html(html)
        print(f"[KG] 图谱生成耗时: {time.time()-t0:.2f}s, 路径: {html_path}", flush=True)
        return html_path

    def kg_refresh(self):
        if not self.current_book:
            return "", "请先选择教材"
        html_path = Path(PROGRESS_PATH) / self.current_book / "kg_graph.html"
        if html_path.exists():
            html_path.unlink()

        with self._kg_lock:
            if self._kg_building:
                return "<p style='color:#888;padding:20px;'>知识图谱正在生成中...</p>", "生成中，请稍候"
            self._kg_building = True

        try:
            html_content = self._build_kg_plot()
            return html_content, f"已刷新 ({len(self._get_kg().graph)} 概念)"
        finally:
            with self._kg_lock:
                self._kg_building = False

    # === 导入模态窗口 ===

    def modal_get_preview(self, file):
        """上传PDF后返回书名和第一页文本预览"""
        if file is None:
            return "", "<p style='color:#64748b'>请上传PDF文件</p>"
        p = Path(file.name if isinstance(file, dict) else str(file))
        name = p.stem
        preview = ""
        try:
            doc = PDFParser(p)
            pages = doc.extract_text_by_page()
            doc.close()
            first_page = pages[0] if pages else ""
            preview = first_page[:500] if first_page else "（第一页无文本）"
        except Exception as e:
            preview = f"无法预览: {e}"
        return name, (
            f"<pre style='white-space:pre-wrap;word-break:break-all;"
            f"height:280px;overflow:auto;font-size:13px;padding:12px;"
            f"background:#0f172a;border-radius:8px;color:#cbd5e1;"
            f"border:1px solid #334155;'>{preview}</pre>"
        )

    def modal_do_import(self, file, toc_pages, auto_preread):
        """模态窗口确认导入"""
        if file is None:
            return (
                gr.update(visible=False),   # modal
                "",                          # ch_display
                "",                          # book_info
                "",                          # kg_html
                None,                        # book_dd
                "",                          # pre_status
                "",                          # modal_status
            )
        p = Path(file.name if isinstance(file, dict) else str(file))
        name = p.stem
        self._ensure(name)

        def do_import():
            try:
                dest = BOOKS_PATH / p.name
                if p.resolve() != dest.resolve():
                    import shutil
                    try:
                        shutil.copy2(p, dest)
                    except PermissionError:
                        pass
                self.book_pdf_path = dest
                parser = PDFParser(dest)
                self.chapters = parser.extract_chapters(toc_pages.strip() if toc_pages else "")
                parser.close()
                self._save_chapters()
                if not self.chapters:
                    self.chapters = [{"title": f"{name} (全文)", "page_number": 1, "end_page": 0}]
                if auto_preread and len(self.chapters) >= 2:
                    self.start_pre_read()
                print(f"[导入完成] {name}")
            except Exception as e:
                print(f"[导入失败] {e}")

        threading.Thread(target=do_import, daemon=True).start()
        ch_html = self._format_chapter_list(self.chapters) if self.chapters else (
            "<div style='max-height:480px;overflow-y:auto;padding:8px;color:#e2e8f0;'>"
            "<p>正在加载目录...</p></div>"
        )
        return (
            ch_html,                                            # ch_display
            f"共{len(self.chapters)}章",                         # book_info
            "",                                                 # kg_html
            gr.update(choices=self.list_books(), value=name), # book_dd
            f"✅ 导入已启动: **{name}**\n\n后台处理中...",         # pre_status
        )

    # === UI 启动 ===

    def launch(self, share=False, port=7860):
        with gr.Blocks(title="Texa") as app:
            with gr.Row(equal_height=True):
                # === 左侧边栏 — 加宽 ===
                with gr.Column(scale=1, elem_id="sidebar", min_width=320):
                    gr.Markdown("## 📚 Texa")

                    book_dd = gr.Dropdown(
                        label="选择教材",
                        choices=self.list_books(),
                        interactive=True,
                    )

                    book_info = gr.Markdown("")
                    # 目录 — 固定高度可滚动
                    ch_display = gr.HTML()
                    pre_status = gr.Markdown("")

                # === 右侧主区域 ===
                with gr.Column(scale=4, elem_id="main-area"):
                    # kg_html 定义在全局，供知识图谱 Tab 和 on_switch 使用
                    kg_html = gr.HTML(visible=False)

                    with gr.Tabs():
                        with gr.TabItem("💬 Chat"):
                            chatbot = gr.Chatbot(
                                height=650, elem_id="chatbot", show_label=False,
                                latex_delimiters=LATEX_DELIMITERS,
                            )
                            with gr.Row():
                                qi = gr.Textbox(
                                    placeholder="输入问题...", scale=5,
                                    show_label=False, container=False,
                                )
                                send_btn = gr.Button("→", variant="primary", scale=1)
                            send_btn.click(self.ask_stream, inputs=[qi, chatbot], outputs=[chatbot, qi])
                            qi.submit(self.ask_stream, inputs=[qi, chatbot], outputs=[chatbot, qi])

                        with gr.TabItem("🔗 知识图谱"):
                            with gr.Row():
                                kg_refresh_btn = gr.Button("🔄 刷新图谱")
                                kg_open_btn = gr.Button("🌐 浏览器打开")
                                kg_status = gr.Textbox(show_label=False, interactive=False, container=False)
                            kg_display = gr.HTML()

                        with gr.TabItem("📝 错题本"):
                            with gr.Tabs():
                                with gr.TabItem("📥 录入"):
                                    with gr.Row():
                                        mb_q_text = gr.Textbox(label="题目内容", lines=4, placeholder="支持 LaTeX，如 $x^2 + y^2 = 1$")
                                        mb_u_ans = gr.Textbox(label="用户答案", lines=2, placeholder="（可选）")
                                    with gr.Row():
                                        mb_c_ans = gr.Textbox(label="正确答案", lines=2, placeholder="（可选）")
                                        mb_src = gr.Textbox(label="来源", placeholder="如：教材P45 / 2024真题")
                                    with gr.Row():
                                        mb_subj = gr.Textbox(label="学科", value="", placeholder="默认使用当前教材名")
                                        mb_tags = gr.Textbox(label="知识点标签", placeholder="用逗号分隔，如：梯度下降, 优化算法")
                                    with gr.Row():
                                        mb_mtypes = gr.CheckboxGroup(choices=MISTAKE_TYPES, label="错因")
                                        mb_diff = gr.Slider(1, 5, value=3, step=1, label="难度")
                                    mb_img = gr.File(label="截图/拍照", file_types=["image"])
                                    mb_add_btn = gr.Button("💾 保存错题", variant="primary")
                                    mb_add_status = gr.Textbox(show_label=False, interactive=False)

                                with gr.TabItem("📋 错题列表"):
                                    with gr.Row():
                                        mb_filter_subj = gr.Textbox(label="学科筛选", placeholder="留空显示全部")
                                        mb_search_kw = gr.Textbox(label="关键词搜索", placeholder="搜索题目内容或标签")
                                        mb_limit = gr.Slider(10, 200, value=50, step=10, label="显示数量")
                                    mb_list_df = gr.Dataframe(
                                        headers=["ID", "题目", "标签", "错因", "难度", "下次复习"],
                                        datatype=["str", "str", "str", "str", "number", "str"],
                                        interactive=False,
                                    )
                                    with gr.Row():
                                        mb_sel_id = gr.Textbox(label="选中错题 ID", placeholder="输入ID查看详情或讲题")
                                        mb_detail_btn = gr.Button("🔍 查看详情")
                                        mb_explain_btn = gr.Button("💡 LLM 讲题")
                                    mb_detail_md = gr.Markdown()
                                    mb_explain_out = gr.Textbox(label="讲题内容", lines=10, interactive=False, )

                                with gr.TabItem("📅 今日复习"):
                                    mb_due_filter = gr.Textbox(label="学科筛选", placeholder="留空显示全部")
                                    mb_due_df = gr.Dataframe(
                                        headers=["ID", "题目", "标签", "错因", "间隔(天)"],
                                        datatype=["str", "str", "str", "str", "number"],
                                        interactive=False,
                                    )
                                    with gr.Row():
                                        mb_review_id = gr.Textbox(label="复习错题 ID", placeholder="输入要复习的错题ID")
                                        mb_quality = gr.Slider(0, 5, value=3, step=1, label="掌握程度 (0=完全不会, 5=完全掌握)")
                                        mb_review_btn = gr.Button("✅ 提交复习", variant="primary")
                                    mb_review_status = gr.Textbox(show_label=False, interactive=False)
                                    mb_due_explain_btn = gr.Button("💡 讲题")
                                    mb_due_explain_out = gr.Textbox(label="讲题内容", lines=10, interactive=False, )

                                with gr.TabItem("📊 统计"):
                                    with gr.Row():
                                        mb_stats_subj = gr.Textbox(label="学科筛选", placeholder="留空显示全部")
                                    mb_stats_md = gr.Markdown()
                                    mb_weak_md = gr.Markdown()

                        with gr.TabItem("📥 导入"):
                            import_file = gr.File(label="上传 PDF 教材", file_types=[".pdf"])
                            import_toc = gr.Textbox(label="目录页码范围（可选）", placeholder="如：1-5")
                            import_preread = gr.Checkbox(label="导入后自动预读（需要目录页码）", value=False)
                            import_btn = gr.Button("📥 开始导入", variant="primary")
                            import_status = gr.Textbox(show_label=False, interactive=False)
                            import_preview = gr.HTML()

            # === 事件绑定 ===

            # 1. 切换教材
            def on_switch(b):
                ch, st, info, kg_html_val, _ = self.switch_book(b)
                return info, ch, st, kg_html_val, kg_html_val

            book_dd.change(on_switch, [book_dd], [book_info, ch_display, pre_status, kg_html, kg_display])

            # 2. 启动
            def on_startup():
                books = self.list_books()
                if books:
                    ch, st, info, kg_html_val, _ = self.switch_book(books[0])
                    return (
                        gr.update(choices=books, value=books[0]),
                        info, ch, st, kg_html_val, kg_html_val,
                    )
                return gr.update(choices=[]), "请导入教材", "", "", "", ""

            app.load(
                on_startup,
                outputs=[book_dd, book_info, ch_display, pre_status, kg_html, kg_display],
            )

            # 3. 知识图谱
            def on_kg_refresh():
                html_content, status_msg = self.kg_refresh()
                return html_content, status_msg

            kg_refresh_btn.click(on_kg_refresh, outputs=[kg_display, kg_status])
            kg_open_btn.click(self._open_kg_in_browser, outputs=[kg_status])

            # 4. 错题本 — 录入
            mb_add_btn.click(
                self.mb_add,
                inputs=[mb_q_text, mb_u_ans, mb_c_ans, mb_src, mb_subj, mb_tags, mb_mtypes, mb_diff, mb_img],
                outputs=[mb_add_status, mb_list_df, mb_due_df, mb_stats_md, mb_weak_md],
            )

            # 5. 错题本 — 列表筛选
            def on_mb_list_filter(subject_filter, search_kw, limit):
                return self.mb_list(subject_filter, search_kw, limit)

            mb_filter_subj.change(on_mb_list_filter, inputs=[mb_filter_subj, mb_search_kw, mb_limit], outputs=[mb_list_df])
            mb_search_kw.change(on_mb_list_filter, inputs=[mb_filter_subj, mb_search_kw, mb_limit], outputs=[mb_list_df])
            mb_limit.change(on_mb_list_filter, inputs=[mb_filter_subj, mb_search_kw, mb_limit], outputs=[mb_list_df])

            mb_detail_btn.click(self.mb_detail, inputs=[mb_sel_id], outputs=[mb_detail_md])
            mb_explain_btn.click(self.mb_explain, inputs=[mb_sel_id], outputs=[mb_explain_out])

            # 6. 错题本 — 今日复习
            def on_mb_due_filter(subject_filter):
                return self.mb_due(subject_filter)

            mb_due_filter.change(on_mb_due_filter, inputs=[mb_due_filter], outputs=[mb_due_df])

            mb_review_btn.click(
                self.mb_review,
                inputs=[mb_review_id, mb_quality],
                outputs=[mb_review_status, mb_due_df],
            )
            mb_due_explain_btn.click(self.mb_explain, inputs=[mb_review_id], outputs=[mb_due_explain_out])

            # 7. 错题本 — 统计
            def on_mb_stats(subject_filter):
                return self.mb_stats(subject_filter), self.mb_weak(subject_filter)

            mb_stats_subj.change(on_mb_stats, inputs=[mb_stats_subj], outputs=[mb_stats_md, mb_weak_md])

            # 8. 导入
            def do_import(file, preread, toc):
                if file is None:
                    return "", "", "", "", gr.update(), "请上传PDF文件", ""
                try:
                    ch_html, pre_st, info, kg_val, dd_upd, _name = self.import_book(file, preread, toc)
                    return ch_html, pre_st, info, kg_val, dd_upd, f"✅ {_name} 导入成功", ch_html
                except Exception as e:
                    import traceback
                    return "", "", "", "", gr.update(), f"❌ 导入失败: {e}", traceback.format_exc()

            import_btn.click(
                do_import,
                inputs=[import_file, import_preread, import_toc],
                outputs=[ch_display, pre_status, book_info, kg_html, book_dd, import_status, import_preview],
            )

            # 9. 错题本初始加载
            def on_mb_init():
                return (
                    self.mb_list("", "", 50),
                    self.mb_due(""),
                    self.mb_stats(""),
                    self.mb_weak(""),
                )

            app.load(on_mb_init, outputs=[mb_list_df, mb_due_df, mb_stats_md, mb_weak_md])

        # 后台静默预加载嵌入模型，避免首问卡顿
        self._start_warmup()

        app.launch(
            share=share, server_port=port,
            theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
            css=CSS,
        )
