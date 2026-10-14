"""One-off read-only analysis for exposed Runtime-0.8B diagnostics; no inference imports."""
import collections
import json
import re
from pathlib import Path

from evaluation.runtime_benchmark.scoring import Benchmark
from diagnose_runtime_08b import BASE, ROOT, read, save, lines, baseline_hashes

CATEGORIES = ('user intent misunderstanding', 'tool vs direct-answer boundary', 'multi-intent priority/order',
              'negation/correction failure', 'candidate-description misunderstanding',
              'reference/context misunderstanding', 'ambiguous / potentially disputable gold', 'other')


def parse_fields(raw, scorer):
    try:
        value = scorer.json_strict(raw)
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def split_atoms(value):
    return [atom.strip() for atom in re.split(r'[；;\n]+', value) if atom.strip()] if isinstance(value, str) else []


def field_analysis(row, output, scorer):
    raw = output.get('raw_output')
    frozen = scorer.evaluate(row, raw)
    value = parse_fields(raw, scorer)
    expected = row['gold']; task = row['task']
    required = list(expected)
    fields = {key: False for key in required}
    unsupported, out_profile, invented = [], [], []
    retention = {'constraints_hit': 0, 'constraints_total': 0, 'negative_hit': 0, 'negative_total': 0,
                 'objective_atoms_hit': 0, 'objective_atoms_total': 0, 'criteria_atoms_hit': 0, 'criteria_atoms_total': 0}
    source = row['input'].get('text', row['input'].get('question', ''))
    if task == 'goal_summary':
        metadata = row['metadata']
        retention.update(constraints_total=len(metadata['constraint_atoms']),
                         negative_total=sum(bool(re.search(r'不|别|勿|禁止|只|仅|无需|暂缓', a)) for a in metadata['objective_atoms']),
                         objective_atoms_total=len(metadata['objective_atoms']), criteria_atoms_total=len(metadata['criteria_atoms']))
    if value is not None:
        invented = sorted(set(value) - set(expected))
        if task == 'goal_summary':
            metadata = row['metadata']
            title = value.get('title'); objective = value.get('objective'); criteria = value.get('success_criteria')
            objective_atoms = split_atoms(objective)
            criterion_atoms = [item['description'].strip() for item in criteria
                               if isinstance(item, dict) and isinstance(item.get('description'), str)] if isinstance(criteria, list) else []
            fields['title'] = isinstance(title, str) and title.strip() == expected['title'].strip()
            fields['objective'] = sorted(objective_atoms) == sorted(metadata['objective_atoms'])
            fields['success_criteria'] = sorted(criterion_atoms) == sorted(metadata['criteria_atoms'])
            actual_text = objective if isinstance(objective, str) else ''
            constraints = metadata['constraint_atoms']
            # Explicit lexical negation/exclusivity atoms; not a learned semantic classifier.
            negatives = [a for a in metadata['objective_atoms'] if re.search(r'不|别|勿|禁止|只|仅|无需|暂缓', a)]
            retention = {'constraints_hit': sum(a in actual_text for a in constraints), 'constraints_total': len(constraints),
                         'negative_hit': sum(a in actual_text for a in negatives), 'negative_total': len(negatives),
                         'objective_atoms_hit': sum(a in actual_text for a in metadata['objective_atoms']),
                         'objective_atoms_total': len(metadata['objective_atoms']),
                         'criteria_atoms_hit': sum(any(a in v for v in criterion_atoms) for a in metadata['criteria_atoms']),
                         'criteria_atoms_total': len(metadata['criteria_atoms'])}
            out_profile = [a for a in objective_atoms if a not in metadata['objective_atoms']] + [a for a in criterion_atoms if a not in metadata['criteria_atoms']]
            unsupported = [a for a in out_profile if a not in source]
            if isinstance(title, str) and title not in source:
                unsupported.append(title)
        elif task == 'question_understanding':
            for key in required:
                if key == 'dimensions':
                    actual = value.get(key)
                    fields[key] = isinstance(actual, list) and all(isinstance(x, str) for x in actual) and sorted(actual) == sorted(expected[key])
                else:
                    fields[key] = value.get(key) == expected[key]
            schema = json.loads((scorer.ROOT / 'schemas/question_understanding.output.schema.json').read_text())
            for key in ('action', 'intent'):
                if key in value and value[key] not in schema['properties'][key]['enum']:
                    unsupported.append({'field':key, 'value':value[key], 'reason':'out_of_enum'})
            if isinstance(value.get('dimensions'), list):
                for item in value['dimensions']:
                    if item not in schema['properties']['dimensions']['items']['enum']:
                        unsupported.append({'field':'dimensions', 'value':item, 'reason':'out_of_enum_or_type'})
            ref = value.get('reference_id')
            candidates = {x['id'] for x in row['input']['candidate_references']}
            if isinstance(ref, str) and ref and ref not in candidates:
                unsupported.append({'field':'reference_id', 'value':ref, 'reason':'out_of_candidates'})
            spans = value.get('entity_spans')
            if isinstance(spans, list):
                for span in spans:
                    if not isinstance(span, dict) or type(span.get('start')) is not int or type(span.get('end')) is not int or not 0 <= span['start'] < span['end'] <= len(source):
                        unsupported.append({'field':'entity_spans', 'value':span, 'reason':'ungrounded_or_invalid_span'})
        else:
            fields['action_id'] = value.get('action_id') == expected['action_id']
            allowed = {a['id'] for a in row['input']['admissible_actions']}
            if value.get('action_id') not in allowed:
                unsupported.append({'field':'action_id', 'value':value.get('action_id'), 'reason':'out_of_candidates'})
    # Strict parse rate includes any JSON type; dict-only core contract is separate.
    try:
        scorer.json_strict(raw); json_valid = True
    except (ValueError, TypeError):
        json_valid = False
    return {'id':row['id'], 'task':task, 'diagnostic_only':True, 'json_valid':json_valid,
            'schema_valid':frozen['schema_valid'], 'contract_valid':frozen['executable'],
            'complete_semantic_match':frozen['structured_match'], 'frozen_diagnostic_result':frozen,
            'field_matches':fields, 'field_complete_match':all(fields.values()), **retention,
            'invented_fields':invented, 'unsupported_values':unsupported, 'out_of_profile_atoms':out_profile,
            'needs_semantic_review':task=='goal_summary' and bool(out_profile),
            'finish_reason':output.get('finish_reason'), 'length':output.get('finish_reason')=='length',
            'operational_status':output.get('status','missing'), 'raw_output':raw}


