"""Offline provider-response replay; no real image or paid model requests."""
import json
import logging
from types import SimpleNamespace

import pytest

from backend.services import multimodal_bridge as bridge_module
from backend.services.multimodal_bridge import VisualProblemIR, VisionModelBridge


def response(content, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish,
    )])


@pytest.fixture
def vision(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_VISUAL_IR_MAX_TOKENS", "3000")
    bridge = VisionModelBridge.__new__(VisionModelBridge)
    bridge.config = SimpleNamespace(credential_configured=True)
    bridge.client = object()
    image = tmp_path / "question.png"
    image.write_bytes(b"original image bytes")
    return bridge, image


@pytest.fixture
def question():
    return {
        "schema_version": "visual-problem-ir/v2",
        "problem_text": r"设数列 $x_n$ 收敛，则（　）。",
        "visual_type": "text_only",
        "options": [
            r"A. 当 $\lim\sin x_n=0$ 时，$\lim x_n=0$",
            r"B. 当 $\lim(x_n+\sqrt{|x_n|})=0$ 时，$\lim x_n=0$",
            r"C. 当 $\lim(x_n+x_n^2)=0$ 时，$\lim x_n=0$",
            r"D. 当 $\lim(x_n+\sin x_n)=0$ 时，$\lim x_n=0$",
        ],
        "required_inputs": [],
    }


def replay(monkeypatch, responses):
    calls = []
    pending = iter(responses)

    def complete(*args, **kwargs):
        calls.append(kwargs)
        item = next(pending)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(bridge_module, "create_vision_completion", complete)
    return calls


def test_local_format_repair_preserves_all_options_and_needs_one_call(vision, question, monkeypatch):
    raw = json.dumps(question, ensure_ascii=False)
    # Single TeX backslashes and trailing separators in both an array and object.
    raw = raw.replace('\\\\', '\\').replace('"required_inputs": []', '"required_inputs": [],')
    raw = raw.replace('], "required_inputs"', ',], "required_inputs"')
    calls = replay(monkeypatch, [response(raw)])
    result = vision[0].analyze(vision[1])
    assert result.problem_text == question["problem_text"]
    assert result.options == question["options"]
    assert len(calls) == 1


def test_trailing_comma_repair_does_not_change_quoted_punctuation():
    stem = '文字 ,} 与 ,]、转义引号 " 和反斜杠 \\ 保持原样'
    raw = json.dumps({"problem_text": stem, "visual_type": "text_only"}, ensure_ascii=False)
    assert VisualProblemIR.from_model_output(raw[:-1] + ',}').problem_text == stem


@pytest.mark.parametrize("text", [
    '{"problem_text":"半个题干',
    '{"problem_text":"题干","options":[,]}',
    '{"problem_text":"题干","options":["A",,"B"]}',
    '{"problem_text":"题干" "options":[]}',
])
def test_format_repair_never_invents_missing_values_or_structure(text):
    with pytest.raises(ValueError, match="结构化结果不完整"):
        VisualProblemIR.from_model_output(text)


@pytest.mark.parametrize("finish,content", [
    ("stop", '{"problem_text":"未闭合'),
    ("stop", ""),
    ("stop", '{"entities":[]}'),
    ("length", '{"problem_text":"未闭合'),
    # A syntactically closed prefix may still omit final options or input gates.
    ("length", '{"problem_text":"部分题干","options":["A"]}'),
])
def test_one_fresh_image_retry_recovers_without_reusing_partial_text(
    vision, question, monkeypatch, finish, content,
):
    calls = replay(monkeypatch, [response(content, finish), response(json.dumps(question))])
    result = vision[0].analyze(vision[1], user_question="请完整讲解", subject="数学")
    assert result.options == question["options"]
    assert len(calls) == 2
    assert calls[0]["messages"][0]["content"][1] == calls[1]["messages"][0]["content"][1]
    retry_text = calls[1]["messages"][0]["content"][0]["text"]
    assert "重新核对原图" in retry_text
    assert "请完整讲解" in retry_text
    assert "未闭合" not in retry_text
    assert calls[1]["max_tokens"] == (6000 if finish == "length" else 3000)


def test_repeated_truncation_fails_without_leaking_model_text(vision, monkeypatch, caplog):
    raw = '{"problem_text":"private-stem secret-api-key <think>private-thinking'
    calls = replay(monkeypatch, [response(raw, "length"), response(raw, "length")])
    with caplog.at_level(logging.INFO, logger=bridge_module.__name__):
        with pytest.raises(ValueError, match="输出被截断.*自动重新识别") as error:
            vision[0].analyze(vision[1])
    assert len(calls) == 2
    assert "reason=truncated" in caplog.text
    assert "finish_reason=length" in caplog.text
    for secret in ("private-stem", "secret-api-key", "private-thinking", "original image bytes"):
        assert secret not in caplog.text + str(error.value)


def test_repeated_bad_format_reports_format_error(vision, monkeypatch):
    calls = replay(monkeypatch, [response('{"problem_text":'), response('{"problem_text":')])
    with pytest.raises(ValueError, match="格式异常.*自动重新识别"):
        vision[0].analyze(vision[1])
    assert len(calls) == 2


def test_retry_shares_original_time_budget(vision, question, monkeypatch):
    ticks = iter([10.0, 10.0, 100.0])
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: next(ticks))
    calls = replay(monkeypatch, [response('{"problem_text":'), response(json.dumps(question))])
    vision[0].analyze(vision[1])
    assert [call["timeout"] for call in calls] == [120.0, 30.0]


def test_expired_budget_does_not_start_another_request(vision, monkeypatch):
    ticks = iter([10.0, 10.0, 131.0])
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: next(ticks))
    calls = replay(monkeypatch, [response('{"problem_text":')])
    with pytest.raises(ValueError, match="格式异常"):
        vision[0].analyze(vision[1])
    assert len(calls) == 1


def test_stopped_run_does_not_start_retry(vision, monkeypatch):
    calls = replay(monkeypatch, [response('{"problem_text":')])
    with pytest.raises(ValueError):
        vision[0].analyze(vision[1], can_retry=lambda: False)
    assert len(calls) == 1


def test_transport_failure_does_not_trigger_format_retry(vision, monkeypatch):
    calls = replay(monkeypatch, [TimeoutError("network timeout")])
    with pytest.raises(TimeoutError):
        vision[0].analyze(vision[1])
    assert len(calls) == 1


def test_filtered_response_is_never_treated_as_a_question_or_retried(vision, monkeypatch):
    calls = replay(monkeypatch, [response("不能处理", "content_filter")])
    with pytest.raises(ValueError, match="未能处理"):
        vision[0].analyze(vision[1])
    assert len(calls) == 1


def test_thinking_is_removed_before_json_parsing(vision, question, monkeypatch):
    calls = replay(monkeypatch, [response('<think>{"problem_text":"错误内容"}</think>' + json.dumps(question))])
    result = vision[0].analyze(vision[1])
    assert result.problem_text == question["problem_text"]
    assert len(calls) == 1
