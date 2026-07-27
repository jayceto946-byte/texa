import type { MathTemplate } from './mathTemplates';

const MARKER_PATTERN = /\[\[(selection|cursor)\|([\s\S]*?)\]\]/g;

export interface MathInsertionResult {
  value: string;
  selectionStart: number;
  selectionEnd: number;
}

interface MaterializedTemplate {
  text: string;
  selectionRange: [number, number] | null;
  cursorRange: [number, number] | null;
}

function materializeTemplate(pattern: string, selectedText: string): MaterializedTemplate {
  let text = '';
  let lastIndex = 0;
  let selectionRange: [number, number] | null = null;
  let cursorRange: [number, number] | null = null;

  for (const match of pattern.matchAll(MARKER_PATTERN)) {
    const index = match.index ?? 0;
    const kind = match[1];
    const fallback = match[2];
    text += pattern.slice(lastIndex, index);

    const replacement = kind === 'selection' && selectedText ? selectedText : fallback;
    const start = text.length;
    text += replacement;
    const range: [number, number] = [start, text.length];

    if (kind === 'selection') selectionRange = range;
    if (kind === 'cursor') cursorRange = range;
    lastIndex = index + match[0].length;
  }

  text += pattern.slice(lastIndex);
  return { text, selectionRange, cursorRange };
}

export function insertMathTemplate(
  currentValue: string,
  selectionStart: number,
  selectionEnd: number,
  template: MathTemplate,
): MathInsertionResult {
  const safeStart = Math.max(0, Math.min(selectionStart, currentValue.length));
  const safeEnd = Math.max(safeStart, Math.min(selectionEnd, currentValue.length));
  const selectedText = currentValue.slice(safeStart, safeEnd);
  const materialized = materializeTemplate(template.value, selectedText);
  const value = currentValue.slice(0, safeStart) + materialized.text + currentValue.slice(safeEnd);
  const targetRange = selectedText
    ? materialized.cursorRange
    : materialized.selectionRange ?? materialized.cursorRange;
  const relativeStart = targetRange?.[0] ?? materialized.text.length;
  const relativeEnd = targetRange?.[1] ?? materialized.text.length;

  return {
    value,
    selectionStart: safeStart + relativeStart,
    selectionEnd: safeStart + relativeEnd,
  };
}
