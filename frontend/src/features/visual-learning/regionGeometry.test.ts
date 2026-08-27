import { describe, expect, it } from 'vitest';
import { moveRegion, normalizedPoint, regionFromPoints, resizeRegion } from './regionGeometry';

describe('visual Figure region geometry', () => {
  it('normalizes pointer coordinates against the rendered image rectangle', () => {
    const rect = { left: 100, top: 50, width: 400, height: 200 } as DOMRect;
    expect(normalizedPoint(300, 100, rect)).toEqual({ x: 0.5, y: 0.25 });
  });

  it('keeps drag direction independent and click creates a bounded region', () => {
    expect(regionFromPoints({ x: 0.8, y: 0.7 }, { x: 0.2, y: 0.1 })).toEqual({
      x1: 0.2, y1: 0.1, x2: 0.8, y2: 0.7,
    });
    expect(regionFromPoints({ x: 0.98, y: 0.98 }, { x: 0.98, y: 0.98 })).toEqual({
      x1: 0.9, y1: 0.9, x2: 1, y2: 1,
    });
  });

  it('moves and resizes keyboard regions without leaving normalized space', () => {
    expect(moveRegion({ x1: 0.8, y1: 0.8, x2: 1, y2: 1 }, 0.1, 0.1)).toEqual({
      x1: 0.8, y1: 0.8, x2: 1, y2: 1,
    });
    expect(resizeRegion({ x1: 0.2, y1: 0.2, x2: 0.5, y2: 0.5 }, -1, -1)).toEqual({
      x1: 0.2, y1: 0.2, x2: 0.21000000000000002, y2: 0.21000000000000002,
    });
  });
});
