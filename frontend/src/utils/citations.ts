import type { AssistantSource } from '../types';

/**
 * Citation 协议：模型在正文句末输出 [[cite:E<id>]]，id 是证据块编号（E1…）。
 * 展示编号由正文首次引用顺序派生，与模型无关；display number 不是 source identity。
 *
 * 模型在连续引用时可能输出折叠形式 [[cite:E1][cite:E5]]（共享一对 [[ ]]），
 * 该正则同时匹配标准形式与折叠形式：单引用、连续引用、多引用均被替换，
 * 保证正文中不暴露 [[cite:...]] / [cite:...] 等内部协议。
 */
export const CITATION_TOKEN_RE = /\[\[cite:(E[\w-]+)\](?:\[cite:(E[\w-]+)\])*\]/g;

// New answers are canonicalized by the backend. This compatibility pattern
// also accepts saved model variants such as ［[cite:E7]］ and folded groups.
const CITATION_GROUP_RE = /[［[]{2}\s*cite\s*:\s*E[\w-]+\s*[］\]](?:\s*[［[]\s*cite\s*:\s*E[\w-]+\s*[］\]])*\s*[］\]]/gi;
const CITATION_ID_RE = /cite\s*:\s*(E[\w-]+)/gi;

const SUPERSCRIPTS = ['¹', '²', '³', '⁴', '⁵', '⁶', '⁷', '⁸', '⁹'];

export function displayNumber(n: number): string {
  if (n >= 1 && n <= 9) return SUPERSCRIPTS[n - 1];
  return `[${n}]`;
}

function collectIds(token: string): string[] {
  return Array.from(token.matchAll(CITATION_ID_RE), (match) => match[1].toUpperCase());
}

export function normalizeCitationTokens(content: string): string {
  return content.replace(CITATION_GROUP_RE, (token) => (
    collectIds(token).map((id) => `[[cite:${id}]]`).join('')
  ));
}

/**
 * 将正文中的 [[cite:E<id>]] 转换为展示上标。
 * - order: id -> 首次出现编号（1 起）
 * - text: 转换后的正文；合法 id 替换为上标，非法 id（不在 validIds）移除 token
 * - validIds 为空/未提供时视为全部合法（流式阶段尚未拿到最终 sources）
 */
export function parseCitations(
  content: string,
  validIds?: Set<string>,
): { text: string; order: Map<string, number> } {
  const order = new Map<string, number>();
  let next = 1;
  const text = normalizeCitationTokens(content).replace(CITATION_TOKEN_RE, (token: string) => {
    const ids = collectIds(token);
    return ids
      .map((id) => {
        if (validIds && validIds.size > 0 && !validIds.has(id)) return '';
        if (!order.has(id)) order.set(id, next++);
        return displayNumber(order.get(id)!);
      })
      .join('');
  });
  return { text, order };
}

/**
 * 把 sources 分为“已被正文引用”（cited）与“仅检索/使用未引用”（references）。
 * cited 需要 E-id 存在且出现在正文引用顺序中；references 保留在“参考材料”区，不生成假上标。
 */
export function partitionSources(
  sources: AssistantSource[],
  order: Map<string, number>,
): { cited: AssistantSource[]; references: AssistantSource[] } {
  const cited = sources
    .filter((src) => src.id && order.has(src.id))
    .sort((left, right) => (
      (order.get(left.id!) ?? Number.MAX_SAFE_INTEGER)
      - (order.get(right.id!) ?? Number.MAX_SAFE_INTEGER)
    ));
  const references = sources.filter((src) => !src.id || !order.has(src.id));
  return { cited, references };
}

export interface SourceLocationGroup {
  key: string;
  path: string[];
  pageIdx: number;
  fallbackLabel: string;
  citationNumbers: number[];
  sources: AssistantSource[];
}

export interface SourceChapterGroup {
  key: string;
  bookName: string;
  chapter: string;
  locations: SourceLocationGroup[];
}

