import React from 'react';
import { displayNumber, type SourceChapterGroup } from '../../utils/citations';

export const SourceGroupList: React.FC<{ groups: SourceChapterGroup[]; cited: boolean }> = ({ groups, cited }) => (
  <div className="space-y-2.5">
    {groups.map((group) => (
      <section key={group.key}>
        <div className="mb-1 text-[11px] font-semibold leading-5 text-text-primary">
          <span className="study-source-book">{group.bookName}</span><span className="study-source-separator"> · </span><span>{group.chapter}</span>
        </div>
        <ul className="space-y-1 border-l border-border pl-2.5">
          {group.locations.map((location) => {
            const path = location.path[0] === group.chapter ? location.path.slice(1) : location.path;
            const locationText = path.length > 0
              ? path.join(' › ')
              : location.fallbackLabel || '章级概述';
            const numberText = location.citationNumbers.map(displayNumber).join('');
            const pageText = location.pageIdx >= 0 ? ` · p.${location.pageIdx + 1}` : '';
            const mergedText = location.sources.length > 1 ? ` · 合并 ${location.sources.length} 段` : '';
            return (
              <li key={location.key} className="flex gap-1.5 text-xs leading-relaxed text-text-secondary">
                <span className={`shrink-0 select-none ${cited ? 'text-accent' : 'text-text-tertiary'}`}>
                  {cited ? numberText : '·'}
                </span>
                <span className="min-w-0">{locationText}{pageText}{mergedText}</span>
              </li>
            );
          })}
        </ul>
      </section>
    ))}
  </div>
);
