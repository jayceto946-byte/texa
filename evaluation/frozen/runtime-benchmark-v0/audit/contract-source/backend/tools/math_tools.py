"""Restricted deterministic mathematics tools for Texa.

The parser intentionally accepts a small expression language instead of
passing model-produced text to Python, ``eval`` or SymPy's general parser.
"""
from __future__ import annotations

import ast
import math
import re
from typing import Any

import sympy as sp

from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec


_SYMBOLS = {name: sp.Symbol(name) for name in ("x", "y", "z", "t", "n", "a", "b", "c")}
_CONSTANTS = {"pi": sp.pi, "e": sp.E, "E": sp.E}
_FUNCTIONS = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
}
_MAX_EXPRESSION_CHARS = 300
_MAX_AST_NODES = 120


class RestrictedMathError(ValueError):
    pass


def _normalize_expression(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise RestrictedMathError("expression is required")
    if len(text) > _MAX_EXPRESSION_CHARS:
        raise RestrictedMathError("expression is too long")
    text = (
        text.replace("^", "**")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("π", "pi")
        .replace("（", "(")
        .replace("）", ")")
    )
    # Accept ordinary textbook forms such as 2x and 3(x+1), while keeping the
    # grammar explicit and bounded.
    text = re.sub(r"(?<=\d)(?=[a-zA-Z(])", "*", text)
    text = re.sub(r"(?<=[a-zA-Z)])(?=\d)", "*", text)
    text = re.sub(r"(?<=\))(?=[a-zA-Z(])", "*", text)
    return text


def _expression_from_ast(node: ast.AST) -> sp.Expr:
    if isinstance(node, ast.Expression):
        return _expression_from_ast(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise RestrictedMathError("only numeric constants are allowed")
        if not math.isfinite(float(node.value)) or abs(float(node.value)) > 1e12:
            raise RestrictedMathError("numeric constant is out of range")
        return sp.Integer(node.value) if isinstance(node.value, int) else sp.Float(str(node.value))
    if isinstance(node, ast.Name):
        if node.id in _SYMBOLS:
            return _SYMBOLS[node.id]
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise RestrictedMathError(f"unsupported symbol: {node.id}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _expression_from_ast(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _expression_from_ast(node.left)
        right = _expression_from_ast(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            if right.is_number and (not right.is_real or abs(float(right)) > 20):
                raise RestrictedMathError("exponent is out of range")
            return left ** right
        raise RestrictedMathError("unsupported operator")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _FUNCTIONS.get(node.func.id)
        if function is None or node.keywords or not 1 <= len(node.args) <= 2:
            raise RestrictedMathError("unsupported function call")
        return function(*[_expression_from_ast(item) for item in node.args])
    raise RestrictedMathError("unsupported expression syntax")


def parse_restricted_expression(value: Any) -> sp.Expr:
    text = _normalize_expression(value)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise RestrictedMathError("expression syntax is invalid") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise RestrictedMathError("expression is too complex")
    return _expression_from_ast(tree)


def _variable(value: Any) -> sp.Symbol:
    name = str(value or "x").strip()
    if name not in _SYMBOLS:
        raise RestrictedMathError(f"unsupported variable: {name}")
    return _SYMBOLS[name]


def _serialized_result(value: Any) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        return {
            "exact": [str(item) for item in values],
            "latex": [sp.latex(item) for item in values],
            "numeric": [float(sp.N(item)) if not getattr(item, "free_symbols", set()) else None for item in values],
        }
    expression = sp.simplify(value)
    numeric = None
    if not expression.free_symbols and expression.is_finite is not False:
        try:
            numeric = float(sp.N(expression, 15))
        except (TypeError, ValueError, OverflowError):
            numeric = None
    return {"exact": str(expression), "latex": sp.latex(expression), "numeric": numeric}


def symbolic_math(_context: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        operation = str(args.get("operation") or "calculate").strip().lower()
        expression_text = str(args.get("expression") or "")
        expression = parse_restricted_expression(expression_text)
        variable = _variable(args.get("variable"))
        verification_request: dict[str, Any]

        if operation == "calculate":
            if expression.free_symbols:
                return ToolResult(False, message="calculate requires a closed numeric expression")
            result = sp.simplify(expression)
            verification_request = {"kind": "equivalence", "left": expression_text, "right": str(result)}
        elif operation == "simplify":
            result = sp.simplify(expression)
            verification_request = {"kind": "equivalence", "left": expression_text, "right": str(result)}
        elif operation == "differentiate":
            result = sp.diff(expression, variable)
            verification_request = {
                "kind": "derivative", "original": expression_text,
                "candidate": str(result), "variable": str(variable),
            }
        elif operation == "integrate":
            lower = args.get("lower")
            upper = args.get("upper")
            if (lower is None) != (upper is None):
                return ToolResult(False, message="both lower and upper bounds are required")
            if lower is None:
                result = sp.integrate(expression, variable)
                verification_request = {
                    "kind": "antiderivative", "original": expression_text,
                    "candidate": str(result), "variable": str(variable),
                }
            else:
                lower_expr = parse_restricted_expression(lower)
                upper_expr = parse_restricted_expression(upper)
                if lower_expr.free_symbols or upper_expr.free_symbols:
                    return ToolResult(False, message="integration bounds must be closed expressions")
                result = sp.integrate(expression, (variable, lower_expr, upper_expr))
                verification_request = {
                    "kind": "definite_integral", "original": expression_text,
                    "candidate": str(result), "variable": str(variable),
                    "lower": str(lower_expr), "upper": str(upper_expr),
                }
        elif operation == "solve":
            right_text = str(args.get("right") or "0")
            right = parse_restricted_expression(right_text)
            result = sp.solve(sp.Eq(expression, right), variable)
            verification_request = {
                "kind": "solutions", "left": expression_text, "right": right_text,
                "candidates": [str(item) for item in result], "variable": str(variable),
            }
        else:
            return ToolResult(False, message=f"unsupported operation: {operation}")

        payload = {
            "operation": operation,
            "expression": expression_text,
            "variable": str(variable),
            "result": _serialized_result(result),
            "verification_request": verification_request,
        }
        warnings = [] if result is not sp.Integral else ["symbolic result remained unevaluated"]
        return ToolResult(True, data=payload, message="确定性计算完成", warnings=warnings)
    except (RestrictedMathError, TypeError, ValueError, ZeroDivisionError) as exc:
        return ToolResult(False, message=str(exc))


def verify_math_result(_context: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        kind = str(args.get("kind") or "equivalence")
        variable = _variable(args.get("variable"))
        residuals: list[sp.Expr] = []
        if kind == "equivalence":
            residuals = [sp.simplify(
                parse_restricted_expression(args.get("left"))
                - parse_restricted_expression(args.get("right"))
            )]
        elif kind == "derivative":
            residuals = [sp.simplify(
                sp.diff(parse_restricted_expression(args.get("original")), variable)
                - parse_restricted_expression(args.get("candidate"))
            )]
        elif kind == "antiderivative":
            residuals = [sp.simplify(
                sp.diff(parse_restricted_expression(args.get("candidate")), variable)
                - parse_restricted_expression(args.get("original"))
            )]
        elif kind == "definite_integral":
            lower = parse_restricted_expression(args.get("lower"))
            upper = parse_restricted_expression(args.get("upper"))
            expected = sp.integrate(
                parse_restricted_expression(args.get("original")),
                (variable, lower, upper),
            )
            residuals = [sp.simplify(expected - parse_restricted_expression(args.get("candidate")))]
        elif kind == "solutions":
            left = parse_restricted_expression(args.get("left"))
            right = parse_restricted_expression(args.get("right"))
            candidates = list(args.get("candidates") or [])[:12]
            if not candidates:
                residuals = [sp.Integer(1)]
            else:
                residuals = [sp.simplify((left - right).subs(variable, parse_restricted_expression(item))) for item in candidates]
        else:
            return ToolResult(False, message=f"unsupported verification kind: {kind}")

        passed = bool(residuals) and all(item == 0 for item in residuals)
        verification = {
            "status": "verified" if passed else "failed",
            "method": kind,
            "passed": passed,
            "residuals": [str(item) for item in residuals],
        }
        return ToolResult(passed, data=verification, message="结果校验完成", verification=verification)
    except (RestrictedMathError, TypeError, ValueError, ZeroDivisionError) as exc:
        return ToolResult(False, message=str(exc), verification={"status": "error", "passed": False})


def register_math_tools(registry: ToolRegistry) -> None:
    common_result = {
        "type": "object",
        "required": ["operation", "result"],
        "properties": {"operation": {"type": "string"}, "result": {"type": "object"}},
    }
    registry.register(ToolSpec(
        name="symbolic_math",
        description="Compute a restricted numeric or symbolic expression without executing arbitrary code.",
        parameters={
            "type": "object",
            "required": ["operation", "expression"],
            "properties": {
                "operation": {"enum": ["calculate", "simplify", "differentiate", "integrate", "solve"]},
                "expression": {"type": "string", "maxLength": _MAX_EXPRESSION_CHARS},
                "variable": {"enum": list(_SYMBOLS)},
                "right": {"type": "string"},
                "lower": {"type": ["string", "number"]},
                "upper": {"type": ["string", "number"]},
            },
        },
        result_schema=common_result,
        capabilities=("numeric_calculation", "symbolic_algebra", "calculus", "equation_solving"),
        read_only=True,
        risk_level="low",
        timeout_seconds=5.0,
        version="1",
        provenance="sympy-1.14/restricted-ast",
        handler=symbolic_math,
    ))
    registry.register(ToolSpec(
        name="verify_math_result",
        description="Verify equivalence, derivatives, antiderivatives or equation solutions by deterministic substitution.",
        parameters={
            "type": "object",
            "required": ["kind"],
            "properties": {
                "kind": {"enum": ["equivalence", "derivative", "antiderivative", "definite_integral", "solutions"]},
                "left": {"type": "string"}, "right": {"type": "string"},
                "original": {"type": "string"}, "candidate": {"type": "string"},
                "candidates": {"type": "array", "maxItems": 12},
                "lower": {"type": ["string", "number"]}, "upper": {"type": ["string", "number"]},
                "variable": {"enum": list(_SYMBOLS)},
            },
        },
        result_schema={"type": "object", "required": ["status", "passed", "residuals"]},
        capabilities=("answer_verification", "symbolic_validation"),
        read_only=True,
        risk_level="low",
        timeout_seconds=5.0,
        version="1",
        provenance="sympy-1.14/restricted-ast",
        handler=verify_math_result,
    ))
