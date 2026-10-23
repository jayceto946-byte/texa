"""Small IR -> Runtime receipt -> actual model-message contract regressions."""
import hashlib
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from backend.services.figure_learning import FigureLearningService
from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
from backend.tools.registry import ToolContext, ToolRegistry
from graph.evidence_pack import build_evidence_pack
from graph.generator import generate_node, prepare_answer_generation
from graph.textbook_context import expand_textbook_context
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint, persist_canonical_book

PATH = ["第一章", "1.1 中值定理"]


def block(identifier, text, kind="paragraph", **kwargs):
    return DocumentBlock(identifier, kind, text, PATH, 2, 2, source_kind="pdf", source_file="book.pdf", **kwargs)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    manifests = {}
    monkeypatch.setattr("ingestion.index_pipeline.load_index_manifest", lambda name: manifests.get(name, {}))
    monkeypatch.setattr("backend.services.figure_learning.load_index_manifest", lambda name: manifests.get(name, {}))
    FigureLearningService._book_cache.clear()
    service = FigureLearningService(tmp_path)
    monkeypatch.setattr("backend.services.figure_learning.FigureLearningService", lambda: service)
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", "refined")

    def make(extra=None, *, source_kind="pdf", headings=True):
        blocks = ([block("h", "1.1 中值定理", "heading")] if headings else []) + [
            block("premise", "设函数在闭区间连续，在开区间可导。"),
            block("theorem", "定理：存在一个内点，使得下式成立。"),
            block("eq1", r"$$f'(\\xi)=\\frac{f(b)-f(a)}{b-a}$$", "formula"),
            block("proof", "证明：构造辅助函数，应用罗尔定理。"),
            block("eq2", r"$$g(x)=f(x)-kx$$", "formula"),
            block("step", "将端点值代入辅助函数可知两端相等。"),
            block("example", "例1：求函数在给定区间的割线斜率。", "example"),
            block("example-eq", r"$$k=\\frac{f(b)-f(a)}{b-a}$$", "formula"),
        ] + (extra or [])
        book = CanonicalBook("数学", source_kind, blocks, "fixture-v1")
        if source_kind != "pdf":
            for row in blocks:
                row.source_kind = source_kind
        persist_canonical_book(book, progress_root=tmp_path)
        fingerprint = canonical_book_fingerprint(book)
        manifests[book.book_name] = {"index_version": "v1", "canonical_hash": fingerprint}
        anchor = {"book_name": book.book_name, "chunk_id": "retrieved-proof", "chapter": PATH[0],
                  "section_title": PATH[-1], "section_path": PATH, "role": "derivation",
                  "provenance_schema": "texa.provenance/v1", "index_version": "v1",
                  "canonical_hash": fingerprint, "source_block_ids": ["proof"], "text": blocks[4 if headings else 3].text}
        return book, anchor
    return make, service, manifests, tmp_path


def state_for(items, intent="derivation"):
    return {"user_input": "讲解中值定理及证明", "intent": intent, "book_name": "数学", "subject": "数学",
            "answer_mode": "textbook_grounded", "use_textbook_context": True,
            "evidence_items": items, "evidence_support": {"status": "supported"}}


@pytest.mark.parametrize("preset", ["refined", "minimal", "legacy"])
def test_theorem_premises_proof_and_example_reach_actual_model(corpus, monkeypatch, preset):
    make, _, _, _ = corpus
    book, anchor = make()
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", preset)
    calls = []
    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content="在闭区间连续且开区间可导。")
    monkeypatch.setattr("graph.generator.get_llm", lambda **kwargs: SimpleNamespace(invoke=invoke))
    state = state_for([anchor])
    generate_node(state)
    assert len(calls) == 1
    human = calls[0][-1].content
    for row in book.blocks:
        assert row.text in human
    assert human.index("闭区间连续") < human.index("定理：") < human.index("证明：")
    assert "status=complete" in human
    source = state["evidence_sources"][0]
    assert source["index_version"] == "v1" and source["canonical_hash"] == anchor["canonical_hash"]
    assert source["source_block_ids"] == [row.block_id for row in book.blocks]
    assert [row["block_id"] for row in source["source_locations"]] == source["source_block_ids"]
    assert "retrieved-proof" not in human and anchor["canonical_hash"] not in human
    if preset == "refined":
        assert "## 引用协议" not in human and "[[cite:E1]]" not in human
    assert state["verification_evidence"][0]["text"] in human


