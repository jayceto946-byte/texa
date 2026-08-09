from types import SimpleNamespace

import backend.services.textbook_scope as scope


def _no_local_kg(book_name):
    return SimpleNamespace(_is_local=False), ""


def test_no_book_is_general_qa():
    assert scope.decide_textbook_context(
        "Transformer 的 QKV 是什么？", "Transformer 的 QKV 是什么？", book_name=""
    ) == (False, "no_selected_book")


def test_explicit_textbook_request_always_keeps_retrieval(monkeypatch):
    monkeypatch.setattr(scope, "get_safe_kg", _no_local_kg)
    assert scope.decide_textbook_context(
        "根据教材解释 Transformer 的 QKV。",
        "根据教材解释 Transformer 的 QKV。",
        book_name="sensor-book",
    ) == (True, "explicit_textbook_request")


def test_resolved_followup_inherits_selected_book(monkeypatch):
    monkeypatch.setattr(scope, "get_safe_kg", _no_local_kg)
    assert scope.decide_textbook_context(
        "帮我解释这个概念。",
        "帮我解释压阻效应。",
        book_name="sensor-book",
    ) == (True, "resolved_session_followup")


def test_absent_distinctive_literals_bypass_selected_book(monkeypatch):
    monkeypatch.setattr(scope, "get_safe_kg", _no_local_kg)
    monkeypatch.setattr(scope, "_lexical_index_available", lambda book_name: True)
    monkeypatch.setattr(scope, "search_book", lambda book_name, query, k=3: [])
    assert scope.decide_textbook_context(
        "Transformer 的 QKV 是什么？",
        "Transformer 的 QKV 是什么？",
        book_name="sensor-book",
    ) == (False, "external_literal_absent")


def test_literal_found_in_book_keeps_textbook_context(monkeypatch):
    monkeypatch.setattr(scope, "get_safe_kg", _no_local_kg)
    monkeypatch.setattr(scope, "_lexical_index_available", lambda book_name: True)
    monkeypatch.setattr(
        scope,
        "search_book",
        lambda book_name, query, k=3: [{"content": "ISFET 是一种离子敏场效应器件"}],
    )
    assert scope.decide_textbook_context(
        "什么是 ISFET？", "什么是 ISFET？", book_name="sensor-book"
    ) == (True, "book_literal_match")


def test_absent_chinese_definition_anchor_bypasses_book(monkeypatch):
    monkeypatch.setattr(scope, "get_safe_kg", _no_local_kg)
    monkeypatch.setattr(scope, "_lexical_index_available", lambda book_name: True)
    monkeypatch.setattr(scope, "search_book", lambda book_name, query, k=3: [])
    assert scope.decide_textbook_context(
        "什么是量子纠缠？", "什么是量子纠缠？", book_name="sensor-book"
    ) == (False, "definition_anchor_absent")


def test_no_book_with_subject_is_subject_general(monkeypatch):
    monkeypatch.setattr(scope, "_subject_anchor_support", lambda subject, question: None)
    decision = scope.decide_answer_scope(
        "解释误差传播。",
        "解释误差传播。",
        book_name="",
        subject="专业课/误差理论",
    )
    assert decision.answer_mode == "subject_general"
    assert decision.use_textbook_context is False


def test_no_subject_or_book_is_global_general():
    decision = scope.decide_answer_scope(
        "解释量子纠缠。",
        "解释量子纠缠。",
        book_name="",
        subject="",
    )
    assert decision.answer_mode == "global_general"


def test_strong_anchor_absent_from_subject_requires_confirmation(monkeypatch):
    monkeypatch.setattr(scope, "_subject_anchor_support", lambda subject, question: False)
    decision = scope.decide_answer_scope(
        "Transformer 的 QKV 是什么？",
        "Transformer 的 QKV 是什么？",
        book_name="sensor-book",
        subject="专业课/传感器",
    )
    assert decision.answer_mode == "subject_mismatch"
    assert decision.requires_scope_confirmation is True
    assert decision.reason == "subject_anchor_absent"


def test_explicit_global_mode_overrides_subject_boundary(monkeypatch):
    monkeypatch.setattr(scope, "_subject_anchor_support", lambda subject, question: False)
    decision = scope.decide_answer_scope(
        "Transformer 的 QKV 是什么？",
        "Transformer 的 QKV 是什么？",
        book_name="sensor-book",
        subject="专业课/传感器",
        requested_mode="global_general",
    )
    assert decision.answer_mode == "global_general"
    assert decision.use_textbook_context is False
