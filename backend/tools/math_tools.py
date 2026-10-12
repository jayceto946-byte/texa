"""Restricted deterministic mathematics tools for Texa.

The parser intentionally accepts a small expression language instead of
passing model-produced text to Python, ``eval`` or SymPy's general parser.
"""
from __future__ import annotations

import ast
import math
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import contextvars

import sympy as sp

from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec


_SYMBOLS = {name: sp.Symbol(name) for name in ("x", "y", "z", "t", "n", "a", "b", "c")}
_CONSTANTS = {"pi": sp.pi, "e": sp.E, "E": sp.E, "I": sp.I, "oo": sp.oo}
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
_ASSUMPTIONS = contextvars.ContextVar("math_assumptions", default={})


class MathInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: Literal["calculate", "simplify", "differentiate", "integrate", "solve", "limit"]
    expression: str = Field(min_length=1, max_length=300)
    variable: Literal["x", "y", "z", "t", "n", "a", "b", "c"] = "x"
    right: str = Field(default="0", max_length=300)
    lower: str | int | float | None = None
    upper: str | int | float | None = None
    point: str | int | float | None = None
    direction: Literal["+", "-", "+-"] = "+-"
    assumptions: dict[str, Literal["real", "positive", "integer", "nonnegative"]] = Field(default_factory=dict, max_length=8)

    @model_validator(mode="after")
    def bounded_assumptions(self):
        if any(name not in _SYMBOLS for name in self.assumptions):
            raise ValueError("unsupported assumption symbol")
        if any(isinstance(v, str) and len(v) > 300 for v in (self.lower, self.upper, self.point)):
            raise ValueError("bound exceeds expression budget")
        return self


class MathOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: str
    expression: str
    variable: str
    assumptions: dict[str, str]
    result: dict[str, Any]
    verification_request: dict[str, Any]
    status: Literal["computed", "unevaluated"]


class MathVerifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["equivalence", "derivative", "antiderivative", "definite_integral", "solutions", "limit"]
    variable: Literal["x", "y", "z", "t", "n", "a", "b", "c"] = "x"
    left: str = Field(default="", max_length=300)
    right: str = Field(default="", max_length=300)
    original: str = Field(default="", max_length=300)
    candidate: str = Field(default="", max_length=300)
    candidates: list[str] = Field(default_factory=list, max_length=12)
    lower: str | int | float | None = None
    upper: str | int | float | None = None
    point: str | int | float | None = None
    direction: Literal["+", "-", "+-"] = "+-"
    assumptions: dict[str, Literal["real", "positive", "integer", "nonnegative"]] = Field(default_factory=dict)


class MathVerifyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: str
    method: str
    passed: bool
    residuals: list[str]


class RestrictedMathError(ValueError):
    pass


def _normalize_expression(value: Any) -> str:
    text = ("" if value is None else str(value)).strip()
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
    text = re.sub(r"(?<=\d)(?=[a-zA-Z(])(?![eE][+-]?\d)", "*", text)
    text = re.sub(r"(?<=[a-df-zA-DF-Z)])(?=\d)", "*", text)
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
        literal = getattr(node, "_math_literal", str(node.value)).replace("_", "")
        if not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", literal):
            raise RestrictedMathError("unsupported numeric literal")
        scale = re.search(r"[eE]([+-]?\d+)$", literal)
        if scale and abs(int(scale.group(1))) > 300:
            raise RestrictedMathError("numeric scale is out of range")
        return sp.Rational(literal)
    if isinstance(node, ast.Name):
        if node.id in _SYMBOLS:
            assumption = _ASSUMPTIONS.get().get(node.id)
            return sp.Symbol(node.id, **{assumption: True}) if assumption else _SYMBOLS[node.id]
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
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            node._math_literal = ast.get_source_segment(text, node)
    return _expression_from_ast(tree)


def _variable(value: Any) -> sp.Symbol:
    name = str(value or "x").strip()
    if name not in _SYMBOLS:
        raise RestrictedMathError(f"unsupported variable: {name}")
    assumption = _ASSUMPTIONS.get().get(name)
    return sp.Symbol(name, **{assumption: True}) if assumption else _SYMBOLS[name]


def _serialized_result(value: Any) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        return {
            "exact": [str(item) for item in values],
            "latex": [sp.latex(item) for item in values],
            "numeric": [_serialized_result(item)["numeric"] for item in values],
        }
    expression = sp.simplify(value)
    numeric = None
    if not expression.free_symbols and expression.is_finite is not False:
        try:
            numeric = float(sp.N(expression, 15))
            if not math.isfinite(numeric) or (numeric == 0 and expression != 0):
                numeric = None
        except (TypeError, ValueError, OverflowError):
            numeric = None
    return {"exact": str(expression), "latex": sp.latex(expression), "numeric": numeric}


def _symbolic_math(_context: ToolContext, args: dict[str, Any]) -> ToolResult:
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
        elif operation == "limit":
            if args.get("point") is None:
                raise RestrictedMathError("limit point is required")
            point = sp.oo if args["point"] in ("oo", "inf") else -sp.oo if args["point"] == "-oo" else parse_restricted_expression(args["point"])
            if point.free_symbols:
                raise RestrictedMathError("limit point must be closed")
            result = sp.limit(expression, variable, point, dir=args.get("direction", "+-"))
            verification_request = {"kind": "limit", "original": expression_text,
                "candidate": str(result), "variable": str(variable), "point": args["point"],
                "direction": args.get("direction", "+-")}
        else:
            return ToolResult(False, message=f"unsupported operation: {operation}")

        payload = {
            "operation": operation,
            "expression": expression_text,
            "variable": str(variable),
            "result": _serialized_result(result),
            "verification_request": verification_request,
            "assumptions": dict(_ASSUMPTIONS.get()),
            "status": "unevaluated" if isinstance(result, sp.Expr) and result.has(sp.Integral, sp.Limit) else "computed",
        }
        verification_request["assumptions"] = dict(_ASSUMPTIONS.get())
        if isinstance(result, sp.Expr) and result.has(sp.nan, sp.zoo):
            raise RestrictedMathError("result is undefined")
        warnings = ["symbolic result remained unevaluated"] if payload["status"] == "unevaluated" else []
        return ToolResult(True, data=payload, message="确定性计算完成", warnings=warnings)
    except (RestrictedMathError, TypeError, ValueError, ZeroDivisionError) as exc:
        return ToolResult(False, message=str(exc))


def _verify_math_result(_context: ToolContext, args: dict[str, Any]) -> ToolResult:
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
        elif kind == "limit":
            point = sp.oo if args["point"] in ("oo", "inf") else -sp.oo if args["point"] == "-oo" else parse_restricted_expression(args["point"])
            residuals = [sp.simplify(sp.limit(parse_restricted_expression(args["original"]), variable,
                point, dir=args.get("direction", "+-")) - parse_restricted_expression(args["candidate"]))]
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


def symbolic_math(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    from backend.tools.math_worker import execute_math
    return execute_math("symbolic_math", args, context)


def verify_math_result(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    from backend.tools.math_worker import execute_math
    return execute_math("verify_math_result", args, context)


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
        runtime_input=MathInput, runtime_output=MathOutput, execution_mode="isolated",
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
        runtime_input=MathVerifyInput, runtime_output=MathVerifyOutput, execution_mode="isolated",
    ))
    for name in ("symbolic_math", "verify_math_result"):
        registry.get(name).parameters = registry.get(name).runtime_input.model_json_schema()
