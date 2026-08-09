from graph.generator import _build_generate_prompt, generate_node, scope_boundary_message, suggested_fallback_mode


def test_subject_general_prompt_enforces_current_subject_boundary():
    prompt = _build_generate_prompt({
        "intent": "definition",
        "user_input": "什么是压阻效应？",
        "subject": "专业课/传感器",
        "answer_mode": "subject_general",
        "use_textbook_context": False,
        "history_results": [],
    })

    assert "Current subject: 专业课/传感器" in prompt
    assert "Do not silently switch to another discipline" in prompt
    assert "standard formal definition" in prompt


def test_global_general_prompt_does_not_claim_subject_or_textbook_scope():
    prompt = _build_generate_prompt({
        "intent": "definition",
        "user_input": "Transformer 的 QKV 是什么？",
        "subject": "专业课/传感器",
        "answer_mode": "global_general",
        "use_textbook_context": False,
        "history_results": [],
    })

    assert "cross-subject general mode" in prompt
    assert "Current subject:" not in prompt
    assert "selected textbook" in prompt


def test_subject_mismatch_returns_boundary_without_llm():
    state = {
        "intent": "definition",
        "user_input": "Transformer 的 QKV 是什么？",
        "subject": "专业课/传感器",
        "answer_mode": "subject_mismatch",
        "scope_reason": "subject_anchor_absent",
        "use_textbook_context": False,
    }

    result = generate_node(state)

    assert result["final_output"] == scope_boundary_message(state)
    assert "跨学科通用回答" in result["final_output"]


def test_insufficient_textbook_evidence_suggests_explicit_subject_fallback():
    state = {
        "answer_mode": "textbook_grounded",
        "use_textbook_context": True,
        "subject": "专业课/传感器",
        "evidence_support": {"status": "insufficient"},
    }
    assert suggested_fallback_mode(state) == "subject_general"
