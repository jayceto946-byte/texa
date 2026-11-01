export function replaceSourceText(source: string, start: number, end: number, replacement: string) {
  return source.slice(0, start) + replacement + source.slice(end);
}

export function replaceSourceFormula(source: string, start: number, end: number, latex: string, display: boolean, remove = false) {
  let replacement = remove ? '' : display ? `$$\n${latex.trim()}\n$$` : `$${latex.trim()}$`;
  if (!remove && display && start === end) replacement = `${start ? '\n\n' : ''}${replacement}\n\n`;
  return replaceSourceText(source, start, end, replacement);
}
