import React, { useRef, useState } from 'react';
import { BookOpen, Focus, Scan, X } from 'lucide-react';
import { useAuthenticatedBlobUrl } from '../../hooks/useAuthenticatedBlobUrl';
import type { FigureArtifact, VisualRegion } from '../../types';
import { moveRegion, normalizedPoint, regionFromPoints, regionStyle, resizeRegion } from './regionGeometry';

type Point = { x: number; y: number };

export default function FigureRegionViewer({
  figure,
  region,
  onRegionChange,
  onOpenSource,
  onClose,
}: {
  figure: FigureArtifact;
  region: VisualRegion | null;
  onRegionChange: (region: VisualRegion | null) => void;
  onOpenSource: () => void;
  onClose: () => void;
}) {
  const asset = useAuthenticatedBlobUrl(figure.image_url);
  const imageRef = useRef<HTMLImageElement>(null);
  const pointerStart = useRef<Point | null>(null);
  const [draft, setDraft] = useState<VisualRegion | null>(null);

  const pointFromEvent = (event: React.PointerEvent): Point | null => {
    const rect = imageRef.current?.getBoundingClientRect();
    return rect ? normalizedPoint(event.clientX, event.clientY, rect) : null;
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !imageRef.current) return;
    const point = pointFromEvent(event);
    if (!point) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointerStart.current = point;
    setDraft(regionFromPoints(point, point));
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!pointerStart.current) return;
    const point = pointFromEvent(event);
    if (point) setDraft(regionFromPoints(pointerStart.current, point));
  };

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!pointerStart.current) return;
    const point = pointFromEvent(event) || pointerStart.current;
    const next = regionFromPoints(pointerStart.current, point);
    pointerStart.current = null;
    setDraft(null);
    onRegionChange(next);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!region || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const amount = event.altKey ? 0.002 : 0.01;
    const dx = event.key === 'ArrowLeft' ? -amount : event.key === 'ArrowRight' ? amount : 0;
    const dy = event.key === 'ArrowUp' ? -amount : event.key === 'ArrowDown' ? amount : 0;
    onRegionChange(event.shiftKey ? resizeRegion(region, dx, dy) : moveRegion(region, dx, dy));
  };

  const visibleRegion = draft || region;
  return (
    <section className="figure-region-workspace" aria-label="教材 Figure 选区">
      <header className="figure-region-header">
        <div className="min-w-0">
          <div className="figure-region-caption">{figure.caption || '无图注 Figure'}</div>
          <div className="figure-region-source">
            {figure.page ? `p.${figure.page}` : '未标页'} · {figure.section_path.join(' › ') || figure.book_name}
          </div>
        </div>
        <div className="figure-region-actions">
          <button type="button" onClick={() => onRegionChange({ x1: 0.375, y1: 0.375, x2: 0.625, y2: 0.625 })}>
            <Focus className="h-3.5 w-3.5" />中心选区
          </button>
          <button type="button" onClick={() => onRegionChange(null)} disabled={!region}>整图</button>
          <button type="button" onClick={onOpenSource}><BookOpen className="h-3.5 w-3.5" />教材页</button>
          <button type="button" onClick={onClose} aria-label="结束查看教材图片"><X className="h-4 w-4" /></button>
        </div>
      </header>
      <div className="figure-region-stage">
        {asset.loading && <div className="figure-region-status">正在读取教材图片…</div>}
        {asset.error && <div className="figure-region-status is-error">{asset.error}</div>}
        {asset.url && (
          <div
            className="figure-region-image-wrap"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onKeyDown={onKeyDown}
            tabIndex={0}
            aria-label={region ? '当前 Figure 选区。方向键移动，Shift 加方向键调整右下边界。' : 'Figure 图片。拖动或点击创建选区。'}
          >
            <img ref={imageRef} src={asset.url} alt={figure.caption || `教材 Figure ${figure.figure_id}`} draggable={false} />
            {visibleRegion && <div className="figure-region-selection" style={regionStyle(visibleRegion)} aria-hidden="true"><Scan className="h-4 w-4" /></div>}
          </div>
        )}
      </div>
      <p className="figure-region-help">
        {region ? '已选择局部。可重新拖框；方向键移动，Shift + 方向键调整大小。' : '拖框选择局部，单击会在当前位置生成选区；不选区域时按整图提问。'}
      </p>
    </section>
  );
}
