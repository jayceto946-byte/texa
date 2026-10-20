export function scopePopoverLayout({ anchor, viewport, subjectOnly, compact, placement, align }: {
  anchor: { left: number; right: number; top: number; bottom: number };
  viewport: { width: number; height: number };
  subjectOnly: boolean;
  compact: boolean;
  placement: 'top' | 'bottom';
  align: 'left' | 'right';
}) {
  const margin = 12;
  const gap = 6;
  const width = Math.min(subjectOnly ? compact ? 320 : 380 : compact ? 560 : 620, viewport.width - margin * 2);
  const above = Math.max(0, anchor.top - margin - gap);
  const below = Math.max(0, viewport.height - anchor.bottom - margin - gap);
  const openAbove = placement === 'top' ? above >= 200 || above >= below : below < 200 && above > below;
  const maxHeight = Math.min(compact ? 320 : 360, openAbove ? above : below);
  const left = Math.max(margin, Math.min(align === 'right' ? anchor.right - width : anchor.left, viewport.width - width - margin));
  return { width, left, maxHeight, openAbove, edge: openAbove ? viewport.height - anchor.top + gap : anchor.bottom + gap,
    layout: subjectOnly ? 'subjects' : width >= 520 ? 'books' : 'wrapped' };
}
