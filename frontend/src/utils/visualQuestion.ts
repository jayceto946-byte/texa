/** Display only the recognized stem/options; visual evidence stays in task assets. */
const escapedTexCommands = new Set([
  'frac', 'fbox', 'forall', 'begin', 'beta', 'bar', 'boldsymbol', 'mathbf', 'big', 'Big',
  'bigl', 'bigr', 'bigg', 'biggl', 'biggr', 'binom', 'boxed', 'bullet', 'backslash',
  'text', 'textbf', 'textrm', 'textit', 'theta', 'times', 'tau', 'tan', 'tanh', 'to',
  'tfrac', 'tilde', 'triangle', 'top', 'tiny', 'tag', 'right', 'rightarrow', 'rangle',
  'rceil', 'rfloor', 'rho', 'rm', 'nabla', 'nu', 'neq', 'ne', 'not', 'notin', 'neg', 'newcommand',
]);
const needsCorrection = '题干识别结果需要重新校对，请对照原图补全。';

/** The chat bubble is the user's request. OCR belongs to task evidence. */
export function visualUserQuestion(content: string, question?: string): string {
  const marker = /(?:图片题干（识别文本，请校对）|补充图片题干)\s*[：:]/;
  const request = (question || content).split(marker)[0].trim();
  return !request || isVisualEnvelope(request) ? '请解答图片中的问题。' : request;
}

function isVisualEnvelope(text: string): boolean {
  return /"schema_version"\s*:\s*"visual-problem-ir\//.test(text)
    || (/"problem_text"\s*:/.test(text) && /"(?:visual_type|visual_summary|entities|relations)"\s*:/.test(text));
}

// Older OCR providers emitted single TeX backslashes in JSON strings. Preserve
// already escaped pairs, including newlines, quotes and Unicode escapes.
function repairVisualJsonEscapes(text: string): string {
  let result = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '"') quoted = !quoted;
    if (quoted && ch === '\\' && i + 1 < text.length) {
      const next = text[i + 1];
      const name = text.slice(i + 1).match(/^[A-Za-z]+/)?.[0] || '';
      if (!'"\\/bfnrtu'.includes(next) || escapedTexCommands.has(name)
        || (next === 'u' && !/^[0-9a-fA-F]{4}/.test(text.slice(i + 2)))) {
        result += '\\\\';
        continue;
      }
      result += text.slice(i, i + 2);
      i += 1;
      continue;
    }
    // JSON permits these only as escapes; OCR sometimes emits literal lines.
    result += quoted && ch === '\n' ? '\\n' : quoted && ch === '\r' ? '\\r' : quoted && ch === '\t' ? '\\t' : ch;
  }
  return result;
}

function envelopeQuestion(content: string, depth = 0): string | null {
  if (!isVisualEnvelope(content)) return null;
  if (depth >= 3) return needsCorrection;
  try {
    const start = content.indexOf('{');
    const end = content.lastIndexOf('}');
    const data: unknown = JSON.parse(repairVisualJsonEscapes(content.slice(start, end + 1)));
    if (!data || typeof data !== 'object' || Array.isArray(data)) return needsCorrection;
    const ir = data as Record<string, unknown>;
    const stem = typeof ir.problem_text === 'string' ? ir.problem_text.trim() : '';
    const nested = envelopeQuestion(stem, depth + 1);
    const text = nested ?? stem;
    const options = Array.isArray(ir.options) ? ir.options.filter((v): v is string => typeof v === 'string' && Boolean(v.trim()) && !text.includes(v)) : [];
    return [text, options.join('\n')].filter(Boolean).join('\n\n') || needsCorrection;
  } catch {
    // A broken envelope is not OCR prose. Do not expose or invent its contents.
    return needsCorrection;
  }
}

export function readableVisualQuestion(content: string, brokenText = needsCorrection): string {
  const question = envelopeQuestion(content);
  if (question !== null) return question === needsCorrection ? brokenText : question;
  const session = /图片题干（识别文本，请校对）|补充图片题干/.test(content);
  // Compatibility with frozen visual-session prose, without changing storage.
  return content.replace(/^(实体|关系|标注|图形说明|图形条件|图中标注|用户标记|公式|选项|手写作答|识别不确定项|所需材料|待补充材料)：\s*\n([\s\S]*?)(?=\n\s*\n|$)/gm, (block, label: string, value: string) => {
    if (session && label !== '选项') return '';
    try {
      const parsed: unknown = JSON.parse(value);
      if (!Array.isArray(parsed)) return block;
      if (label === '实体') return '';
      const lines = parsed.filter((item): item is string => typeof item === 'string');
      return lines.length ? `${label}：\n${lines.join('\n')}\n` : '';
    } catch { return block; }
  }).replace(/\n{3,}/g, '\n\n').trim();
}
