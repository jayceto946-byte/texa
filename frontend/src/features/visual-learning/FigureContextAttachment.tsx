import { BookOpen, Images, Scan, X } from 'lucide-react';

import type { FigureArtifact } from '../../types';

export default function FigureContextAttachment({
  figure,
  onEditRegion,
  onOpenSource,
  onRemove,
}: {
  figure: FigureArtifact;
  onEditRegion: () => void;
  onOpenSource: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="composer-figure-context" aria-label="当前教材图片">
      <Images className="h-4 w-4 shrink-0 text-text-secondary" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="composer-figure-caption">{figure.caption || '无图注教材图'}</div>
        <div className="composer-figure-meta">
          {figure.page ? `p.${figure.page}` : '未标页'} · 继续询问时默认使用整图
        </div>
      </div>
      <div className="composer-figure-actions">
        <button type="button" onClick={onEditRegion}>
          <Scan className="h-3.5 w-3.5" aria-hidden="true" />
          <span>查看与框选</span>
        </button>
        <button type="button" onClick={onOpenSource} aria-label="查看教材图来源" title="查看教材图来源">
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
        <button type="button" onClick={onRemove} aria-label="移除教材图" title="移除教材图">
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