def test_runtime_receipt_repacking_keeps_long_formula_tail(corpus):
    make, _, _, _ = corpus
    _, anchor = make([block("long", "连续推导说明。" * 410), block("tail", "完整推导的最终一步。")])
    registry = ToolRegistry()
    scope = {"id": "frozen", "book_name": "数学", "subject": "数学", "index_versions": {"数学": "v1"},
             "resources": [{"book_name": "数学", "is_primary": True, "is_selected": True}]}
    register_textbook_search_runtime(registry, scope, versions=lambda _: "v1", retrieve=lambda *a, **k: {
        "evidence_items": [anchor], "evidence_support": {"status": "supported"}, "retrieval_status": "ok"})
    result = registry.runtime_tool("search_textbook").handler(ToolContext(book_name="数学", subject="数学"),
        {"query": "推导中值定理", "chapter": ""})
    assert result.success
    receipt = result.data["evidence_items"][0]
    assert len(receipt["text"]) > 1800
    state = state_for(result.data["evidence_items"])
    human = prepare_answer_generation(state)[-1].content
    assert "完整推导的最终一步。" in human
    assert human.count("教材学习单元：") == 1
    assert state["verification_evidence"][0]["text"] == receipt["text"]
    assert len(json.dumps(result.to_dict(), ensure_ascii=False)) < 128000


def test_budget_closes_at_block_boundary_and_returns_versioned_anchor(corpus):
    make, service, _, _ = corpus
    _, anchor = make([block("too-long", "这个原文块不应被切成半个证明。" * 900), block("end", "尾部。")])
    expanded = expand_textbook_context([anchor], service=service)
    pack = build_evidence_pack(expanded, intent="derivation", char_budget=3000)
    unit = pack["items"][0]["learning_unit"]
    assert unit["status"] == unit["text_status"] == "partial"
    assert unit["continuation"] == {"block_id": "too-long", "index_version": "v1", "canonical_hash": anchor["canonical_hash"],
                                    "book_name": "数学", "unit_id": "h", "anchor_chunk_id": "retrieved-proof",
                                    "anchor_content_fingerprint": expanded[0]["anchor_content_fingerprint"]}
    assert "这个原文块" not in pack["text"] and "status=partial" in pack["text"]
    assert len(pack["text"]) <= pack["budget"] == 3000
    assert "too-long" not in pack["items"][0]["source_block_ids"]
    final = prepare_answer_generation(state_for(pack["verification_items"]))[-1].content
    assert "status=partial" in final and "这个原文块" not in final


@pytest.mark.parametrize("kind", ["ocr", "mineru"])
def test_ocr_is_not_claimed_restored_even_when_all_blocks_present(corpus, kind):
    make, service, _, _ = corpus
    _, anchor = make(source_kind=kind)
    item = expand_textbook_context([anchor], service=service)[0]
    assert item["learning_unit"]["status"] == "unknown"
    assert item["learning_unit"]["text_status"] == "complete"
    human = prepare_answer_generation(state_for([item]))[-1].content
    assert "source=unknown" in human and "不证明OCR正确" in human


@pytest.mark.parametrize("asset", ["missing", "available", "optional"])
@pytest.mark.parametrize("mode", ["split", "native"])
def test_required_figure_availability_does_not_mean_model_read(corpus, monkeypatch, asset, mode):
    make, service, _, root = corpus
    monkeypatch.setenv("LLM_MULTIMODAL_MODE", mode)
    attributes = {"figure_id": "fig", "asset_relpath": "figures/f.png", "asset_status": "missing"}
    if asset != "missing":
        path = root / "数学" / "figures" / "f.png"
        path.parent.mkdir(parents=True)
        Image.new("RGB", (20, 20)).save(path)
        attributes.update(asset_status="ready", content_hash=hashlib.sha256(path.read_bytes()).hexdigest(), image_width=20, image_height=20)
    rows = ([] if asset == "optional" else [block("ref", "根据图1可知辅助函数的形状。")])
    rows += [block("fig", "图1 辅助函数", "figure", attributes=attributes)]
    _, anchor = make(rows)
    expanded = expand_textbook_context([anchor], service=service)
    figure = expanded[0]["learning_unit"]["figures"][0]
    assert figure["availability"] == ("missing" if asset == "missing" else "available")
    assert figure["model_input"] == ("not_required" if asset == "optional" else "not_read")
    assert figure["multimodal_mode"] == mode
    assert figure["reading_role"] == ("vision" if mode == "split" else "reasoning")
    state = state_for(expanded)
    messages = prepare_answer_generation(state)
    assert all(isinstance(m.content, str) for m in messages)  # No pixels were sent.
    assert "URL和图注不是原图" in messages[-1].content
    assert "status=" + ("complete" if asset == "optional" else "partial") in messages[-1].content


