"""Bind exact final-answer relations to existing successful local receipts.

No extra computation, symbolic proof, source inference or model judgment.
The AST is identity only: 2+3 is not folded into 5 and x/x is not reduced to 1.
Unsupported LaTeX and unbound assumptions remain unknown.
"""
from __future__ import annotations

import ast
import hashlib
import re

_FORMULAS = re.compile(r'\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|\$[^$\n]+\$', re.S)


def formula_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _plain(value):
    value = re.sub(r'\\tag\{[^}]*\}', '', value)
    for token in ('\\(', '\\)', '\\[', '\\]', '$', '\\left', '\\right', '\\,', '\\!'):
        value = value.replace(token, '')
    value = value.replace('\\cdot', '*').replace('\\times', '*').replace('−', '-')
    value = re.sub(r'\s+', '', value)
    return value


def _identity(value):
    value = _plain(str(value))
    if re.search(r'\d[eE][+-]?\d', value):
        return None  # Do not reinterpret scientific notation as multiplication.
    for _ in range(8):
        replaced = re.sub(r'\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}', r'((\1)/(\2))', value)
        if replaced == value:
            break
        value = replaced
    value = value.replace('{', '(').replace('}', ')').replace('^', '**')
    value = re.sub(r'(?<=\d)(?=[A-Za-z(])|(?<=\))(?=\()', '*', value)
    if not value or len(value) > 700 or not re.fullmatch(r'[A-Za-z0-9_+*/().-]+', value):
        return None
    try:
        tree = ast.parse(value, mode='eval')
    except (SyntaxError, ValueError, RecursionError):
        return None
    nodes = list(ast.walk(tree))
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Load,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.UAdd, ast.USub)
    if len(nodes) > 128 or any(not isinstance(n, allowed) for n in nodes):
        return None
    if any(isinstance(n, ast.Constant) and type(n.value) not in (int, float) for n in nodes):
        return None
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


def bind_math_claims(answer, question, pack):
    bindings = []
    for match in list(_FORMULAS.finditer(answer))[:128]:
        formula = match.group()
        plain = _plain(formula).rstrip(',;，；。')
        sides = plain.split('=')
        if len(sides) != 2:
            continue  # One verified edge cannot certify a larger chain.
        for index, receipt in enumerate((pack.get('outputs') or [])[:16]):
            args = receipt.get('args') or {}
            verification = receipt.get('verification') or {}
            if (receipt.get('tool') != 'verify_math_result' or receipt.get('success') is not True
                    or verification.get('passed') is not True or args.get('assumptions')):
                continue
            kind, matched = args.get('kind'), False
            if kind == 'equivalence':
                actual = [_identity(side) for side in sides]
                expected = [_identity(args.get(key, '')) for key in ('left', 'right')]
                matched = all(actual) and all(expected) and (actual == expected or actual == expected[::-1])
            elif kind == 'derivative':
                variable = str(args.get('variable') or 'x')
                # Bind the derivative's named function to the frozen question,
                # never infer an original function from the candidate alone.
                source = re.search(r"([A-Za-z])\(" + re.escape(variable) + r"\)\s*=\s*([A-Za-z0-9_+*/^(). -]+)", question)
                matched = bool(source and sides[0] == source[1] + "'(" + variable + ')'
                    and _identity(source[2]) is not None and _identity(source[2]) == _identity(args.get('original', ''))
                    and _identity(sides[1]) is not None and _identity(sides[1]) == _identity(args.get('candidate', '')))
            if matched:
                bindings.append({'formula_sha256': formula_hash(formula), 'answer_span': [match.start(), match.end()],
                    'runtime_call_id': receipt.get('runtime_call_id'), 'receipt_index': index,
                    'kind': kind, 'receipt_scope': verification.get('scope', ''), 'covers_formula': True,
                    'binding_scope': 'listed_relation_only_not_modeling_or_whole_answer'})
                break
        if len(bindings) >= 32:
            break
    return bindings
