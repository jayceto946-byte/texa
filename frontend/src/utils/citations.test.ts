import { describe, expect, it } from 'vitest';
import { CITATION_TOKEN_RE, displayNumber, groupSourcesByLocation, normalizeCitationTokens, parseCitations, partitionSources } from './citations';
import type { AssistantSource } from '../types';

const src = (id: string): AssistantSource => ({ id, book_name: '传感器短书', label: `${id} 的教材位置` });

describe('parseCitations', () => {
  it('把 [[cite:E1]] 转换为上标 ¹（TEST 2）', () => {
    const { text, order } = parseCitations('热敏电阻具有灵敏度高、响应快等特点。[[cite:E1]]');
    expect(text).toBe('热敏电阻具有灵敏度高、响应快等特点。¹');
    expect(order.get('E1')).toBe(1);
  });

  it('编号按正文首次引用顺序派生，与模型无关（TEST 8）', () => {
    const body = 'A[[cite:E4]] B[[cite:E2]] C[[cite:E4]]';
    const { text, order } = parseCitations(body);
    expect(order.get('E4')).toBe(1);
    expect(order.get('E2')).toBe(2);
    // 同一 id 复用同一编号
    expect(text).toBe('A¹ B² C¹');
  });

  it('非法 id（不在 validIds）被忽略，不创建假引用（TEST 7）', () => {
    const valid = new Set(['E1']);
    const { text, order } = parseCitations('正文[[cite:E1]] 错误[[cite:E999]]', valid);
    expect(text).toBe('正文¹ 错误');
    expect(order.has('E999')).toBe(false);
  });

  it('validIds 为空时全部视为合法（流式阶段）', () => {
    const { text, order } = parseCitations('x[[cite:E3]]', undefined);
    // 编号按首次引用顺序派生，E3 首个出现 → ¹
    expect(text).toBe('x¹');
    expect(order.get('E3')).toBe(1);
  });

  it('连续引用折叠形式 [[cite:E1][cite:E5]] 不泄漏协议文本（TEST 9）', () => {
    const { text, order } = parseCitations('压阻效应具有灵敏度高、响应快的特点。[[cite:E1][cite:E5]]');
    // 两个引用都被替换为上标，正文不暴露 [[cite:...]]
    expect(text).toBe('压阻效应具有灵敏度高、响应快的特点。¹²');
    expect(order.get('E1')).toBe(1);
    expect(order.get('E5')).toBe(2);
  });

  it('折叠形式与合法 id 集合结合时，非法 id 被剔除不创建假上标', () => {
    const valid = new Set(['E1']);
    const { text, order } = parseCitations('正文[[cite:E1][cite:E999]]', valid);
    expect(text).toBe('正文¹');
    expect(order.has('E999')).toBe(false);
  });

  it('三段连续折叠 [[cite:E1][cite:E5][cite:E7]] 全部替换', () => {
    const { text, order } = parseCitations('A[[cite:E1][cite:E5][cite:E7]]B');
    expect(text).toBe('A¹²³B');
    expect([...order.keys()]).toEqual(['E1', 'E5', 'E7']);
  });

  it('兼容历史消息中的全角与半角混合引用标记', () => {
    const body = 'A［[cite:E7]］ B［［cite:E1］］';
    expect(normalizeCitationTokens(body)).toBe('A[[cite:E7]] B[[cite:E1]]');
    const { text, order } = parseCitations(body, new Set(['E1', 'E7']));
    expect(text).toBe('A¹ B²');
    expect([...order.keys()]).toEqual(['E7', 'E1']);
  });
});

