"""Finite real algebra checks, called only by verify_math_result(kind=steps).

All acceptance uses exact symbolic certificates/sets, never sample agreement.
Raw AST restrictions are collected before simplification or substitution.
"""
from __future__ import annotations

import sympy as sp
from backend.tools.math_step_contract import StepBatch, Problem, Statement
from backend.tools.registry import ToolResult


class UnknownMath(ValueError):
    pass


def _same(a: Statement, b: Statement) -> bool:
    # Syntactic continuity deliberately does not erase undefined subexpressions.
    def norm(text):
        return ''.join((text or '').split()).replace('**', '^')
    return norm(a.left) == norm(b.left) and ((a.right is None and b.right is None) or
        (a.right is not None and b.right is not None and norm(a.right) == norm(b.right)))


class RealAlgebra:
    def __init__(self, problem):
        from backend.tools.math_tools import _variable
        self.x = _variable(problem.variable)
        self.parameters = {_variable(name) for name in problem.parameters}
        self.conditions = [f'{problem.variable}:{problem.domain}', *[f'{name}:{predicate}' for name, predicate in problem.parameters.items()], *problem.conditions]
        domains = {'real': sp.S.Reals, 'integer': sp.S.Integers,
            'positive': sp.Interval.open(0, sp.oo), 'nonnegative': sp.Interval(0, sp.oo),
            'negative': sp.Interval.open(-sp.oo, 0), 'nonpositive': sp.Interval(-sp.oo, 0),
            'nonzero': sp.Complement(sp.S.Reals, sp.FiniteSet(0))}
        # Integer sets are not handled by the finite real solver yet.
        if problem.domain == 'integer':
            raise UnknownMath('integer-domain completeness is not supported')
        self.domain = domains[problem.domain]
        import re
        for condition in problem.conditions:
            match = re.fullmatch(r'\s*' + re.escape(problem.variable) + r'\s*(!=|>=|<=|>|<|=)\s*([+-]?(?:\d+(?:/\d+)?))\s*', condition)
            if not match:
                raise UnknownMath('unsupported trusted condition')
            value = sp.Rational(match[2])
            relation = {'!=': sp.Ne, '>=': sp.Ge, '<=': sp.Le, '>': sp.Gt, '<': sp.Lt, '=': sp.Eq}[match[1]]
            self.domain = self.domain.intersect(self.inequality(relation(self.x, value)))
        if self.domain.is_empty is not False:
            raise UnknownMath('inconsistent or unresolved source conditions')

    def parse(self, text):
        from backend.tools.math_tools import parse_restricted_expression
        value = parse_restricted_expression(text, evaluate=False)
        if value.free_symbols - {self.x} - self.parameters:
            raise UnknownMath('undeclared symbols or parameters')
        for node in sp.preorder_traversal(value):
            if node.has(sp.Float, sp.I, sp.oo, sp.zoo, sp.nan):
                raise UnknownMath('non-finite or non-real algebra')
            if node.is_Number:
                if not node.is_Rational or abs(node) > 10**12:
                    raise UnknownMath('unsupported coefficient')
            elif node.is_Symbol:
                continue
            elif isinstance(node, sp.Pow):
                if not (node.exp.is_Integer and abs(node.exp) <= 8 or node.exp in (sp.Rational(1, 2), sp.Rational(-1, 2))):
                    raise UnknownMath('unsupported algebraic power')
            elif not isinstance(node, (sp.Add, sp.Mul, sp.Abs)):
                raise UnknownMath('outside finite algebra fragment')
        return value

    def inequality(self, relation):
        if relation is sp.S.true:
            return sp.S.Reals
        if relation is sp.S.false:
            return sp.S.EmptySet
        if relation.free_symbols - {self.x}:
            raise UnknownMath('parameter inequality cannot be certified')
        try:
            result = sp.solve_univariate_inequality(relation, self.x, relational=False)
        except (NotImplementedError, ValueError, TypeError) as exc:
            raise UnknownMath('unresolved domain condition') from exc
        return self.concrete(result)

    def concrete(self, value):
        if value.has(sp.ConditionSet, sp.ImageSet) or value.free_symbols:
            raise UnknownMath('unresolved symbolic set')
        return value

    def domain_of(self, expression):
        result = sp.S.Reals
        # Walk the original, unevaluated tree. In particular x/x, 0/x and
        # sqrt(x)^2 still impose restrictions even if their value simplifies.
        for node in sp.preorder_traversal(expression):
            if isinstance(node, sp.Pow):
                base, exponent = node.args
                if exponent < 0 and sp.simplify(base).is_nonzero is not True:
                    if base.free_symbols & self.parameters:
                        raise UnknownMath('parameter denominator may vanish')
                    zeros = sp.solveset(base, self.x, domain=sp.S.Reals)
                    result = result - self.concrete(zeros)
                if exponent.q == 2:
                    result = result.intersect(self.inequality(sp.Ge(base, 0)))
        return self.concrete(result)

    def statement(self, statement):
        left = self.parse(statement.left)
        domain = self.domain.intersect(self.domain_of(left))
        if statement.right is None:
            return left, domain
        right = self.parse(statement.right)
        domain = domain.intersect(self.domain_of(right))
        expression = sp.simplify(left - right)
        # solveset's polynomial degree is bounded as well as the AST budget.
        numerator = sp.fraction(sp.cancel(expression))[0]
        if numerator.is_polynomial(self.x) and sp.degree(numerator, self.x) > 4:
            raise UnknownMath('equation degree exceeds finite solver budget')
        return expression, domain

    def solutions(self, statement):
        expression, domain = self.statement(statement)
        if expression.free_symbols & self.parameters:
            raise UnknownMath('parameter equation branches are not certified')
        try:
            result = sp.solveset(expression, self.x, domain=domain)
        except (NotImplementedError, ValueError, TypeError) as exc:
            raise UnknownMath('solution set cannot be certified') from exc
        return self.concrete(result)

    def compare_sets(self, a, b):
        if a == b:
            return True
        delta = self.concrete(sp.SymmetricDifference(a, b))
        if delta.is_empty is True:
            return True
        if delta.is_empty is False:
            return False
        raise UnknownMath('set equality unresolved')

    def check(self, step):
        checked, pending = [], []
        if step.relation == 'identity':
            before, bd = self.statement(step.before)
            after, ad = self.statement(step.after)
            if not self.compare_sets(bd, ad):
                return 'invalid', ['original_AST_domains_differ'], [], f'{bd} != {ad}'
            checked.append('original_AST_domains_equal')
            if bd.is_empty is not False:
                raise UnknownMath('empty or unresolved expression domain')
            residual = sp.simplify(before - after)
            if residual == 0:
                return 'valid', checked + ['exact_symbolic_identity'], [], None
            # A disproof is an exact point satisfying all preserved conditions,
            # never equality of a finite sample. No floats or tolerance.
            for point in [0, 1, -1, 2, -2, 3, -3, sp.Rational(1, 2), sp.Rational(-1, 2)]:
                if bd.contains(point) is sp.S.true:
                    value = sp.simplify(residual.subs(self.x, point))
                    if value.is_finite is True and value.is_zero is False:
                        return 'invalid', checked + ['exact_counterexample'], [], f'{self.x}={point}; residual={value}'
            if residual.free_symbols & self.parameters:
                raise UnknownMath('parameter identity is unresolved')
            zeros = self.concrete(sp.solveset(residual, self.x, domain=bd))
            if self.compare_sets(zeros, bd):
                return 'valid', checked + ['exact_zero_set_covers_domain'], [], None
            return 'invalid', checked + ['exact_zero_set_does_not_cover_domain'], [], str(bd - zeros)
        before = self.solutions(step.before)
        checked.append('source_equation_solved_with_original_AST_domain')
        if step.relation in {'candidate_solution', 'solution_set'}:
            values = []
            for text in step.candidates:
                raw = self.parse(text)
                if raw.free_symbols or self.domain_of(raw) != sp.S.Reals:
                    raise UnknownMath('candidate must be a defined closed real value')
                value = sp.simplify(raw)
                if value.is_real is not True or value.is_finite is not True:
                    raise UnknownMath('candidate must be real and finite')
                values.append(value)
            candidates = sp.FiniteSet(*values)
            if step.relation == 'candidate_solution':
                if not values:
                    raise UnknownMath('empty candidate list proves no candidate')
                pending.append('solution_set_completeness_not_checked')
                extra = self.concrete(candidates - before)
                verdict = self.compare_sets(extra, sp.S.EmptySet)
                return ('valid' if verdict else 'invalid'), checked + ['candidate_membership_only'], pending, str(extra) if not verdict else None
            verdict = self.compare_sets(before, candidates)
            return ('valid' if verdict else 'invalid'), checked + ['complete_solution_set_equality'], [], str(sp.SymmetricDifference(before, candidates)) if not verdict else None
        after = self.solutions(step.after)
        if step.relation == 'implication':
            missing = self.concrete(before - after)
            verdict = self.compare_sets(missing, sp.S.EmptySet)
            pending.append('reverse_implication_not_checked')
            return ('valid' if verdict else 'invalid'), checked + ['forward_solution_set_inclusion'], pending, str(missing) if not verdict else None
        verdict = self.compare_sets(before, after)
        return ('valid' if verdict else 'invalid'), checked + ['equation_solution_set_equality'], [], str(sp.SymmetricDifference(before, after)) if not verdict else None


