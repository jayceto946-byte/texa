import pytest
from backend.tools.registry import ToolContext, get_tool_registry


@pytest.mark.parametrize("args,exact", [
    ({"operation": "calculate", "expression": "0.1+0.2"}, "3/10"),
    ({"operation": "calculate", "expression": "1e-3"}, "1/1000"),
    ({"operation": "calculate", "expression": "0.12345678901234567890"}, "1234567890123456789/10000000000000000000"),
    ({"operation": "simplify", "expression": "sqrt(x^2)", "assumptions": {"x": "positive"}}, "x"),
    ({"operation": "differentiate", "expression": "x^3"}, "3*x**2"),
    ({"operation": "integrate", "expression": "x^2", "lower": "0", "upper": "1"}, "1/3"),
    ({"operation": "integrate", "expression": "x^2", "lower": 0, "upper": 1}, "1/3"),
    ({"operation": "limit", "expression": "sin(x)/x", "point": "0"}, "1"),
    ({"operation": "limit", "expression": "sin(x)/x", "point": 0}, "1"),
    ({"operation": "solve", "expression": "x^2+1"}, ["-I", "I"]),
])
def test_supported_operations_are_exact_and_canonical(args, exact):
    registry = get_tool_registry()
    result = registry.call("symbolic_math", args, ToolContext())
    assert result.success, result.message
    assert result.data["result"]["exact"] == exact
    registry.runtime_tool("symbolic_math").runtime_output.model_validate(result.data)


@pytest.mark.parametrize("expression", ["__import__('os')", "x.__class__", "[x for x in range(3)]", "x**1000", "1/0"])
def test_unsafe_or_undefined_math_has_structured_error(expression):
    result = get_tool_registry().call("symbolic_math", {"operation": "calculate", "expression": expression}, ToolContext())
    assert not result.success and result.data["error_code"]


def test_stokes_exact_result_already_simplified_and_supports_verification():
    registry = get_tool_registry()
    result = registry.call('symbolic_math', {'operation': 'calculate', 'expression': 'pi*(2/5)*(2/sqrt(5))'}, ToolContext())
    assert result.success
    assert result.data['result']['exact'] == '4*sqrt(5)*pi/25'
    verified = registry.call('verify_math_result', result.data['verification_request'], ToolContext())
    assert verified.success
    assert result.data['result']['numeric'] == pytest.approx(1.1239703569665163)
