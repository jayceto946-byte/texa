import type { VisualRegion } from '../../types';

const clamp = (value: number) => Math.max(0, Math.min(1, value));

export function normalizedPoint(clientX: number, clientY: number, rect: DOMRect): { x: number; y: number } {
  return {
    x: clamp((clientX - rect.left) / Math.max(1, rect.width)),
    y: clamp((clientY - rect.top) / Math.max(1, rect.height)),
  };
}

export function regionFromPoints(
  start: { x: number; y: number },
  end: { x: number; y: number },
  clickSize = 0.16,
): VisualRegion {
  if (Math.abs(start.x - end.x) < 0.005 && Math.abs(start.y - end.y) < 0.005) {
    const half = clickSize / 2;
    return {
      x1: clamp(start.x - half), y1: clamp(start.y - half),
      x2: clamp(start.x + half), y2: clamp(start.y + half),
    };
  }
  return {
    x1: Math.min(start.x, end.x), y1: Math.min(start.y, end.y),
    x2: Math.max(start.x, end.x), y2: Math.max(start.y, end.y),
  };
}

export function moveRegion(region: VisualRegion, dx: number, dy: number): VisualRegion {
  const width = region.x2 - region.x1;
  const height = region.y2 - region.y1;
  const x1 = clamp(Math.min(1 - width, region.x1 + dx));
  const y1 = clamp(Math.min(1 - height, region.y1 + dy));
  return { x1, y1, x2: x1 + width, y2: y1 + height };
}

export function resizeRegion(region: VisualRegion, dx: number, dy: number): VisualRegion {
  return {
    ...region,
    x2: clamp(Math.max(region.x1 + 0.01, region.x2 + dx)),
    y2: clamp(Math.max(region.y1 + 0.01, region.y2 + dy)),
  };
}

export function regionStyle(region: VisualRegion): Record<string, string> {
  return {
    left: `${region.x1 * 100}%`,
    top: `${region.y1 * 100}%`,
    width: `${(region.x2 - region.x1) * 100}%`,
    height: `${(region.y2 - region.y1) * 100}%`,
  };
}
