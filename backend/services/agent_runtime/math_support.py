"""Whole-question, frozen pure math exception; uncertain requests keep their scope."""
import re

_EXPR = r"[A-Za-z0-9_\s.+*/^()×÷−π-]+"
_PATTERNS = [
    rf"(?:计算|算出|求值|化简)\s*{_EXPR}",
    rf"(?:解|求解)方程\s*{_EXPR}={_EXPR}",
    rf"(?:求|计算)(?:函数)?\s*{_EXPR}(?:关于\s*[xyzt]\s*)?的(?:一阶)?导数",
    rf"(?:求|计算)\s*{_EXPR}(?:关于\s*[xyzt]\s*)?的(?:不定)?积分",
    rf"(?:求|计算)\s*{_EXPR}在\s*[xyzt]\s*=\s*{_EXPR}(?:到|至){_EXPR}的定积分",
    rf"(?:求|计算)\s*{_EXPR}(?:当|在)\s*[xyzt]\s*(?:趋于|趋近|→)\s*{_EXPR}时?的极限",
]


def explicit_math_only(question: str, resolved_query: str, *, scope_reason="", attachments=False) -> bool:
    if attachments or scope_reason == "requested_textbook_grounded":
        return False
    def complete(value):
        value = str(value).strip().rstrip("。；;？！?!")
        return any(re.fullmatch(pattern, value, re.I) for pattern in _PATTERNS)
    return complete(question) and complete(resolved_query)
