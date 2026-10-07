"""Deterministic structure, source membership and review-state validation."""
import copy
import re

from memory.session_notes import NoteError, encode, fingerprint, new_id
from utils.thinking_filter import strip_thinking

BLOCK_TYPES = {"heading", "paragraph", "list", "equation", "callout"}
ROLES = {None, "concept", "method", "derivation", "example", "correction", "conclusion", "open_question"}
LIMITS = {"title": 200, "abstract": 500, "subject": 100, "tags": 20, "tag_chars": 40, "blocks": 300, "document_bytes": 512 * 1024}
FIELDS = {"title", "abstract", "subject", "tags", "chapter_refs", "blocks"}


def invalid(message, *, reason="structure", path="document"):
    raise NoteError("invalid_document", message, reason=reason, path=path)


def validate_document(document, snapshot, *, previous=None, generated=False):
    if not isinstance(document, dict) or set(document) - FIELDS:
        invalid("文档包含未知字段", path="document", reason="unknown_field")
    doc = copy.deepcopy(document)
    try:
        encoded = encode(doc)
        size = len(encoded.encode())
    except (TypeError, ValueError):
        invalid("正文必须为合法的 JSON 内容")
    if re.search(r"</?think(?:ing)?>", encoded, re.I):
        invalid("文档包含未过滤的 thinking")
    if size > LIMITS["document_bytes"]:
        invalid("可编辑内容超过 512 KiB")
    if not isinstance(doc.get("title"), str) or not 1 <= len(doc["title"].strip()) <= LIMITS["title"]:
        invalid("标题必须为 1–200 字", path="document.title", reason="title_length_or_type")
    for key, limit in (("abstract", LIMITS["abstract"]), ("subject", LIMITS["subject"])):
        if not isinstance(doc.get(key, ""), str) or len(doc.get(key, "")) > limit:
            invalid(f"{key} 超过长度限制", path=f"document.{key}", reason="field_length_or_type")
        doc.setdefault(key, "")
    tags = doc.setdefault("tags", [])
    if not isinstance(tags, list) or len(tags) > LIMITS["tags"] or any(not isinstance(t, str) or not 1 <= len(t) <= LIMITS["tag_chars"] for t in tags):
        invalid("标签最多 20 个，每个 1–40 字", path="document.tags", reason="tag_length_or_type")
    chapters = doc.setdefault("chapter_refs", [])
    if not isinstance(chapters, list) or len(chapters) > 50:
        invalid("章节关联无效", path="document.chapter_refs", reason="chapter_type_or_count")
    # The client selects existing, server-created version anchors only.
    known_chapters = {c["chapter_ref_id"]: c for c in snapshot.get("chapter_refs", [])}
    known_chapters.update({c["chapter_ref_id"]: c for c in (previous or {}).get("chapter_refs", [])})
    if any(not isinstance(c, dict) or not isinstance(c.get("chapter_ref_id"), str) or c.get("chapter_ref_id") not in known_chapters for c in chapters):
        invalid("章节引用必须来自已解析的版本锚点")
    doc["chapter_refs"] = [copy.deepcopy(known_chapters[c["chapter_ref_id"]]) for c in chapters]
    blocks = doc.get("blocks")
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= LIMITS["blocks"]:
        invalid("正文必须为 1–300 个内容块", path="document.blocks", reason="block_count_or_type")
    source_map = {s["source_ref_id"]: s for s in snapshot["sources"]}
    evidence_map = {e["evidence_ref_id"]: e for e in snapshot["evidence"]}
    old_blocks = {b["block_id"]: b for b in (previous or {}).get("blocks", [])}
    ids, warnings = set(), copy.deepcopy(snapshot.get("warnings", []))
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or set(block) - {"block_id", "type", "role", "group_id", "data", "source_ref_ids", "evidence_ref_ids", "authorship", "source_alignment", "verification"}:
            invalid("内容块字段无效", path=f"document.blocks[{index}]", reason="block_structure")
        bid = block.get("block_id")
        if not isinstance(bid, str) or not re.fullmatch(r"[\w.-]{1,100}", bid) or bid in ids:
            invalid("内容块编号无效或重复", path=f"document.blocks[{index}]", reason="block_structure")
        ids.add(bid)
        typ, data = block.get("type"), block.get("data")
        role = block.get("role")
        if not isinstance(typ, str) or typ not in BLOCK_TYPES or (role is not None and not isinstance(role, str)) or role not in ROLES or not isinstance(data, dict):
            invalid("内容块类型、角色或正文无效", path=f"document.blocks[{index}]", reason="block_structure")
        if block.get("group_id") is not None and (not isinstance(block["group_id"], str) or len(block["group_id"]) > 100):
            invalid("组编号无效", path=f"document.blocks[{index}]", reason="block_structure")
        allowed_data = {"heading": {"text", "level"}, "paragraph": {"markdown"}, "list": {"items", "ordered"}, "equation": {"latex", "annotation"}, "callout": {"markdown", "tone"}}[typ]
        if set(data) - allowed_data:
            invalid("内容类型包含未知属性", path=f"document.blocks[{index}]", reason="block_structure")
        if typ == "list":
            if not isinstance(data.get("items"), list) or not data["items"] or any(not isinstance(i, str) or not i.strip() for i in data["items"]) or type(data.get("ordered", False)) is not bool:
                invalid("列表不能为空，列表项必须为文字", path=f"document.blocks[{index}]", reason="block_structure")
        else:
            key = {"heading": "text", "paragraph": "markdown", "equation": "latex", "callout": "markdown"}[typ]
            if not isinstance(data.get(key), str) or not data[key].strip():
                invalid("内容块正文不能为空", path=f"document.blocks[{index}]", reason="block_structure")
            if typ == "heading" and (type(data.get("level", 2)) is not int or data.get("level", 2) not in {1, 2, 3}):
                invalid("标题层级必须为 1–3", path=f"document.blocks[{index}]", reason="block_structure")
            if typ == "callout" and (not isinstance(data.get("tone", "info"), str) or data.get("tone", "info") not in {"info", "warning", "error"}):
                invalid("提示类型无效", path=f"document.blocks[{index}]", reason="block_structure")
            if typ == "equation" and not isinstance(data.get("annotation", ""), str):
                invalid("公式说明必须为文字", path=f"document.blocks[{index}]", reason="block_structure")
        values = [(key, value) for key, value in data.items() if isinstance(value, str)]
        values.extend((f"items[{n}]", value) for n, value in enumerate(data.get("items", [])))
        for key, value in values:
            # JSON accepts \f/\b/\r/\t, which can silently destroy LaTeX commands.
            controls = r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]"
            damaged = re.search(controls, value) or re.search(r"(?:\r(?:ac|ight|ho)|\t(?:ext|heta|imes|au)|\n(?:u|abla))(?![A-Za-z])", value)
            if damaged:
                invalid("正文含损坏的 LaTeX 转义或控制字符", reason="invalid_latex_escape", path=f"document.blocks[{index}].data.{key}")
        text = encode(data)
        if strip_thinking(text) != text.strip() or re.search(r"</?think(?:ing)?>", text, re.I):
            invalid("内容包含未过滤的 thinking")
        refs, evidence = block.setdefault("source_ref_ids", []), block.setdefault("evidence_ref_ids", [])
        if not isinstance(refs, list) or not isinstance(evidence, list) or any(not isinstance(r, str) or r not in source_map for r in refs) or any(not isinstance(e, str) or e not in evidence_map or evidence_map[e]["source_ref_id"] not in refs for e in evidence):
            raise NoteError("invalid_source_ref", "引用必须属于冻结快照且教材来源必须属于本块引用消息")
        if generated and any(not source_map[r]["included"] for r in refs):
            raise NoteError("invalid_source_ref", "引用的消息未纳入本次整理")
        old = old_blocks.get(bid)
        if generated:
            block.update(authorship="generated", source_alignment="traceable" if refs else "supplemented", verification={"status": "not_checked", "reasons": []})
        elif old:
            changed = any(block.get(k) != old.get(k) for k in ("type", "role", "data", "source_ref_ids", "evidence_ref_ids", "group_id"))
            block.update(authorship="mixed" if changed and old["authorship"] != "user" else old["authorship"], source_alignment="needs_review" if changed else old["source_alignment"], verification=copy.deepcopy(old["verification"]))
            if changed:
                block["verification"] = {"status": "needs_review", "reasons": ["user_edit_requires_review"]}
        else:
            block.update(authorship="user", source_alignment="user_added", verification={"status": "not_checked", "reasons": []})
        reasons = list(block["verification"].get("reasons", []))
        for warning in snapshot.get("warnings", []):
            if warning["source_ref_id"] in refs:
                reasons.extend(warning["reasons"])
        if generated and refs:
            original = "\n".join(source_map[r]["content"] for r in refs)
            numerals = re.findall(r"(?<![\w])\d+(?:\.\d+)?", " ".join(str(v) for v in data.values()))
            formulas = [data["latex"]] if typ == "equation" else re.findall(r"\$\$?(.+?)\$\$?", data.get("markdown", ""), re.S)
            if any(n not in original for n in numerals) or any(re.sub(r"\s+", "", f) not in re.sub(r"\s+", "", original) for f in formulas):
                reasons.append("numeric_or_formula_support_needs_review")
            if typ != "heading" and refs and all(source_map[r]["role"] == "user" for r in refs):
                reasons.append("user_statement_only")
        if reasons:
            block["verification"] = {"status": "needs_review", "reasons": sorted(set(reasons))}
            warnings.append({"block_id": bid, "reasons": sorted(set(reasons))})
        if generated:
            block["block_id"] = new_id("noteblock")
            if warnings and warnings[-1].get("block_id") == bid:
                warnings[-1]["block_id"] = block["block_id"]
    # Removing a condition or question from a grouped derivation warrants review.
    if previous:
        warnings.extend(copy.deepcopy(w) for w in previous.get("quality", {}).get("warnings", []) if w.get("group_id"))
        removed = [b for b in previous["blocks"] if b["block_id"] not in ids and b.get("group_id")]
        for b in removed:
            warnings.append({"group_id": b["group_id"], "reasons": ["group_member_removed"]})
    quality = {"validation_version": "note-structure-v2", "warnings": warnings, "semantic_review": "not_checked"}
    quality["warning_hash"] = fingerprint(warnings)
    return doc, quality