function cleanSourcePath(source: AssistantSource): string[] {
  const path = Array.isArray(source.section_path) ? source.section_path : [];
  const parts: string[] = [];
  for (const value of path) {
    const part = String(value || '').trim();
    if (part && !parts.includes(part)) parts.push(part);
  }
  const chapter = String(source.chapter || '').trim();
  const section = String(source.section_title || '').trim();
  if (chapter && !parts.includes(chapter)) parts.unshift(chapter);
  if (section && !parts.includes(section)) parts.push(section);
  return parts;
}

/** Group sources by textbook/chapter and merge chunks that share one visible location. */
export function groupSourcesByLocation(
  sources: AssistantSource[],
  citationOrder?: Map<string, number>,
): SourceChapterGroup[] {
  const orderedSources = citationOrder
    ? [...sources].sort((left, right) => (
      (citationOrder.get(left.id || '') ?? Number.MAX_SAFE_INTEGER)
      - (citationOrder.get(right.id || '') ?? Number.MAX_SAFE_INTEGER)
    ))
    : sources;

  // Cited rows must remain globally 1..N even when the answer alternates
  // between chapters. Use consecutive chapter/location runs in that case;
  // retrieval-only material can use compact unique chapter groups.
  if (citationOrder) {
    const groups: SourceChapterGroup[] = [];
    for (const source of orderedSources) {
      const path = cleanSourcePath(source);
      const bookName = String(source.book_name || '教材').trim();
      const chapter = String(source.chapter || path[0] || '未标注章节').trim();
      const chapterIdentity = `${bookName}\u0000${chapter}`;
      let chapterGroup = groups.at(-1);
      if (!chapterGroup || !chapterGroup.key.startsWith(`${chapterIdentity}\u0001`)) {
        chapterGroup = {
          key: `${chapterIdentity}\u0001${groups.length}`,
          bookName,
          chapter,
          locations: [],
        };
        groups.push(chapterGroup);
      }

      const pageIdx = typeof source.page_idx === 'number' ? source.page_idx : -1;
      const fallbackLabel = String(source.label || '').trim();
      const locationIdentity = `${path.join('\u0000')}\u0000${pageIdx}\u0000${path.length ? '' : fallbackLabel}`;
      let location = chapterGroup.locations.at(-1);
      if (!location || !location.key.endsWith(`\u0001${locationIdentity}`)) {
        location = {
          key: `${chapterGroup.key}\u0001${locationIdentity}`,
          path,
          pageIdx,
          fallbackLabel,
          citationNumbers: [],
          sources: [],
        };
        chapterGroup.locations.push(location);
      }
      location.sources.push(source);
      const number = source.id ? citationOrder.get(source.id) : undefined;
      if (number && !location.citationNumbers.includes(number)) {
        location.citationNumbers.push(number);
      }
    }
    return groups;
  }

  const chapterGroups = new Map<string, SourceChapterGroup>();
  const locationMaps = new Map<string, Map<string, SourceLocationGroup>>();

  for (const source of orderedSources) {
    const path = cleanSourcePath(source);
    const bookName = String(source.book_name || '教材').trim();
    const chapter = String(source.chapter || path[0] || '未标注章节').trim();
    const chapterKey = `${bookName}\u0000${chapter}`;
    let chapterGroup = chapterGroups.get(chapterKey);
    if (!chapterGroup) {
      chapterGroup = { key: chapterKey, bookName, chapter, locations: [] };
      chapterGroups.set(chapterKey, chapterGroup);
      locationMaps.set(chapterKey, new Map());
    }

    const pageIdx = typeof source.page_idx === 'number' ? source.page_idx : -1;
    const fallbackLabel = String(source.label || '').trim();
    const locationKey = `${path.join('\u0000')}\u0000${pageIdx}\u0000${path.length ? '' : fallbackLabel}`;
    const locationMap = locationMaps.get(chapterKey)!;
    let location = locationMap.get(locationKey);
    if (!location) {
      location = {
        key: `${chapterKey}\u0001${locationKey}`,
        path,
        pageIdx,
        fallbackLabel,
        citationNumbers: [],
        sources: [],
      };
      locationMap.set(locationKey, location);
      chapterGroup.locations.push(location);
    }
    location.sources.push(source);
  }

  return Array.from(chapterGroups.values());
}
