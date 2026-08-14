"""CLI — LangGraph 驱动 v3.0"""
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.prompt import Prompt, Confirm

from config import BOOKS_PATH, MULTIMODAL_ENABLED
from ingestion.pdf_parser import PDFParser
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.vector_store import ChapterVectorStore
from graph.main_graph import run_graph
from agents.quiz import generate_quiz_from_state, check_answer
from memory.study_memory import StudyMemory
from memory.feedback import FeedbackLoop
from memory.spaced_repetition import SpacedRepetition

console = Console()


class StudyCLI:
    def __init__(self):
        self._vector_store = None
        self.memory: Optional[StudyMemory] = None
        self.feedback: Optional[FeedbackLoop] = None
        self.current_book: Optional[str] = None

    @property
    def vector_store(self):
        if self._vector_store is None:
            self._vector_store = ChapterVectorStore()
        return self._vector_store

    def show_banner(self):
        banner = """
╔══════════════════════════════════════════════╗
║              📚 Texa v3.0 (LangGraph)           ║
║   Planner → Retrieve → Chapter → Generate    ║
║   ⭐ 多模态 | 知识图谱 | 反馈闭环 | SM-2      ║
╚══════════════════════════════════════════════╝
        """
        console.print(Panel(banner, style="bold cyan"))

    def show_menu(self):
        menu = Table(title="主菜单", show_header=False, border_style="blue")
        menu.add_column("命令", style="bold yellow")
        menu.add_column("说明", style="white")
        menu.add_row("1. import", "导入PDF → 构建知识库+知识图谱")
        menu.add_row("2. ask", "任意问题 (自动路由+跨章节)")
        menu.add_row("3. teach", "系统讲解指定章节")
        menu.add_row("4. quiz", "生成练习题")
        menu.add_row("5. review", "📅 SM-2 间隔重复复习")
        menu.add_row("6. progress", "学习进度+分析")
        menu.add_row("7. kg", "🔗 查看知识图谱/概念关系")
        menu.add_row("8. ocr", "🖼️ 公式OCR/多模态问答")
        menu.add_row("9. exit", "退出")
        console.print(menu)

    def _get_books(self):
        return list(BOOKS_PATH.glob("*.pdf"))

    def _ensure_book(self, name: str):
        self.memory = StudyMemory(name)
        self.feedback = FeedbackLoop(name)
        self.current_book = name

    def cmd_import(self):
        pdfs = self._get_books()
        if not pdfs:
            console.print("[yellow]请将PDF放入 data/books/[/yellow]")
            return
        for i, pdf in enumerate(pdfs, 1):
            console.print(f"  {i}. {pdf.name} ({pdf.stat().st_size/1024/1024:.1f}MB)")
        choice = Prompt.ask("选择编号", default="1")
        try:
            pdf_path = pdfs[int(choice) - 1]
        except (ValueError, IndexError):
            console.print("[red]无效[/red]"); return

        book_name = pdf_path.stem
        self._ensure_book(book_name)

        with console.status(f"[cyan]解析 {pdf_path.name}...[/cyan]") as st:
            parser = PDFParser(pdf_path)
            chapters = parser.extract_chapters()
            parser.close()

            if not chapters:
                p2 = PDFParser(pdf_path)
                chapters = [{"title": book_name, "text": p2.extract_text()}]
                p2.close()

            st.update(f"分割 {len(chapters)} 章...")
            splitter = ChapterSplitter()
            chunks = splitter.split_book(chapters)

            st.update(f"向量索引 ({len(chunks)} 块)...")
            by_ch = {}
            for c in chunks:
                by_ch.setdefault(c["chapter"], []).append(c)
            for cn, cc in by_ch.items():
                self.vector_store.build_chapter_store(cn, cc)

            st.update("构建知识图谱...")
            from knowledge.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(book_name)
            kg.build_from_chapters(chapters)

            st.update("提取图片...")
            from ingestion.ocr import PDFImageExtractor
            ext = PDFImageExtractor(pdf_path)
            ext.close()

        console.print(f"\n[bold green]✓ 导入完成！[/bold green] {book_name} | {len(chapters)}章 | {len(chunks)}块 | 知识图谱已构建")

    def cmd_ask(self):
        if not self._get_books():
            console.print("[yellow]请先导入教材[/yellow]"); return
        if not self.current_book:
            self._ensure_book(self._get_books()[0].stem)

        console.print("[cyan]输入问题 (img <path> 附加图片, back 返回):[/cyan]")
        while True:
            q = Prompt.ask("\n[bold yellow]Q[/bold yellow]")
            if q.lower() in ("back", "exit", "quit"):
                break

            images = []
            if q.startswith("img "):
                parts = q[4:].split("|")
                q = parts[0].strip()
                images = [p.strip() for p in parts[1:] if Path(p.strip()).exists()]

            with console.status("[cyan]Planner → Retrieve → Generate...[/cyan]"):
                result = run_graph(q, book_name=self.current_book, user_images=images)

            chs = result.get("target_chapters", [])
            tag = ",".join(chs[:3]) if chs else "general"
            console.print(Panel(Markdown(result.get("final_output", "")),
                                title=f"🤖 [{result.get('intent', '')}] 📖 {tag}",
                                border_style="green"))

            rating = Prompt.ask("评分 (1-5, 回车跳过)", default="")
            if rating.isdigit():
                fb = self.feedback.process_feedback(
                    chs[0] if chs else "", int(rating),
                    knowledge_point=q[:30],
                )

    def cmd_teach(self):
        if not self._get_books():
            console.print("[yellow]请先导入[/yellow]"); return
        if not self.current_book:
            self._ensure_book(self._get_books()[0].stem)

        chs = self.vector_store.get_chapter_names()
        for i, c in enumerate(chs, 1):
            console.print(f"  {i}. {c}")
        choice = Prompt.ask("选择章节编号", default="1")
        try:
            chapter = chs[int(choice) - 1]
        except (ValueError, IndexError):
            console.print("[red]无效[/red]"); return

        q = f"系统讲解{chapter}"
        with console.status("[cyan]Planner → Retrieve → Chapter → Generate...[/cyan]"):
            result = run_graph(q, book_name=self.current_book)

        console.print(Panel(Markdown(result.get("final_output", "")),
                            title=f"📖 {chapter}", border_style="blue"))

    def cmd_quiz(self):
        if not self._get_books():
            console.print("[yellow]请先导入[/yellow]"); return

        chs = self.vector_store.get_chapter_names()
        for i, c in enumerate(chs, 1):
            console.print(f"  {i}. {c}")
        choice = Prompt.ask("章节编号", default="1")
        try:
            chapter = chs[int(choice) - 1]
        except (ValueError, IndexError):
            console.print("[red]无效[/red]"); return

        state = {"target_chapters": [chapter]}
        with console.status("[cyan]生成题目..."):
            questions = generate_quiz_from_state(state)

        if questions and questions[0].get("error"):
            console.print(f"[red]{questions[0]['question']}[/red]"); return

        console.print(f"\n[bold cyan]📝 {chapter}[/bold cyan]")
        for i, q in enumerate(questions, 1):
            console.print(f"\n[bold yellow]{i}. {q['question']}[/bold yellow]")
            if q.get("options"):
                for o in q["options"]:
                    console.print(f"  {o}")

            ans = Prompt.ask("答案")
            r = check_answer(q, ans)
            if r["correct"]:
                console.print(f"  [green]✓ 正确 ({r['score']})[/green]")
            else:
                console.print(f"  [red]✗ 答案: {q.get('answer','')}[/red]")

            console.print(Panel(Markdown(f"**解析**: {q.get('explanation','')}"), border_style="dim"))

            if self.memory:
                self.memory.add_quiz_record(
                    chapter, q['question'], q.get('answer', ''),
                    r['correct'], ans,
                    knowledge_point=q.get('knowledge_point', ''),
                    score=r.get('score', 0),
                )

    def cmd_review(self):
        if not self.memory:
            console.print("[yellow]请先导入[/yellow]"); return

        due = self.memory.get_due_reviews()
        if not due:
            console.print("[green]🎉 今日无待复习！[/green]")
            return

        console.print(f"[cyan]📅 待复习 {len(due)} 个知识点[/cyan]\n")
        for idx, card in enumerate(due[:10], 1):
            console.print(f"[bold yellow]{idx}. [{card['chapter']}] {card['knowledge_point']}[/bold yellow]")
            console.print(f"  间隔:{card['interval']}天 | 难度:{card['easiness']:.1f} | 复习:{card['repetitions']}次")
            q = Prompt.ask("掌握程度 0(不会)-5(精通)", default="3", choices=["0","1","2","3","4","5"])
            self.memory.mark_review_done(card['card_id'], int(q))

    def cmd_progress(self):
        if not self.memory:
            console.print("[yellow]请先导入[/yellow]"); return

        stats = self.memory.get_stats()
        table = Table(title="📊 学习统计", border_style="cyan")
        table.add_column("指标", style="yellow"); table.add_column("数值", style="white")
        table.add_row("已学章节", str(stats["chapters_studied"]))
        table.add_row("做题总数", str(stats["total_quiz"]))
        table.add_row("正确率", f"{stats['accuracy']}%")
        table.add_row("连续学习", f"{stats['streak']}天")
        table.add_row("知识点(SR)", str(stats.get("sr_total", 0)))
        table.add_row("已掌握(SR)", str(stats.get("sr_mastered", 0)))
        table.add_row("今日待复习", str(stats.get("sr_due_today", 0)))
        console.print(table)

        weak = self.memory.get_weakness()
        if weak:
            console.print("[yellow]薄弱章节:[/yellow] ")
            for w in weak[:5]:
                console.print(f"  ⚠ {w}")

    def cmd_kg(self):
        if not self.current_book:
            console.print("[yellow]请先导入[/yellow]"); return

        from knowledge.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(self.current_book)

        concepts = list(kg.graph.keys())
        if not concepts:
            console.print("[yellow]知识图谱为空，重新导入以自动构建[/yellow]")
            return

        console.print(f"[cyan]知识图谱 ({len(concepts)} 个概念)[/cyan]")
        q = Prompt.ask("搜索概念/路径 (如 '导数' 或 'path 导数')")
        if q.startswith("path "):
            c = q[5:].strip()
            path = kg.find_path(c)
            console.print(f"学习路径: [green]{' → '.join(path)}[/green]")
        else:
            related = kg.find_related(q.strip())
            if related:
                console.print(f"关联概念: [green]{', '.join(related[:10])}[/green]")
            else:
                console.print("[dim]未找到关联[/dim]")

    def cmd_ocr(self):
        if not MULTIMODAL_ENABLED:
            console.print("[red]需 Kimi K2.6[/red]"); return

        console.print("1. OCR识别  2. 多模态问答")
        cmd = Prompt.ask("选择", default="1")
        img = Prompt.ask("图片路径")
        if not Path(img).exists():
            console.print("[red]文件不存在[/red]"); return

        from ingestion.ocr import FormulaOCR
        ocr = FormulaOCR()
        with console.status("[cyan]处理中..."):
            if cmd == "1":
                r = ocr.extract_formulas(img)
            else:
                q = Prompt.ask("问题")
                r = ocr.multimodal_ask(q, [img])
        console.print(Panel(Markdown(r), border_style="green"))

    def run(self):
        self.show_banner()
        books = self._get_books()
        if books:
            self._ensure_book(books[0].stem)
            console.print(f"[dim]自动加载: {self.current_book} | LangGraph v3[/dim]")

        while True:
            self.show_menu()
            cmd = Prompt.ask("\n[bold cyan]命令[/bold cyan]", default="ask")
            cmds = {
                "1": self.cmd_import, "import": self.cmd_import,
                "2": self.cmd_ask, "ask": self.cmd_ask,
                "3": self.cmd_teach, "teach": self.cmd_teach,
                "4": self.cmd_quiz, "quiz": self.cmd_quiz,
                "5": self.cmd_review, "review": self.cmd_review,
                "6": self.cmd_progress, "progress": self.cmd_progress,
                "7": self.cmd_kg, "kg": self.cmd_kg,
                "8": self.cmd_ocr, "ocr": self.cmd_ocr,
            }
            if cmd in ("9", "exit", "quit"):
                console.print("[bold cyan]加油考研人！[/bold cyan]")
                sys.exit(0)
            elif cmd in cmds:
                cmds[cmd]()
            else:
                console.print("[red]未知命令[/red]")
