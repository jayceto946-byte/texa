"""Visual inputs become frozen Session text; original bytes remain task assets."""
from __future__ import annotations

def visual_session_text(artifacts: dict, fallback: str = "") -> str:
    irs = [artifacts.get("visual_ir") or {}, *(artifacts.get("supplemental_visual_irs") or [])]
    parts = []
    question = str(artifacts.get("question") or fallback).strip()
    if question:
        parts.append(question)
    for index, ir in enumerate(irs):
        if not isinstance(ir, dict):
            continue
        text = str(ir.get("problem_text") or "").strip()
        if text:
            parts.append(("图片题干（识别文本，请校对）" if index == 0 else "补充图片题干") + "：\n" + text)
        for key, label in (("visual_summary", "图形说明"), ("formulas", "公式"), ("options", "选项"),
                           ("annotations", "图中标注"),
                           ("handwritten_work", "手写作答"), ("user_marks", "用户标记"),
                           ("uncertainties", "识别不确定项")):
            value = ir.get(key)
            if value:
                text_value = value if isinstance(value, str) else "\n".join(str(item) for item in value if isinstance(item, str))
                if text_value and text_value not in text:
                    parts.append(label + "：\n" + text_value)
        for key, label in (("relations", "图形条件"), ("required_inputs", "待补充材料")):
            descriptions = []
            for item in ir.get(key) or []:
                if not isinstance(item, dict):
                    continue
                description = str(item.get("description") or item.get("reason") or item.get("name") or "").strip()
                if description and description not in text:
                    descriptions.append(description)
            if descriptions:
                parts.append(label + "：\n" + "\n".join(descriptions))
    return "\n\n".join(parts) or fallback