def test_referenced_figure_without_a_resource_is_reported_missing(corpus):
    make, service, _, _ = corpus
    _, anchor = make([block("ref", "如图8.2所示。")])
    item = expand_textbook_context([anchor], service=service)[0]
    assert item["learning_unit"]["figures"][0]["availability"] == "missing"
    assert item["learning_unit"]["status"] == "partial"


@pytest.mark.parametrize("failure", ["version", "block", "boundary"])
def test_uncertain_identity_or_boundary_cannot_be_complete(corpus, failure):
    make, service, manifests, _ = corpus
    _, anchor = make(headings=failure != "boundary")
    if failure == "version":
        manifests["数学"]["index_version"] = "v2"
    elif failure == "block":
        anchor["source_block_ids"] = ["missing"]
    item = expand_textbook_context([anchor], service=service)[0]
    assert item["learning_unit"]["status"] == "unknown"
    assert "status=unknown" in build_evidence_pack([item], intent="qa")["text"]


def test_duplicate_anchors_expand_once_and_ordinary_qa_keeps_original_budget(corpus):
    make, service, _, _ = corpus
    _, anchor = make()
    rows = expand_textbook_context([anchor, {**anchor, "chunk_id": "formula-hit", "source_block_ids": ["eq1"]}], service=service)
    assert len(rows) == 1
    assert rows[0]["learning_unit"]["anchor_chunk_ids"] == ["retrieved-proof", "formula-hit"]
    plain = {**anchor, "role": "factual", "text": "普通教材问答" * 500}
    assert expand_textbook_context([plain], intent="factual_recall", service=service) == [plain]
    assert build_evidence_pack([plain])["items"][0]["chars"] == 1800


def test_teach_applies_its_final_budget_before_model_not_after(corpus, monkeypatch):
    from graph.chapter_subgraph import chapter_subgraph_run
    make, _, _, _ = corpus
    # At 6000 chars this whole last block cannot fit; old content[:6000]
    # silently cut it even while the 9000-char pack claimed completeness.
    _, anchor = make([block("large", "必须完整传入的原文公式说明。" * 460)])
    calls = []
    monkeypatch.setattr("graph.chapter_subgraph.get_llm", lambda: SimpleNamespace(invoke=lambda m: calls.append(m) or SimpleNamespace(content="教学内容。")))
    monkeypatch.setattr("graph.chapter_subgraph.SummaryStore", lambda name: SimpleNamespace(get=lambda _: None, set=lambda *a: None))
    state = state_for([anchor], intent="teach")
    chapter_subgraph_run(state)
    assert len(calls) == 1
    human = calls[0][-1].content
    assert "status=partial" in human
    assert "必须完整传入" not in human
    assert state["verification_evidence"][0]["text"] in human
    assert "large" not in state["evidence_sources"][0]["source_block_ids"]


def test_equations_and_table_fields_are_not_lost_when_text_is_only_a_title(corpus):
    make, _, _, _ = corpus
    _, anchor = make([block("fields", "所需公式", equations=[r"$$x^2+y^2=1$$"]),
                      block("table", "取值表", "table", table_header=["x", "y"], table_rows=[["1", "2"]])])
    human = prepare_answer_generation(state_for([anchor]))[-1].content
    assert r"$$x^2+y^2=1$$" in human and "1 | 2" in human


def test_many_small_blocks_respect_runtime_checkpoint_envelope(corpus):
    make, service, _, _ = corpus
    _, anchor = make([block(f"s-{n}", f"第{n}步：继续推导，保留原文身份。") for n in range(100)])
    pack = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="derivation")
    receipt = pack["verification_items"]
    state = state_for(receipt, intent="teach")
    from graph.chapter_subgraph import prepare_chapter_subgraph
    prepare_chapter_subgraph(state)
    assert len(json.dumps({"answer_state": state, "candidates": [], "delivery": "chat"}, ensure_ascii=False)) < 64000
    assert pack["items"][0]["learning_unit"]["status"] == "partial"
    assert pack["items"][0]["learning_unit"]["reason"] == "provenance_budget"


