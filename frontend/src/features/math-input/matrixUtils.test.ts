import { describe, expect, it } from 'vitest';

import { buildMatrixLatex, createMatrixCells, isMatrixComplete, resizeMatrixCells } from './matrixUtils';

describe('matrixUtils', () => {
  it('preserves existing values while resizing', () => {
    const resized = resizeMatrixCells([['1', '2'], ['3', '4']], 3, 2);
    expect(resized).toEqual([['1', '2'], ['3', '4'], ['', '']]);
  });

  it('builds a square-bracket matrix', () => {
    expect(buildMatrixLatex([['1', '2'], ['3', '4']], 'bmatrix'))
      .toBe([
        '\\begin{bmatrix}',
        '1 & 2 \\\\',
        '3 & 4',
        '\\end{bmatrix}',
      ].join('\n'));
  });

  it('requires every matrix cell before saving', () => {
    expect(isMatrixComplete(createMatrixCells(2, 2))).toBe(false);
    expect(isMatrixComplete([['1', '0'], ['x', '-1']])).toBe(true);
  });
});
