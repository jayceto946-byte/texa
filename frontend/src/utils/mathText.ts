const chineseRe = /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/;

function normalizeLatexText(text: string): string {
  return text
    .replace(/＄/g, '$')
    .replace(/\\\\\s*\[(?:\d+(?:\.\d+)?)(?:pt|em|ex|mm|cm|in)\]/g, '\\\\')
    .replace(/\\\\\[/g, '\\[')
    .replace(/\\\\\]/g, '\\]')
    .replace(/\\\\\(/g, '\\(')
    .replace(/\\\\\)/g, '\\)')
    .replace(/\r\n/g, '\n');
}

function protectMathAndCode(text: string): { text: string; tokens: string[] } {
  const tokens: string[] = [];
  const protect = (match: string) => {
    const token = `@@MATH_PROTECTED_${tokens.length}@@`;
    tokens.push(match);
    return token;
  };
  return {
    text: text
      .replace(/```[\s\S]*?```/g, protect)
      .replace(/\$\$[\s\S]*?\$\$/g, protect)
      .replace(/\$(?!\$)(?:\\.|[^$\\])*?\$/g, protect)
      .replace(/`[^`]*`/g, protect),
    tokens,
  };
}

function restoreProtected(text: string, tokens: string[]): string {
  return tokens.reduce((acc, token, index) => acc.replace(`@@MATH_PROTECTED_${index}@@`, () => token), text);
}
function convertTexDelimiters(text: string): string {
  return text
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_match, body: string) => '$$\n' + body + '\n$$')
    .replace(/\\\(((?:.|\n)*?)\\\)/g, (_match, body: string) => `$${body}$`);
}

function singleDollarPositions(line: string): number[] {
  const positions: number[] = [];
  for (let index = 0; index < line.length; index += 1) {
    if (
      line[index] === '$'
      && line[index - 1] !== '$'
      && line[index + 1] !== '$'
      && !isEscaped(line, index)
    ) positions.push(index);
  }
  return positions;
}

function repairMultilineInlineMath(text: string): string {
  let inFence = false;
  let inBlockMath = false;
  return text.split('\n').map((originalLine) => {
    let line = originalLine;
    const stripped = line.trim();
    if (stripped.startsWith('```')) {
      inFence = !inFence;
      return line;
    }
    const blockTokens = line.match(/(?<!\\)\$\$/g)?.length || 0;
    if (!inFence && blockTokens % 2 === 1) inBlockMath = !inBlockMath;
    if (inFence || inBlockMath) return line;
    const positions = singleDollarPositions(line);
    if (positions.length === 1) {
      const position = positions[0];
      if (!line.slice(0, position).trim()) line = `${line.trimEnd()}$`;
      else if (!line.slice(position + 1).trim()) line = `$${line.trimStart()}`;
    }
    return line;
  }).join('\n');
}

function wrapBareLatex(text: string): string {
  const { text: unprotected, tokens } = protectMathAndCode(text);
  const withTemperatures = unprotected.replace(
    /(?<![$\\])((?:[A-Za-z][A-Za-z0-9_{}]*\s*=\s*)?[-+]?\d+(?:\.\d+)?\s*\^?\\circ\s*(?:\\text\{C\}|C))(?![$A-Za-z])/g,
    '$$$1$',
  );
  const lines = withTemperatures.split('\n').map((line) => {
    const stripped = line.trim();
    if (
      stripped
      && !stripped.includes('$')
      && /\\(?:approx|text|circ|frac|sqrt|sum|int|Delta|theta|lambda|mu|sigma|mathrm|mathbf)\b/.test(stripped)
      && !containsChineseOutsideBraces(stripped)
    ) {
      return `${line.slice(0, line.length - line.trimStart().length)}$${stripped}$`;
    }
    return line;
  }).join('\n');
  return restoreProtected(lines, tokens);
}
function wrapBareMathEnvironments(text: string): string {
  const { text: unprotected, tokens } = protectMathAndCode(text);
  const envs = 'aligned|align|gathered|gather|cases|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|split|equation';
  const envPattern = new RegExp(`(\\\\begin\\{(?:${envs})\\}[\\s\\S]*?\\\\end\\{(?:${envs})\\})`, 'g');
  return restoreProtected(
    unprotected.replace(envPattern, (_match, body: string) => '$$\n' + body + '\n$$'),
    tokens,
  );
}

function isEscaped(text: string, index: number): boolean {
  let slashCount = 0;
  for (let i = index - 1; i >= 0 && text[i] === '\\'; i -= 1) slashCount += 1;
  return slashCount % 2 === 1;
}

function containsChineseOutsideBraces(text: string): boolean {
  let depth = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '\\') {
      i += 1;
      continue;
    }
    if (ch === '{') depth += 1;
    else if (ch === '}') depth = Math.max(0, depth - 1);
    else if (depth === 0 && chineseRe.test(ch)) return true;
  }
  return false;
}

function balanceDollarMath(text: string): string {
  let result = '';
  let i = 0;
  let inlineOpen = false;
  let blockOpen = false;

  while (i < text.length) {
    if (text[i] !== '$' || isEscaped(text, i)) {
      result += text[i];
      i += 1;
      continue;
    }

    const isBlock = text[i + 1] === '$';
    const token = isBlock ? '$$' : '$';
    const rest = text.slice(i + token.length);

    if (!inlineOpen && !blockOpen) {
      const closeIndex = rest.search(isBlock ? /(?<!\\)\$\$/ : /(?<!\\)\$/);
      const candidate = closeIndex >= 0 ? rest.slice(0, closeIndex) : rest;
      const first = candidate.trimStart()[0];
      if (first && chineseRe.test(first)) {
        result += token.replace(/\$/g, '\\$');
        i += token.length;
        continue;
      }
      if (containsChineseOutsideBraces(candidate) && closeIndex < 0) {
        result += token.replace(/\$/g, '\\$');
        i += token.length;
        continue;
      }
    }

    if (isBlock) blockOpen = !blockOpen;
    else if (!blockOpen) inlineOpen = !inlineOpen;
    result += token;
    i += token.length;
  }

  if (blockOpen) result += '$$';
  if (inlineOpen) result += '$';
  return result;
}

export function prepareMathMarkdown(text: string): string {
  const normalized = convertTexDelimiters(normalizeLatexText(text));
  return balanceDollarMath(wrapBareMathEnvironments(wrapBareLatex(repairMultilineInlineMath(normalized))));
}
