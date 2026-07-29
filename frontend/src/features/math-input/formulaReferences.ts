export type FormulaReferenceInsertion = {
  text: string;
  cursor: number;
};

export function insertFormulaReference(
  text: string,
  referenceNumber: number,
  selectionStart: number = text.length,
  selectionEnd: number = selectionStart,
): FormulaReferenceInsertion {
  const start = Math.max(0, Math.min(selectionStart, text.length));
  const end = Math.max(start, Math.min(selectionEnd, text.length));
  const token = `公式${referenceNumber}`;
  const nextText = `${text.slice(0, start)}${token}${text.slice(end)}`;
  return { text: nextText, cursor: start + token.length };
}