def summarize(details):
    n = len(details)
    def count(key): return sum(bool(x[key]) for x in details)
    def frac(numerator, denominator): return numerator / denominator if denominator else None
    fields = {key: {'correct':sum(d['field_matches'].get(key, False) for d in details), 'N':n}
              for key in sorted({key for d in details for key in d['field_matches']})}
    field_n = sum(len(d['field_matches']) for d in details)
    result = {'N':n, 'json_valid':count('json_valid'), 'schema_valid':count('schema_valid'),
              'contract_valid':count('contract_valid'), 'complete_semantic_match':count('complete_semantic_match'),
              'field_complete_match':count('field_complete_match'), 'fields':fields,
              'field_accuracy_micro':frac(sum(sum(d['field_matches'].values()) for d in details), field_n),
              'field_denominator':field_n, 'length_count':count('length'),
              'truncation_rate_finish_length':frac(count('length'), n),
              'invented_field_cases':sum(bool(d['invented_fields']) for d in details),
              'unsupported_value_cases':sum(bool(d['unsupported_values']) for d in details),
              'goal_profile_needs_review':count('needs_semantic_review')}
    for key in ('constraints', 'negative', 'objective_atoms', 'criteria_atoms'):
        hit = sum(d[key+'_hit'] for d in details); total = sum(d[key+'_total'] for d in details)
        result[key+'_retention'] = {'hit':hit, 'total':total, 'rate':frac(hit,total)}
    return result


