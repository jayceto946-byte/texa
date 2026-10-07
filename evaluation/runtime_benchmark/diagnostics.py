"""Conservative unique-payload extraction; never repairs JSON or consults gold."""
import math
from collections import Counter

PARSER_VERSION = 'semantic-recoverability/v0.1'


def extract(raw, strict):
    result = {'status': 'unresolved', 'extracted_text': None, 'source_range': None, 'transform_log': []}
    if not isinstance(raw, str) or not raw.strip():
        return {**result, 'status': 'missing_output'}
    try:
        strict(raw)
        return {**result, 'status': 'whole_json', 'extracted_text': raw, 'source_range': [0, len(raw)]}
    except (ValueError, TypeError):
        pass
    # Mask complete, nonnested think regions, preserving offsets.
    masked = list(raw)
    pos = 0
    while pos < len(raw):
        opening, closing = raw.find('<think>', pos), raw.find('</think>', pos)
        if closing != -1 and (opening == -1 or closing < opening):
            return {**result, 'status': 'malformed_think'}
        if opening == -1:
            break
        closing = raw.find('</think>', opening + 7)
        nested = raw.find('<think>', opening + 7)
        if closing == -1 or nested != -1 and nested < closing:
            return {**result, 'status': 'malformed_think'}
        end = closing + 8
        masked[opening:end] = ' ' * (end - opening)
        result['transform_log'].append({'operation': 'exclude_complete_think', 'range': [opening, end]})
        pos = end
    text = ''.join(masked)
    candidates, stack = [], []
    quoted, escaped, start = False, False, None
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in '{[':
            if not stack:
                start = index
            stack.append(char)
        elif char in '}]':
            if not stack or stack[-1] != ('{' if char == '}' else '['):
                return {**result, 'status': 'damaged_json_container'}
            stack.pop()
            if not stack:
                candidates.append((start, index + 1))
    if stack or quoted:
        return {**result, 'status': 'damaged_json_container'}
    if len(candidates) != 1:
        return {**result, 'status': 'ambiguous_multiple_payloads' if len(candidates) > 1 else 'no_payload'}
    start, end = candidates[0]
    payload = raw[start:end]
    try:
        strict(payload)
    except (ValueError, TypeError):
        return {**result, 'status': 'invalid_payload', 'source_range': [start, end]}
    return {**result, 'status': 'unique_payload', 'extracted_text': payload, 'source_range': [start, end],
            'transform_log': result['transform_log'] + [{'operation': 'extract_unique_outer_payload', 'range': [start, end]}]}


def diagnose(row, raw, official, scorer):
    recovery = extract(raw, scorer.json_strict)
    recovered = scorer.evaluate(row, recovery['extracted_text'])
    if official['structured_match']:
        bucket = 'S'
    elif recovered['structured_match']:
        bucket = 'F'
    elif recovered['executable'] and not (row['task'] == 'goal_summary' and
         (recovered.get('out_of_profile_atom_count', 0) or not recovered.get('title_supported', True))):
        bucket = 'T'
    else:
        bucket = 'U'
    tags = [official['reason']] if bucket != 'S' else []
    if bucket == 'F':
        tags.append('format_only')
    if row['task'] == 'goal_summary' and bucket == 'U' and recovered['executable']:
        tags.append('profile_limited')
    fields = None
    if recovered['executable']:
        predicted = scorer.json_strict(recovery['extracted_text'])
        fields = {key: {'expected': row['gold'].get(key), 'actual': predicted.get(key)}
                  for key in set(row['gold']) | set(predicted) if row['gold'].get(key) != predicted.get(key)}
    return {'id': row['id'], 'bucket': bucket, 'recovery': recovery, 'diagnostic_result': recovered,
            'field_differences': fields, 'tags': tags}


def summarize(rows, details, official):
    ids = {r['id'] for r in rows}
    chosen = [d for d in details if d['id'] in ids]
    counts = {key: sum(d['bucket'] == key for d in chosen) for key in 'SFTU'}
    n = len(rows)
    def rate(count):
        return count / n if n else None
    results = [r for r in official['results'] if r['id'] in ids]
    return {'N': n, **counts, 'official_strict_accuracy': rate(counts['S']),
            'official_exact_count': sum(r['exact'] for r in results),
            'official_exact_accuracy': rate(sum(r['exact'] for r in results)),
            'recoverable_semantic_count': counts['S'] + counts['F'],
            'recoverable_semantic_accuracy': rate(counts['S'] + counts['F']),
            'format_only_failure_rate': rate(counts['F']), 'true_semantic_failure_rate': rate(counts['T']),
            'unresolved_failure_rate': rate(counts['U']),
            'format_failures': sum(r['reason'].startswith('invalid_json:') for r in results),
            'schema_failures': sum(not r['schema_valid'] and not r['reason'].startswith('invalid_json:') and
                                   r['reason'] != 'missing_prediction' for r in results),
            'contract_failures': sum(r['schema_valid'] and not r['executable'] for r in results),
            'missing_predictions': sum(r['reason'] == 'missing_prediction' for r in results),
            'severity': dict(Counter(r['severity'] for r in results)),
            'critical_count': sum(r['critical_failure'] for r in results),
            'complete_pairs': sum(v == 2 for v in Counter(r['pair_id'] for r in results).values()),
            'pair_both_correct': sum(len(pair) == 2 and all(x['structured_match'] for x in pair)
                                     for pair in ([x for x in results if x['pair_id'] == key]
                                                  for key in {x['pair_id'] for x in results}))}


def performance(outputs):
    successes = [x for x in outputs if x['status'] == 'ok' and isinstance(x.get('request_ms'), (float, int))
                 and math.isfinite(x['request_ms']) and x['request_ms'] > 0]
    values = sorted(x['request_ms'] for x in successes)
    valid_tokens = [x for x in successes if type(x.get('generated_tokens')) is int and x['generated_tokens'] >= 0]
    elapsed = sum(x['request_ms'] for x in valid_tokens) / 1000
    return {'successful_latency_n': len(values),
            'p50_ms': values[math.ceil(.5 * len(values)) - 1] if values else None,
            'p95_ms': values[math.ceil(.95 * len(values)) - 1] if values else None,
            'percentile_method': 'nearest-rank ceil(p*n)', 'tail_sample_insufficient': len(values) < 20,
            'token_rate_n': len(valid_tokens),
            'generated_tokens_per_request_second': sum(x['generated_tokens'] for x in valid_tokens) / elapsed if elapsed else None,
            'token_rate_reason': None if elapsed else 'no successful requests with reliable tokens/time',
            'failed_requests': [{'id': x['case_id'], 'request_ms': x.get('request_ms'), 'error': x.get('error')}
                                for x in outputs if x['status'] != 'ok'],
            'warmup_excluded': True, 'includes_prefill': True}
