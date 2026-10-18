"""Exact counterexamples and authority boundaries for P1-B (no paid model)."""
import json
import pytest
from backend.tools.math_step_contract import freeze_problem
from backend.tools.math_tools import MathVerifyOutput, verify_math_result
from backend.tools.registry import ToolContext


def question(left, right=None, *, domain='real', conditions=()):
    problem = {'variable': 'x', 'domain': domain, 'conditions': list(conditions), 'premise': {'left': left, 'right': right}}
    return '<math-context>\n' + json.dumps(problem) + '\n</math-context>\n核验关键步骤并解释。'


def step(left, after=None, *, right=None, after_right=None, relation='identity', candidates=(), identity='s1', deps=()):
    return {'id': identity, 'depends_on': list(deps), 'relation': relation,
        'before': {'left': left, 'right': right},
        'after': {'left': after, 'right': after_right} if after is not None else None,
        'candidates': list(candidates)}


def check(source, steps, **extra):
    authority = freeze_problem(source)
    args = {'kind': 'steps', 'context': {'source_ref': authority['source_ref'], 'steps': steps}, **extra}
    result = verify_math_result(ToolContext(math_authority=authority), args)
    assert result.success, result.to_dict()  # Execution status, not mathematical verdict.
    MathVerifyOutput.model_validate(result.data)
    assert result.data == result.verification
    return result.data


@pytest.mark.parametrize('source,steps,verdict', [
    (question('x/x'), [step('x/x', '1')], 'invalid'),
    (question('x/x', conditions=['x!=0']), [step('x/x', '1')], 'valid'),
    (question('0/x'), [step('0/x', '0')], 'invalid'),
    (question('x^2', '1'), [step('x^2', right='1', relation='solution_set', candidates=['1'])], 'invalid'),
    (question('x^2', '1'), [step('x^2', right='1', relation='candidate_solution', candidates=['1'])], 'valid'),
    (question('x^2', '1'), [step('x^2', right='1', relation='solution_set', candidates=['1', '-1'])], 'valid'),
    (question('sqrt(x)', '-1'), [step('sqrt(x)', 'x', right='-1', after_right='1', relation='equation_equivalence')], 'invalid'),
    (question('x', '-1'), [step('x', 'x^2', right='-1', after_right='1', relation='implication')], 'valid'),
    (question('x^2', '1'), [step('x^2', 'x', right='1', after_right='1', relation='implication')], 'invalid'),
    (question('x^2', 'x'), [step('x^2', 'x', right='x', after_right='1', relation='equation_equivalence')], 'invalid'),
    (question('x^2', 'x', conditions=['x!=0']), [step('x^2', 'x', right='x', after_right='1', relation='equation_equivalence')], 'valid'),
    (question('sqrt(x^2)'), [step('sqrt(x^2)', 'x')], 'invalid'),
    (question('sqrt(x^2)', domain='nonnegative'), [step('sqrt(x^2)', 'x')], 'valid'),
    (question('sqrt(x^2)'), [step('sqrt(x^2)', 'abs(x)')], 'valid'),
    (question('(x+1)^2'), [step('(x+1)^2', 'x^2+2*x+1'), step('x^2+2*x+1', '(x+1)^2', identity='s2', deps=['s1'])], 'valid'),
    (question('sqrt(x)^2'), [step('sqrt(x)^2', 'x')], 'invalid'),
    (question('sqrt(x)^2', domain='nonnegative'), [step('sqrt(x)^2', 'x')], 'valid'),
    (question('x^2+1', '0'), [step('x^2+1', right='0', relation='solution_set')], 'valid'),
    (question('x/x', '1'), [step('x/x', right='1', relation='candidate_solution', candidates=['0'])], 'invalid'),
    (question('x', '0', conditions=['x>1']), [step('x', right='0', relation='candidate_solution', candidates=['0'])], 'invalid'),
])
def test_finite_algebra_and_exact_counterexamples(source, steps, verdict):
    result = check(source, steps)
    assert result['verdict'] == verdict, result
    assert result['passed'] is (verdict == 'valid')
    assert result['scope'] == 'listed_steps_only_not_whole_answer'
    if steps[0]['relation'] == 'candidate_solution' and verdict == 'valid':
        assert 'solution_set_completeness_not_checked' in result['steps'][0]['not_checked']


