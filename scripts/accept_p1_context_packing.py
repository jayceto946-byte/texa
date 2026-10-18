"""Finite, explicitly authorized sensor packing acceptance; no production writes.

Deterministic mode is the default. --model sends only the current derivation
through the existing DeepSeek profile, with a hard persistent 3-request ceiling.
Private reasoning and credentials never enter artifacts. Full textbook text and
public model messages stay in /private/tmp; committed artifacts contain metrics.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
QA = Path("/private/tmp/texa-p1-context-packing")
OUT = ROOT / "docs/qa/p1-context-packing"
BASE = "655aa481743b20e24eaab52f5f75d141b4db83dc"
TAGS = [f"1.{n}" for n in range(5, 12)]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def encoded(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def setup():
    QA.mkdir(parents=True, exist_ok=True)
    os.environ.update(ENV_PATH=str(QA / "empty.env"), DATA_DIR=str(QA / "data"),
        PROGRESS_PATH=str(QA / "progress"), VECTOR_DB_PATH=str(QA / "vector"),
        BOOKS_PATH=str(QA / "books"), MINERU_OUTPUT_PATH=str(QA / "mineru"),
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TEXA_TEACHING_PROMPT_MODE="refined")
    import accept_p1_reliability as harness
    import accept_p1_sensor as sensor
    harness.QA = QA
    harness.OUT = OUT
    sensor.QA = QA
    sensor.OUT = OUT
    # Existing profile selection only reads credentials/configuration into RAM.
    role = harness.setup()
    assert role.model == "deepseek-flash" and role.provider.provider_id == "deepseek"
    return sensor, role


def baseline(items, service):
    import graph.textbook_context as current
    modules = []
    try:
        for name, path in (("graph.textbook_context", "graph/textbook_context.py"),
                           ("packing_baseline_evidence", "graph/evidence_pack.py")):
            source = subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT, text=True)
            module = types.ModuleType(name)
            exec(compile(source, BASE + "/" + path, "exec"), module.__dict__)
            sys.modules[name] = module
            modules.append(module)
        anchors = [anchor for item in items for anchor in item.get("expansion_anchors", [item])]
        expanded = modules[0].expand_textbook_context(anchors, intent="teach", service=service)
        packed = modules[1].build_evidence_pack(expanded, intent="teach")
        raw = modules[0].pack_learning_unit(expanded[0], 8995)
        return packed, raw, expanded[0]
    finally:
        sys.modules["graph.textbook_context"] = current
        sys.modules.pop("packing_baseline_evidence", None)


def run_deterministic(sensor):
    from graph.evidence_pack import build_evidence_pack
    from graph.generator import prepare_answer_generation
    from graph.textbook_context import pack_learning_unit, read_textbook_continuation, source_locations
    from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
    from backend.tools.registry import ToolRegistry, ToolContext
    from backend.services.agent_runtime.contracts import RunCommand, FixedAction
    from backend.services.agent_runtime.runner import FixedRunner
    from backend.services.agent_runtime.store import RuntimeStore, _dump
    book, rows, manifest, service, identity = sensor.sources()
    items = sensor.retrieve_for(rows, service, sensor.CASES["C"][1])
    assert items[0]["chunk_id"] == "e62ed1070495dd21e981"
    before, raw, old_full = baseline(items, service)
    full = items[0]
    old_metadata = {"unit": old_full["learning_unit"], "locations": old_full["source_locations"],
        "blocks": [{k: v for k, v in b.items() if k not in {"text", "source_location", "equations", "section_path"}}
                   for b in old_full["context_blocks"]]}
    after = build_evidence_pack(items, intent="teach")
    scope = {"id": "packing-sensor", "book_name": sensor.BOOK, "subject": "传感器",
        "index_versions": {sensor.BOOK: manifest["index_version"]},
        "resources": [{"book_name": sensor.BOOK, "is_primary": True, "is_selected": True}]}
    registry = ToolRegistry()
    register_textbook_search_runtime(registry, scope, versions=lambda _: manifest["index_version"],
        retrieve=lambda *a, **kw: {"evidence_items": items, "evidence_support": {"status": "supported"}, "retrieval_status": "real_bm25"})
    store_path = QA / "deterministic-runtime.db"
    store = RuntimeStore(store_path)
    case = "packing-" + str(time.time_ns())
    owner = case
    snap = store.create(RunCommand(case, case, case, case, case, sensor.CASES["C"][2], owner, budget_calls=1))
    run = snap["run"]["id"]
    snapshot = FixedRunner(store, registry, allowlist=frozenset({"search_textbook"})).execute(run, owner,
        FixedAction("call", tool_id="search_textbook", args={"query": sensor.CASES["C"][2], "chapter": ""}, operation_key=case),
        context=ToolContext(book_name=sensor.BOOK, subject="传感器"))
    receipt = snapshot["tool_calls"][0]["result"]
    assert snapshot["tool_calls"][0]["status"] == "succeeded"
    selected = receipt["data"]["evidence_items"]
    state = {"user_input": sensor.CASES["C"][2], "book_name": sensor.BOOK, "subject": "传感器", "intent": "teach",
        "use_textbook_context": True, "answer_mode": "textbook_grounded", "evidence_items": selected,
        "evidence_support": {"status": "supported"}}
    from graph.chapter_subgraph import prepare_chapter_subgraph
    prepare_chapter_subgraph(state)
    store.configure_chat(run, owner, state=state, candidates=(), request_question=state["user_input"], book_name=sensor.BOOK, subject="传感器")
    messages = prepare_answer_generation(state)
    from langchain_core.messages import messages_to_dict
    store.save_native_messages(run, owner, messages_to_dict(messages))
    visible = state["verification_evidence"][0]
    human = messages[-1].content
    body = "\n\n".join(b["text"] for b in visible["context_blocks"])
    assert all(r"\tag{" + tag + "}" in human for tag in TAGS)
    assert all(b["text"] in human for b in visible["context_blocks"])
    assert all(r"\tag{" + tag + "}" in full["text"] for tag in TAGS)
    source_by_id = {b["block_id"]: b for b in full["context_blocks"]}
    assert source_locations(visible) == [source_by_id[x]["source_location"] for x in visible["source_block_ids"]]
    actual_metadata = encoded({**state["evidence_sources"][0], "context_blocks": [
        {k: v for k, v in b.items() if k != "text"} for b in visible["context_blocks"]]})
    assert actual_metadata <= 8000
    assert len(_dump(receipt)) < 128000
    assert len(_dump({"answer_state": state, "candidates": [], "delivery": "chat"})) < 64000
    assert len(_dump(messages_to_dict(messages))) < 64000
    # Enumerate omitted prefix pages through the same versioned Canonical reader.
    # No automated model loop is added; each read remains a normal budgeted action.
    pointer = visible["learning_unit"].get("preceding")
    seen = set(visible["source_block_ids"])
    continuation_pages = []
    for _ in range(10):
        if pointer is None:
            break
        segment = build_evidence_pack(read_textbook_continuation(pointer, service=service), intent="teach")
        row = segment["verification_items"][0]
        new_ids = set(row["source_block_ids"]) - seen
        assert new_ids or pointer["block_id"] in seen
        seen.update(row["source_block_ids"])
        continuation_pages.append({"block_ids": row["source_block_ids"], "chars": len(row["text"]),
                                   "status": row["learning_unit"]["status"]})
        pointer = row["learning_unit"].get("continuation")
    assert pointer is None and seen == set(full["source_block_ids"])
    short = sensor.retrieve_for(rows, service, sensor.CASES["A"][1])
    short_old, _, _ = baseline(short, service)
    short_new = build_evidence_pack(short, intent="teach")
    assert short_old["text"] == short_new["text"]
    image = sensor.DESKTOP / "mineru_output" / sensor.BOOK / "hybrid_auto_external/CGQ/images/page_16_equation_25.jpg"
    summary = {"base": BASE, "identity": identity, "before": {
        "expanded_blocks": len(full["context_blocks"]), "expanded_body_chars": len(full["text"]),
        "full_old_metadata_utf8_bytes": encoded(old_metadata),
        "full_old_metadata_default_json_utf8_bytes": len(json.dumps(old_metadata, ensure_ascii=False).encode()),
        "old_accounted_metadata_characters": raw[4], "selected_prefix_blocks": len(raw[2]),
        "selected_prefix_body_chars": len(raw[3]), "budget_reason": raw[1]["reason"],
        "visible_chars": len(before["verification_items"][0]["text"]),
        "visible_body_chars": len(before["verification_items"][0].get("context_source_text", "")),
        "final_source_metadata_utf8_bytes": encoded(before["items"][0]),
        "visible_formula_tags": [t for t in TAGS if r"\tag{" + t + "}" in before["text"]],
        "status": before["items"][0]["learning_unit"]["status"]},
        "after": {"visible_blocks": len(visible["context_blocks"]), "visible_body_chars": len(body),
        "visible_chars": len(visible["text"]), "visible_sha256": digest(visible["text"]),
        "visible_formula_tags": TAGS, "metadata_utf8_bytes": actual_metadata,
        "conservative_metadata_reservation": pack_learning_unit(items[0], 8995)[4],
        "text_status": visible["learning_unit"]["text_status"], "status": visible["learning_unit"]["status"],
        "source_status": visible["learning_unit"]["source_status"],
        "source_block_ids": visible["source_block_ids"], "learning_unit": visible["learning_unit"],
        "receipt_chars": len(_dump(receipt)), "receipt_utf8_bytes": len(_dump(receipt).encode()),
        "checkpoint_chars": len(_dump({"answer_state": state, "candidates": [], "delivery": "chat"})),
        "native_messages_chars": len(_dump(messages_to_dict(messages))),
        "final_human_chars": len(human), "final_human_sha256": digest(human)},
        "continuation": {"all_39_blocks_readable": True, "pages": continuation_pages},
        "short_A_text_unchanged": True,
        "formula_1_9": {"image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "source_image_available": True, "observation": "Source crop also shows partial/partial k with (-1); source notation defect, not a proven OCR-only defect. IR unchanged."},
        "result": "PASS"}
    write(QA / "final-messages.json", [{"role": m.type, "content": m.content} for m in messages])
    write(QA / "deterministic-receipt.json", receipt)
    write(OUT / "deterministic.json", summary)
    assert sensor.sources()[-1]["files"] == identity["files"]
    print(json.dumps({"deterministic": "PASS", "after": {k: v for k, v in summary["after"].items()
        if k not in {"learning_unit", "source_block_ids"}}}, ensure_ascii=False))
    return items, manifest, identity


def run_model(sensor, role, items, manifest, identity):
    import httpx
    from langchain_core.callbacks import BaseCallbackHandler
    from llm.factory import build_chat_model
    from utils.thinking_filter import strip_thinking
    ledger_path = OUT / "usage.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {
        "provider": "deepseek", "model": "deepseek-flash", "request_limit": 3, "requests": []}
    case = "packing-C-" + str(time.time_ns())
    current = {}
    def guard(request):
        assert request.url.host == "api.deepseek.com" and request.url.path.endswith("/chat/completions")
        data = json.loads(request.content)
        assert data["model"] == "deepseek-flash" and data["temperature"] == 1
        assert data["thinking"] == {"type": "enabled"} and data["reasoning_effort"] == "high"
        assert data["max_tokens"] == 8192
        assert len(ledger["requests"]) < 3, "finite 3-request acceptance ceiling"
        public = [{k: v for k, v in m.items() if k != "reasoning_content"} for m in data["messages"]]
        text = json.dumps(public, ensure_ascii=False)
        assert all(isinstance(m.get("content", ""), (str, type(None))) for m in public)
        # Only question/derivation and ordinary system/tool contracts may leave.
        assert all(tag in text for tag in TAGS)
        record = {"case": case, "index": len(ledger["requests"]) + 1, "temperature": 1,
                  "status": "requested", "public_input_sha256": digest(text), "input_bytes": len(request.content),
                  "formula_tags_in_actual_request": TAGS}
        ledger["requests"].append(record)
        current.update(record=record, start=time.monotonic())
        write(ledger_path, ledger)
        write(QA / (case + "-public-input.json"), public)
    original_init = httpx.Client.__init__
    clients = []
    def guarded_init(self, *args, **kwargs):
        hooks = dict(kwargs.pop("event_hooks", {}) or {})
        hooks["request"] = [*hooks.get("request", []), guard]
        kwargs.update(event_hooks=hooks, trust_env=False)
        original_init(self, *args, **kwargs)
        clients.append(self)
    httpx.Client.__init__ = guarded_init
    class Receipt(BaseCallbackHandler):
        def on_llm_end(self, response, **kw):
            m = response.generations[0][0].message
            current["record"].update(status="returned", usage=m.usage_metadata or {},
                request_ms=round((time.monotonic() - current["start"]) * 1000, 2),
                response_model=m.response_metadata.get("model_name"), finish_reason=m.response_metadata.get("finish_reason"))
            write(ledger_path, ledger)
            (QA / (case + "-public-answer.txt")).write_text(strip_thinking(m.content) if isinstance(m.content, str) else "")
    def factory(resolved, temperature=1, **kw):
        kw.update(max_retries=0, stream_usage=True, request_timeout=180)
        return build_chat_model(resolved, 1, **kw).model_copy(update={"callbacks": [Receipt()], "max_tokens": 8192})
    start = time.monotonic()
    try:
        result = sensor.native(case, sensor.CASES["C"][2], items, manifest, role, factory)
        write(QA / (case + "-runtime.json"), result)
        answer = result.get("answer", "")
        summary = {"case": case, "run_status": result.get("run_status"), "task_status": result.get("task_status"),
            "error_code": result.get("error_code"), "answer_chars": len(answer), "answer_sha256": digest(answer),
            "verification": result.get("verification"), "tool_statuses": [{"id": c["tool_id"], "status": c["status"]} for c in result.get("tool_calls", [])],
            "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
            "model": role.model, "temperature": 1, "thinking": "enabled", "reasoning_effort": "high"}
        write(OUT / (case + ".json"), summary)
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        httpx.Client.__init__ = original_init
        for client in clients:
            client.close()
        assert sensor.sources()[-1]["files"] == identity["files"]


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--model", action="store_true")
    options = args.parse_args()
    sensor, role = setup()
    items, manifest, identity = run_deterministic(sensor)
    if options.model:
        run_model(sensor, role, items, manifest, identity)


if __name__ == "__main__":
    main()