def test_source_titles_narrow_context_without_claiming_prerequisites_complete(corpus):
    make, service, _, _ = corpus
    _, anchor = make([block("next-topic", "2. 另一主题", attributes={"mineru_type": "paragraph_title"}),
                      block("unrelated", "不应展开的另一主题。")])
    item = expand_textbook_context([anchor], service=service)[0]
    assert "不应展开" not in item["text"]
    assert item["learning_unit"]["boundary"] == "source_title"
    assert item["learning_unit"]["status"] == "unknown"


def test_far_anchor_excerpt_survives_surrounding_provenance_budget(corpus):
    make, service, _, _ = corpus
    _, anchor = make([block(f"intro-{n}", "很长的背景说明。" * 10) for n in range(50)] +
                     [block("far", "本次实际命中的原文和必要前提。")])
    anchor.update(source_block_ids=["far"], text="本次实际命中的原文和必要前提。")
    pack = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="derivation")
    assert anchor["text"] in pack["text"]
    source = pack["items"][0]
    assert source["learning_unit"]["status"] == "partial"
    assert source["learning_unit"]["reason"] == "anchor_window"
    assert source["learning_unit"]["preceding"]["block_id"] == "h"
    assert source["source_block_ids"] == ["far"]
    final = prepare_answer_generation(state_for(pack["verification_items"]))[-1].content
    assert anchor["text"] in final and final.count("教材学习单元：") == 1


def test_long_ir_derivation_keeps_anchor_and_formula_tail_under_metadata_budget(corpus):
    from graph.textbook_context import pack_learning_unit, provenance_size, source_locations
    make, service, _, _ = corpus
    extra = [block(f"background-{n}", "拟合背景。" * 10) for n in range(60)]
    extra += [block("least-squares", "最小二乘法：设拟合直线，定义残差及平方和。")]
    extra += [block(f"eq-{n}", rf"y_{{{n}}}=kx+b\tag{{1.{n}}}", "formula") for n in range(5, 12)]
    _, anchor = make(extra, source_kind="mineru")
    anchor.update(source_block_ids=["least-squares"], text=extra[60].text)
    expanded = expand_textbook_context([anchor], service=service)[0]
    packed, unit, blocks, body, size = pack_learning_unit(expanded, 8995)
    assert size == provenance_size(expanded, unit, blocks) <= 8000
    assert unit["status"] == unit["text_status"] == "partial"
    assert unit["source_status"] == "unknown"
    assert blocks[0]["block_id"] == "least-squares"
    pack = build_evidence_pack([expanded], intent="teach")
    receipt = pack["verification_items"][0]
    assert source_locations(receipt) == [b["source_location"] for b in blocks]
    human = prepare_answer_generation(state_for([receipt]))[-1].content
    assert all(b["text"] in human for b in blocks)
    assert all(rf"\tag{{1.{n}}}" in human for n in range(5, 12))
    assert receipt["canonical_hash"] == anchor["canonical_hash"]
    assert receipt["source_location_defaults"]["source_kind"] == "mineru"
    assert "source_kind" not in receipt["source_locations"][0]


def test_compaction_roundtrips_differing_locations_and_review_status(corpus):
    from graph.textbook_context import source_locations, compact_locations
    make, service, _, _ = corpus
    _, anchor = make([block("review", "待复核公式", "formula", review_status="needs_review")])
    expanded = expand_textbook_context([anchor], service=service)[0]
    expanded["context_blocks"][-1]["source_location"]["source_file"] = "supplement.pdf"
    original = [b["source_location"] for b in expanded["context_blocks"]]
    common, compact = compact_locations(original)
    assert "source_file" not in common
    assert source_locations({"source_location_defaults": common, "source_locations": compact}) == original
    pack = build_evidence_pack([expanded], intent="teach")
    receipt = pack["verification_items"][0]
    assert source_locations(receipt) == original
    assert receipt["context_blocks"][-1]["review_status"] == "needs_review"
    assert receipt["learning_unit"]["status"] == "unknown"