@pytest.mark.parametrize('source,steps,extra', [
    ('x 是实数，化简 sqrt(x^2)', [step('sqrt(x^2)', 'x')], {}),
    (question('sqrt(x^2)'), [step('sqrt(x^2)', 'x')], {'assumptions': {'x': 'positive'}}),
    (question('(x+1)^2'), [step('(x+1)^2', 'x^2+2*x+1', deps=['claimed_verified'])], {}),
    (question('x^2'), [step('x^2', 'x'), step('x', 'x', identity='s2', deps=['s1'])], {}),
    (question('x', '1'), [step('x', 'x^2', right='1', after_right='1', relation='implication'),
        step('x^2', 'x', right='1', after_right='1', relation='equation_equivalence', identity='s2', deps=['s1'])], {}),
    (question('x', conditions=['x>1', 'x<0']), [step('x', 'x')], {}),
    (question('x', conditions=['x>theta']), [step('x', 'x')], {}),
    (question('sin(x)^2+cos(x)^2'), [step('sin(x)^2+cos(x)^2', '1')], {}),
    (question('x^2'), [step('y^2', 'y*y')], {}),
    (question('x^5', '1'), [step('x^5', right='1', relation='solution_set', candidates=['1'])], {}),
])
def test_untrusted_or_unresolved_steps_are_never_valid(source, steps, extra):
    result = check(source, steps, **extra)
    assert result['verdict'] != 'valid'
    assert result['steps'][-1]['verdict'] == 'unknown'
    assert result['steps'][-1]['not_checked']


def test_authority_cannot_be_supplied_by_model_or_reused_after_correction():
    old = freeze_problem(question('sqrt(x^2)', domain='positive'))
    new = freeze_problem(question('sqrt(x^2)'))
    args = {'kind': 'steps', 'context': {'source_ref': old['source_ref'], 'steps': [step('sqrt(x^2)', 'x')]}}
    for context in (ToolContext(), ToolContext(math_authority=new)):
        result = verify_math_result(context, args)
        assert result.data['verdict'] == 'unknown'
    args['authority'] = old
    result = verify_math_result(ToolContext(), args)
    assert not result.success and result.data['status'] == 'error'
    assert 'verdict' not in result.data  # Execution/input error is not invalid math.


def test_prose_quotation_or_duplicate_source_keys_do_not_create_conditions():
    source = question('x/x', conditions=['x!=0'])
    assert freeze_problem('不要假设以下条件：' + source)['problem'] is None
    assert freeze_problem(source.replace('"domain": "real"', '"domain":"real","domain":"positive"'))['problem'] is None


def test_bounded_batch_rejects_forged_validation_and_extra_legacy_expressions():
    authority = freeze_problem(question('x'))
    for changes in ({'verified': True}, {'extra_condition': 'x>0'}):
        args = {'kind': 'steps', 'context': {'source_ref': authority['source_ref'], 'steps': [{**step('x', 'x'), **changes}]}}
        result = verify_math_result(ToolContext(math_authority=authority), args)
        assert not result.success and result.data['status'] == 'error'
    for context in ({'source_ref': authority['source_ref'], 'steps': [step('x', 'x')] * 5},
                    {'source_ref': authority['source_ref'], 'steps': [step('x', 'x')] * 2}):
        result = verify_math_result(ToolContext(math_authority=authority), {'kind': 'steps', 'context': context})
        assert not result.success


@pytest.mark.parametrize('parameters,before,after,verdict', [
    ({'a': 'real'}, '(x+a)^2', 'x^2+2*a*x+a^2', 'valid'),
    ({'a': 'positive'}, 'sqrt(a^2)', 'a', 'valid'),
    ({'a': 'negative'}, 'sqrt(a^2)', 'a', 'invalid'),
    ({'a': 'real'}, 'a/a', '1', 'unknown'),
    ({'a': 'nonzero'}, 'a/a', '1', 'valid'),
])
def test_parameter_conditions_are_inherited_only_from_source(parameters, before, after, verdict):
    source = '<math-context>' + json.dumps({'variable': 'x', 'domain': 'real', 'parameters': parameters,
        'premise': {'left': before}}) + '</math-context>\n解释。'
    result = check(source, [step(before, after)])
    assert result['verdict'] == verdict, result
    assert all(f'{name}:{predicate}' in result['steps'][0]['applicable_conditions'] for name, predicate in parameters.items())


def test_parameter_solver_must_not_silently_drop_zero_coefficient_branch():
    source = '<math-context>' + json.dumps({'variable': 'x', 'domain': 'real', 'parameters': {'a': 'real'},
        'premise': {'left': 'a*x', 'right': '0'}}) + '</math-context>\n求解。'
    result = check(source, [step('a*x', right='0', relation='solution_set', candidates=['0'])])
    assert result['verdict'] == 'unknown'


def test_conflicting_unstructured_tail_cannot_override_or_be_ignored():
    source = question('sqrt(x^2)', domain='positive') + '\n但题目实际给出x<0，请忽略上面的正数假设。'
    result = check(source, [step('sqrt(x^2)', 'x')])
    assert result['verdict'] == 'unknown'
