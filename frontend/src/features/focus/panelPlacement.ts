/** Anchor below the header and keep the reading composer outside the popover. */
export function panelPlacement({ width, mainWidth, headerBottom, headerRight, contentBottom }: {
  width: number; mainWidth: number; headerBottom: number; headerRight: number; contentBottom: number;
}) {
  const top = headerBottom + 8;
  const available = Math.max(0, contentBottom - top - 8);
  return {
    sheet: width <= 760 || mainWidth < 392 || available < 400,
    top,
    right: Math.max(16, width - headerRight + 16),
    maxHeight: Math.min(560, available),
  };
}
