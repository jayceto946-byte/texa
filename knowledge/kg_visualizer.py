"""知识图谱可视化 — Obsidian 风格树状层级图谱"""
import base64
import json
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from config import PROGRESS_PATH


class KGVisualizer:
    """生成树状层级的知识图谱 HTML"""

    # 跳过这些目录项
    SKIP_SECTIONS = {"本章学习要点", "本章小结", "习题", "思考题", "参考文献", "附录"}

    def __init__(self, book_name: str):
        self.book_name = book_name
        self.progress_path = Path(PROGRESS_PATH) / book_name
        self.kg_path = self.progress_path / "knowledge_graph.json"
        self.chapters_path = self.progress_path / "_chapters.json"
        self.output_path = self.progress_path / "kg_graph.html"
        self._vector_store = None

    def _get_vector_store(self):
        """获取向量存储实例（懒加载）"""
        if self._vector_store is None:
            try:
                from ingestion.vector_store import get_vector_store
                self._vector_store = get_vector_store()
            except Exception as e:
                print(f"[KG] 向量库加载失败: {e}")
                self._vector_store = None
        return self._vector_store

    def load_kg(self) -> dict:
        """加载知识图谱

        优先使用新版 KnowledgeGraph 类（支持本地预构建图谱），
        回退到直接读取旧格式 JSON 文件。
        """
        from knowledge.knowledge_graph import get_kg
        kg = get_kg(self.book_name)
        graph = kg.graph()
        if graph:
            return graph
        # 回退
        if self.kg_path.exists():
            with open(self.kg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def load_chapters(self) -> list:
        """加载章节信息，过滤掉学习要点和习题"""
        if self.chapters_path.exists():
            with open(self.chapters_path, "r", encoding="utf-8") as f:
                chapters = json.load(f)
            # 过滤掉学习要点和习题
            for ch in chapters:
                ch["subsections"] = [
                    sub for sub in ch.get("subsections", [])
                    if not any(skip in sub.get("title", "") for skip in self.SKIP_SECTIONS)
                ]
            return chapters
        return []

    def parse_chapter_hierarchy(self, chapters: list) -> Tuple[Dict, Dict]:
        """
        解析章节层级结构
        返回: (chapter_map, section_map)
        chapter_map: {chapter_id: {num, title, sections}}
        section_map: {section_id: {num, title, chapter_id}}
        """
        chapter_map = {}
        section_map = {}

        for i, ch in enumerate(chapters):
            ch_title = ch.get("title", "")
            # 提取章节号
            ch_match = re.match(r'第([一二三四五六七八九十\d]+)章', ch_title)
            if ch_match:
                ch_num = self._chinese_to_num(ch_match.group(1))
                ch_key = f"第{ch_num}章"
            else:
                ch_num = i + 1
                ch_key = f"第{ch_num}章"

            # 章节显示名：第1章 标题
            ch_display = ch_title if not ch_title.startswith("第") else ch_title

            chapter_map[ch_key] = {
                "num": ch_num,
                "title": ch_display,
                "raw_title": ch_title,
                "sections": {}
            }

            # 解析小节
            for j, sub in enumerate(ch.get("subsections", [])):
                sub_title = sub.get("title", "")
                # 提取节号
                sec_match = re.match(r'第([一二三四五六七八九十\d]+)节', sub_title)
                if sec_match:
                    sec_num = self._chinese_to_num(sec_match.group(1))
                    sec_key = f"{ch_key}.{sec_num}"
                else:
                    sec_num = j + 1
                    sec_key = f"{ch_key}.{sec_num}"

                section_map[sec_key] = {
                    "num": sec_num,
                    "title": sub_title,
                    "chapter_id": ch_key,
                    "raw_title": sub_title
                }
                chapter_map[ch_key]["sections"][sec_key] = section_map[sec_key]

        return chapter_map, section_map

    def _chinese_to_num(self, s: str) -> int:
        """中文数字转阿拉伯数字"""
        chinese_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                       '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if s.isdigit():
            return int(s)
        result = 0
        for char in s:
            if char in chinese_nums:
                result = result * 10 + chinese_nums[char]
        return result if result > 0 else 1

    def _get_kimi_k25(self):
        """获取 Kimi K2.5 模型实例"""
        from langchain_openai import ChatOpenAI
        from config import MOONSHOT_API_KEY, MOONSHOT_API_BASE

        return ChatOpenAI(
            model="kimi-k2.5",  # Kimi K2.5 模型名称
            temperature=1,  # Kimi K2.5 只支持 temperature=1
            api_key=MOONSHOT_API_KEY,
            base_url=MOONSHOT_API_BASE,
            streaming=False,  # 批量处理不需要流式
        )

    def assign_concepts_to_sections_with_llm(self, kg: dict, chapters: list,
                                               chapter_map: dict, section_map: dict,
                                               vector_store=None) -> Dict[str, List[dict]]:
        """
        使用 LLM (Kimi K2.5) 批量分配概念到小节
        方案：按小节提取概念，而不是逐个概念询问
        """
        print("[KG-LLM] 使用 Kimi K2.5 进行批量分配...")

        section_concepts = {sec_id: [] for sec_id in section_map}
        section_concepts["未分类"] = []

        # 尝试获取向量库
        if vector_store is None:
            try:
                from ingestion.vector_store import get_vector_store
                vector_store = get_vector_store()
            except Exception:
                vector_store = None

        # 获取所有概念名集合，用于匹配
        all_concepts = set(kg.keys())
        concept_assigned = {c: False for c in all_concepts}

        print(f"[KG-LLM] 开始批量分配 {len(all_concepts)} 个概念到 {len(section_map)} 个小节...")

        # 按小节批量提取（限制最多处理50个小节，避免过长）
        total_cost = 0
        processed = 0
        for sec_key, sec_data in sorted(section_map.items(), key=lambda x: x[0]):
            processed += 1
            if processed > 50:  # 限制处理数量
                print(f"[KG-LLM] 已达到处理上限(50)，剩余 {len(section_map) - 50} 个小节跳过")
                break
            ch_key = sec_data["chapter_id"]
            sec_title = sec_data["title"]
            ch_title = chapter_map[ch_key]["raw_title"]

            # 获取该小节的文本
            section_text = self._get_section_text(
                ch_title, sec_title,
                section_map, sec_key,
                vector_store, chapters
            )

            if not section_text or len(section_text) < 50:
                continue

            # 构建提示词
            concepts_list = "\n".join([f"- {c}" for c in sorted(all_concepts) if not concept_assigned[c]])
            prompt = f"""分析以下教材小节内容，从列表中选出该小节涉及的核心概念。

## 教材小节
章节：{ch_title}
小节：{sec_title}

## 待选概念列表
{concepts_list[:2000]}  # 限制长度避免token过多

## 小节内容（前1500字）
{section_text[:1500]}

## 输出要求
只输出属于该小节的概念名称，每行一个。不要输出任何解释。
如果列表中的概念都不属于该小节，输出"无"。"""

            try:
                # 调用 Kimi K2.5
                llm = self._get_kimi_k25()
                response = llm.invoke(prompt).content.strip()

                # 解析返回的概念列表
                matched = []
                for line in response.split('\n'):
                    line = line.strip().strip('-').strip()
                    if line and line in all_concepts and not concept_assigned[line]:
                        matched.append(line)
                        concept_assigned[line] = True

                # 添加到结果
                for concept in matched:
                    section_concepts[sec_key].append({
                        "name": concept,
                        "info": kg[concept],
                        "chapter": ch_key
                    })

                # 估算成本（粗略）
                prompt_tokens = len(prompt) // 4
                response_tokens = len(response) // 4
                total_cost += (prompt_tokens * 0.001 + response_tokens * 0.002) / 1000  # Kimi价格估算

                print(f"[KG-LLM] {sec_key} ({sec_title[:20]}...): 提取 {len(matched)} 个概念")

            except Exception as e:
                print(f"[KG-LLM] {sec_key} 处理失败: {e}")
                continue

        # 处理未分配的概念
        unassigned = [c for c, assigned in concept_assigned.items() if not assigned]
        for concept in unassigned:
            # 尝试根据知识图谱记录的章节分配
            ch_title = kg[concept].get("chapter", "")
            assigned = False
            for ch_key, ch_data in chapter_map.items():
                if ch_title in ch_data["raw_title"] or ch_data["raw_title"] in ch_title:
                    # 分配到该章节的第一个小节
                    if ch_data["sections"]:
                        first_sec = min(ch_data["sections"].keys())
                        section_concepts[first_sec].append({
                            "name": concept,
                            "info": kg[concept],
                            "chapter": ch_key
                        })
                        assigned = True
                    break

            if not assigned:
                section_concepts["未分类"].append({
                    "name": concept,
                    "info": kg[concept],
                    "chapter": "未分类"
                })

        print(f"[KG-LLM] 分配完成，估算成本: ¥{total_cost:.3f}")
        return section_concepts

    def _get_section_text(self, ch_title: str, sec_title: str,
                          section_map: dict, sec_key: str,
                          vector_store, chapters: list) -> str:
        """获取小节的文本内容"""
        if vector_store is None:
            return ""

        try:
            # 尝试搜索小节标题
            query = f"{ch_title} {sec_title}"
            outcome = vector_store.search_all(query, k=3)

            texts = []
            for title, d_list in outcome.items.items():
                for d in d_list:
                    texts.append(d.page_content)

            return "\n".join(texts)
        except Exception:
            # 回退：从 chapters 获取
            for ch in chapters:
                if ch.get("title") == ch_title:
                    return ch.get("text", "")
        return ""

    def assign_concepts_to_sections(self, kg: dict, chapters: list,
                                    chapter_map: dict, section_map: dict,
                                    use_llm: bool = True, vector_store=None) -> Dict[str, List[dict]]:
        """
        分配概念到小节
        use_llm=True: 使用LLM批量分配（推荐，成本低）
        use_llm=False: 使用简单规则分配
        """
        if use_llm:
            return self.assign_concepts_to_sections_with_llm(
                kg, chapters, chapter_map, section_map, vector_store
            )

        # 简化版本（备用）
        section_concepts = {sec_id: [] for sec_id in section_map}
        section_concepts["未分类"] = []

        for concept, info in kg.items():
            ch_title = info.get("chapter", "")
            matched_ch = None
            for ch_key, ch_data in chapter_map.items():
                if ch_title in ch_data["raw_title"] or ch_data["raw_title"] in ch_title:
                    matched_ch = ch_key
                    break

            if matched_ch and chapter_map[matched_ch]["sections"]:
                first_sec = min(chapter_map[matched_ch]["sections"].keys())
                section_concepts[first_sec].append({
                    "name": concept,
                    "info": info,
                    "chapter": matched_ch
                })
            else:
                section_concepts["未分类"].append({
                    "name": concept,
                    "info": info,
                    "chapter": "未分类"
                })

        return section_concepts

    def _resolve_image_to_base64(self, img_src: str) -> Optional[str]:
        """将图片路径转为 base64 data URL"""
        # 尝试多个可能的图片目录
        possible_paths = [
            Path(PROGRESS_PATH).parent / "books" / self.book_name / "images" / img_src.replace('./', ''),
            Path(PROGRESS_PATH).parent.parent / "mineru_output" / self.book_name / "images" / img_src.replace('./', ''),
            Path(PROGRESS_PATH).parent / "images" / img_src.replace('./', ''),
        ]

        for img_path in possible_paths:
            if img_path.exists():
                try:
                    ext = img_path.suffix.lower()
                    mime = {'png': 'image/png', 'jpg': 'image/jpeg',
                            'jpeg': 'image/jpeg', 'gif': 'image/gif'}.get(ext, 'image/jpeg')
                    data = base64.b64encode(img_path.read_bytes()).decode()
                    return f"data:{mime};base64,{data}"
                except Exception as e:
                    print(f"[KG-IMG] 转换失败 {img_path}: {e}")
                    continue

        # 如果找不到文件，返回原始路径
        return None

    def _extract_images_with_base64(self, concept: str, docs_data: list) -> List[dict]:
        """从文档中提取图片并转为 base64"""
        images = []
        seen_srcs = set()

        for txt in docs_data:
            # 查找 Markdown 图片语法 ![alt](src)
            img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
            imgs = re.findall(img_pattern, txt)

            for alt, src in imgs:
                if src in seen_srcs:
                    continue
                seen_srcs.add(src)

                # 只处理附近文本包含概念的图片
                idx = txt.find(f"![{alt}]({src})")
                context = txt[max(0, idx-200):min(len(txt), idx+300)]
                if concept not in context:
                    continue

                # 转为 base64
                base64_data = self._resolve_image_to_base64(src)
                if base64_data:
                    images.append({
                        "alt": alt or concept,
                        "src": base64_data,
                        "original_path": src
                    })
                    if len(images) >= 3:  # 最多3张
                        break

            if len(images) >= 3:
                break

        return images

    def enrich_definitions(self, kg: dict, vector_store=None) -> tuple:
        """提取概念定义。

        vector_store=None（默认）: 从本地章节文本搜索，零成本
        vector_store=实例     : 从向量库搜索（加载嵌入模型，较慢）
        """
        definitions = {}
        images = {}

        # === 零成本路径：从本地章节文本提取 ===
        if vector_store is None:
            print(f"[KG-DEF] 从本地文本提取 {len(kg)} 个概念的定义...")
            chapters_data = self.load_chapters()
            chapter_texts = {ch.get("title", ""): ch.get("text", "") for ch in chapters_data}

            for concept in kg:
                definition = "（暂无摘要）"
                # 遍历章节文本找包含概念的句子
                for ch_title, text in chapter_texts.items():
                    if not text:
                        continue
                    sentences = re.split(r'[。；;\n]', text)
                    for s in sentences:
                        if concept in s and 10 < len(s) < 300:
                            # 优先选包含定义关键词的句子
                            if any(w in s for w in ["是", "称为", "定义为", "指", "表示"]):
                                definition = s.strip()
                                break
                    if definition != "（暂无摘要）":
                        break

                # 回退到章节名
                if definition == "（暂无摘要）":
                    chapter = kg[concept].get("chapter", "")
                    if chapter:
                        definition = f"《{chapter}》中的核心概念"

                definitions[concept] = definition[:500] if len(definition) > 500 else definition
                images[concept] = []

            print(f"[KG-DEF] 本地提取完成")
            return definitions, images

        # === 向量库路径（传入实例时）===
        print(f"[KG-DEF] 从向量库提取 {len(kg)} 个概念的定义...")
        for concept in kg:
            definition = "（暂无摘要）"
            concept_texts = []

            try:
                queries = [concept, f"{concept} 是", f"{concept} 指", f"{concept} 定义"]
                for query in queries:
                    outcome = vector_store.search_all(query, k=2)
                    for title, d_list in outcome.items.items():
                        for d in d_list:
                            txt = d.page_content
                            concept_texts.append(txt)
                            sentences = re.split(r'[。；;\n]', txt)
                            for s in sentences:
                                if concept in s and 15 < len(s) < 500:
                                    if any(w in s for w in ["是", "称为", "定义为", "指"]):
                                        definition = s.strip()
                                        break
                            if definition != "（暂无摘要）":
                                break
                        if definition != "（暂无摘要）":
                            break
                    if definition != "（暂无摘要）":
                        break

                concept_images = self._extract_images_with_base64(concept, concept_texts)
                images[concept] = concept_images
            except Exception as e:
                print(f"[KG-DEF] 提取 {concept} 失败: {e}")
                images[concept] = []

            if definition == "（暂无摘要）":
                chapter = kg[concept].get("chapter", "")
                if chapter:
                    definition = f"《{chapter}》中的核心概念"

            definitions[concept] = definition[:500] if len(definition) > 500 else definition

        print(f"[KG-DEF] 向量库提取完成")
        return definitions, images

    def generate_html(self, kg: dict = None, definitions: dict = None,
                      images: dict = None, kg_instance=None) -> str:
        """生成树状层级的交互式 HTML

        Args:
            kg: 旧格式知识图谱字典
            definitions: 概念定义字典
            images: 概念图片字典
            kg_instance: 新版 KnowledgeGraph 实例（用于注入公式、出现位置等丰富信息）
        """

        if kg is None:
            kg = self.load_kg()

        if not kg:
            return "<p>知识图谱为空</p>"

        if definitions is None:
            definitions, images = self.enrich_definitions(kg)

        chapters = self.load_chapters()
        chapter_map, section_map = self.parse_chapter_hierarchy(chapters)

        # 概念分配到小节（默认不用LLM，纯规则匹配，零成本）
        section_concepts = self.assign_concepts_to_sections(
            kg, chapters, chapter_map, section_map,
            use_llm=False, vector_store=None
        )

        # 颜色配置
        chapter_colors = {
            "第1章": "#e74c3c", "第2章": "#3498db", "第3章": "#2ecc71",
            "第4章": "#f39c12", "第5章": "#9b59b6", "第6章": "#1abc9c",
            "第7章": "#e67e22", "第8章": "#34495e", "第9章": "#d35400",
            "第10章": "#27ae60", "未分类": "#95a5a6"
        }

        # 构建树状节点数据
        nodes_data = []
        edges_data = []
        node_id_map = {}  # 用于处理同名概念在不同章节的情况

        # 根节点
        root_id = "ROOT"
        nodes_data.append({
            "id": root_id,
            "label": self.book_name,
            "level": 0,
            "group": "root",
            "shape": "box",
            "color": {"background": "#2c3e50", "border": "#1a252f"},
            "font": {"color": "#ffffff", "bold": True, "size": 16},
            "margin": 12,
            "definition": "教材根节点",
            "prerequisites": [],
            "extensions": [],
            "images": [],
            "x": 0, "y": -500
        })

        # 章节节点 — 奇数章在左，偶数章在右，纵向分布
        for ch_key in sorted(chapter_map.keys(), key=lambda x: chapter_map[x]["num"]):
            ch_data = chapter_map[ch_key]
            ch_color = chapter_colors.get(ch_key, "#3498db")
            ch_num = ch_data["num"]
            is_left = ch_num % 2 == 1
            ch_x = -400 if is_left else 400
            ch_y = (ch_num - 1) * 320 - 350

            nodes_data.append({
                "id": ch_key,
                "label": ch_key,
                "level": 1,
                "group": "chapter",
                "shape": "box",
                "color": {"background": ch_color, "border": self._darken_color(ch_color)},
                "font": {"color": "#ffffff", "bold": True, "size": 14},
                "margin": 10,
                "definition": ch_data["title"],
                "prerequisites": [],
                "extensions": [],
                "images": [],
                "chapter": ch_key,
                "x": ch_x, "y": ch_y
            })
            edges_data.append({"from": root_id, "to": ch_key})

            # 小节节点
            sec_list = sorted(ch_data["sections"].keys(), key=lambda x: section_map[x]["num"])
            for sec_idx, sec_key in enumerate(sec_list):
                sec_data = ch_data["sections"][sec_key]
                sec_color = self._lighten_color(ch_color)
                sec_label = self._simplify_section_title(sec_data["title"])
                sec_x = ch_x + (-70 if is_left else 70)
                sec_y = ch_y + (sec_idx + 1) * 160

                nodes_data.append({
                    "id": sec_key,
                    "label": sec_label,
                    "level": 2,
                    "group": "section",
                    "shape": "box",
                    "color": {"background": sec_color, "border": ch_color},
                    "font": {"color": "#2c3e50", "bold": True, "size": 12},
                    "margin": 8,
                    "definition": sec_data["title"],
                    "prerequisites": [],
                    "extensions": [],
                    "images": [],
                    "chapter": ch_key,
                    "section": sec_key,
                    "x": sec_x, "y": sec_y
                })
                edges_data.append({"from": ch_key, "to": sec_key})

                # 概念节点
                concept_list = section_concepts.get(sec_key, [])
                for cidx, concept_info in enumerate(concept_list):
                    concept_name = concept_info["name"]
                    unique_id = f"{sec_key}::{concept_name}"
                    node_id_map[concept_name] = unique_id

                    info = concept_info["info"]
                    definition = definitions.get(concept_name, "（暂无摘要）")
                    concept_imgs = images.get(concept_name, []) if images else []

                    node_formulas = []
                    node_occurrences = []
                    if kg_instance and getattr(kg_instance, '_is_local', False):
                        detail = kg_instance.get_concept_detail(concept_name)
                        if detail:
                            node_formulas = detail.get('related_formulas', [])[:5]
                            node_occurrences = detail.get('occurrences', [])[:3]

                    concept_x = sec_x + (-60 if is_left else 60) + (cidx % 3 - 1) * 30
                    concept_y = sec_y + 100 + (cidx // 3) * 70

                    nodes_data.append({
                        "id": unique_id,
                        "label": concept_name,
                        "level": 3,
                        "group": "concept",
                        "shape": "box",
                        "color": {"background": "#ecf0f1", "border": ch_color},
                        "font": {"color": "#2c3e50", "bold": False, "size": 11},
                        "margin": 6,
                        "definition": definition,
                        "prerequisites": info.get("prerequisites", []),
                        "extensions": info.get("extensions", []),
                        "images": concept_imgs,
                        "formulas": node_formulas,
                        "occurrences": node_occurrences,
                        "chapter": ch_key,
                        "section": sec_key,
                        "concept": concept_name,
                        "x": concept_x, "y": concept_y
                    })
                    edges_data.append({"from": sec_key, "to": unique_id})

        # 处理未分类概念 — 放在最下方中央
        if section_concepts.get("未分类"):
            uncat_id = "未分类"
            nodes_data.append({
                "id": uncat_id,
                "label": "未分类",
                "level": 1,
                "group": "chapter",
                "shape": "box",
                "color": {"background": "#95a5a6", "border": "#7f8c8d"},
                "font": {"color": "#ffffff", "bold": True, "size": 14},
                "margin": 10,
                "definition": "未分类概念",
                "prerequisites": [],
                "extensions": [],
                "images": [],
                "chapter": "未分类",
                "x": 0, "y": 2000
            })
            edges_data.append({"from": root_id, "to": uncat_id})

            uncat_list = section_concepts["未分类"]
            for ucidx, concept_info in enumerate(uncat_list):
                concept_name = concept_info["name"]
                unique_id = f"未分类::{concept_name}"
                node_id_map[concept_name] = unique_id

                info = concept_info["info"]
                definition = definitions.get(concept_name, "（暂无摘要）")
                concept_imgs = images.get(concept_name, []) if images else []

                node_formulas = []
                node_occurrences = []
                if kg_instance and getattr(kg_instance, '_is_local', False):
                    detail = kg_instance.get_concept_detail(concept_name)
                    if detail:
                        node_formulas = detail.get('related_formulas', [])[:5]
                        node_occurrences = detail.get('occurrences', [])[:3]

                uc_x = (ucidx % 3 - 1) * 120
                uc_y = 2150 + (ucidx // 3) * 70

                nodes_data.append({
                    "id": unique_id,
                    "label": concept_name,
                    "level": 2,
                    "group": "concept",
                    "shape": "box",
                    "color": {"background": "#ecf0f1", "border": "#95a5a6"},
                    "font": {"color": "#2c3e50", "bold": False, "size": 11},
                    "margin": 6,
                    "definition": definition,
                    "prerequisites": info.get("prerequisites", []),
                    "extensions": info.get("extensions", []),
                    "images": concept_imgs,
                    "formulas": node_formulas,
                    "occurrences": node_occurrences,
                    "chapter": "未分类",
                    "section": "未分类",
                    "concept": concept_name,
                    "x": uc_x, "y": uc_y
                })
                edges_data.append({"from": uncat_id, "to": unique_id})

        # 生成章节筛选器（两层：章 → 节）
        chapter_filters = self._generate_chapter_filters(chapter_map, section_map, chapter_colors)

        return self._render_html(nodes_data, edges_data, chapter_filters, len(kg))

    def _simplify_section_title(self, title: str) -> str:
        """简化小节标题显示"""
        # 将"第一节 xxx" → "1.1 xxx"
        match = re.match(r'第([一二三四五六七八九十\d]+)节\s*(.+)', title)
        if match:
            num = self._chinese_to_num(match.group(1))
            return f"{num}. {match.group(2)}"
        return title

    def _generate_chapter_filters(self, chapter_map: dict, section_map: dict,
                                   chapter_colors: dict) -> str:
        """生成层级章节筛选器 HTML"""
        filters = []

        for ch_key in sorted(chapter_map.keys(), key=lambda x: chapter_map[x]["num"]):
            ch_data = chapter_map[ch_key]
            color = chapter_colors.get(ch_key, "#3498db")

            # 章级筛选
            filters.append(f'''
            <div class="chapter-item">
                <label class="chapter-filter" data-type="chapter" data-id="{ch_key}">
                    <input type="checkbox" checked value="{ch_key}">
                    <span class="color-dot" style="background:{color}"></span>
                    <span class="chapter-name">{ch_key}</span>
                </label>
                <div class="section-list">
            ''')

            # 节级筛选
            for sec_key in sorted(ch_data["sections"].keys(), key=lambda x: section_map[x]["num"]):
                sec_data = ch_data["sections"][sec_key]
                sec_label = self._simplify_section_title(sec_data["title"])
                filters.append(f'''
                    <label class="section-filter" data-type="section" data-id="{sec_key}" data-parent="{ch_key}">
                        <input type="checkbox" checked value="{sec_key}">
                        <span>{sec_label}</span>
                    </label>
                ''')

            filters.append('</div></div>')

        # 未分类
        if True:  # 始终显示未分类选项
            filters.append(f'''
            <div class="chapter-item">
                <label class="chapter-filter" data-type="chapter" data-id="未分类">
                    <input type="checkbox" checked value="未分类">
                    <span class="color-dot" style="background:#95a5a6"></span>
                    <span class="chapter-name">未分类</span>
                </label>
            </div>
            ''')

        return '\n'.join(filters)

    def _darken_color(self, hex_color: str, amount: int = 30) -> str:
        """加深颜色"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darkened = tuple(max(0, c - amount) for c in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*darkened)

    def _lighten_color(self, hex_color: str, amount: int = 40) -> str:
        """减淡颜色"""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        lightened = tuple(min(255, c + amount) for c in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*lightened)

    def _render_html(self, nodes_data: list, edges_data: list,
                     chapter_filters: str, concept_count: int) -> str:
        """渲染完整 HTML"""

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.book_name} — 知识图谱</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <!-- MathJax for LaTeX -->
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            overflow: hidden;
        }}

        .header {{
            height: 50px;
            background: #161b22;
            border-bottom: 1px solid #30363d;
            display: flex;
            align-items: center;
            padding: 0 20px;
            gap: 20px;
        }}

        .header h1 {{ font-size: 16px; font-weight: 500; color: #e6edf3; }}
        .header-stats {{ font-size: 12px; color: #8b949e; margin-left: auto; }}

        .main-container {{
            display: flex;
            height: calc(100vh - 50px);
        }}

        .sidebar {{
            width: 280px;
            background: #161b22;
            border-right: 1px solid #30363d;
            padding: 16px;
            overflow-y: auto;
            flex-shrink: 0;
        }}

        .sidebar-section {{ margin-bottom: 20px; }}

        .sidebar-title {{
            font-size: 11px;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }}

        .search-box {{
            width: 100%;
            padding: 8px 12px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            font-size: 13px;
            outline: none;
        }}

        .search-box:focus {{ border-color: #58a6ff; }}

        /* 章节筛选器 */
        .chapter-item {{ margin-bottom: 4px; }}

        .chapter-filter, .section-filter {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: background 0.15s;
        }}

        .chapter-filter:hover, .section-filter:hover {{ background: #21262d; }}

        .chapter-filter input, .section-filter input {{ cursor: pointer; }}

        .color-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            flex-shrink: 0;
        }}

        .chapter-name {{ color: #e6edf3; font-weight: 500; }}

        .section-list {{
            margin-left: 24px;
            border-left: 1px solid #30363d;
            padding-left: 8px;
        }}

        .section-filter {{
            font-size: 12px;
            color: #8b949e;
            padding: 4px 8px;
        }}

        .section-filter span {{ color: #c9d1d9; }}

        .control-btns {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .btn {{
            padding: 6px 12px;
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: #c9d1d9;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.15s;
        }}

        .btn:hover {{ background: #30363d; }}

        .graph-container {{
            flex: 1;
            position: relative;
            background: #0d1117;
        }}

        #mynetwork {{ width: 100%; height: 100%; }}

        /* 详情面板 */
        .detail-panel {{
            position: fixed;
            right: 20px;
            top: 70px;
            width: 380px;
            max-height: calc(100vh - 100px);
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            overflow-y: auto;
            display: none;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            z-index: 100;
        }}

        .detail-panel.active {{ display: block; }}

        .detail-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid #30363d;
        }}

        .detail-title {{ font-size: 18px; font-weight: 600; color: #e6edf3; }}
        .detail-subtitle {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}

        .detail-close {{
            background: none;
            border: none;
            color: #8b949e;
            font-size: 20px;
            cursor: pointer;
            padding: 0;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 4px;
        }}

        .detail-close:hover {{ background: #30363d; color: #e6edf3; }}

        .detail-section {{ margin-bottom: 20px; }}

        .detail-section-title {{
            font-size: 11px;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }}

        .detail-definition {{
            font-size: 14px;
            line-height: 1.8;
            color: #c9d1d9;
            background: #0d1117;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #30363d;
        }}

        .detail-definition .MathJax {{
            color: #c9d1d9 !important;
        }}

        .detail-images {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 10px;
        }}

        .detail-image {{
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #30363d;
        }}

        .detail-image img {{
            width: 100%;
            height: auto;
            display: block;
        }}

        .detail-links {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
        }}

        .detail-link {{
            padding: 4px 10px;
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 12px;
            font-size: 12px;
            color: #58a6ff;
            cursor: pointer;
            transition: all 0.15s;
        }}

        .detail-link:hover {{ background: #30363d; }}

        .detail-empty {{
            font-size: 12px;
            color: #6e7681;
            font-style: italic;
        }}

        .detail-formulas {{
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}

        .detail-formula {{
            font-size: 13px;
            color: #c9d1d9;
            background: #0d1117;
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid #30363d;
            font-family: 'Courier New', monospace;
            overflow-x: auto;
        }}

        .detail-occurrences {{
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}

        .detail-occurrence {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 12px;
            padding: 6px 10px;
            background: #0d1117;
            border-radius: 6px;
            border: 1px solid #30363d;
        }}

        .occ-page {{
            background: #1f6feb;
            color: #fff;
            padding: 2px 8px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 11px;
            white-space: nowrap;
        }}

        .occ-role {{
            color: #8b949e;
            text-transform: capitalize;
        }}

        .loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
            color: #8b949e;
        }}

        .loading-spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid #30363d;
            border-top-color: #58a6ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 12px;
        }}

        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📚 {self.book_name}</h1>
        <span class="header-stats">{concept_count} 个概念</span>
    </div>

    <div class="main-container">
        <div class="sidebar">
            <div class="sidebar-section">
                <div class="sidebar-title">🔍 搜索概念</div>
                <input type="text" class="search-box" id="searchBox"
                       placeholder="输入概念名称...">
            </div>

            <div class="sidebar-section">
                <div class="sidebar-title">📑 章节筛选</div>
                <div class="chapter-filters">
                    {chapter_filters}
                </div>
            </div>

            <div class="sidebar-section">
                <div class="sidebar-title">⚙️ 视图控制</div>
                <div class="control-btns">
                    <button class="btn" onclick="expandAll()">全部展开</button>
                    <button class="btn" onclick="collapseAll()">全部折叠</button>
                    <button class="btn" onclick="fitView()">适应屏幕</button>
                </div>
            </div>
        </div>

        <div class="graph-container">
            <div class="loading" id="loading">
                <div class="loading-spinner"></div>
                <div>正在构建知识图谱...</div>
            </div>
            <div id="mynetwork"></div>
        </div>
    </div>

    <div class="detail-panel" id="detailPanel">
        <div class="detail-header">
            <div>
                <div class="detail-title" id="detailTitle">概念名称</div>
                <div class="detail-subtitle" id="detailSubtitle">章节信息</div>
            </div>
            <button class="detail-close" onclick="closeDetail()">×</button>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">定义摘要</div>
            <div class="detail-definition" id="detailDefinition">暂无定义</div>
        </div>

        <div class="detail-section" id="imagesSection" style="display:none;">
            <div class="detail-section-title">相关图片</div>
            <div class="detail-images" id="detailImages"></div>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">前置知识</div>
            <div class="detail-links" id="detailPrereqs">
                <span class="detail-empty">无</span>
            </div>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">后续延伸</div>
            <div class="detail-links" id="detailExtensions">
                <span class="detail-empty">无</span>
            </div>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">相关公式</div>
            <div class="detail-formulas" id="detailFormulas">
                <span class="detail-empty">无</span>
            </div>
        </div>

        <div class="detail-section">
            <div class="detail-section-title">出现位置</div>
            <div class="detail-occurrences" id="detailOccurrences">
                <span class="detail-empty">无</span>
            </div>
        </div>
    </div>

    <script>
        const nodesData = {json.dumps(nodes_data, ensure_ascii=False)};
        const edgesData = {json.dumps(edges_data, ensure_ascii=False)};

        let network = null;
        let nodes = null;
        let edges = null;

        function initGraph() {{
            const container = document.getElementById('mynetwork');

            nodes = new vis.DataSet(nodesData);
            edges = new vis.DataSet(edgesData);

            const data = {{ nodes: nodes, edges: edges }};

            const options = {{
                nodes: {{
                    shape: 'box',
                    margin: 8,
                    font: {{
                        multi: 'html',
                        face: 'Microsoft YaHei, sans-serif'
                    }},
                    borderWidth: 2,
                    borderWidthSelected: 3,
                    shadow: {{
                        enabled: true,
                        color: 'rgba(0,0,0,0.2)',
                        size: 5,
                        x: 0,
                        y: 2
                    }}
                }},
                edges: {{
                    width: 1.5,
                    color: {{ color: '#30363d', highlight: '#58a6ff' }},
                    smooth: false,  // 直线
                    arrows: {{
                        to: {{ enabled: true, scaleFactor: 0.5, type: 'arrow' }}
                    }}
                }},
                layout: {{}},
                physics: {{
                    enabled: true,
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {{
                        gravitationalConstant: -30,
                        centralGravity: 0.002,
                        springLength: 140,
                        springConstant: 0.03,
                        damping: 0.92,
                        avoidOverlap: 0.6
                    }},
                    stabilization: {{
                        enabled: true,
                        iterations: 150,
                        updateInterval: 25
                    }}
                }},
                interaction: {{
                    hover: true,
                    tooltipDelay: 200,
                    navigationButtons: true,
                    keyboard: true
                }}
            }};

            network = new vis.Network(container, data, options);

            network.once('stabilizationIterationsDone', function() {{
                document.getElementById('loading').style.display = 'none';
            }});

            network.on('click', function(params) {{
                if (params.nodes.length > 0) {{
                    showDetail(params.nodes[0]);
                }} else {{
                    closeDetail();
                }}
            }});

            network.on('doubleClick', function(params) {{
                if (params.nodes.length > 0) {{
                    toggleCollapse(params.nodes[0]);
                }}
            }});
        }}

        function showDetail(nodeId) {{
            const node = nodes.get(nodeId);
            if (!node) return;

            document.getElementById('detailTitle').textContent = node.label;

            let subtitle = '';
            if (node.chapter && node.section) {{
                subtitle = `${{node.chapter}} · ${{node.section}}`;
            }} else if (node.chapter) {{
                subtitle = node.chapter;
            }}
            document.getElementById('detailSubtitle').textContent = subtitle;

            // 定义（支持LaTeX）
            const defEl = document.getElementById('detailDefinition');
            defEl.innerHTML = escapeHtml(node.definition || '（暂无摘要）');
            // 重新渲染MathJax
            if (window.MathJax) {{
                MathJax.typesetPromise([defEl]);
            }}

            // 图片
            const imgSection = document.getElementById('imagesSection');
            const imgContainer = document.getElementById('detailImages');
            if (node.images && node.images.length > 0) {{
                imgSection.style.display = 'block';
                imgContainer.innerHTML = node.images.map(img =>
                    `<div class="detail-image"><img src="${{escapeHtml(img.src)}}" alt="${{escapeHtml(img.alt)}}"/></div>`
                ).join('');
            }} else {{
                imgSection.style.display = 'none';
            }}

            // 前置知识
            const prereqsEl = document.getElementById('detailPrereqs');
            if (node.prerequisites && node.prerequisites.length > 0) {{
                prereqsEl.innerHTML = node.prerequisites.map(p =>
                    `<span class="detail-link" onclick="findAndFocus('${{escapeHtml(p)}}')">${{escapeHtml(p)}}</span>`
                ).join('');
            }} else {{
                prereqsEl.innerHTML = '<span class="detail-empty">无</span>';
            }}

            // 后续延伸
            const extsEl = document.getElementById('detailExtensions');
            if (node.extensions && node.extensions.length > 0) {{
                extsEl.innerHTML = node.extensions.map(e =>
                    `<span class="detail-link" onclick="findAndFocus('${{escapeHtml(e)}}')">${{escapeHtml(e)}}</span>`
                ).join('');
            }} else {{
                extsEl.innerHTML = '<span class="detail-empty">无</span>';
            }}

            // 相关公式（支持 LaTeX）
            const formulasEl = document.getElementById('detailFormulas');
            if (node.formulas && node.formulas.length > 0) {{
                formulasEl.innerHTML = node.formulas.map(f =>
                    `<div class="detail-formula">\\(${{escapeHtml(f.formula_latex || '')}}\\)</div>`
                ).join('');
                if (window.MathJax) {{
                    MathJax.typesetPromise([formulasEl]);
                }}
            }} else {{
                formulasEl.innerHTML = '<span class="detail-empty">无</span>';
            }}

            // 出现位置
            const occEl = document.getElementById('detailOccurrences');
            if (node.occurrences && node.occurrences.length > 0) {{
                occEl.innerHTML = node.occurrences.map(o => {{
                    const page = o.page_idx >= 0 ? `P${{o.page_idx}}` : '未知页';
                    const roleMap = {{
                        'definition': '定义', 'theorem': '定理', 'proof': '证明',
                        'derivation': '推导', 'algorithm': '算法', 'example': '例题',
                        'exercise': '习题', 'property': '性质', 'reference': '参考'
                    }};
                    const role = roleMap[o.role] || (o.role || '参考');
                    return `<div class="detail-occurrence"><span class="occ-page">${{page}}</span><span class="occ-role">${{role}}</span></div>`;
                }}).join('');
            }} else {{
                occEl.innerHTML = '<span class="detail-empty">无</span>';
            }}

            document.getElementById('detailPanel').classList.add('active');
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}

        function closeDetail() {{
            document.getElementById('detailPanel').classList.remove('active');
            network.unselectAll();
        }}

        function findAndFocus(conceptName) {{
            // 查找包含该概念名的节点
            const found = nodes.get({{
                filter: function(item) {{
                    return item.label === conceptName ||
                           (item.concept && item.concept === conceptName);
                }}
            }});

            if (found.length > 0) {{
                const nodeId = found[0].id;
                network.selectNodes([nodeId]);
                network.focus(nodeId, {{
                    scale: 1.0,
                    animation: {{ duration: 400, easingFunction: 'easeInOutQuad' }}
                }});
                showDetail(nodeId);
            }}
        }}

        function toggleCollapse(nodeId) {{
            // 获取该节点的所有子节点
            const childEdges = edges.get({{ filter: function(e) {{ return e.from === nodeId; }} }});
            const childIds = childEdges.map(e => e.to);

            if (childIds.length === 0) return;

            // 检查第一个子节点是否隐藏
            const firstChild = nodes.get(childIds[0]);
            const shouldHide = !firstChild.hidden;

            // 递归隐藏/显示子节点
            function setHiddenRecursive(id, hidden) {{
                nodes.update({{ id: id, hidden: hidden }});
                const childEdges = edges.get({{ filter: function(e) {{ return e.from === id; }} }});
                childEdges.forEach(e => setHiddenRecursive(e.to, hidden));
            }}

            childIds.forEach(id => setHiddenRecursive(id, shouldHide));
        }}

        function expandAll() {{
            nodes.forEach(node => {{
                nodes.update({{ id: node.id, hidden: false }});
            }});
        }}

        function collapseAll() {{
            // 只保留根节点和章节节点
            nodes.forEach(node => {{
                if (node.group === 'section' || node.group === 'concept') {{
                    nodes.update({{ id: node.id, hidden: true }});
                }}
            }});
        }}

        function fitView() {{
            network.fit({{ animation: {{ duration: 300, easingFunction: 'easeInOutQuad' }} }});
        }}

        // 搜索功能
        document.getElementById('searchBox').addEventListener('input', function(e) {{
            const query = e.target.value.toLowerCase().trim();
            if (!query) {{
                nodes.forEach(node => nodes.update({{ id: node.id, hidden: false }}));
                return;
            }}

            nodes.forEach(node => {{
                const match = node.label.toLowerCase().includes(query);
                nodes.update({{ id: node.id, hidden: !match }});
            }});
        }});

        // 章节筛选
        document.querySelectorAll('.chapter-filter input').forEach(cb => {{
            cb.addEventListener('change', function() {{
                const chId = this.value;
                const checked = this.checked;

                // 更新该章节下所有节点的显示状态
                nodes.forEach(node => {{
                    if (node.chapter === chId) {{
                        nodes.update({{ id: node.id, hidden: !checked }});
                    }}
                }});

                // 同步更新小节筛选器
                document.querySelectorAll(`[data-parent="${{chId}}"] input`).forEach(secCb => {{
                    secCb.checked = checked;
                    secCb.disabled = !checked;
                }});
            }});
        }});

        document.querySelectorAll('.section-filter input').forEach(cb => {{
            cb.addEventListener('change', function() {{
                const secId = this.value;
                const checked = this.checked;

                // 更新该小节下所有概念节点的显示状态
                nodes.forEach(node => {{
                    if (node.section === secId) {{
                        nodes.update({{ id: node.id, hidden: !checked }});
                    }}
                }});
            }});
        }});

        initGraph();
    </script>
</body>
</html>'''

        return html

    def save_html(self, html: str = None) -> str:
        """保存 HTML 文件"""
        if html is None:
            html = self.generate_html()

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return str(self.output_path)


def generate_kg_html(book_name: str, vector_store=None) -> str:
    """便捷函数：生成并保存知识图谱 HTML"""
    viz = KGVisualizer(book_name)
    kg = viz.load_kg()

    if not kg:
        return ""

    definitions, images = viz.enrich_definitions(kg, vector_store)

    # 尝试传入新版 KG 实例以注入公式/出现信息
    kg_instance = None
    try:
        from knowledge.knowledge_graph import get_kg
        kg_instance = get_kg(book_name)
    except Exception:
        pass

    html = viz.generate_html(kg, definitions, images, kg_instance=kg_instance)
    return viz.save_html(html)


if __name__ == "__main__":
    import sys
    book = sys.argv[1] if len(sys.argv) > 1 else "优化设计"
    path = generate_kg_html(book)
    print(f"已生成: {path}")
