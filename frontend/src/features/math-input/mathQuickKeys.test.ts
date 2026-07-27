import { describe, expect, it } from 'vitest';

import { mathQuickKeys } from './mathQuickKeys';

describe('mathQuickKeys', () => {
  it('keeps quick keys unique and in one compact group', () => {
    expect(new Set(mathQuickKeys.map((key) => key.id)).size).toBe(mathQuickKeys.length);
    expect(mathQuickKeys).toHaveLength(20);
  });

  it('provides square and cube exponent commands', () => {
    expect(mathQuickKeys.find((key) => key.id === 'square')?.latex).toBe('^2');
    expect(mathQuickKeys.find((key) => key.id === 'cube')?.latex).toBe('^3');
  });
});
