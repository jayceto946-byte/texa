"""Build fixed embedding/retrieval fixtures from the current textbook corpus.

This is an explicit maintenance command. It only reads Chroma and writes the
two paths passed on the command line; the benchmark itself never reads the
user's live vector database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import VECTOR_DB_PATH


PARITY_PATH = ROOT / "evaluation" / "datasets" / "embedding_parity.json"
RETRIEVAL_PATH = ROOT / "evaluation" / "datasets" / "embedding_retrieval.json"

SHORT_CONCEPTS = [
    "压阻效应", "压电效应", "霍尔效应", "磁阻效应", "热电效应", "光电效应", "光生伏特效应",
    "传感器静态特性", "传感器动态特性", "灵敏度", "分辨力", "分辨率", "线性度", "迟滞", "重复性",
    "稳定性", "温度漂移", "频率响应", "阶跃响应", "应变片", "电容式传感器", "电感式传感器",
    "霍尔式传感器", "压电式传感器", "温度传感器", "绝对误差", "相对误差", "引用误差", "系统误差",
    "随机误差", "粗大误差", "标准差", "算术平均值", "有效数字", "测量不确定度", "最小二乘法",
    "目标函数", "设计变量", "约束条件", "可行域", "梯度法", "牛顿法", "共轭梯度法", "黄金分割法",
    "二次插值法", "罚函数法", "单纯形法", "遗传算法", "线性规划", "非线性规划",
]

SIMILAR_PAIRS = [
    ("压阻效应", "压电效应"), ("静态特性", "动态特性"), ("灵敏度", "分辨率"),
    ("绝对误差", "相对误差"), ("系统误差", "随机误差"), ("随机误差", "粗大误差"),
    ("重复性", "再现性"), ("线性度", "迟滞"), ("分辨力", "阈值"), ("稳定性", "温度稳定性"),
    ("霍尔效应", "磁阻效应"), ("外光电效应", "内光电效应"), ("热电效应", "热阻效应"),
    ("电容式传感器", "电感式传感器"), ("有源传感器", "无源传感器"),
    ("频率响应", "阶跃响应"), ("一阶传感器", "二阶传感器"), ("应变", "应力"),
    ("准确度", "精密度"), ("测量范围", "量程"), ("标准差", "极限误差"),
    ("算术平均值", "加权平均值"), ("贝塞尔公式", "极差法"), ("已定系统误差", "未定系统误差"),
    ("直接测量", "间接测量"), ("等精度测量", "不等精度测量"), ("目标函数", "约束函数"),
    ("设计变量", "设计常量"), ("可行点", "不可行点"), ("局部最优解", "全局最优解"),
    ("梯度法", "共轭梯度法"), ("牛顿法", "阻尼牛顿法"), ("黄金分割法", "二次插值法"),
    ("外罚函数法", "内罚函数法"), ("线性规划", "非线性规划"), ("单纯形法", "复合形法"),
    ("遗传算法", "工程遗传算法"), ("目标函数极小值", "目标函数极大值"),
    ("等式约束", "不等式约束"), ("绝对灵敏度", "相对灵敏度"),
]

MANUAL_QUERIES = [
    ("什么是压阻效应？", ["sensor_core_1b8facd9eadc"], "definition"),
    ("压阻效应有什么特点？", ["sensor_core_1b8facd9eadc"], "property"),
    ("压阻效应和压电效应有什么区别？", ["sensor_core_1b8facd9eadc", "3326d3ba1d7b2959"], "relation"),
    ("压阻效应在什么情况下会更明显？", ["sensor_core_1b8facd9eadc"], "fuzzy"),
    ("传感器的静态特性指什么？", ["78aa05eb06e7e4a7"], "definition"),
    ("静态特性和动态特性有什么区别？", ["78aa05eb06e7e4a7", "763587b98e06edc8"], "relation"),
    ("传感器灵敏度怎么算？", ["ef054f6e3bbd1efd"], "formula"),
    ("灵敏度和分辨率是一回事吗？", ["ef054f6e3bbd1efd", "sensor_core_e11327c9b083"], "relation"),
    ("什么是传感器的分辨力和阈值？", ["sensor_core_e11327c9b083"], "definition"),
    ("绝对误差如何定义？", ["error_theory_887bc39f5212"], "definition"),
    ("绝对误差和相对误差如何换算？", ["error_theory_887bc39f5212", "error_theory_b15afb344a4b"], "formula"),
    ("什么是霍尔效应？", ["3317f043cb02a7b4"], "definition"),
    ("霍尔式传感器可以测哪些量？", ["sensor_core_995e301c1911"], "application"),
    ("国家标准如何定义传感器？", ["cf627dfbf4388782"], "definition"),
    ("传感器线性度如何评定？", ["b2d611ef2daab44c"], "formula"),
    ("迟滞误差是什么？", ["sensor_core_7b8eb2b8e479"], "definition"),
    ("重复性和再现性有什么区别？", ["2f4358aa8fa48d50"], "relation"),
    ("摄氏温标和华氏温标如何换算？", ["59f533b2da5add69"], "formula"),
    ("热电效应产生的条件是什么？", ["d9f9bb10853cb714"], "principle"),
    ("外光电效应和内光电效应有什么区别？", ["4c608532786fd73c"], "relation"),
    ("电容式传感器有什么优点？", ["sensor_core_0b346bc343f5"], "property"),
    ("电感式传感器的工作原理是什么？", ["sensor_core_993267e2ac5f"], "principle"),
    ("金属应变片如何把应变转换为电阻变化？", ["4fcb122101ef4883"], "principle"),
    ("测量不确定度的定义是什么？", ["error_theory_eddb004659bb"], "definition"),
    ("随机误差为什么具有统计规律？", ["error_theory_168f2f948d7e"], "principle"),
    ("系统误差为什么不能靠重复测量减小？", ["error_theory_02fc6551ae9c"], "principle"),
    ("什么是粗大误差？", ["error_theory_68c2d88120ee"], "definition"),
    ("测量结果为什么取算术平均值？", ["error_theory_6d3229095a73"], "principle"),
    ("有效数字的舍入规则是什么？", ["error_theory_eba8d7849594"], "procedure"),
    ("最小二乘法用于解决什么问题？", ["error_theory_ae08f82ea523"], "application"),
    ("优化设计中的目标函数是什么？", ["p13_c39"], "definition"),
    ("设计变量和设计常量如何区分？", ["p12_c37"], "relation"),
    ("优化问题的约束条件有什么几何意义？", ["p14_c41"], "principle"),
    ("梯度法为什么沿负梯度方向搜索？", ["p65_c164"], "principle"),
    ("牛顿法有哪些优点和局限？", ["p74_c185"], "property"),
    ("共轭梯度法为什么比普通梯度法收敛快？", ["p68_c170"], "relation"),
    ("黄金分割法怎样缩小搜索区间？", ["p41_c107"], "procedure"),
    ("二次插值法的基本思想是什么？", ["p45_c115"], "principle"),
    ("罚函数法怎样把约束优化转成无约束优化？", ["p125_c299"], "principle"),
    ("遗传算法的迭代步骤是什么？", ["p160_c374"], "procedure"),
]


def _stable_score(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_corpus(vector_db: Path) -> dict[str, dict]:
    import chromadb

    client = chromadb.PersistentClient(path=str(vector_db))
    variants: dict[str, list[dict]] = {}
    for collection in sorted(client.list_collections(), key=lambda item: item.name):
        data = collection.get(include=["documents", "metadatas"])
        for document, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
            metadata = metadata or {}
            chunk_id = str(metadata.get("chunk_id") or "").strip()
            text = str(document or "").strip()
            if not chunk_id or not text:
                continue
            variants.setdefault(chunk_id, []).append({
                "id": chunk_id,
                "text": text,
                "book_name": str(metadata.get("book_name") or ""),
                "section_title": str(metadata.get("section_title") or metadata.get("chapter") or ""),
            })
    # Prefer the shortest duplicate: versioned aggregate rows can add retrieval
    # prefixes while retaining the same semantic chunk_id.
    return {key: min(values, key=lambda item: (len(item["text"]), item["text"])) for key, values in variants.items()}


def _select(rows: list[dict], count: int, used: set[str], predicate) -> list[dict]:
    candidates = [row for row in rows if row["id"] not in used and predicate(row)]
    candidates.sort(key=lambda row: _stable_score(row["id"]))
    selected = candidates[:count]
    used.update(row["id"] for row in selected)
    if len(selected) != count:
        raise RuntimeError(f"Fixture selection underflow: wanted {count}, got {len(selected)}")
    return selected


def build(vector_db: Path) -> tuple[dict, dict]:
    corpus = _load_corpus(vector_db)
    rows = list(corpus.values())
    used: set[str] = set()
    entries = [
        {"id": f"short_{index:03d}", "category": "short_concept", "text": text}
        for index, text in enumerate(SHORT_CONCEPTS, 1)
    ]
    normal = _select(rows, 100, used, lambda row: 50 <= len(row["text"]) <= 300)
    entries.extend({"id": f"normal_{i:03d}", "category": "textbook_paragraph", **row} for i, row in enumerate(normal, 1))
    long_rows = _select(rows, 60, used, lambda row: 900 <= len(row["text"]) <= 2400)
    entries.extend({"id": f"long_{i:03d}", "category": "long_textbook_chunk", **row} for i, row in enumerate(long_rows, 1))
    math_re = re.compile(r"\$|\\(?:frac|mathrm|begin|sqrt|Delta|sigma|mu)|[=≤≥±×÷∑∫℃℉]")
    formula = _select(rows, 50, used, lambda row: 100 <= len(row["text"]) <= 1400 and math_re.search(row["text"]) is not None)
    entries.extend({"id": f"formula_{i:03d}", "category": "formula_symbol_mix", **row} for i, row in enumerate(formula, 1))
    for pair_index, pair in enumerate(SIMILAR_PAIRS, 1):
        for side, text in zip(("a", "b"), pair):
            entries.append({
                "id": f"pair_{pair_index:03d}_{side}",
                "category": "high_similarity_concept",
                "pair_id": f"pair_{pair_index:03d}",
                "text": text,
            })
    parity = {
        "schema_version": 1,
        "model": "BAAI/bge-small-zh-v1.5",
        "selection": "fixed deterministic sample from the project's textbook Chroma corpus",
        "counts": {
            "total": len(entries), "short_concept": 50, "textbook_paragraph": 100,
            "long_textbook_chunk": 60, "formula_symbol_mix": 50, "high_similarity_concept": 80,
            "high_similarity_pairs": 40,
        },
        "texts": entries,
    }

    missing = sorted({target for _, targets, _ in MANUAL_QUERIES for target in targets} - corpus.keys())
    if missing:
        raise RuntimeError(f"Manual relevance targets missing from source corpus: {missing}")
    manual_targets = {target for _, targets, _ in MANUAL_QUERIES for target in targets}
    retrieval_rows = [corpus[target] for target in sorted(manual_targets)]
    retrieval_used = set(manual_targets)
    retrieval_rows.extend(_select(rows, 500 - len(retrieval_rows), retrieval_used, lambda row: 30 <= len(row["text"]) <= 2400))
    retrieval_rows.sort(key=lambda row: row["id"])
    manual = [
        {"id": f"manual_{index:03d}", "query": query, "query_type": query_type,
         "expected_chunk_ids": targets, "label_source": "human_curated"}
        for index, (query, targets, query_type) in enumerate(MANUAL_QUERIES, 1)
    ]
    eligible_reference = [
        row for row in retrieval_rows
        if len(row["section_title"]) >= 4 and row["section_title"].lower() not in {"unsectioned", "习题"}
        and not row["section_title"].startswith(("图", "表"))
    ]
    eligible_reference.sort(key=lambda row: _stable_score(row["id"] + row["section_title"]))
    reference = []
    for index, row in enumerate(eligible_reference[:60], 1):
        variants = ["请解释{title}。", "{title}的主要内容是什么？", "教材如何说明{title}？"]
        template = variants[(index - 1) % len(variants)]
        reference.append({
            "id": f"reference_{index:03d}", "query": template.format(title=row["section_title"]),
            "query_type": "reference_baseline", "expected_chunk_ids": [row["id"]],
            "label_source": "torch_reference",
        })
    if len(reference) != 60:
        raise RuntimeError("Not enough reference queries")
    retrieval = {
        "schema_version": 1,
        "model": "BAAI/bge-small-zh-v1.5",
        "corpus_source": "fixed isolated sample; benchmark never queries live Chroma",
        "counts": {"corpus": len(retrieval_rows), "queries": 100, "human_curated": 40, "torch_reference": 60},
        "corpus": retrieval_rows,
        "queries": manual + reference,
    }
    return parity, retrieval


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vector-db", type=Path, default=VECTOR_DB_PATH)
    parser.add_argument("--parity-output", type=Path, default=PARITY_PATH)
    parser.add_argument("--retrieval-output", type=Path, default=RETRIEVAL_PATH)
    args = parser.parse_args()
    parity, retrieval = build(args.vector_db.resolve())
    for path, payload in ((args.parity_output, parity), (args.retrieval_output, retrieval)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {path}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
