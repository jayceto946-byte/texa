import { describe, expect, it } from 'vitest';

import { insertFormulaReference } from './formulaReferences';

describe('insertFormulaReference', () => {
  it('inserts a compact formula reference at the current cursor', () => {
    expect(insertFormulaReference('请用计算', 2, 2, 2)).toEqual({
      text: '请用公式2计算',
      cursor: 5,
    });
  });

  it('replaces the current selection and clamps invalid offsets', () => {
    expect(insertFormulaReference('比较这一项', 1, 2, 5)).toEqual({
      text: '比较公式1',
      cursor: 5,
    });
    expect(insertFormulaReference('', 3, 99, 120)).toEqual({ text: '公式3', cursor: 3 });
  });
});