def policy_audit(rows, original, scorer):
    audit = []; overlap = {key:[] for key in ('overlap_correct','Qwen-only_correct','Rule-only_correct','both_wrong')}
    for row in rows:
        if row['task'] != 'policy_select': continue
        pred = scorer.json_strict(original[row['id']]['raw_output'])
        rule = row['metadata']['rule_prediction']
        q_correct = pred == row['gold']; r_correct = rule == row['gold']
        key = 'overlap_correct' if q_correct and r_correct else 'Qwen-only_correct' if q_correct else 'Rule-only_correct' if r_correct else 'both_wrong'
        overlap[key].append(row['id'])
        if q_correct: continue
        actions = {action['id']:action for action in row['input']['admissible_actions']}
        selected, gold = actions[pred['action_id']], actions[row['gold']['action_id']]
        question = row['input']['request']; tags = row['tags']; cues = []
        if 'multi_intent_order' in tags:
            primary = 'multi-intent priority/order'
        elif selected['kind'] != gold['kind']:
            primary = 'tool vs direct-answer boundary'
        else:
            primary = 'other'
        if row['id']=='TRB0-0066':
            primary = 'ambiguous / potentially disputable gold'
        if re.search(r'不是|别|不对|说反|改口|先别|只|先放下', question):
            cues.append('negation/correction failure')
        if re.search(r'前者|后者|前一个|后一个|刚才|同学|标题', question):
            cues.append('reference/context misunderstanding')
        if primary == 'multi-intent priority/order' and selected['kind'] != gold['kind']:
            cues.append('tool vs direct-answer boundary')
        meaning = lambda action: action['args'].get('tool_id',action['kind'])
        reason = f"gold 的下一步是 {meaning(gold)}；模型选择 {meaning(selected)}。"
        if primary=='multi-intent priority/order':
            reason += '题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。'
        elif primary=='tool vs direct-answer boundary':
            reason += '实际请求读取已有数据，模型转为直接回答。'
        elif primary=='ambiguous / potentially disputable gold':
            reason += '前半句“看掌握情况再找练习题”和末句“先调题目列表”方向不同；gold采用末句，需要人工核对纠正优先约定，不改gold。'
        audit.append({'id':row['id'],'primary_category':primary,'secondary_surface_categories':cues,
                      'needs_review': primary in ('other','ambiguous / potentially disputable gold'),
                      'root_cause_needs_review':True,
                      'root_cause_unresolved':['user intent misunderstanding','candidate-description misunderstanding'],
                      'input':row['input'],'candidates':row['input']['admissible_actions'],'gold':row['gold'],
                      'model_choice':pred,'rule_choice':rule,'concise_reason':reason})
    categories = {key:{'primary_count':sum(x['primary_category']==key for x in audit),
                       'primary_ids':[x['id'] for x in audit if x['primary_category']==key],
                       'surface_count':sum(key in x['secondary_surface_categories'] for x in audit),
                       'surface_ids':[x['id'] for x in audit if key in x['secondary_surface_categories']]}
                  for key in CATEGORIES}
    for key, group in categories.items():
        ids=[case['id'] for case in audit if key in case['root_cause_unresolved'] or
             key in case['secondary_surface_categories'] and key in ('negation/correction failure','reference/context misunderstanding') or
             case['primary_category']==key and case['needs_review']]
        group.update(needs_review_count=len(ids),needs_review_ids=ids)
    return {'diagnostic_only':True,'N':80,'errors':len(audit),'overlap':{k:{'count':len(v),'ids':v} for k,v in overlap.items()},
            'categories':categories,'cases':audit,
            'causal_caveat':'Primary labels classify observed error surfaces relative to frozen gold. Secondary cue labels are not proof of causal misunderstanding; 40 cognitive root causes need review.'}


