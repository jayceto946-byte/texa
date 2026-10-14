"""Synthetic audit witnesses; no model calls, production assets, or migrations.

Run with venv310/bin/python. Results describe current behavior, not passing gates.
All inputs below are authored synthetic fixtures. Network connections are denied.
"""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    assert sys.version_info[:2] == (3, 10)
    with tempfile.TemporaryDirectory(prefix="texa-business-audit-") as temporary:
        root = Path(temporary)
        for key, suffix in {
            "DATA_DIR": "data", "PROGRESS_PATH": "progress", "VECTOR_DB_PATH": "vectors",
            "BOOKS_PATH": "books", "CHAPTERS_PATH": "chapters", "IMAGES_PATH": "images",
            "MINERU_OUTPUT_PATH": "mineru", "ENV_PATH": "empty.env",
        }.items():
            os.environ[key] = str(root / suffix)
        (root / "empty.env").touch()
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False",
                          QUESTION_UNDERSTANDING_MODE="off")
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
            results = run_probes()
    output = Path(__file__).with_name("audit-probes.json")
    output.write_text(json.dumps({"boundary": "Synthetic production-function witnesses; no live Planner, model, vector corpus, or Electron acceptance", "python": sys.version.split()[0], "results": results}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(results, ensure_ascii=False, indent=2))


def run_probes():
    from graph.retrieval_node import _extract_query_focus, _supports_query_literals, _assess_evidence_support
    from graph.evidence_pack import build_evidence_pack
    from graph.generator import finalize_answer_verification
    from backend.services.answer_verification import derive_required_outputs, verify_answer
    from backend.services.session_notes.generation import decode_result
    from backend.services.session_notes.validation import validate_document
    from memory.session_notes import NoteError

    results = {}
    results["D02_focus"] = {q: _extract_query_focus(q, []) for q in
                           ("什么是电阻式传感器？", "电阻式传感器是什么？", "请解释电阻式传感器")}
    results["F03_literal"] = {q: _supports_query_literals(q, "二阶测量系统的动态响应") for q in
                             ("16. 写出二阶测量系统的动态响应", "写出二阶测量系统的动态响应")}
    results["literal_substring"] = _supports_query_literals("型号PT100", "型号PT1000")

    query = "写出二阶测量系统微分方程、灵敏度、固有频率、阻尼比和阶跃响应"
    results["F03_coverage"] = {"focus": _extract_query_focus(query, []), "outputs": derive_required_outputs(query, answer_mode="textbook_grounded")}
    raw = [{"chunk_id": "synthetic-resistance", "book_name": "audit", "chapter": "audit",
            "text": "压阻效应是材料受力后电阻率发生变化的现象。", "query_coverage": 1.0}]
    pack = build_evidence_pack(raw, intent="definition")
    state = {"user_input": "什么是霍尔效应？", "answer_mode": "textbook_grounded", "intent": "definition",
             "evidence_items": raw, "evidence_sources": pack["items"]}
    finalize_answer_verification(state, "霍尔效应由磁场引起。[[cite:E1]]")
    results["production_citation_missing_text"] = state["answer_verification"]
    results["test_shaped_citation_with_text"] = verify_answer("霍尔效应由磁场引起。[[cite:E1]]",
        required_outputs=derive_required_outputs("什么是霍尔效应？", answer_mode="textbook_grounded"),
        sources=[{"id": "E1", "text": raw[0]["text"]}])
    results["formula_false_pass"] = verify_answer("欧姆定律为 $U=I/R$。[[cite:E1]]",
        required_outputs=derive_required_outputs("写出欧姆定律公式", answer_mode="textbook_grounded"),
        sources=[{"id": "E1", "text": "欧姆定律为 $U=IR$。"}])
    tail = [{"chunk_id": "synthetic-long", "chapter": "audit", "text": "电阻式传感器。" + "背景内容。" * 400 + "灵敏度是输出变化与输入变化之比。", "is_direct_hit": True}]
    support = _assess_evidence_support("电阻式传感器的灵敏度是什么？", tail)
    clipped = build_evidence_pack(tail, intent="definition")
    results["post_pack_coverage"] = {"before": support["status"], "required_fact_in_final_pack": "灵敏度" in clipped["text"], "chars": clipped["char_count"]}

    base = {"document": {"title": "合成笔记", "blocks": [{"block_id": "b1", "type": "equation", "data": {"latex": "PLACEHOLDER"}, "source_ref_ids": [], "evidence_ref_ids": []}]}}
    note_results = {}
    for name, latex in (("correct_double_escape", r"\\frac{a}{b}"), ("json_valid_control_escape", r"\frac{a}{b}"), ("invalid_json_escape", r"\alpha")):
        raw_note = json.dumps(base, ensure_ascii=False).replace("PLACEHOLDER", latex)
        try:
            parsed = decode_result(raw_note)
            doc, _ = validate_document(parsed["document"], {"sources": [], "evidence": [], "chapter_refs": []}, generated=True)
            value = doc["blocks"][0]["data"]["latex"]
            note_results[name] = {"accepted": True, "control_characters": any(ord(c) < 32 for c in value), "preserves_latex_command": value.startswith("\\")}
        except NoteError as exc:
            note_results[name] = {"accepted": False, "code": exc.code}
    results["note_latex_contract"] = note_results

    from graph.planner import plan_node
    plan_response = SimpleNamespace(content=json.dumps({"intent": "comparison", "target_chapters": ["第二章"], "sub_tasks": []}))
    with patch("graph.intent_classifier.classify_intent_local", return_value={"intent": "comparison", "is_simple": False}), patch("graph.intent_classifier.is_fast_path_eligible", return_value=False), patch("graph.safe_retrieval.get_safe_vector_store", return_value=(SimpleNamespace(get_chapter_names=lambda **kw: ["第一章", "第二章"]), "")), patch("graph.planner.get_llm", return_value=SimpleNamespace(invoke=lambda *a, **kw: plan_response)):
        planned = plan_node({"user_input": "比较两种传感器的原理和特点", "book_name": "audit", "target_chapters": ["第一章"], "use_textbook_context": True})
    results["planner_explicit_scope"] = {"requested": ["第一章"], "returned": planned["target_chapters"]}

    from backend.api import exercises
    from backend.schemas import ExerciseAnswerGenerateRequest
    record = SimpleNamespace(chapter="第一章", subject="专业课", question_text="根据附表计算输出电压")
    with patch.object(exercises, "_bank", return_value=SimpleNamespace(get=lambda _id: record)), patch("graph.retrieval_node.retrieve_node", return_value={"evidence_items": raw, "evidence_support": {"status": "supported"}}), patch("config.get_llm", return_value=SimpleNamespace(invoke=lambda *a, **kw: SimpleNamespace(content="输出为123伏。"))):
        response = exercises.generate_exercise_answer(ExerciseAnswerGenerateRequest(id="synthetic"), book_name="audit")
    results["exercise_unverified_draft"] = {"success": response["success"], "verification_present": "verification" in response.get("data", {}), "data_keys": sorted(response.get("data", {}))}
    return results


if __name__ == "__main__":
    main()
