"""Editable exercise drafts using the shared QA evidence and answer contract."""
from __future__ import annotations

import re

from backend.services.answer_verification import derive_required_outputs
from graph.generator import (
    grounded_failure_message, has_textbook_evidence,
    prepare_answer_generation, finalize_generated_answer,
)
from graph.main_graph import build_initial_state
from graph.retrieval_node import retrieve_node


def _missing_inputs(question: str, evidence: list[dict]) -> list[dict]:
    """Require referenced tables/figures from the exercise source, not unrelated hits."""
    missing = []
    for kind, pattern in (("table", r"附表|下表|表中|表内"), ("figure", r"附图|下图|如图|图中")):
        if re.search(pattern, question):
            if kind == "table" and re.search(r"\|.+\|\s*\n\|[ :|\-]+\|\s*\n\|.+\|", question):
                continue
            # Current records do not freeze complete source units. Only an exact
            # exercise hit plus its retrieved neighbors can supply the attachment.
            source_ids = {str(item.get("chunk_id") or "") for item in evidence
                          if question.strip() in str(item.get("text") or "")}
            supplied = any(item.get("block_type") == kind and
                           (str(item.get("chunk_id") or "") in source_ids or
                            str(item.get(f"{kind}_anchor_chunk_id") or "") in source_ids)
                           for item in evidence)
            if not supplied:
                missing.append({"id": f"exercise_{kind}", "kind": kind,
                                "label": "题目引用的附表" if kind == "table" else "题目引用的附图",
                                "status": "missing", "blocking": True})
    return missing


def _generate_draft(record, state: dict) -> dict:
    from config import get_llm

    state.update(retrieve_node(state))
    missing = _missing_inputs(record.question_text, state.get("evidence_items") or [])
    if missing:
        return {"success": False, "delivery_status": "waiting_for_input",
                "data": {"required_inputs": missing, "required_outputs": state["required_outputs"]},
                "message": "请先补充并校对题目引用的附图或附表，再生成答案"}
    if not has_textbook_evidence(state):
        return {"success": False, "delivery_status": "degraded", "message": grounded_failure_message(state),
                "retrieval_status": state.get("retrieval_status", "unavailable")}
    messages = prepare_answer_generation(state)
    draft = get_llm(temperature=0.1).invoke(messages).content
    if not isinstance(draft, str) or not draft.strip():
        return {"success": False, "message": "模型未生成有效答案"}
    answer = finalize_generated_answer(state, draft)
    verification = state["answer_verification"]
    status = "completed" if verification["status"] == "passed" else "unverified" if verification["status"] == "unverified" else "degraded"
    return {"success": True, "delivery_status": status,
            "data": {"answer": answer, "verification": verification, "delivery_status": status,
                     "required_outputs": state["required_outputs"], "required_inputs": [],
                     "sources": state.get("evidence_sources") or [],
                     "evidence_count": len(state.get("evidence_sources") or [])},
            "message": "已生成教材答案草稿，请检查修改后保存" if status == "completed" else "答案草稿尚未通过完整核验，请核对缺失项后编辑保存"}


def generate_answer(record, *, book_name: str) -> dict:
    from uuid import uuid4
    from backend.services.learning_task import get_learning_task_store

    state = build_initial_state(
        user_input=record.question_text, book_name=book_name, subject=record.subject,
        target_chapters=[record.chapter] if record.chapter else [], use_textbook_context=True,
    )
    state["intent"] = "application"
    state["required_outputs"] = derive_required_outputs(record.question_text, intent="application", answer_mode="textbook_grounded")
    store = get_learning_task_store()
    task = store.create(task_type="exercise_answer", goal=record.question_text, answer_mode="textbook_grounded",
                        required_outputs=state["required_outputs"],
                        artifacts={"origin": {"kind": "exercise", "exercise_id": getattr(record, "id", ""),
                                              "book_name": book_name}})
    run_id = uuid4().hex
    task = store.claim_run(task, run_id)
    try:
        response = _generate_draft(record, state)
    except Exception:
        response = {"success": False, "delivery_status": "failed", "reason": "exercise_answer_generation_failed",
                    "message": "生成标准答案失败，请检查模型连接后重试"}
    data = response.setdefault("data", {})
    task.required_inputs = data.get("required_inputs") or []
    task.verification = data.get("verification") or {"status": "failed", "reason": response.get("reason") or response.get("delivery_status") or "empty_answer"}
    task.artifacts["answer"] = data.get("answer") or ""
    task.artifacts["sources"] = data.get("sources") or []
    store.save_for_run(task, run_id)
    status = response.get("delivery_status") or ("completed" if response.get("success") else "failed")
    task = store.checkpoint_for_run(task, run_id, "answer", status="degraded" if status == "unverified" else status)
    data["learning_task"] = task.to_dict(public=True)
    return response