def analyze(out):
    b = Benchmark()
    before = read(out / 'baseline-before.json'); after = baseline_hashes()
    if before != after:
        raise ValueError('baseline changed during diagnostic')
    save(out / 'baseline-integrity.json', {'diagnostic_only':True,'unchanged':True,'checked_files':len(before),
                                          'freeze_sha256':b.freeze_hash})
    experiment = read(out / 'experiment.json')
    original = {x['case_id']:x for x in lines(BASE / 'p3-semantic-all-verified/outputs.jsonl')}
    baseline_model=read(BASE/'p2-primary/run.json')['model']
    for arm in ('A','B','B_json','D'):
        model=read(out/f'arm-{arm}/run.json')['model']
        for key in ('local_path','quantization','weight_dtypes','libraries','template_settings'):
            assert model[key]==baseline_model[key],(arm,key)
    assert __import__('hashlib').sha256((out/'jobs-A.jsonl').read_bytes()).hexdigest()==experiment['prompts_sha256']
    rows = [b.by_id[id_] for id_ in experiment['case_ids_A_B']]
    details, summaries, states = {}, {}, {}
    for arm in ('original','A','B','B_json'):
        if arm=='original':
            outputs = original
        else:
            states[arm] = read(out / f'arm-{arm}/run.json')
            records = lines(out / f'arm-{arm}/outputs.jsonl') if (out / f'arm-{arm}/outputs.jsonl').exists() else []
            outputs = {x['case_id']:x for x in records}
            allowed_ids=set(experiment['case_ids_A_B']) if arm!='B_json' else {r['id'] for r in rows if r['task']=='question_understanding'}
            if len(outputs)!=len(records) or set(outputs)-allowed_ids:
                raise ValueError('duplicate/unknown diagnostic ID')
            requests = lines(out / f'arm-{arm}/requests.jsonl') if (out / f'arm-{arm}/requests.jsonl').exists() else []
            jobs = {j['case_id']:j for j in lines(out / 'jobs-A.jsonl')}
            assert len(requests)==len(records)
            for request, record in zip(requests, records):
                assert request['messages']==jobs[request['case_id']]['messages']
                assert request['rendered_prompt']==record['rendered_prompt']
                if arm=='B': assert request['backend_schema']==read(out / 'backend-schemas.json')[request['task']]
                if arm=='B_json': assert request['backend_schema']=={'type':'object'}
        details[arm] = [field_analysis(row, outputs.get(row['id'], {}), b.scorer) for row in rows
                       if arm!='B_json' or row['task']=='question_understanding']
        summaries[arm] = {task:summarize([d for d in details[arm] if d['task']==task])
                          for task in ('goal_summary','question_understanding','policy_select') if any(d['task']==task for d in details[arm])}
    # Unsupported decoding is a capability result, never a 0%-accuracy model result.
    if states['B']['status']=='incomplete' and 'uniqueItems' in states['B'].get('error',''):
        summaries['B']['question_understanding']={'available':False,'N_planned':41,'N_generated':0,
                                                'compilation_failures':1,'not_attempted':40,
                                                'reason':states['B']['error'],'diagnostic_only':True}
    audits = policy_audit(b.rows, original, b.scorer)
    save(out / 'probe-C-audit.json', audits)
    budget_outputs = lines(out / 'arm-D/outputs.jsonl')
    budget_by_id = {(x['source_arm'],x['case_id']):x for x in budget_outputs}
    jobs=lines(out/'jobs-D-final.jsonl')
    assert len(budget_by_id)==len(budget_outputs) and set(budget_by_id)=={(j['source_arm'],j['case_id']) for j in jobs}
    budget_details=[]
    for job in jobs:
        source=job['source_arm']; id_=job['case_id']
        source_outputs=original if source=='original' else {x['case_id']:x for x in lines(out/f'arm-{source}/outputs.jsonl')}
        current=source_outputs[id_]
        assert current['finish_reason']=='length' and current['status']=='ok'
        assert job['max_new_tokens']==384*2
        doubled=budget_by_id[(source,id_)]
        assert doubled['rendered_prompt']==current['rendered_prompt']
        assert doubled['max_new_tokens']==job['max_new_tokens']
        budget_details.append({'id':id_,'source_arm':source,'current':field_analysis(b.by_id[id_],current,b.scorer),
                               'double':field_analysis(b.by_id[id_],budget_by_id[(source,id_)],b.scorer)})
    budget_summary = {source:{arm:summarize([x[arm] for x in budget_details if x['source_arm']==source])
                             for arm in ('current','double')} for source in sorted({x['source_arm'] for x in budget_details})}
    result = {'diagnostic_only':True,'exposed_dev':True,'summaries':summaries,'case_metrics':details,
              'budget_summary':budget_summary,'budget_cases':budget_details,'policy_audit':audits,
              'baseline_unchanged':True,'inference_states':states,'experiment':experiment}
    result['budget_run']=read(out/'arm-D/run.json')
    result['model_identity_matches_baseline']=True
    save(out / 'diagnostic-metrics.json', result)
    print(json.dumps({'summaries':summaries,'budget_summary':budget_summary,
                      'overlap':{k:v['count'] for k,v in audits['overlap'].items()},
                      'categories':audits['categories']},ensure_ascii=False,indent=2))


