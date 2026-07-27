import type { MathTemplate } from './mathTemplates';

const TEMPLATE_MARKER_PATTERN = /\[\[(selection|cursor)\|[\s\S]*?\]\]/g;

export function templateToEditorLatex(template: MathTemplate): string {
  let latex = template.value.trim();
  if (latex.startsWith('$$') && latex.endsWith('$$')) latex = latex.slice(2, -2).trim();
  else if (latex.startsWith('$') && latex.endsWith('$')) latex = latex.slice(1, -1).trim();
  return latex.replace(TEMPLATE_MARKER_PATTERN, '\\placeholder{}');
}

export function hasUnfilledPlaceholder(latex: string): boolean {
  return /\\placeholder\s*\{[^}]*\}/.test(latex);
}