def verify_steps(authority: dict | None, args: dict) -> ToolResult:
    from backend.tools.math_tools import _ASSUMPTIONS
    batch = StepBatch.model_validate(args['context'])
    authority = authority or {}
    reason = None
    problem = None
    if batch.source_ref != authority.get('source_ref') or not authority.get('problem'):
        reason = 'missing_or_stale_trusted_problem_source'
    elif args.get('assumptions'):
        reason = 'model_assumptions_cannot_extend_or_override_source'
    else:
        problem = Problem.model_validate(authority['problem'])
    rows, previous = [], {}
    token = _ASSUMPTIONS.set({**problem.parameters, problem.variable: 'real'} if problem else {})
    try:
        algebra = None
        if not reason:
            try:
                algebra = RealAlgebra(problem)
            except (UnknownMath, NotImplementedError, ValueError, TypeError, ZeroDivisionError) as exc:
                reason = str(exc)
        for step in batch.steps:
            missing = [dep for dep in step.depends_on if dep not in previous or previous[dep]['verdict'] != 'valid'
                or previous[dep]['relation'] not in {'identity', 'equation_equivalence'}]
            local_reason = reason
            if missing:
                local_reason = 'unverified_or_non_equivalent_dependency'
            elif not reason:
                # All dependencies are checked; one must supply precisely this
                # premise. An implication cannot be used as an equivalence.
                anchors = [Statement.model_validate(previous[d]['after']) for d in step.depends_on if previous[d]['after']]
                if not any(_same(step.before, anchor) for anchor in (anchors or [problem.premise])):
                    local_reason = 'before_not_bound_to_source_or_verified_predecessor'
            checked, pending, counterexample = [], [], None
            verdict = 'unknown'
            if not local_reason:
                try:
                    verdict, checked, pending, counterexample = algebra.check(step)
                except (UnknownMath, NotImplementedError, ValueError, TypeError, ZeroDivisionError) as exc:
                    local_reason = str(exc)
            if local_reason:
                pending.append(local_reason)
            row = {'id': step.id, 'verdict': verdict, 'relation': step.relation,
                'depends_on': step.depends_on, 'before': step.before.model_dump(), 'candidates': step.candidates,
                'after': step.after.model_dump() if step.after else None,
                'checked': checked, 'not_checked': pending, 'counterexample': counterexample,
                'scope': step.relation, 'applicable_conditions': algebra.conditions if algebra else []}
            rows.append(row)
            previous[step.id] = row
    finally:
        _ASSUMPTIONS.reset(token)
    verdict = 'invalid' if any(r['verdict'] == 'invalid' for r in rows) else 'unknown' if any(r['verdict'] == 'unknown' for r in rows) else 'valid'
    data = {'status': 'verified' if verdict == 'valid' else 'failed' if verdict == 'invalid' else 'unverified',
        'verdict': verdict, 'execution_status': 'completed', 'method': 'contextual_steps',
        'passed': verdict == 'valid', 'residuals': [], 'assumptions': {},
        'scope': 'listed_steps_only_not_whole_answer', 'limitations': ['Does not certify modelling, omitted steps, geometry or natural-language proofs.'],
        'source_ref': authority.get('source_ref', ''), 'source_kind': authority.get('source_kind', ''),
        'steps': rows}
    # Execution completion is independent of mathematical validity. The legacy
    # passed field remains false for invalid/unknown, so no final gate promotion.
    return ToolResult(True, data=data, verification=data, message='上下文步骤校验完成')
