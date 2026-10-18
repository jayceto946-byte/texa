"""Restricted deterministic mathematics tools for Texa.

The parser intentionally accepts a small expression language instead of
passing model-produced text to Python, ``eval`` or SymPy's general parser.
"""
from __future__ import annotations

import ast
import keyword
import io
import tokenize
import math
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import contextvars

import sympy as sp

from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec
from backend.tools.math_step_contract import StepBatch, StepReceipt


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
    "Abs": sp.Abs,  # SymPy's own serialized spelling must round-trip.
}
_MAX_EXPRESSION_CHARS = 300
_MAX_AST_NODES = 120
_ASSUMPTIONS = contextvars.ContextVar("math_assumptions", default={})
_GREEK = dict(zip("αβγδεζηθικλμνξορστυφχψω", (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron rho sigma tau upsilon phi chi psi omega".split())))
Assumption = Literal["real", "positive", "integer", "nonnegative", "negative", "nonpositive", "nonzero"]


def _symbol_name(value: str) -> str:
    name = _GREEK.get(value, value)
    if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", name) or "__" in name
            or (keyword.iskeyword(name) and name != "lambda") or name in _FUNCTIONS or name in _CONSTANTS):
        raise ValueError("expected a mathematical symbol name (not a function, constant or code)")
    return name


class MathConditions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    variable: str = Field(default="x", max_length=32, description="Mathematical identifier, e.g. x, theta, lambda, x_1; Greek letter aliases accepted.")
    assumptions: dict[str, Assumption] = Field(default_factory=dict, max_length=16,
        description="Explicit SymPy predicates only (nonzero means real and nonzero; integer implies real). Omitted symbols are complex; arbitrary inequalities/intervals are not supported. Do not invent conditions.")

    @field_validator("variable")
    @classmethod
    def valid_variable(cls, value):
        return _symbol_name(value)

    @field_validator("assumptions")
    @classmethod
    def valid_assumptions(cls, value):
        normalized = {_symbol_name(name): assumption for name, assumption in value.items()}
        if len(normalized) != len(value):
            raise ValueError("duplicate symbol aliases in assumptions")
        return normalized

    @model_validator(mode="after")
    def bounded_conditions(self):
        if any(isinstance(v, str) and len(v) > 300 for v in
               (getattr(self, key, None) for key in ("lower", "upper", "point"))):
            raise ValueError("bound exceeds expression budget")
        return self


class MathInput(MathConditions):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: Literal["calculate", "simplify", "differentiate", "integrate", "solve", "limit"]
    expression: str = Field(min_length=1, max_length=300)
    right: str = Field(default="0", max_length=300)
    lower: str | int | float | None = None
    upper: str | int | float | None = None
    point: str | int | float | None = None
    direction: Literal["+", "-", "+-"] = "+-"

    @model_validator(mode="after")
    def operation_conditions(self):
        if self.operation != "integrate" and (self.lower is not None or self.upper is not None):
            raise ValueError("bounds are supported only for integration; solve intervals are not supported")
        if self.operation != "limit" and self.point is not None:
            raise ValueError("point is supported only for limits")
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
    limitations: list[str] = Field(default_factory=list)


class MathVerifyInput(MathConditions):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["equivalence", "derivative", "antiderivative", "definite_integral", "solutions", "limit", "steps"]
    context: StepBatch | None = None
    left: str = Field(default="", max_length=300)
    right: str = Field(default="", max_length=300)
    original: str = Field(default="", max_length=300)
    candidate: str = Field(default="", max_length=300)
    candidates: list[str] = Field(default_factory=list, max_length=12)
    lower: str | int | float | None = None
    upper: str | int | float | None = None
    point: str | int | float | None = None
    direction: Literal["+", "-", "+-"] = "+-"

    @model_validator(mode="after")
    def verification_conditions(self):
        if (self.kind == "steps") != (self.context is not None):
            raise ValueError("steps require a context batch; context is exclusive to steps")
        if self.kind == "steps" and any((self.left, self.right, self.original, self.candidate, self.candidates)):
            raise ValueError("steps use only context statements")
        if self.kind != "definite_integral" and (self.lower is not None or self.upper is not None):
            raise ValueError("bounds are supported only for definite integrals; solution intervals are not supported")
        if self.kind != "limit" and self.point is not None:
            raise ValueError("point is supported only for limits")
        return self


class MathVerifyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["verified", "failed", "unverified"]
    method: str
    passed: bool
    residuals: list[str]
    assumptions: dict[str, str] = Field(default_factory=dict)
    scope: str = ""
    limitations: list[str] = Field(default_factory=list)
    verdict: Literal["valid", "invalid", "unknown"] | None = None
    execution_status: Literal["completed"] | None = None
    source_ref: str = ""
    source_kind: str = ""
    steps: list[StepReceipt] = Field(default_factory=list)


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
    # Python reserves lambda; the Greek alias is a Name node, never a lambda
    # expression. Only bare symbol names are canonicalized by _symbol_name.
    text = re.sub(r"\blambda\b", "λ", text)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        normalized = []
        previous = None
        for token in tokens:
            if previous and ((previous.type == tokenize.NUMBER and (token.type == tokenize.NAME or token.string == "("))
                    or (previous.string == ")" and (token.type in {tokenize.NAME, tokenize.NUMBER} or token.string == "("))):
                normalized.append((tokenize.OP, "*"))
            normalized.append((token.type, token.string))
            previous = token
        return tokenize.untokenize(normalized)
    except (tokenize.TokenError, IndentationError) as exc:
        raise RestrictedMathError("expression syntax is invalid") from exc


def _expression_from_ast(node: ast.AST, *, evaluate=True) -> sp.Expr:
    if isinstance(node, ast.Expression):
        return _expression_from_ast(node.body, evaluate=evaluate)
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
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        return _variable(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _expression_from_ast(node.operand, evaluate=evaluate)
        return value if isinstance(node.op, ast.UAdd) else sp.Mul(-1, value, evaluate=evaluate)
    if isinstance(node, ast.BinOp):
        left = _expression_from_ast(node.left, evaluate=evaluate)
        right = _expression_from_ast(node.right, evaluate=evaluate)
        if isinstance(node.op, ast.Add):
            return sp.Add(left, right, evaluate=evaluate)
        if isinstance(node.op, ast.Sub):
            return sp.Add(left, sp.Mul(-1, right, evaluate=evaluate), evaluate=evaluate)
        if isinstance(node.op, ast.Mult):
            return sp.Mul(left, right, evaluate=evaluate)
        if isinstance(node.op, ast.Div):
            return sp.Mul(left, sp.Pow(right, -1, evaluate=evaluate), evaluate=evaluate)
        if isinstance(node.op, ast.Pow):
            if right.is_number and (not right.is_real or abs(float(right)) > 20):
                raise RestrictedMathError("exponent is out of range")
            return sp.Pow(left, right, evaluate=evaluate)
        raise RestrictedMathError("unsupported operator")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _FUNCTIONS.get(node.func.id)
        if function is None or node.keywords or len(node.args) not in ((1, 2) if node.func.id in {"log", "ln"} else (1,)):
            raise RestrictedMathError("unsupported function call")
        return function(*[_expression_from_ast(item, evaluate=evaluate) for item in node.args], evaluate=evaluate)
    raise RestrictedMathError("unsupported expression syntax")


def parse_restricted_expression(value: Any, *, evaluate=True) -> sp.Expr:
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
    expression = _expression_from_ast(tree, evaluate=evaluate)
    if len(expression.free_symbols) > 16:
        raise RestrictedMathError("too many symbols")
    return expression


def _variable(value: Any) -> sp.Symbol:
    name = _symbol_name(str(value or "x").strip())
    assumption = _ASSUMPTIONS.get().get(name)
    return sp.Symbol(name, **{assumption: True}) if assumption else sp.Symbol(name)


def _serialized_result(value: Any, *, simplified: bool = False, raw: Any = None) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        values = list(value)
        return {
            "raw": [str(item) for item in values],
            "exact": [str(item) for item in values],
            "latex": [sp.latex(item) for item in values],
            "numeric": [_serialized_result(item)["numeric"] for item in values],
        }
    expression = value if simplified else sp.simplify(value)
    numeric = None
    if not expression.free_symbols and expression.is_finite is not False:
        try:
            numeric = float(sp.N(expression, 15))
            if not math.isfinite(numeric) or (numeric == 0 and expression != 0):
                numeric = None
        except (TypeError, ValueError, OverflowError):
            numeric = None
    return {"raw": str(value if raw is None else raw), "exact": str(expression), "latex": sp.latex(expression), "numeric": numeric}


def _domain_limitations(expression: sp.Expr) -> list[str]:
    """Conservative sufficient conditions, not a general domain/proof solver.

    Called on an unevaluated AST so x/x and 0*log(x) keep their restrictions.
    A failed condition probe means unknown, not that the expression is invalid.
    """
    limitations = []
    for node in sp.preorder_traversal(expression):
        if node.has(sp.nan, sp.zoo, sp.Integral, sp.Limit, sp.Derivative, sp.Piecewise):
            limitations.append("存在未求值、条件分支或未定义表达式，不能确认结论")
        if not node.free_symbols:
            if node.is_finite is False:
                limitations.append("表达式不具有限值")
            continue
        if isinstance(node, sp.Pow):
            base, exponent = map(sp.simplify, node.args)
            if exponent.is_nonnegative is not True and base.is_nonzero is not True:
                limitations.append(f"需要确认 {base} 非零及幂的定义域")
            if exponent.is_integer is not True and base.is_positive is not True:
                if not (exponent.is_rational and exponent.is_positive and base.is_nonnegative is True):
                    limitations.append(f"需要确认 {node} 的幂/根式分支和定义域")
        elif node.func == sp.log and sp.simplify(node.args[0]).is_positive is not True:
            limitations.append(f"需要确认 {node} 的对数定义域/分支")
        elif node.func == sp.tan and sp.cos(node.args[0]).is_nonzero is not True:
            limitations.append(f"需要确认 {node} 无极点")
        elif node.func in {sp.asin, sp.acos, sp.atan}:
            limitations.append(f"尚未核验 {node} 的反三角函数定义域/分支")
    return list(dict.fromkeys(limitations))


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
                if any(variable in bound.free_symbols or bound.is_extended_real is False for bound in (lower_expr, upper_expr)):
                    return ToolResult(False, message="integration bounds must be real and independent of the integration variable")
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
            "result": _serialized_result(result, simplified=operation in {"calculate", "simplify"},
                                         raw=expression if operation in {"calculate", "simplify"} else result),
            "verification_request": verification_request,
            "assumptions": dict(_ASSUMPTIONS.get()),
            "status": "unevaluated" if isinstance(result, sp.Expr) and result.has(sp.Integral, sp.Limit) else "computed",
            "limitations": _domain_limitations(parse_restricted_expression(expression_text, evaluate=False)),
        }
        verification_request["assumptions"] = dict(_ASSUMPTIONS.get())
        if operation == "integrate" and args.get("lower") is not None:
            if any(parse_restricted_expression(args[key]).is_extended_real is not True for key in ("lower", "upper")):
                payload["limitations"].append("积分限的实数条件尚未确认")
        for value in result if isinstance(result, (list, tuple)) else [result]:
            payload["limitations"].extend(_domain_limitations(value))
        payload["limitations"] = list(dict.fromkeys(payload["limitations"]))
        if isinstance(result, sp.Expr) and result.has(sp.nan, sp.zoo):
            raise RestrictedMathError("result is undefined")
        warnings = ["symbolic result remained unevaluated"] if payload["status"] == "unevaluated" else []
        if operation == "solve":
            warnings.append("返回候选解；代入校验不证明解集完整性或全部定义域条件")
        warnings.extend(payload["limitations"])
        warnings.append("计算结果只覆盖本次输入的运算；不验证建模、未输入的条件或自然语言推导")
        return ToolResult(True, data=payload, message="确定性计算完成", warnings=warnings)
    except (RestrictedMathError, TypeError, ValueError, ZeroDivisionError) as exc:
        return ToolResult(False, message=str(exc))


def _verify_math_result(_context: ToolContext, args: dict[str, Any]) -> ToolResult:
    try:
        kind = str(args.get("kind") or "equivalence")
        variable = _variable(args.get("variable"))
        residuals: list[sp.Expr] = []
        checked = []
        limitations = []
        scope = "input_expressions_under_explicit_assumptions"

        def read(key):
            value = parse_restricted_expression(args.get(key), evaluate=False)
            checked.append(value)
            return value

        if kind == "equivalence":
            residuals = [sp.simplify(read("left") - read("right"))]
        elif kind == "derivative":
            residuals = [sp.simplify(sp.diff(read("original"), variable) - read("candidate"))]
            scope = "local_derivative_identity_not_global_differentiability"
        elif kind == "antiderivative":
            residuals = [sp.simplify(sp.diff(read("candidate"), variable) - read("original"))]
            scope = "local_antiderivative_identity_not_boundary_or_convergence_proof"
        elif kind == "definite_integral":
            lower = parse_restricted_expression(args.get("lower"))
            upper = parse_restricted_expression(args.get("upper"))
            if any(variable in bound.free_symbols or bound.is_extended_real is False for bound in (lower, upper)):
                raise RestrictedMathError("integration bounds must be real and independent of the integration variable")
            if any(bound.is_extended_real is not True for bound in (lower, upper)):
                limitations.append("积分限的实数条件尚未确认")
            original = parse_restricted_expression(args.get("original"), evaluate=False)
            expected = sp.integrate(original, (variable, lower, upper))
            residuals = [sp.simplify(expected - read("candidate"))]
            checked.append(expected)
            scope = "specified_definite_integral_only"
            # A finite SymPy value alone is not a convergence certificate. Use
            # its domain utility for the bounded, parameter-free regular case.
            if (original.free_symbols | lower.free_symbols | upper.free_symbols) - {variable}:
                limitations.append("含参数积分的收敛条件尚未确认")
            else:
                try:
                    domain = sp.calculus.util.continuous_domain(original, variable, sp.S.Reals)
                    interval = sp.Interval(sp.Min(lower, upper), sp.Max(lower, upper))
                    if interval.is_subset(domain) is not True:
                        limitations.append("积分区间含奇点或端点条件；未确认收敛性")
                except (NotImplementedError, ValueError, TypeError):
                    limitations.append("未确认积分区间上的定义域和收敛性")
        elif kind == "solutions":
            left = parse_restricted_expression(args.get("left"), evaluate=False)
            right = parse_restricted_expression(args.get("right"), evaluate=False)
            candidates = list(args.get("candidates") or [])
            scope = "candidate_substitution_only_not_solution_set_completeness"
            if not candidates:
                limitations.append("空候选集不能用代入法证明无解")
            else:
                for item in candidates:
                    candidate = parse_restricted_expression(item, evaluate=False)
                    checked.extend([candidate, left.subs(variable, candidate), right.subs(variable, candidate)])
                    assumption = _ASSUMPTIONS.get().get(str(variable))
                    if assumption and getattr(sp.simplify(candidate), "is_" + assumption) is not True:
                        limitations.append("候选解尚未确认满足变量假设")
                    residuals.append(sp.simplify(checked[-2] - checked[-1]))
        elif kind == "limit":
            point = sp.oo if args["point"] in ("oo", "inf") else -sp.oo if args["point"] == "-oo" else parse_restricted_expression(args["point"])
            if point.free_symbols:
                raise RestrictedMathError("limit point must be closed")
            expected = sp.limit(parse_restricted_expression(args["original"], evaluate=False), variable,
                point, dir=args.get("direction", "+-"))
            checked.append(expected)
            residuals = [sp.simplify(expected - read("candidate"))]
            scope = "specified_limit_only_not_value_at_limit_point"
        else:
            return ToolResult(False, message=f"unsupported verification kind: {kind}")

        for value in checked:
            limitations.extend(_domain_limitations(value))
        if any(item.has(sp.nan, sp.zoo, sp.oo, -sp.oo, sp.Integral, sp.Limit, sp.Derivative, sp.Piecewise) for item in residuals):
            limitations.append("残差未求值或未定义")
        limitations = list(dict.fromkeys(limitations))
        passed = bool(residuals) and all(item == 0 for item in residuals) and not limitations
        disproved = any(item.is_zero is False for item in residuals) and not limitations
        if not passed and not disproved and not limitations:
            limitations.append("在所给假设下无法确认残差为零；需补充条件或另行核验")
        verification = {
            "status": "verified" if passed else "failed" if disproved else "unverified",
            "method": kind,
            "passed": passed,
            "residuals": [str(item) for item in residuals],
            "assumptions": dict(_ASSUMPTIONS.get()),
            "scope": scope,
            "limitations": limitations,
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
        description=("Compute a restricted numeric or symbolic expression without executing arbitrary code. "
            "Returns raw operation result, already simplified exact form, LaTeX and numeric approximation. "
            "Do not call simplify again just to rewrite the returned exact value; use it directly. "
            "Symbols are bounded mathematical identifiers (theta, lambda, alpha, beta, x_1, etc.); Greek aliases accepted. "
            "Omitted assumptions mean complex symbols. Supply given sign/real/integer conditions explicitly; "
            "arbitrary parameter inequalities and solve intervals are not supported. "
            "Allowed functions: sin,cos,tan,asin,acos,atan,exp,log,ln,sqrt,abs. "
            "Computed is not verified. Results cover only the input operation, not modelling or teaching derivations. "
            "Use further calls when needed for a new calculation or verification."),
        parameters={
            "type": "object",
            "required": ["operation", "expression"],
            "properties": {
                "operation": {"enum": ["calculate", "simplify", "differentiate", "integrate", "solve"]},
                "expression": {"type": "string", "maxLength": _MAX_EXPRESSION_CHARS},
                "variable": {"type": "string"},
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
        version="2",
        provenance="sympy-1.14/restricted-ast",
        handler=symbolic_math,
        runtime_input=MathInput, runtime_output=MathOutput, execution_mode="isolated",
    ))
    registry.register(ToolSpec(
        name="verify_math_result",
        description=("Verify only supplied expressions under explicit assumptions; unresolved domain/branch conditions return unverified. "
            "Derivative/antiderivative checks are local identities; definite integrals require real bounds independent of the variable. "
            "Parametric integral convergence can remain unverified even with assumptions. "
            "Solutions are substitution checks only, never a proof of complete solution sets. "
            "Use kind=steps for up to four dependent real algebra checks bound to the Runtime source_ref. "
            "Specify identity, implication, equation_equivalence, candidate_solution or solution_set. "
            "Only a leading user-authored <math-context> JSON block supplies trusted conditions; "
            "without it return unknown. Do not add assumptions or claim prior verification. "
            "No check certifies modelling, omitted conditions or natural-language derivations."),
        parameters={
            "type": "object",
            "required": ["kind"],
            "properties": {
                "kind": {"enum": ["equivalence", "derivative", "antiderivative", "definite_integral", "solutions"]},
                "left": {"type": "string"}, "right": {"type": "string"},
                "original": {"type": "string"}, "candidate": {"type": "string"},
                "candidates": {"type": "array", "maxItems": 12},
                "lower": {"type": ["string", "number"]}, "upper": {"type": ["string", "number"]},
                "variable": {"type": "string"},
            },
        },
        result_schema={"type": "object", "required": ["status", "passed", "residuals"]},
        capabilities=("answer_verification", "symbolic_validation"),
        read_only=True,
        risk_level="low",
        timeout_seconds=5.0,
        version="3",
        provenance="sympy-1.14/restricted-ast",
        handler=verify_math_result,
        runtime_input=MathVerifyInput, runtime_output=MathVerifyOutput, execution_mode="isolated",
    ))
    for name in ("symbolic_math", "verify_math_result"):
        registry.get(name).parameters = registry.get(name).runtime_input.model_json_schema()
