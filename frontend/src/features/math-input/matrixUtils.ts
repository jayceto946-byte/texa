export type MatrixEnvironment = 'bmatrix' | 'pmatrix' | 'vmatrix' | 'matrix';

export function createMatrixCells(rows: number, columns: number): string[][] {
  return Array.from({ length: rows }, () => Array.from({ length: columns }, () => ''));
}

export function resizeMatrixCells(cells: string[][], rows: number, columns: number): string[][] {
  return Array.from({ length: rows }, (_, rowIndex) =>
    Array.from({ length: columns }, (_, columnIndex) => cells[rowIndex]?.[columnIndex] ?? ''),
  );
}

export function buildMatrixLatex(cells: string[][], environment: MatrixEnvironment): string {
  const body = cells.map((row) => row.map((cell) => cell.trim()).join(' & ')).join(' \\\\\n');
  return `\\begin{${environment}}\n${body}\n\\end{${environment}}`;
}

export function isMatrixComplete(cells: string[][]): boolean {
  return cells.length > 0 && cells.every((row) => row.length > 0 && row.every((cell) => cell.trim().length > 0));
}