def test_metadata_limit_is_shared_and_counts_utf8_without_fallback_escape(corpus):
    from graph.textbook_context import pack_learning_unit
    make, service, _, _ = corpus
    _, anchor = make()
    item = expand_textbook_context([anchor], service=service)[0]
    item["learning_unit"]["figures"] = [{"availability": "unknown", "model_input": "not_read", "reference": "图" * 4000}]
    assert pack_learning_unit(item, 8995)[0] == ""
    # Even the primary excerpt must not bypass the remaining metadata allowance.
    assert build_evidence_pack([item], intent="teach")["verification_items"] == []
    _, anchor = make([block(f"s-{n}", "连续说明") for n in range(100)])
    item = expand_textbook_context([anchor], service=service)[0]
    packed, unit, blocks, _, size = pack_learning_unit(item, 8995, metadata_limit=3000)
    assert size <= 3000 and packed and blocks
    assert unit["reason"] == "provenance_budget"


def test_continuation_reads_next_whole_blocks_and_rejects_stale_or_outside(corpus):
    from graph.textbook_context import read_textbook_continuation, continuation_anchor
    make, service, manifests, _ = corpus
    _, anchor = make([block(f"tail-{n}", "后续完整推导。" * 120) for n in range(8)], source_kind="mineru")
    item = expand_textbook_context([anchor], service=service)[0]
    first = build_evidence_pack([item], intent="teach", char_budget=3000)["verification_items"][0]
    pointer = first["learning_unit"]["continuation"]
    following = read_textbook_continuation(pointer, service=service)
    second = build_evidence_pack(following, intent="teach", char_budget=3000)["verification_items"][0]
    assert second["source_block_ids"][0] == pointer["block_id"]
    assert set(second["source_block_ids"]).isdisjoint(first["source_block_ids"])
    assert second["learning_unit"]["status"] == "partial"
    assert second["learning_unit"]["source_status"] == "unknown"
    assert second["canonical_hash"] == first["canonical_hash"]
    registry = ToolRegistry()
    scope = {"id": "frozen", "book_name": "数学", "subject": "数学", "index_versions": {"数学": "v1"}, "resources": []}
    register_textbook_search_runtime(registry, scope, versions=lambda _: "v1",
        retrieve=lambda *a, **kw: pytest.fail("continuation must not search"))
    tool = registry.runtime_tool("search_textbook")
    result = tool.handler(ToolContext(book_name="数学", subject="数学"),
                          {"query": "继续", "chapter": "", "continuation": pointer})
    assert result.success and result.data["retrieval_status"] == "versioned_canonical_continuation"
    with pytest.raises(Exception, match="escaped frozen scope"):
        tool.handler(ToolContext(book_name="数学", subject="数学"),
                     {"query": "继续", "chapter": "", "continuation": {**pointer, "book_name": "其他教材"}})
    with pytest.raises(ValueError, match="escaped unit"):
        read_textbook_continuation({**pointer, "unit_id": "proof"}, service=service)
    manifests["数学"]["index_version"] = "v2"
    with pytest.raises(ValueError, match="version mismatch"):
        read_textbook_continuation(pointer, service=service)


@pytest.mark.parametrize("mutation", [
    {"book_name": "其他教材"}, {"index_version": "old-version"},
    {"canonical_hash": "0" * 64}, {"unit_id": "proof"}, {"block_id": "absent"},
])
def test_current_continuation_rejects_forged_or_stale_pointers_through_tool(corpus, mutation):
    from backend.services.agent_runtime.contracts import RuntimeDenied
    make, service, _, _ = corpus
    _, anchor = make([block(f"tail-{n}", "后续推导。" * 120) for n in range(8)])
    first = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="teach", char_budget=3000)["verification_items"][0]
    pointer = first["learning_unit"]["continuation"]
    registry = ToolRegistry()
    register_textbook_search_runtime(registry,
        {"book_name": "数学", "subject": "数学", "index_versions": {"数学": "v1"}, "resources": []},
        versions=lambda _: "v1", retrieve=lambda *a, **kw: pytest.fail("invalid continuation must not search"))
    tool = registry.runtime_tool("search_textbook")
    args = tool.runtime_input.model_validate({"query": "继续", "continuation": {**pointer, **mutation}}).model_dump()
    with pytest.raises(RuntimeDenied, match="continuation"):
        tool.handler(ToolContext(book_name="数学", subject="数学"), args)


