"""重建向量索引，给每个 chunk 的 metadata 补上 role 字段。

用法：
    cd D:/AI/agent/kaoyan-assistant
    . venv310/Scripts/activate
    python scripts/rebuild_index_with_roles.py --book_name 优化设计

原理：
    从 mineru_output/<book>/hybrid_auto/<book>_middle_chunks.json 读取 chunk 数据，
    使用 MinerU 原生 chunk_id（如 p20_c54），与 KG occurrence 的 chunk_id 一致，
    从而正确匹配 role metadata。
"""
import argparse
import json
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from ingestion.vector_store import get_vector_store
from knowledge.knowledge_graph import get_kg
from config import VECTOR_DB_PATH


def extract_chapter_title(section_title: str) -> str:
    """从 section_title 中提取章节名（去掉末尾页码数字）。"""
    # 去掉末尾空格+数字，如 "第一章 XXX 12" → "第一章 XXX"
    return re.sub(r'\s+\d+\s*$', '', section_title).strip()


def rebuild_with_roles(book_name: str):
    """从 middle_chunks.json 重建索引，加入 role metadata。"""
    kg = get_kg(book_name)
    vs = get_vector_store()

    if not kg._is_local:
        print(f"[WARN] KG 无本地数据 ({book_name})，跳过")
        return

    chunk_roles = kg._chunk_role
    print(f"[INFO] KG chunk_roles: {len(chunk_roles)} 条")

    # 读取 middle_chunks.json
    middle_path = Path("mineru_output") / book_name / "hybrid_auto" / f"{book_name}_middle_chunks.json"
    if not middle_path.exists():
        print(f"[ERR] 未找到 middle_chunks: {middle_path}")
        return

    with open(middle_path, "r", encoding="utf-8") as f:
        all_chunks = json.load(f)

    print(f"[INFO] middle_chunks: {len(all_chunks)} 条")

    # 按章节分组
    chapters: dict[str, list[dict]] = {}
    for ch in all_chunks:
        sec = ch.get("section_title", "")
        title = extract_chapter_title(sec)
        if not title:
            title = "未分类"
        if title not in chapters:
            chapters[title] = []
        # 转换为 build_chapter_store 期望的格式
        chapters[title].append({
            "content": ch.get("text", ""),
            "chunk_id": ch.get("chunk_id", ""),
            "chapter": title,
            "chunk_index": 0,  # 不需要实际索引
        })

    print(f"[INFO] 共 {len(chapters)} 个章节")

    # 删除旧索引
    import chromadb
    client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
    for col in client.list_collections():
        if col.name == "_chapter_map.json":
            continue
        try:
            client.delete_collection(col.name)
            print(f"[DEL] 旧 collection: {col.name}")
        except Exception:
            pass
    # 清空映射
    vs._stores.clear()
    vs._map.clear()
    if vs._map_file.exists():
        vs._map_file.unlink()

    # 重建每个章节
    for title, chunks in chapters.items():
        if not chunks:
            continue
        vs.build_chapter_store(title, chunks, chunk_roles=chunk_roles)
        print(f"[BUILD] {title}: {len(chunks)} chunks")

    print("[DONE] 重建完成")


if __name__ == "__main__":
    raise SystemExit("Legacy direct Chroma writer disabled. Use scripts/reindex_book.py instead.")
    parser = argparse.ArgumentParser(description="从 middle_chunks 重建向量索引并补 role")
    parser.add_argument("--book_name", default="优化设计", help="书籍名称")
    args = parser.parse_args()
    rebuild_with_roles(args.book_name)
