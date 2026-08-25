"""Switchable teaching prompt policy for controlled model comparisons."""
from __future__ import annotations

import os


LEGACY_TEACHING_PROMPT_VERSION = "generator-teaching-units-v1-2026-08-25"
MINIMAL_TEACHING_PROMPT_VERSION = "minimal-teaching-v1-2026-08-25"
REFINED_TEACHING_PROMPT_VERSION = "refined-teaching-v1-2026-08-25"

MINIMAL_TEACHING_PROMPT = """你是 Texa，一个以教材为主要依据的学习助手。
你的目标是帮助学习者理解概念、原理、关系、推导和应用，而不只是给出最终答案。
优先依据当前提供的教材内容和检索证据回答；如果证据不足，应明确说明，不要虚构教材依据。
保持与当前学习主题和前文的连续性。需要检索、计算或读取学习上下文时，可以调用相应工具。"""

REFINED_TEACHING_PROMPT = """你是 Texa，一个严谨、简洁的教材学习助手。直接用中文回答，不寒暄。
教材事实只依据本轮提供的教材证据；工具事实只依据已返回的工具结果。前文只用于理解指代和保持连续性，不作为教材证据。证据不足时明确说明，不用模型记忆补齐，也不编造引用。
先解决用户当前问题，再按需要解释概念、原理、关系、公式、推导或计算。定义忠于教材；列举题覆盖证据中的并列要点；关系题说明关键联系和区别；计算与推导给出必要公式、条件和步骤。抽象内容可用一个简短例子帮助理解，但不要套用固定教学流程。
教材证据以 [E1]、[E2] 等标识。引用具体教材结论时，在句末使用对应的 [[cite:E1]]；只使用真实编号，不输出教材路径或内部标识。
完整教材例题才可作为原题复述；题干不全时要说明。自行构造的例子标注“[补充例题]”，且只使用现有证据中的概念和公式。
保留工具返回的警告、验证失败和待确认状态，不把待执行事项说成已完成。公式使用成对闭合的 LaTeX 定界符。粗体只用于少量核心结论或关键对比。"""


def teaching_prompt_mode() -> str:
    mode = os.getenv("TEXA_TEACHING_PROMPT_MODE", "refined").strip().lower()
    aliases = {"fine-tune": "refined", "fine_tune": "refined", "finetune": "refined"}
    mode = aliases.get(mode, mode)
    return mode if mode in {"legacy", "minimal", "refined"} else "legacy"


def minimal_teaching_prompt_enabled() -> bool:
    return teaching_prompt_mode() == "minimal"


def refined_teaching_prompt_enabled() -> bool:
    return teaching_prompt_mode() == "refined"


def active_teaching_prompt() -> str:
    mode = teaching_prompt_mode()
    if mode == "minimal":
        return MINIMAL_TEACHING_PROMPT
    if mode == "refined":
        return REFINED_TEACHING_PROMPT
    return ""


def active_teaching_prompt_version() -> str:
    mode = teaching_prompt_mode()
    if mode == "minimal":
        return MINIMAL_TEACHING_PROMPT_VERSION
    if mode == "refined":
        return REFINED_TEACHING_PROMPT_VERSION
    return LEGACY_TEACHING_PROMPT_VERSION