def write_report(out):
    """Only readable deliverable; machine records remain evidence, not new official scores."""
    m=read(out/'diagnostic-metrics.json'); sums=m['summaries']; audit=m['policy_audit']
    target=ROOT/'docs/runtime-benchmark-v0.1/Runtime-0.8B-Diagnostic-Probe.md'
    if target.exists(): raise FileExistsError(target)
    evidence='../validation/runtime-benchmark-v0.1/'+out.name
    def pct(value): return '—' if value is None else f'{value:.1%}'
    text=[
        '# Runtime-0.8B-Diagnostic-Probe', '',
        '2026-10-06。`diagnostic_only=true`，exposed dev diagnostic；本轮不是新的正式 Benchmark 成绩。模型保持本地 Qwen3.5-0.8B MLX 8bit、greedy、temperature=0、thinking=false、batch=1、seed=0。没有训练、Runtime 改动或模型/依赖下载。', '',
        '## 直接结论', '',
        '1. **原 baseline 的低分同时来自输出合同负担和语义/执行判断缺陷。** Primary 的121条失败中，81条（66.9%，占161条的50.3%）是Goal/Understanding的格式、Schema或跨字段合同失败，40条是Policy合法候选选择错误。这是原失败形态分类，不能说81条的语义原本正确。移除完整Schema后，Goal/Understanding的Schema合法输出从3/81变成69/81，但两任务新增完整匹配仍为0；本轮没有证明这81条可以通过格式减负恢复语义成功。',
        '2. **低合同负担下测得的完整语义交付仍为Goal 0/40、Understanding 0/41。** 部分字段存在有效信息：Goal title为23/40，Understanding intent为12/41、dimensions为7/41。它们是有界字段的gold匹配，不能合并成“模型完全不懂”，也不能当作完整任务成功。',
        '3. **原Policy 50%的主要模式是候选位置偏好。** 80条中79次选a1；40个错例的可观察主类是28个工具/直接回答边界、11个先后顺序、1个存在相反顺序表述需复核的样本。新20条定向诊断由原12/20变为简化15/20，受约束14/20，显示部分语义可受清楚说明激活；选择a1的偏好仍很强。',
        '4. **Rule与Qwen错误集合高度互补，但主要是相反槽位先验。** 两者同时正确0；Qwen-only 40；Rule-only 39；同时错误1。Rule在冻结包中80次全部选a0，Qwen几乎总选a1。知道gold后选择两者可得到79/80的oracle上界，当前没有不使用gold便能可靠选择两者的仲裁器，不能把98.75%当作可部署ensemble能力。',
        '5. **当前相对更适合研究狭窄的Policy selection。** 有少量核心短语/intent抽取能力，但semantic extraction尚不能完成对象/动作交付；Goal transformation会添限制与示例产物；reference/context resolution没有新增正向证据，不适合交由它承担。',
        '6. **证据不足以直接进入覆盖全部Runtime职责的LoRA/SFT。** Policy可成为后续最小训练可行性研究对象，但定向20题、已曝光且仍有槽位偏好，尚不能证明稳定foundation prior。Goal/Understanding的输出纪律、范围保持、复制示例和错误澄清同时失稳。本轮到解释低分为止，不开始训练。', '',
        '这里的“0%”是本轮固定提示下、原gold/profile要求的完整交付匹配；不是开放语义能力或理论上限为零。一个格式示例也引入了可观测的内容复制，进一步限制“semantic ceiling”的解释。', '',
        '## 条件、选择与评分资格', '',
        '- A/B共用相同输入、相同gold、相同模型和预算：全部40 Goal、全部41 primary Understanding、10个Policy语言对共20题。Policy按family选取，原提示在该20题上为60%，高于全80题50%；不能将75%外推为80题的改进成绩。',
        '- Goal仍用现有`title/objective/success_criteria`三字段。`constraints`不是该GoalSummary的既有字段，因此没有新增它；范围/否定/期限仍放在objective中，按原metadata atoms测保留。Understanding仍保留既有五字段和Unicode位置合同，没有新Runtime IR。',
        '- A省略完整JSON Schema，使用简洁说明、允许枚举和一个独立合法格式示例。没有当前case的gold、metadata、caption、规则预测或few-shot答案。输入JSON未改写，候选未删减/重排。',
        '- B使用既有`mlx_vlm.structured.build_json_schema_logits_processor`，通过`mlx_lm.stream_generate(logits_processors=[...])`接入。后端版本：mlx-vlm 0.6.5、llguidance 1.7.6；Backend schema来自原冻结文件，无case-specific gold、实体位置或候选筛选。Schema不作为B的模型文本。',
        '- 完整Schema对Policy/Goal实际可运行；Understanding在首次编译时报告`ValueError: Unimplemented keys: ["uniqueItems"]`，未生成任何token。这一失败原样保留，后续40题未以该后端运行；不是模型0%成绩。另设B-json-only，原生`{"type":"object"}`语法约束，生成同样41个Understanding首答；它不保证五字段Schema。没有自行实现parser、删除uniqueItems冒称完整Schema支持、重试答案或self-correction。',
        '- 每个条件每题一次生成，无跨题KV复用；raw逐条flush后评分。D仅对finish=length的条件扩大预算，复用其已保存的current raw。每条D使用与current完全相同的rendered prompt/解码类型，预算384→768。',
        '- 评分仍在venv310/Python 3.10，MLX推理复用经授权的既有LM Studio Python 3.11环境。加载路径/8bit量化/weight dtypes/库版本/模板设置与baseline逐项一致。辅助Schema只约束既有输出结构/枚举，不按gold缩小语义候选。',
        '- 原baseline记录和配置共48个文件运行前后SHA256相同；271个冻结文件及case/input/gold hashes再次校验通过。原raw、official report、gold/scorer和prompt version未覆盖。当前展示原raw上的新字段诊断，不重写任何正式成绩。', '',
        '### 指标定义', '',
        '`strict JSON valid`要求整个raw可被原json_strict读取；不剥围栏、不取子串、不修复。`schema valid`是原输出Schema；`contract valid`还检查候选、span及字段组合。`完整语义匹配`用未修改的frozen evaluate/structured_match，调用结果全标diagnostic_only，未生成新的official-report。', '',
        '字段准确率：Goal title去首尾空白；objective原atoms多集合相等；success_criteria descriptions多集合相等。Understanding五字段按原合同逐项相等，dimensions忽略顺序。分母包含所有预定样本和所有要求字段，截断/无输出不悄悄剔除。', '',
        'constraint/negative retention按gold原文atom在objective中的出现计算；negative集合是包含不/别/勿/禁止/只/仅/无需/暂缓的objective atoms，共42条（包括独占范围）。这是字面保留下界，同义改写可能被低估。out-of-profile或不在原输入中的值只标unsupported/needs_review，不一律声称已证实幻觉；明显复制无关示例产物另列。', '',
        '## Probe A / B：格式合法与语义交付分开看', '',
        '| 任务/条件 | N | 严格JSON | Schema合法 | 合同合法 | 完整语义匹配 | 字段micro | length |',
        '|---|---:|---:|---:|---:|---:|---:|---:|'
    ]
    for task in ('goal_summary','question_understanding','policy_select'):
        for arm,label in (('original','原提示/旧raw'),('A','简化'),('B','简化+完整Schema'),('B_json','简化+JSON语法')):
            if task not in sums[arm]: continue
            s=sums[arm][task]
            if s.get('available') is False:
                text.append(f'| {task} / {label} | 41预定、0生成 | 不支持 | 不支持 | — | — | — | — |')
                continue
            text.append(f"| {task} / {label} | {s['N']} | {s['json_valid']}/{s['N']} | {s['schema_valid']}/{s['N']} | {s['contract_valid']}/{s['N']} | {s['complete_semantic_match']}/{s['N']} | {pct(s['field_accuracy_micro'])} | {s['length_count']}/{s['N']} |")
    text += ['', 'Goal原提示40条都是合法JSON，主要错误是39条把Schema本身当作答案输出；减负后39/40可通过合同，但没有一条正确保留全部目标、限制和检查项。因此不能把Goal失败主要解释为JSON语法问题。约束解码在有限预算内也不能保证完整JSON：B的3条仍length，不是解析器修复后成功。', '',
             '### Goal字段、限制与无关值', '',
             '| 条件 | title | objective完整atoms | criteria完整atoms | 限制保留 | 否定/独占范围保留 | 原字段之外的key病例 | unsupported值病例 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm,label in (('original','原提示'),('A','简化'),('B','简化+完整Schema')):
        s=sums[arm]['goal_summary'];c=s['constraints_retention'];n=s['negative_retention']
        text.append(f"| {label} | {s['fields']['title']['correct']}/40 | {s['fields']['objective']['correct']}/40 | {s['fields']['success_criteria']['correct']}/40 | {c['hit']}/{c['total']} ({pct(c['rate'])}) | {n['hit']}/{n['total']} ({pct(n['rate'])}) | {s['invented_field_cases']}/40 | {s['unsupported_value_cases']}/40 |")
    text += ['', 'A有26/40把独立示例的“列出反应式”写进实际success_criteria，B为18/40；这些40个原输入均未要求这个产物。A另有10条照搬“不讨论呼吸作用”、24条出现“周末前完成”（是否为无依据期限需结合原输入；计数不是全部幻觉数）。示例复制是明确新增干扰，不能把本轮称为0.8B的最佳可能语义上限。', '',
             '例如TRB0-0085输入要求“只学第一章、不用其他教材、列出概念之间的联系”，A抓对检查项，却加入“不讨论呼吸作用；周末前完成”，丢掉不用其他教材。TRB0-0101输入限制“不要自己编题”，A抓对title/检查项，却替换为“不讨论其他内容；周末前完成”。A仅4条检查项完整匹配，逐条复核仍有明确限制丢失/添加；完整0/40不能只解释为同义改写受罚。', '',
             '### Understanding字段与错误引用', '',
             '| 条件 | action | intent | dimensions | entity_spans | reference_id |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for arm,label in (('original','原提示'),('A','简化'),('B_json','简化+JSON语法')):
        s=sums[arm]['question_understanding'];f=s['fields']
        text.append('| '+label+' | '+' | '.join(f"{f[key]['correct']}/41" for key in ('action','intent','dimensions','entity_spans','reference_id'))+' |')
    text += ['', 'A五字段micro为29.27%，其中41个reference_id成功只是正确留空；去掉这个全部相同字段，其他四字段仅19/164=11.59%。B-json-only五字段micro为8.29%；其他四字段17/164=10.37%。不能用留空成功证明历史指代能力。', '',
             'A的41条全部选择clarify，实体位置从未匹配；样例出现start=end=0。B-json-only全部选择clarify并引用r0，样例entity_spans为空。原题明确提到当前对象且没有允许引用/澄清的gate；r0虽是既有候选，却不是本题合法引用。这是错误对象/动作使用，不是新造候选。', '',
             'A有41/41 unsupported值/无效span flag；B-json-only有20/41 enum/type/grounding flag，其余错误引用不计“发明值”，但仍全部合同拒绝。两组没有额外字段。完整Schema Understanding后端不可用，不能宣称已经测得“全部Schema错误消除后”的Understanding上限。', '',
             '### Policy小样本：有效说明能激活部分语义，但槽位偏好还在', '',
             '原20题12/20；A 15/20；B 14/20。A只新增TRB0-0005、TRB0-0009、TRB0-0049三题正确，没有丢失旧正确题；B新增0005、0049。三题分别涉及改口、先查记录不凭印象、真实查记录而非通用技巧。A仍17/20选择a1，B为18/20；该20题始终选a1的基线是12/20。', '',
             '因此0.8B有部分可响应明确提示的选择能力，不能称完全不理解；这里的主要变化来自更明确的任务/工具说明及去Schema提示，不能单独归因于JSON格式。定向样本、暴露状态和family相似性使15/20不能替代原40/80或充当训练验收。', '',
             '## Probe C：40个原Policy错误审计', '',
             '主类互斥、合计40。附加线索可重叠；识别出否定或引用语句不等于证明模型因该机制而错。由于原输出只有action_id，40例的认知根因均标root_cause_needs_review，不能可靠区分用户意图理解与候选工具描述理解。', '',
             '| 类别 | 确认可观察主类 | 附加表面线索 | needs_review说明 |',
             '|---|---:|---:|---|']
    for category in CATEGORIES:
        c=audit['categories'][category]
        note='40例认知根因待复核，0表示未可靠确认该原因' if category in ('user intent misunderstanding','candidate-description misunderstanding') else '线索归类，不能独立证明因果' if category in ('negation/correction failure','reference/context misunderstanding') else 'TRB0-0066原文含相反顺序，保留gold待复核' if category=='ambiguous / potentially disputable gold' else '按原gold比较可观察动作差异'
        text.append(f"| {category} | {c['primary_count']} | {c['surface_count']} | {note} |")
    text += ['', '各类case IDs：']
    for category in CATEGORIES:
        c=audit['categories'][category]
        text.append(f"- **{category}**：主类 {', '.join(c['primary_ids']) or '无可靠确认'}；附加线索 {', '.join(c['surface_ids']) or '无'}。")
    text += ['', '原始输入、候选、gold、模型选择和每例理由全部在文末附录；机器记录见本报告的证据链接。TRB0-0066的gold按末句“先调题目列表”选择习题，是可解释的标注；将它标needs_review只表示前半句和末句有顺序冲突，不声明gold错误，也不从正式分母中删除。', '',
             '### Qwen / Rule错误互补性', '',
             '| 比较 | count / 80 |', '|---|---:|']
    for key,record in audit['overlap'].items():text.append(f"| {key} | {record['count']}/80 |")
    text += ['', 'Rule来源是原冻结curator中的rule_prediction，本轮未执行已变化的生产Runtime规则。Rule原80题全部a0；Qwen为a1×79、a2×1；gold为a0×39、a1×41。两者同对0、独有对79、同错TRB0-0074。',
             '这个分布强烈支持“不同候选位置先验造成表面互补”，尚未证明两者各自有互补的语义专长。Policy候选顺序不是随机重新排列，本轮也没有做候选重排探针；因此这里是基于观测的诊断推论，因果结论仍需其他独立实验。', '',
             '## Probe D：只扩大length样本的预算', '',
             '| 来源条件 | length样本 | 384预算JSON / 完整匹配 | 768预算JSON / 完整匹配 | 768仍length |',
             '|---|---:|---:|---:|---:|']
    for source in ('original','A','B'):
        cur=m['budget_summary'][source]['current'];double=m['budget_summary'][source]['double']
        text.append(f"| {source} | {cur['N']} | {cur['json_valid']} / {cur['complete_semantic_match']} | {double['json_valid']} / {double['complete_semantic_match']} | {double['length_count']}/{double['N']} |")
    text += ['', '原11条均为Understanding：8 primary、3 secondary；secondary包含原locked intent冲突样本，不混入primary语义成绩。A新增length为Goal TRB0-0106；B新增Goal length为0082、0105、0106；B-json-only无length。所有正常stop病例均未扩大预算。',
             '预算翻倍没有恢复任何完整输出。原Understanding在768预算下继续生成重复/越界实体数组或错误dimensions类型；Goal继续在objective中重复“不讨论其他采样方法”等限制。观测更符合“偏离合同后持续展开/重复”，而非短一点就可正确收尾的答案。不能证明任何更大预算都无用，但384→768没有支持预算不足是当前低分主因。', '',
             '## 职责与训练价值判断', '',
             '| 职责 | 本轮依据 | 当前判断 |', '|---|---|---|',
             '| Policy selection | 明确说明后20题60%→75%；原80题50%，a1偏好仍明显 | 四者中最值得有限研究；尚不可靠，也未达到稳定prior证据 |',
             '| semantic extraction | Goal核心title 57.5%–62.5%；Understanding intent约27%–29%、dimension约15%–17%；实体/动作仍0 | 有零散信息提取；不足以承担五字段理解或可信限制抽取 |',
             '| Goal transformation | 完整0/40；限制字面保留约36%–37%，否定/独占约17%–21%；复制无关产物 | 当前不适合整理可信Goal契约 |',
             '| reference/context resolution | 原secondary旧resolver失败；新primary引用只应留空，无正向历史指代选择样本；JSON-only反而误用r0 | 没有支持接管的证据，也不能从本轮推断所有历史指代能力 |', '',
             '当前不支持把大量U解释成“纯格式损失、训练一下JSON即可解决”。原Schema提示确实造成可观测的复制/结构负担；去掉它后，输出形状改善与语义交付改善分离。Goal示例污染、条件丢失、Understanding错误clarify/引用和Policy槽位偏好都需要实质验证。',
             '证据不足以启动面向全部Runtime职责的LoRA/SFT；如果后续仅研究Policy训练，也需要打破候选槽位偏好、用独立family/未曝光数据检验否定/纠正/顺序能力，并单独确认训练收益。这些只是本次结论的条件，不是新增实施任务。', '',
             '## 证据与完整性', '',
             f'- [诊断配置/预定病例/提示词版本]({evidence}/experiment.json)',
             f'- [A原始requests]({evidence}/arm-A/requests.jsonl)、[A raw]({evidence}/arm-A/outputs.jsonl)',
             f'- [B原生解码与uniqueItems错误记录]({evidence}/arm-B/run.json)、[B raw]({evidence}/arm-B/outputs.jsonl)',
             f'- [Understanding JSON-only raw]({evidence}/arm-B_json/outputs.jsonl)',
             f'- [预算选择规则与条件]({evidence}/budget-selection.json)、[D raw]({evidence}/arm-D/outputs.jsonl)',
             f'- [逐字段诊断指标]({evidence}/diagnostic-metrics.json)、[40例Policy机器审计]({evidence}/probe-C-audit.json)',
             f'- [baseline未改变校验]({evidence}/baseline-integrity.json)',
             '- 记录类型全部diagnostic_only；原正式成绩仍是primary 40/161、semantic_all 40/200。无best-of、修复后official重评分、LoRA、dashboard、生产接入或Harness接口扩建。', '',
             '## 附录：40个原Policy错误的逐例依据', '',
             '每例input保持原字段；candidates即input.admissible_actions，下面直接包含在原input中。主类、附加线索、needs_review和理由均可追溯。认知根因的needs_review不因可观察动作主类明确而解除。', '']
    for index,case in enumerate(audit['cases'],1):
        text += [f"### {index}. {case['id']} — {case['primary_category']}", '',
                 f"附加线索：{', '.join(case['secondary_surface_categories']) or '无可靠线索'}。gold/歧义复核：{case['needs_review']}；认知根因复核：True。",
                 case['concise_reason'], '', '```json',
                 json.dumps({key:case[key] for key in ('input','gold','model_choice','rule_choice')},ensure_ascii=False,indent=2), '```', '']
    target.write_text('\n'.join(text)+'\n')
    return target