describe('partitionSources', () => {
  it('被引用的进 cited，未引用的进 references（TEST 5/6）', () => {
    const order = new Map([['E1', 1], ['E2', 2]]);
    const { cited, references } = partitionSources([src('E1'), src('E2'), src('E3')], order);
    expect(cited.map((s) => s.id)).toEqual(['E1', 'E2']);
    expect(references.map((s) => s.id)).toEqual(['E3']);
  });

  it('无 citation 时全部归入 references，不产生假上标（TEST 5）', () => {
    const { cited, references } = partitionSources([src('E1')], new Map());
    expect(cited).toEqual([]);
    expect(references.map((s) => s.id)).toEqual(['E1']);
  });

  it('cited 按正文首次引用编号排序，不沿用检索顺序', () => {
    const order = new Map([['E5', 1], ['E3', 2], ['E1', 3]]);
    const { cited } = partitionSources([src('E1'), src('E3'), src('E5')], order);
    expect(cited.map((source) => source.id)).toEqual(['E5', 'E3', 'E1']);
  });
});

describe('groupSourcesByLocation', () => {
  it('按教材与章节分组，并合并同一位置的多个证据段', () => {
    const sources: AssistantSource[] = [
      {
        id: 'E2', book_name: '传感器短书', chapter: '第六章 压电式传感器',
        section_title: '第三节 压电式传感器的应用举例',
        section_path: ['第六章 压电式传感器', '第三节 压电式传感器的应用举例'],
        page_idx: 8,
      },
      {
        id: 'E4', book_name: '传感器短书', chapter: '第六章 压电式传感器',
        section_title: '第三节 压电式传感器的应用举例',
        section_path: ['第六章 压电式传感器', '第三节 压电式传感器的应用举例'],
        page_idx: 8,
      },
    ];

    const groups = groupSourcesByLocation(sources, new Map([['E4', 1], ['E2', 2]]));

    expect(groups).toHaveLength(1);
    expect(groups[0].chapter).toBe('第六章 压电式传感器');
    expect(groups[0].locations).toHaveLength(1);
    expect(groups[0].locations[0].sources).toHaveLength(2);
    expect(groups[0].locations[0].citationNumbers).toEqual([1, 2]);
  });

  it('章名与节名相同时只保留一次路径', () => {
    const groups = groupSourcesByLocation([{
      id: 'E1', book_name: '传感器短书', chapter: '第六章 压电式传感器',
      section_title: '第六章 压电式传感器', section_path: [],
    }]);
    expect(groups[0].locations[0].path).toEqual(['第六章 压电式传感器']);
  });

  it('跨章节交错引用仍按正文编号严格递增', () => {
    const sources: AssistantSource[] = [
      { id: 'E1', book_name: '短书', chapter: '第六章', section_title: '第一节' },
      { id: 'E2', book_name: '短书', chapter: '第六章', section_title: '第二节' },
      { id: 'E3', book_name: '短书', chapter: '第十章', section_title: '第一节' },
      { id: 'E4', book_name: '短书', chapter: '第六章', section_title: '第三节' },
    ];
    const order = new Map([['E1', 1], ['E2', 2], ['E3', 3], ['E4', 4]]);

    const groups = groupSourcesByLocation(sources, order);
    const displayed = groups.flatMap((group) => group.locations.flatMap((location) => location.citationNumbers));

    expect(displayed).toEqual([1, 2, 3, 4]);
    expect(groups.map((group) => group.chapter)).toEqual(['第六章', '第十章', '第六章']);
  });
});

describe('displayNumber', () => {
  it('1-9 用上标，超过用 [n]', () => {
    expect(displayNumber(1)).toBe('¹');
    expect(displayNumber(9)).toBe('⁹');
    expect(displayNumber(10)).toBe('[10]');
  });
});

describe('CITATION_TOKEN_RE', () => {
  it('不会匹配 markdown 链接或其他 [[ ]]', () => {
    expect('[[cite:E1]]'.match(CITATION_TOKEN_RE)).not.toBeNull();
    expect('[[wiki:foo]]'.match(CITATION_TOKEN_RE)).toBeNull();
    expect('[link](url)'.match(CITATION_TOKEN_RE)).toBeNull();
  });
});
