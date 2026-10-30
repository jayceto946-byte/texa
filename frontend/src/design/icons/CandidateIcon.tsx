import type { SVGProps } from 'react';
import { geometry } from './geometry';
import type { Direction, Shape } from './geometry';
export function IconGlyph({ shape, size = 24, ...props }: SVGProps<SVGSVGElement> & { shape: Shape; size?: number }) {
  const paths = size <= 16 && shape.small ? shape.small : shape.paths;
  return <svg {...props} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true" focusable="false">
    {paths.map(([d, filled], index) => <path key={index} d={d} fill={filled ? 'currentColor' : 'none'} stroke={filled ? 'none' : undefined} />)}
  </svg>;
}
export function CandidateIcon({ name, direction, ...props }: SVGProps<SVGSVGElement> & { name: string; direction: Direction; size?: number }) {
  return <IconGlyph {...props} shape={geometry[direction][name]} />;
}
export function svgAsset(name: string, direction: Direction, size: number) {
  const shape = geometry[direction][name];
  const paths = size <= 16 && shape.small ? shape.small : shape.paths;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square" stroke-linejoin="miter">${paths.map(([d, filled]) => `<path d="${d}"${filled ? ' fill="currentColor" stroke="none"' : ''}/>`).join('')}</svg>`;
}
