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


@pytest.mark.parametrize('expression,variable,assumptions,expected', [
    ('n*theta/(n+1)', 'theta', {'theta': 'positive'}, 'n/(n + 1)'),
    ('lambda^2+alpha*lambda+beta', 'lambda', {}, 'alpha + 2*lambda'),
    ('θ^2+α*θ+β', 'θ', {'θ': 'positive'}, 'alpha + 2*theta'),
    ('x_1^2+mass2*rate', 'x_1', {}, '2*x_1'),
    ('2theta+3(theta+1)', 'theta', {}, '5'),
])
def test_parameter_names_and_greek_aliases_round_trip(expression, variable, assumptions, expected):
    registry = get_tool_registry()
    result = registry.call('symbolic_math', dict(operation='differentiate', expression=expression,
        variable=variable, assumptions=assumptions), ToolContext())
    assert result.success, result.message
    assert result.data['result']['exact'] == expected
    verification = registry.call('verify_math_result', result.data['verification_request'], ToolContext())
    # The rational expression contains an unconstrained parameter denominator.
    if 'n+1' in expression:
        assert verification.verification['status'] == 'unverified'
    else:
        assert verification.success, verification.to_dict()
        assert verification.data['assumptions'] == result.data['assumptions']


@pytest.mark.parametrize('expression', [
    'theta.__class__', 'lambda: 1', 'alpha[0]', 'beta(x)', 'sin', 'sin(x, y)',
    '__secret', 'x__y', 'x if theta else y', '(lambda x: x)(1)', 'open(1)',
])
def test_symbol_support_does_not_expand_executable_grammar(expression):
    from backend.tools.math_tools import parse_restricted_expression
    with pytest.raises(ValueError):
        parse_restricted_expression(expression)


@pytest.mark.parametrize('args,status', [
    ({'kind': 'equivalence', 'left': 'sqrt(x^2)', 'right': 'x'}, 'unverified'),
    ({'kind': 'equivalence', 'left': 'sqrt(x^2)', 'right': 'x', 'assumptions': {'x': 'nonnegative'}}, 'verified'),
    ({'kind': 'equivalence', 'left': 'sqrt(x^2)', 'right': 'abs(x)', 'assumptions': {'x': 'real'}}, 'verified'),
    ({'kind': 'equivalence', 'left': 'x/x', 'right': '1'}, 'unverified'),
    ({'kind': 'equivalence', 'left': 'x/x', 'right': '1', 'assumptions': {'x': 'nonzero'}}, 'verified'),
    ({'kind': 'equivalence', 'left': '0*log(theta)', 'right': '0'}, 'unverified'),
    ({'kind': 'equivalence', 'left': 'log(theta*beta)', 'right': 'log(theta)+log(beta)',
      'assumptions': {'theta': 'positive', 'beta': 'positive'}}, 'verified'),
    ({'kind': 'equivalence', 'left': '2', 'right': '3'}, 'failed'),
    ({'kind': 'solutions', 'left': 'x/x', 'right': '1', 'candidates': ['0']}, 'unverified'),
    ({'kind': 'solutions', 'left': 'x^2+1', 'right': '0', 'candidates': ['I'], 'assumptions': {'x': 'real'}}, 'unverified'),
    ({'kind': 'solutions', 'left': 'x^2-1', 'right': '0', 'candidates': ['1']}, 'verified'),
    ({'kind': 'solutions', 'left': 'x^2+1', 'right': '0', 'candidates': []}, 'unverified'),
    ({'kind': 'definite_integral', 'original': '1/x', 'lower': '-1', 'upper': '1', 'candidate': '0'}, 'unverified'),
    ({'kind': 'definite_integral', 'original': '1/x', 'lower': '1', 'upper': '2', 'candidate': 'log(2)'}, 'verified'),
    ({'kind': 'definite_integral', 'original': 'x^2', 'lower': '0', 'upper': 'theta', 'candidate': 'theta^3/3'}, 'unverified'),
])
def test_verification_conditions_are_not_erased_by_simplification(args, status):
    result = get_tool_registry().call('verify_math_result', args, ToolContext())
    assert result.verification['status'] == status, result.to_dict()
    assert result.verification['passed'] is (status == 'verified')
    if status != 'error':
        assert result.data == result.verification  # worker preserves non-passed receipts too
        assert result.data['scope']
    if args['kind'] == 'solutions' and status == 'verified':
        assert 'not_solution_set_completeness' in result.data['scope']


def test_real_sqrt_output_and_assumptions_survive_verification_request():
    registry = get_tool_registry()
    result = registry.call('symbolic_math', {'operation': 'simplify', 'expression': 'sqrt(theta^2)',
        'assumptions': {'theta': 'real'}}, ToolContext())
    assert result.data['result']['exact'] == 'Abs(theta)'
    verified = registry.call('verify_math_result', result.data['verification_request'], ToolContext())
    assert verified.success, verified.to_dict()


def test_recorded_statistics_failure_computes_with_given_parameter_conditions():
    registry = get_tool_registry()
    # Exact operation/limits from the 2026-10-13 failed native receipt; the
    # assumptions are explicitly supplied from the original theta>0, n>=1.
    result = registry.call('symbolic_math', {'operation': 'integrate', 'expression': 'n*x^n/theta^n',
        'lower': '0', 'upper': 'theta', 'variable': 'x',
        'assumptions': {'theta': 'positive', 'n': 'positive'}}, ToolContext())
    assert result.success, result.to_dict()
    assert result.data['result']['exact'] == 'n*theta/(n + 1)'
    verification = registry.call('verify_math_result', result.data['verification_request'], ToolContext())
    assert verification.verification['status'] == 'unverified'
    assert any('参数积分' in s for s in verification.verification['limitations'])


def test_integration_bound_cannot_depend_on_integration_variable():
    result = get_tool_registry().call('symbolic_math', {'operation': 'integrate',
        'expression': 'x', 'lower': '0', 'upper': 'x'}, ToolContext())
    assert not result.success


@pytest.mark.parametrize('schema,args', [
    ('MathInput', {'operation': 'solve', 'expression': 'x^2-1', 'lower': '0', 'upper': '2'}),
    ('MathVerifyInput', {'kind': 'solutions', 'left': 'x^2-1', 'right': '0',
                         'candidates': ['-1'], 'lower': '0', 'upper': '2'}),
])
def test_unsupported_solution_intervals_are_rejected_instead_of_ignored(schema, args):
    import backend.tools.math_tools as math_tools
    with pytest.raises(ValueError, match='intervals are not supported'):
        getattr(math_tools, schema).model_validate(args)