def test_continuation_calls_spend_the_existing_runtime_tool_budget(corpus):
    from backend.services.agent_runtime.contracts import RunCommand, FixedAction, RuntimeConflict
    from backend.services.agent_runtime.runner import FixedRunner
    from backend.services.agent_runtime.store import RuntimeStore
    make, service, _, root = corpus
    _, anchor = make([block(f"tail-{n}", "后续推导。" * 120) for n in range(8)])
    first = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="teach", char_budget=3000)["verification_items"][0]
    registry = ToolRegistry()
    register_textbook_search_runtime(registry,
        {"id": "scope", "book_name": "数学", "subject": "数学", "index_versions": {"数学": "v1"}, "resources": []},
        versions=lambda _: "v1", retrieve=lambda *a, **kw: pytest.fail("continuation must not search"))
    store = RuntimeStore(root / "runtime.db")
    snapshot = store.create(RunCommand("key", "req", "task", "conv", "turn", "继续", "owner", budget_calls=1))
    runner = FixedRunner(store, registry, allowlist=frozenset({"search_textbook"}))
    args = {"query": "继续", "continuation": first["learning_unit"]["continuation"]}
    run_id = snapshot["run"]["id"]
    context = ToolContext(book_name="数学", subject="数学")
    result = runner.execute(run_id, "owner", FixedAction("call", tool_id="search_textbook", args=args, operation_key="first"), context=context)
    assert result["consumed_calls"] == 1
    assert result["tool_calls"][0]["status"] == "succeeded"
    assert result["tool_calls"][0]["tool_version"] == "3"
    with pytest.raises(RuntimeConflict, match="budget"):
        runner.execute(run_id, "owner", FixedAction("call", tool_id="search_textbook", args=args, operation_key="second"), context=context)
    assert store.snapshot(run_id)["consumed_calls"] == 1


def test_continuation_advances_beyond_initial_block_scan_cap(corpus):
    from graph.textbook_context import read_textbook_continuation
    make, service, _, _ = corpus
    _, anchor = make([block(f"s-{n}", f"第{n}步") for n in range(180)])
    first = expand_textbook_context([anchor], service=service)[0]
    pointer = first["learning_unit"]["continuation"]
    from backend.services.agent_runtime.textbook_tool import TextbookContinuation
    TextbookContinuation.model_validate(pointer)
    tail = read_textbook_continuation(pointer, service=service)[0]
    assert tail["context_blocks"][0]["block_id"] == pointer["block_id"]
    assert tail["context_blocks"][-1]["block_id"] == "s-179"
    assert tail["learning_unit"]["continuation"] is None
    assert tail["learning_unit"]["text_status"] == "partial"


def test_focused_segment_keeps_required_figure_and_omits_unread_background(corpus):
    make, service, _, _ = corpus
    background = [block(f"bg-{n}", "背景说明。" * 20) for n in range(60)]
    background.insert(0, block("background-ref", "参见图1.1。"))
    background.insert(1, block("bg-figure", "图1.1", "figure"))
    background += [block("target", "本推导需要图1.2，原文公式保持完整。"),
                   block("target-figure", "图1.2", "figure"), block("target-eq", "x=y", "formula")]
    _, anchor = make(background, source_kind="mineru")
    anchor.update(source_block_ids=["target"], text="本推导需要图1.2，原文公式保持完整。")
    pack = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="teach")
    unit = pack["items"][0]["learning_unit"]
    assert unit["status"] == "partial"
    assert [f["figure_id"] for f in unit["figures"]] == ["target-figure"]
    assert unit["figures"][0]["required"] is True
    assert unit["figures"][0]["availability"] == "missing"
    assert unit["figures"][0]["model_input"] == "not_read"
    assert unit["omitted_figures"] == 1
    assert unit["preceding"]["canonical_hash"] == anchor["canonical_hash"]


def test_many_evidence_units_share_one_metadata_cap(corpus):
    from graph.textbook_context import provenance_size, source_locations
    make, service, _, _ = corpus
    _, anchor = make([block(f"n-{n}", "连续教学。" * 10) for n in range(70)])
    first = expand_textbook_context([anchor], service=service)[0]
    # Separate units from different books share the same final metadata envelope.
    second = {**first, "book_name": "辅书", "chunk_id": "second", "text": first["text"] + "另一本教材"}
    pack = build_evidence_pack([first, second], intent="teach")
    total = 0
    for row in pack["verification_items"]:
        locs = {loc["block_id"]: loc for loc in source_locations(row)}
        blocks = [{**b, "source_location": locs[b["block_id"]]} for b in row["context_blocks"]]
        total += provenance_size(row, row["learning_unit"], blocks)
    assert total <= 8000
    assert "retrieved-proof" == pack["items"][0]["chunk_id"]
    assert pack["items"][0]["learning_unit"]["status"] == "partial"


