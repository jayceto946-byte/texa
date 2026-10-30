import { forwardRef } from 'react';
import type { SVGProps } from 'react';
import { texaShapes } from './geometry';

export type TexaIconProps = SVGProps<SVGSVGElement> & { size?: string | number };
/** Production icons keep the approved geometry independent of the design board. */
function createIcon(name: string) {
  const Icon = forwardRef<SVGSVGElement, TexaIconProps>(({ size = 20, children, ...props }, ref) => {
    const shape = texaShapes[name];
    const paths = Number(size) <= 16 && shape.small ? shape.small : shape.paths;
    return <svg aria-hidden="true" focusable="false" {...props} ref={ref} data-texa-icon={name} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="square" strokeLinejoin="miter">
      {paths.map(([d, filled], index) => <path key={index} d={d} fill={filled ? 'currentColor' : 'none'} stroke={filled ? 'none' : undefined} />)}
      {children}
    </svg>;
  });
  Icon.displayName = `TexaIcon(${name})`;
  return Icon;
}
export const TexaSearch = createIcon('search');
export const TexaClose = createIcon('close');
export const TexaBack = createIcon('back');
export const TexaSettings = createIcon('settings');
export const TexaDelete = createIcon('delete');
export const TexaEdit = createIcon('edit');
export const TexaCopy = createIcon('copy');
export const TexaLearning = createIcon('learning');
export const TexaTextbook = createIcon('books');
export const TexaExercises = createIcon('exercises');
export const TexaMistakes = createIcon('mistakes');
export const TexaNotes = createIcon('notes');
export const TexaGoals = createIcon('goals');
export const TexaTextbookRetrieve = createIcon('retrieve');
export const TexaKnowledgeExtract = createIcon('extract');
export const TexaMathVerify = createIcon('verify');
export const TexaExecution = createIcon('agent');
export const TexaCompose = createIcon('compose');
export const TexaSend = createIcon('send');
export const TexaImage = createIcon('image');
