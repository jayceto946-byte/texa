import type { MathExpression } from './types';

export function composeMathQuestion(text: string, expressions: MathExpression[]): string {
  const parts: string[] = [];
  const normalizedText = text.trim();
  if (normalizedText) parts.push(normalizedText);

  expressions.forEach((expression, index) => {
    const latex = expression.latex.trim();
    if (!latex) return;
    const label = `公式 ${index + 1}：`;
    parts.push(expression.displayMode ? `${label}\n\n$$\n${latex}\n$$` : `${label}$${latex}$`);
  });

  return parts.join('\n\n');
}