def test_primary_excerpt_beyond_scan_cap_stays_bounded_and_can_continue(corpus):
    from graph.textbook_context import read_textbook_continuation
    make, service, _, _ = corpus
    _, anchor = make([block(f"n-{n}", "背景。") for n in range(150)] + [block("far-out", "真正命中的原文。")])
    anchor.update(source_block_ids=["far-out"], text="真正命中的原文。")
    packed = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="teach")
    row = packed["verification_items"][0]
    assert row["learning_unit"]["reason"] == "anchor_excerpt_fallback"
    assert anchor["text"] in row["text"]
    tail = read_textbook_continuation(row["learning_unit"]["continuation"], service=service)
    assert tail[0]["context_blocks"][0]["block_id"] == "far-out"


def test_compacted_long_receipt_survives_runtime_pause_resume(corpus, tmp_path):
    from backend.services.agent_runtime.store import RuntimeStore, _dump
    from backend.services.agent_runtime.contracts import RunCommand
    from langchain_core.messages import messages_to_dict, messages_from_dict
    make, service, _, _ = corpus
    _, anchor = make([block(f"long-{n}", "推导。" * 10) for n in range(80)])
    pack = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="teach")
    state = state_for(pack["verification_items"], intent="teach")
    messages = prepare_answer_generation(state)
    store = RuntimeStore(tmp_path / "runtime.db")
    snap = store.create(RunCommand("request", "key", "task", "session", "turn", "推导", "owner", budget_calls=1))
    run = snap["run"]["id"]
    store.configure_chat(run, "owner", state=state, candidates=(), request_question="推导", book_name="数学", subject="数学")
    store.save_native_messages(run, "owner", messages_to_dict(messages))
    store.close(run, "owner", outcome="paused", error_code="interrupted")
    paused = store.snapshot(run)
    resumed = store.resume(paused["task"]["id"], expected_revision=paused["task_revision"], request_key="resume",
                           request_id="resume", owner_token="new", turn_id="turn")
    saved = resumed["run"]["checkpoint"]
    assert saved["answer_state"]["evidence_sources"] == state["evidence_sources"]
    assert messages_from_dict(saved["native_messages"])[-1].content == messages[-1].content
    assert len(_dump(saved["native_messages"])) < 64000
    assert state["verification_evidence"][0]["canonical_hash"] == anchor["canonical_hash"]


def test_expanded_and_repacked_sources_keep_indexed_anchor_fingerprint(corpus, monkeypatch):
    from graph.retrieval_node import _hydrate_active_evidence
    from graph.textbook_context import read_textbook_continuation
    make, service, _, _ = corpus
    _, anchor = make([block(f"long-{n}", "连续推导。" * 80) for n in range(20)])
    pack = build_evidence_pack(expand_textbook_context([anchor], service=service), intent="teach", char_budget=3000)
    state = state_for(pack["verification_items"])
    prepare_answer_generation(state)
    source = state["evidence_sources"][0]
    expected = hashlib.sha256(anchor["text"].encode()).hexdigest()[:24]
    assert source["content_fingerprint"] == expected
    assert source["visible_fingerprint"] != expected
    monkeypatch.setattr("graph.retrieval_node.expand_neighbors", lambda *a, **kw: [anchor])
    restored, errors = _hydrate_active_evidence({"active_evidence_sources": [source],
                                               "active_evidence_ids": [anchor["chunk_id"]]}, "数学")
    assert not errors and restored[0]["text"] == anchor["text"]
    pointer = source["learning_unit"]["continuation"]
    tail = build_evidence_pack(read_textbook_continuation(pointer, service=service), intent="teach", char_budget=3000)
    assert tail["items"][0]["content_fingerprint"] == expected
    assert tail["items"][0]["visible_fingerprint"] != source["visible_fingerprint"]
    monkeypatch.setattr("graph.retrieval_node.expand_neighbors", lambda *a, **kw: [{**anchor, "text": "已变更的原文"}])
    restored, errors = _hydrate_active_evidence({"active_evidence_sources": [source],
                                               "active_evidence_ids": [anchor["chunk_id"]]}, "数学")
    assert not restored and errors[0].startswith("continuity_fingerprint:")
