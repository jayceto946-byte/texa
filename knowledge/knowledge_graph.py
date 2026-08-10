"""知识图谱 — 本地预构建版（MinerU + 分层处理）

支持两种模式：
1. 本地预构建模式：加载 mineru_output/<book>/hybrid_auto/<book>_knowledge_graph.json
   包含 871+ 概念、3611+ 公式、3210+ 出现记录、880+ 条关系
2. 传统回退模式：若无本地数据，回退到旧版简单图谱（PROGRESS_PATH 下）
"""
import json
import re
from pathlib import Path
from collections import defaultdict
from config import BASE_DIR, MINERU_OUTPUT_PATH, PROGRESS_PATH

# ── 全局单例缓存（按 book_name）─────────────────────────────
_kg_cache: dict[str, "KnowledgeGraph"] = {}


def get_kg(book_name: str) -> "KnowledgeGraph":
    """获取全局 KnowledgeGraph 单例实例（按 book_name 缓存）"""
    global _kg_cache
    if book_name not in _kg_cache:
        _kg_cache[book_name] = KnowledgeGraph(book_name)
    return _kg_cache[book_name]


class KnowledgeGraph:
    """考研知识点图谱 — 本地预构建版

    本地模式数据规模示例（优化设计）：
      - 590 个语义块
      - 871 个去重概念（含别名合并、角色分布）
      - 3611 个公式（含变量解析）
      - 3210 条 Occurrence（概念在每处出现的 page/bbox/role）
      - 880 条关系（defines/depends_on/uses/derives_from/satisfies/contains/references/illustrates）
    """

    # 关系类型 → 旧格式映射方向
    # depends_on: A depends_on B  =>  B 是 A 的前置，A 是 B 的延伸
    _PREREQ_RELATIONS = {"depends_on", "derives_from", "uses"}
    _EXT_RELATIONS = {"depends_on", "derives_from", "contains", "defines", "uses", "satisfies"}

    @staticmethod
    def _resolve_local_dir(book_name: str) -> Path:
        candidates = [
            Path(PROGRESS_PATH) / book_name / "kg_enhancement" / "active",
            Path(MINERU_OUTPUT_PATH) / book_name / "hybrid_auto",
            Path(MINERU_OUTPUT_PATH) / book_name / "hybrid_auto_external",
            Path(PROGRESS_PATH) / book_name / "hybrid_auto_external",
            Path(BASE_DIR) / "mineru_output" / book_name / "hybrid_auto",
            Path(BASE_DIR) / "mineru_output" / book_name / "hybrid_auto_external",
        ]
        for candidate in candidates:
            if (candidate / f"{book_name}_knowledge_graph.json").exists():
                return candidate
        return candidates[0]

    def __init__(self, book_name: str):
        self.book_name = book_name
        self._is_local = False
        self._local_dir = self._resolve_local_dir(book_name)
        self._kg_file = self._local_dir / f"{book_name}_knowledge_graph.json"
        self._legacy_graph_cache: dict | None = None

        # --- 本地预构建模式 ---
        if self._kg_file.exists():
            self._is_local = True
            self._load_local()
            self.file = self._kg_file  # 兼容外部读取 file
            return

        # --- 传统回退模式 ---
        self.file = Path(PROGRESS_PATH) / book_name / "knowledge_graph.json"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self._legacy_graph = self._load_old()

    # ------------------------------------------------------------------
    # 本地加载
    # ------------------------------------------------------------------
    def _load_local(self):
        with open(self._kg_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.meta = data.get("meta", {})
        self.concepts = data.get("concepts", [])
        self.formulas = data.get("formulas", [])
        self.occurrences = data.get("occurrences", [])
        self.relations = data.get("relations", [])

        # 构建索引
        self._concept_by_id: dict[str, dict] = {}
        self._concept_by_name: dict[str, str] = {}  # normalized -> concept_id
        self._concept_by_alias: dict[str, str] = {}  # any alias -> concept_id
        self._formula_by_id: dict[str, dict] = {}
        self._occ_by_concept: dict[str, list[dict]] = defaultdict(list)
        self._relations_by_source: dict[str, list[dict]] = defaultdict(list)
        self._relations_by_target: dict[str, list[dict]] = defaultdict(list)
        self._chunk_map: dict[str, dict] = {}
        self._context_map: dict[str, dict] = {}
        self._chunk_to_chapter: dict[str, str] = {}  # chunk_id -> 章节名
        self._chunk_order: list[str] = []  # chunk_id 按文档顺序排列

        for c in self.concepts:
            cid = c["concept_id"]
            self._concept_by_id[cid] = c
            norm = c["canonical_name"].strip().lower()
            self._concept_by_name[norm] = cid
            for alias in c.get("aliases", []):
                a_norm = alias.strip().lower()
                if a_norm not in self._concept_by_alias:
                    self._concept_by_alias[a_norm] = cid

        self._chunk_role: dict[str, str] = {}  # chunk_id → 主角色（按 occurrence role）
        for occ in self.occurrences:
            self._occ_by_concept[occ["concept_id"]].append(occ)
            cid = occ.get("chunk_id", "")
            role = occ.get("role", "reference")
            if cid and cid not in self._chunk_role:
                self._chunk_role[cid] = role

        for r in self.relations:
            sid = r.get("source_id")
            tid = r.get("target_id")
            if sid and sid in self._concept_by_id:
                self._relations_by_source[sid].append(r)
            if tid and tid in self._concept_by_id:
                self._relations_by_target[tid].append(r)

        for fm in self.formulas:
            self._formula_by_id[fm["formula_id"]] = fm

        # 尝试加载 chunks / context_packages（用于文本溯源）
        chunks_path = self._local_dir / f"{self.book_name}_middle_chunks.json"
        if chunks_path.exists():
            try:
                with open(chunks_path, "r", encoding="utf-8") as f:
                    chunks_data = json.load(f)
                    current_chapter = ""
                    for ch in chunks_data:
                        cid = ch.get("chunk_id", "")
                        if not cid:
                            continue
                        # Current ingestion writes chunk bodies as ``content``;
                        # older graph exports used ``text``. Normalize at the
                        # read boundary so every KG lookup follows one schema.
                        if not ch.get("text") and ch.get("content"):
                            ch = {**ch, "text": ch.get("content", "")}
                        self._chunk_map[cid] = ch
                        self._chunk_order.append(cid)
                        sec = ch.get("section_title", "")
                        # 更新当前章节（遇到"第X章"时）
                        if sec and "章" in sec and re.search(r"第[一二三四五六七八九十\d]+章", sec):
                            current_chapter = sec
                        self._chunk_to_chapter[cid] = current_chapter
            except Exception:
                pass

        ctx_path = self._local_dir / f"{self.book_name}_context_packages.json"
        if ctx_path.exists():
            try:
                with open(ctx_path, "r", encoding="utf-8") as f:
                    for cp in json.load(f):
                        self._context_map[cp.get("context_id", "")] = cp
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 传统加载
    # ------------------------------------------------------------------
    def _load_old(self) -> dict:
        if self.file.exists():
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_old(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self._legacy_graph, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # 兼容属性 / 旧格式转换
    # ------------------------------------------------------------------
    def graph(self) -> dict:
        """兼容旧格式：{concept_name: {prerequisites: [], extensions: [], chapter: ""}}"""
        if self._is_local:
            if self._legacy_graph_cache is None:
                self._legacy_graph_cache = self._to_legacy_graph()
            return self._legacy_graph_cache
        return self._legacy_graph

    def _to_legacy_graph(self) -> dict:
        """将本地版知识图谱转换为旧格式字典，供可视化等模块使用。"""
        legacy = {}
        for c in self.concepts:
            name = c["canonical_name"]
            cid = c["concept_id"]

            # prerequisites: 本概念依赖谁
            prereqs = set()
            for r in self._relations_by_source.get(cid, []):
                if r["relation"] in self._PREREQ_RELATIONS:
                    tid = r.get("target_id")
                    if tid and tid in self._concept_by_id:
                        prereqs.add(self._concept_by_id[tid]["canonical_name"])

            # extensions: 谁依赖/推导/包含本概念
            exts = set()
            for r in self._relations_by_target.get(cid, []):
                if r["relation"] in self._EXT_RELATIONS:
                    sid = r.get("source_id")
                    if sid and sid in self._concept_by_id:
                        exts.add(self._concept_by_id[sid]["canonical_name"])

            # chapter：从出现记录推断
            chapter = self._infer_chapter(cid)

            legacy[name] = {
                "prerequisites": sorted(prereqs),
                "extensions": sorted(exts),
                "chapter": chapter,
                "_concept_id": cid,
                "_confidence": c.get("confidence", 0),
                "_occurrence_count": c.get("occurrence_count", 0),
                "_roles": c.get("roles", []),
            }
        return legacy

    # 不用于推断章节的无意义标题
    _SKIP_SECTION_TITLES = {"(no title)", "本章学习要点", "习题", "思考题", "参考文献", "附录"}

    def _infer_chapter(self, concept_id: str) -> str:
        """从出现记录推断概念所属章节。"""
        occs = self._occ_by_concept.get(concept_id, [])
        if not occs:
            return ""

        # 优先用 chunk_id -> chapter 映射（最准确）
        ch_counts = defaultdict(int)
        for occ in occs:
            chunk_id = occ.get("chunk_id", "")
            ch = self._chunk_to_chapter.get(chunk_id, "")
            if ch and ch not in self._SKIP_SECTION_TITLES:
                ch_counts[ch] += 1
        if ch_counts:
            most_common = max(ch_counts, key=ch_counts.get)
            # 尝试提取"第X章"
            m = re.search(r"第[一二三四五六七八九十\d]+章", most_common)
            if m:
                return m.group(0)
            return most_common[:30]

        # 回退：从 occurrence 的 section_title 推断
        sec_counts = defaultdict(int)
        for occ in occs:
            sec = occ.get("section_title", "")
            if sec and sec not in self._SKIP_SECTION_TITLES:
                sec_counts[sec] += 1
        if not sec_counts:
            return ""
        most_common = max(sec_counts, key=sec_counts.get)
        m = re.search(r"第[一二三四五六七八九十\d]+章", most_common)
        if m:
            return m.group(0)
        return most_common[:30]

    # ------------------------------------------------------------------
    # 核心查询接口（旧接口保持兼容，新功能增强）
    # ------------------------------------------------------------------
    def _resolve_concept(self, name: str) -> str | None:
        """将名称解析为 concept_id，支持模糊匹配。"""
        name_norm = name.strip().lower()
        if name_norm in self._concept_by_name:
            return self._concept_by_name[name_norm]
        if name_norm in self._concept_by_alias:
            return self._concept_by_alias[name_norm]
        # 模糊匹配
        best_score = 0.0
        best_cid = None
        for alias, cid in self._concept_by_alias.items():
            # 包含关系优先
            if name_norm in alias or alias in name_norm:
                score = 0.5 + 0.5 * (len(name_norm) / max(len(alias), 1))
                if score > best_score:
                    best_score = score
                    best_cid = cid
        return best_cid

    def find_path(self, concept: str, context: str = "") -> list[str]:
        """查找概念的学习路径（从基础到该概念）。

        本地版：基于 depends_on / derives_from 关系图做上游 DFS。
        传统版：保持旧逻辑。
        """
        if not self._is_local:
            path = []
            visited = set()
            self._dfs_upstream_legacy(concept, path, visited)
            path.reverse()
            if concept not in path:
                path.append(concept)
            return path

        cid = self._resolve_concept(concept)
        if cid is None:
            return [concept]

        path = []
        visited = set()
        self._dfs_upstream(cid, path, visited)
        path.reverse()
        if cid not in path:
            path.append(cid)
        return [self._concept_by_id[c]["canonical_name"] for c in path]

    def _dfs_upstream(self, cid: str, path: list, visited: set):
        if cid in visited:
            return
        visited.add(cid)
        for r in self._relations_by_source.get(cid, []):
            if r["relation"] in self._PREREQ_RELATIONS:
                tid = r.get("target_id")
                if tid and tid not in visited:
                    self._dfs_upstream(tid, path, visited)
        if cid not in path:
            path.append(cid)

    def _dfs_upstream_legacy(self, concept: str, path: list, visited: set):
        if concept in visited:
            return
        visited.add(concept)
        for prereq in self.get_prerequisites(concept):
            self._dfs_upstream_legacy(prereq, path, visited)
            if prereq not in path:
                path.append(prereq)

    def find_related(self, concept: str) -> list[str]:
        """查找所有关联概念（前置 + 延伸 + 同章节）。"""
        if not self._is_local:
            related = set()
            related.update(self.get_prerequisites(concept))
            related.update(self.get_extensions(concept))
            ch = self._legacy_graph.get(concept, {}).get("chapter", "")
            if ch:
                for c, info in self._legacy_graph.items():
                    if info.get("chapter") == ch and c != concept:
                        related.add(c)
            return list(related)

        cid = self._resolve_concept(concept)
        if cid is None:
            return []

        related = set()
        # 通过关系找
        for r in self._relations_by_source.get(cid, []):
            tid = r.get("target_id")
            if tid and tid in self._concept_by_id:
                related.add(self._concept_by_id[tid]["canonical_name"])
        for r in self._relations_by_target.get(cid, []):
            sid = r.get("source_id")
            if sid and sid in self._concept_by_id:
                related.add(self._concept_by_id[sid]["canonical_name"])

        # 同章节
        chapter = self._infer_chapter(cid)
        if chapter:
            for c in self.concepts:
                if c["concept_id"] != cid:
                    c_ch = self._infer_chapter(c["concept_id"])
                    if c_ch == chapter:
                        related.add(c["canonical_name"])
        return list(related)

    def get_prerequisites(self, concept: str) -> list[str]:
        if self._is_local:
            cid = self._resolve_concept(concept)
            if cid is None:
                return []
            prereqs = set()
            for r in self._relations_by_source.get(cid, []):
                if r["relation"] in self._PREREQ_RELATIONS:
                    tid = r.get("target_id")
                    if tid and tid in self._concept_by_id:
                        prereqs.add(self._concept_by_id[tid]["canonical_name"])
            return sorted(prereqs)
        return self._legacy_graph.get(concept, {}).get("prerequisites", [])

    def get_extensions(self, concept: str) -> list[str]:
        if self._is_local:
            cid = self._resolve_concept(concept)
            if cid is None:
                return []
            exts = set()
            for r in self._relations_by_target.get(cid, []):
                if r["relation"] in self._EXT_RELATIONS:
                    sid = r.get("source_id")
                    if sid and sid in self._concept_by_id:
                        exts.add(self._concept_by_id[sid]["canonical_name"])
            return sorted(exts)
        return self._legacy_graph.get(concept, {}).get("extensions", [])

    # ------------------------------------------------------------------
    # 新增：本地版丰富查询接口
    # ------------------------------------------------------------------
    def search_concept(self, query: str, k: int = 5) -> list[dict]:
        """模糊搜索概念，返回最匹配的 k 个概念详情。"""
        if not self._is_local:
            return []
        q = query.strip().lower()
        if not q:
            return []
        scored = []

        def _score_term(term: str, exact_score: int) -> float:
            term = term.strip().lower()
            if not term:
                return 0
            if q == term:
                return exact_score
            if len(q) >= 2 and q in term:
                return 50 + len(q) / max(len(term), 1) * 50
            # 用户问题通常是整句，例如“什么是单纯形法”，需要允许概念名反向命中。
            if len(term) >= 2 and term in q:
                return min(exact_score - 5, 70 + len(term) / max(len(q), 1) * 20)
            return 0

        for c in self.concepts:
            name = c["canonical_name"]
            aliases = c.get("aliases", [])
            score = _score_term(name, 100)
            for alias in aliases:
                score = max(score, _score_term(alias, 90))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    def get_concept_detail(self, concept_name_or_id: str) -> dict | None:
        """获取概念完整详情（含出现记录、相关公式、关系）。"""
        if not self._is_local:
            return None
        cid = self._resolve_concept(concept_name_or_id)
        if cid is None and concept_name_or_id in self._concept_by_id:
            cid = concept_name_or_id
        if cid is None:
            return None
        c = self._concept_by_id[cid]
        occs = self._occ_by_concept.get(cid, [])
        rels = []
        for r in self._relations_by_source.get(cid, []):
            rels.append({
                "direction": "out",
                "relation": r["relation"],
                "target": r.get("target_concept", ""),
                "evidence_text": r.get("evidence_text", ""),
                "page_idx": r.get("page_idx", -1),
            })
        for r in self._relations_by_target.get(cid, []):
            rels.append({
                "direction": "in",
                "relation": r["relation"],
                "source": r.get("source_concept", ""),
                "evidence_text": r.get("evidence_text", ""),
                "page_idx": r.get("page_idx", -1),
            })
        # 相关公式
        related_formulas = []
        for fm in self.formulas:
            if cid in fm.get("related_concepts", []):
                related_formulas.append({
                    "formula_id": fm["formula_id"],
                    "formula_latex": fm["formula_latex"],
                    "variables": fm.get("variables", []),
                })
        return {
            "concept": c,
            "occurrences": occs,
            "relations": rels,
            "related_formulas": related_formulas,
        }

    def get_concepts_by_role(self, role: str) -> list[dict]:
        """按角色筛选概念，如 'definition', 'theorem', 'example' 等。"""
        if not self._is_local:
            return []
        return [c for c in self.concepts if role in c.get("roles", [])]

    def get_formula_by_id(self, formula_id: str) -> dict | None:
        return self._formula_by_id.get(formula_id)

    def get_relations(self, concept_name_or_id: str, relation_type: str = None) -> list[dict]:
        """获取某概念的关系边。"""
        if not self._is_local:
            return []
        cid = self._resolve_concept(concept_name_or_id)
        if cid is None and concept_name_or_id in self._concept_by_id:
            cid = concept_name_or_id
        if cid is None:
            return []
        results = []
        for r in self._relations_by_source.get(cid, []):
            if relation_type is None or r["relation"] == relation_type:
                results.append(r)
        for r in self._relations_by_target.get(cid, []):
            if relation_type is None or r["relation"] == relation_type:
                results.append(r)
        return results

    def get_chunk_text(self, chunk_id: str) -> str:
        """获取原始 chunk 文本（用于溯源）。"""
        ch = self._chunk_map.get(chunk_id, {})
        return ch.get("text", "")

    def get_context_package(self, context_id: str) -> dict | None:
        return self._context_map.get(context_id)

    def get_concept_wiki(
        self,
        concept_name_or_id: str,
        *,
        max_chunks: int = 3,
        max_related: int = 8,
        max_formulas: int = 5,
    ) -> dict:
        """Build a compact wiki card for a concept from KG evidence."""
        detail = self.get_concept_detail(concept_name_or_id)
        if not detail:
            return {}

        concept = detail["concept"]
        name = concept.get("canonical_name", concept_name_or_id)
        definition_chunks = self._concept_role_chunks(
            concept["concept_id"], {"definition", "theorem", "property"}, max_chunks
        )
        if not definition_chunks:
            definition_chunks = self.get_concept_chunks(name, window=0, max_hits=1)[:max_chunks]

        example_chunks = self._concept_role_chunks(
            concept["concept_id"], {"example", "exercise"}, max_chunks
        )
        source_chapters = []
        for ch in definition_chunks + example_chunks:
            chapter = ch.get("chapter") or ch.get("section_title", "")
            if chapter and chapter not in source_chapters:
                source_chapters.append(chapter)

        definition = ""
        if definition_chunks:
            definition = definition_chunks[0].get("text", "").strip()[:800]

        return {
            "concept": {
                "concept_id": concept.get("concept_id", ""),
                "canonical_name": name,
                "aliases": concept.get("aliases", []),
                "roles": concept.get("roles", []),
                "confidence": concept.get("confidence", 0),
                "occurrence_count": concept.get("occurrence_count", 0),
            },
            "definition": definition,
            "definition_chunks": definition_chunks,
            "example_chunks": example_chunks,
            # Retain response keys for older clients without exposing
            # unverified directional relations as product knowledge.
            "prerequisites": [],
            "extensions": [],
            "related_formulas": detail.get("related_formulas", [])[:max_formulas],
            "source_chapters": source_chapters[:max_related],
        }

    def _concept_role_chunks(self, concept_id: str, roles: set[str], limit: int) -> list[dict]:
        chunks = []
        seen = set()
        for occ in self._occ_by_concept.get(concept_id, []):
            if occ.get("role", "reference") not in roles:
                continue
            chunk_id = occ.get("chunk_id", "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            chunks.extend(self._get_nearby_chunks(chunk_id, window=0, role=occ.get("role", "")))
            if len(chunks) >= limit:
                break
        return chunks[:limit]
    # ------------------------------------------------------------------
    # 新增：精确 chunk 定位（用于混合检索）
    # ------------------------------------------------------------------
    # occurrence role 优先级（定义/定理 > 推导/性质 > 例题 > 提及）
    _ROLE_PRIORITY = {
        "definition": 0, "theorem": 1, "property": 2,
        "derivation": 3, "proof": 4, "example": 5,
        "algorithm": 6, "exercise": 7, "reference": 8,
    }

    def get_concept_chunks(self, concept_name: str, window: int = 1, max_hits: int = 3) -> list[dict]:
        """通过概念名精确命中其出现的 chunk，并取前后滑动窗口。

        按 role 优先级排序（definition/theorem 优先），最多取 max_hits 个出现位置。
        返回: [{chunk_id, text, section_title, chapter, page_idx, is_direct_hit, role}]
        """
        if not self._is_local:
            return []

        cid = self._resolve_concept(concept_name)
        if cid is None:
            return []

        occs = self._occ_by_concept.get(cid, [])
        if not occs:
            return []

        # 按 chunk_id 聚合 occurrence，取最高优先级 role
        chunk_info: dict[str, dict] = {}
        for occ in occs:
            chunk_id = occ.get("chunk_id", "")
            if not chunk_id:
                continue
            role = occ.get("role", "reference")
            pri = self._ROLE_PRIORITY.get(role, 99)
            if chunk_id not in chunk_info or pri < chunk_info[chunk_id]["priority"]:
                chunk_info[chunk_id] = {
                    "priority": pri,
                    "role": role,
                    "page_idx": occ.get("page_idx", -1),
                }

        # 按优先级排序，取 top max_hits
        sorted_chunks = sorted(chunk_info.items(), key=lambda x: x[1]["priority"])
        top_chunks = sorted_chunks[:max_hits]

        # 为每个命中 chunk 取前后窗口，合并去重
        results = []
        result_seen = set()
        for chunk_id, info in top_chunks:
            # 例题需要更大窗口 + 向前追溯题干
            w = window
            if info["role"] == "example":
                w = max(window, 3)
            nearby = self._get_nearby_chunks(chunk_id, window=w, role=info["role"])
            for item in nearby:
                if item["chunk_id"] not in result_seen:
                    result_seen.add(item["chunk_id"])
                    results.append(item)

        # 按原文档顺序排列（保证阅读连贯性）
        order_map = {cid: i for i, cid in enumerate(self._chunk_order)}
        results.sort(key=lambda x: order_map.get(x["chunk_id"], 999999))
        return results

    _EXAMPLE_MARKER_RE = re.compile(r'^\s*例\s*\d+([\-\.]\d+)?')

    def _get_nearby_chunks(self, chunk_id: str, window: int = 1, role: str = "") -> list[dict]:
        """取指定 chunk 及其前后 window 个 chunk 的上下文。

        例题特殊处理：向前追溯直到找到以"例X.X"开头的题干 chunk（最多追 5 个），
        避免命中解题步骤 chunk 时题干缺失。
        """
        if not self._chunk_order:
            ch = self._chunk_map.get(chunk_id)
            if ch:
                return [{
                    "chunk_id": chunk_id,
                    "text": ch.get("text", ""),
                    "section_title": ch.get("section_title", ""),
                    "chapter": self._chunk_to_chapter.get(chunk_id, ""),
                    "page_idx": ch.get("page_idx", -1),
                    "is_direct_hit": True,
                    "role": role,
                }]
            return []

        try:
            idx = self._chunk_order.index(chunk_id)
        except ValueError:
            idx = -1

        start = max(0, idx - window) if idx >= 0 else 0
        end = min(len(self._chunk_order), idx + window + 1) if idx >= 0 else len(self._chunk_order)

        # 例题向前追溯题干
        if role == "example" and idx > 0:
            for back in range(1, 6):
                bi = idx - back
                if bi < 0:
                    break
                bcid = self._chunk_order[bi]
                btext = self._chunk_map.get(bcid, {}).get("text", "")
                if self._EXAMPLE_MARKER_RE.search(btext):
                    start = min(start, bi)
                    break

        results = []
        for i in range(start, end):
            cid = self._chunk_order[i]
            ch = self._chunk_map.get(cid, {})
            results.append({
                "chunk_id": cid,
                "text": ch.get("text", ""),
                "section_title": ch.get("section_title", ""),
                "chapter": self._chunk_to_chapter.get(cid, ""),
                "page_idx": ch.get("page_idx", -1),
                "is_direct_hit": (cid == chunk_id),
                "role": role if cid == chunk_id else "",
            })
        return results

    # ------------------------------------------------------------------
    # 构建接口（兼容旧调用）
    # ------------------------------------------------------------------
    def add_concept(self, name: str, chapter: str,
                    prerequisites: list[str] = None,
                    extensions: list[str] = None):
        """传统模式：添加概念节点。本地模式下为只读。"""
        if self._is_local:
            return
        if name not in self._legacy_graph:
            self._legacy_graph[name] = {"chapter": chapter}
        self._legacy_graph[name].setdefault("prerequisites", [])
        self._legacy_graph[name].setdefault("extensions", [])
        if prerequisites:
            for p in prerequisites:
                if p not in self._legacy_graph[name]["prerequisites"]:
                    self._legacy_graph[name]["prerequisites"].append(p)
                if p not in self._legacy_graph:
                    self._legacy_graph[p] = {"chapter": chapter}
                self._legacy_graph[p].setdefault("extensions", [])
                if name not in self._legacy_graph[p]["extensions"]:
                    self._legacy_graph[p]["extensions"].append(name)
        if extensions:
            for e in extensions:
                if e not in self._legacy_graph[name]["extensions"]:
                    self._legacy_graph[name]["extensions"].append(e)
        self._save_old()

    def build_from_chapters(self, chapters_data: list[dict], llm=None, force=False):
        """从章节数据自动构建知识图谱。

        本地模式下：若本地图谱已存在则直接复用，跳过 LLM 构建。
        传统模式下：保持旧行为。
        """
        if self._is_local:
            if self.concepts:
                print(f"[KG] 本地预构建知识图谱已加载 ({len(self.concepts)} 概念)，跳过构建")
                return
        # 传统回退
        if self._legacy_graph and not force:
            print(f"[KG] 知识图谱已存在 ({len(self._legacy_graph)} 概念)，跳过构建")
            return
        if llm is None:
            from config import get_llm
            llm = get_llm()
        for ch in chapters_data:
            title = ch.get("title", "")
            text = ch.get("text", "")[:4000]
            if not text:
                continue
            prompt = f"""分析以下教材章节，提取核心概念及其依赖关系。\n\n## 章节：{title}\n## 内容\n{text}\n\n输出 JSON（不要其他）：\n{{\n  "concepts": [\n    {{"name": "概念名", "prerequisites": ["前置概念1"], "extensions": ["后续概念1"]}}\n  ]\n}}\n"""
            resp = llm.invoke(prompt).content.strip()
            if resp.startswith("```"):
                resp = resp.split("\n", 1)[-1].rsplit("\n", 1)[0]
            try:
                data = json.loads(resp)
                for c in data.get("concepts", []):
                    self.add_concept(
                        c["name"], title,
                        c.get("prerequisites", []),
                        c.get("extensions", []),
                    )
            except json.JSONDecodeError:
                continue

    # ------------------------------------------------------------------
    # 锁接口（兼容旧代码）
    # ------------------------------------------------------------------
    def _lock_file(self) -> Path:
        return self.file.parent / ".kg_building.lock"

    def _is_building(self) -> bool:
        lock = self._lock_file()
        if lock.exists():
            import time
            if time.time() - lock.stat().st_mtime > 1800:
                lock.unlink()
                return False
            return True
        return False

    def _acquire_lock(self):
        self._lock_file().touch()

    def _release_lock(self):
        lock = self._lock_file()
        if lock.exists():
            lock.unlink()
