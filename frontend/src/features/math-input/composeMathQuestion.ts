import type { MathExpression } from './types';

export function composeMathQuestion(text: string, expressions: MathExpression[]): string {
  const normalizedText = text.trim();
  const formulaParts: string[] = [];

  expressions.forEach((expression, index) => {
    const latex = expression.latex.trim();
    if (!latex) return;
    const referenceNumber = expression.referenceNumber ?? index + 1;
    const label = `公式${referenceNumber}：`;
    formulaParts.push(expression.displayMode ? `${label}\n\n$$\n${latex}\n$$` : `${label}$${latex}$`);
  });

  const formulaSection = formulaParts.length
    ? `以下编号与问题中的“公式1”“公式2”等称呼一一对应：\n\n${formulaParts.join('\n\n')}`
    : '';

  return [normalizedText, formulaSection].filter(Boolean).join('\n\n');
}
