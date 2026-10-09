import React, { useEffect, useRef, useState } from 'react';
import { Crop, Loader2, SlidersHorizontal, RotateCw, X } from 'lucide-react';

import { clamp, compressPhotoForUpload, renderProcessedImage, type CropState, type ImageAdjust } from '../imageProcessing';
import { MistakeRange } from './MistakePresentation';

type CropDragMode = 'draw' | 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
type CropDragState = {
  mode: CropDragMode;
  originX: number;
  originY: number;
  startX: number;
  startY: number;
  startCrop: CropState;
};

export const DEFAULT_PROBLEM_CROP: CropState = { x: 5, y: 8, w: 90, h: 78 };
export const DEFAULT_PROBLEM_ADJUST: ImageAdjust = { brightness: 112, contrast: 138, sharpen: 35, grayscale: true };

const cropHandles: { mode: Exclude<CropDragMode, 'draw' | 'move'>; className: string; cursor: string }[] = [
  { mode: 'nw', className: 'left-0 top-0', cursor: 'nwse-resize' },
  { mode: 'n', className: 'left-1/2 top-0 -translate-x-1/2', cursor: 'ns-resize' },
  { mode: 'ne', className: 'right-0 top-0', cursor: 'nesw-resize' },
  { mode: 'e', className: 'right-0 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
  { mode: 'se', className: 'bottom-0 right-0', cursor: 'nwse-resize' },
  { mode: 's', className: 'bottom-0 left-1/2 -translate-x-1/2', cursor: 'ns-resize' },
  { mode: 'sw', className: 'bottom-0 left-0', cursor: 'nesw-resize' },
  { mode: 'w', className: 'left-0 top-1/2 -translate-y-1/2', cursor: 'ew-resize' },
];

export type ProcessedProblemImage = { file: File; preview: string; originalFile?: File; originalSize?: number };

const ProblemImageEditor: React.FC<{
  file: File | null;
  open: boolean;
  title?: string;
  initialCrop?: CropState;
  compressUpload?: boolean;
  onCancel: () => void;
  onApply: (result: ProcessedProblemImage) => void;
}> = ({ file, open, title = '裁剪题目区域', initialCrop = DEFAULT_PROBLEM_CROP, compressUpload = false, onCancel, onApply }) => {
  const [preview, setPreview] = useState('');
  const [crop, setCrop] = useState<CropState>(DEFAULT_PROBLEM_CROP);
  const [adjust, setAdjust] = useState<ImageAdjust>(DEFAULT_PROBLEM_ADJUST);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState('');
  const [workingFile, setWorkingFile] = useState<File | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<CropDragState | null>(null);

  useEffect(() => {
    setWorkingFile(file);
    setError('');
    if (!file) {
      setPreview('');
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    setCrop(initialCrop);
    setAdjust(DEFAULT_PROBLEM_ADJUST);
    return () => URL.revokeObjectURL(url);
  }, [initialCrop, file]);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  if (!open || !file || !preview) return null;

  const pointToPercent = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    return {
      x: clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100),
      y: clamp(((event.clientY - rect.top) / rect.height) * 100, 0, 100),
    };
  };

  const startDrag = (mode: CropDragMode, event: React.PointerEvent<HTMLDivElement>) => {
    const point = pointToPercent(event);
    if (!point) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      mode, originX: point.x, originY: point.y,
      startX: point.x, startY: point.y, startCrop: crop,
    };
    if (mode === 'draw') setCrop({ x: point.x, y: point.y, w: 1, h: 1 });
  };

  const updateDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const point = pointToPercent(event);
    if (!drag || !point) return;
    event.preventDefault();
    const minSize = 5;
    const dx = point.x - drag.startX;
    const dy = point.y - drag.startY;
    const start = drag.startCrop;
    if (drag.mode === 'draw') {
      const left = clamp(Math.min(drag.originX, point.x), 0, 100 - minSize);
      const top = clamp(Math.min(drag.originY, point.y), 0, 100 - minSize);
      const right = clamp(Math.max(drag.originX, point.x), left + minSize, 100);
      const bottom = clamp(Math.max(drag.originY, point.y), top + minSize, 100);
      setCrop({ x: left, y: top, w: right - left, h: bottom - top });
      return;
    }
    if (drag.mode === 'move') {
      setCrop({ ...start, x: clamp(start.x + dx, 0, 100 - start.w), y: clamp(start.y + dy, 0, 100 - start.h) });
      return;
    }
    let left = start.x;
    let top = start.y;
    let right = start.x + start.w;
    let bottom = start.y + start.h;
    if (drag.mode.includes('w')) left = clamp(start.x + dx, 0, right - minSize);
    if (drag.mode.includes('e')) right = clamp(start.x + start.w + dx, left + minSize, 100);
    if (drag.mode.includes('n')) top = clamp(start.y + dy, 0, bottom - minSize);
    if (drag.mode.includes('s')) bottom = clamp(start.y + start.h + dy, top + minSize, 100);
    setCrop({ x: left, y: top, w: right - left, h: bottom - top });
  };

  const finishDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    event.preventDefault();
    dragRef.current = null;
  };

  const apply = async () => {
    setProcessing(true);
    try {
      const result = await renderProcessedImage(workingFile || file, crop, adjust);
      if (compressUpload) {
        try {
          const [originalFile, uploadFile] = await Promise.all([
            compressPhotoForUpload(file), compressPhotoForUpload(result.file, 1800, 700 * 1024),
          ]);
          onApply({ ...result, file: uploadFile, originalFile, originalSize: file.size });
        } catch (cause) { URL.revokeObjectURL(result.preview); throw cause; }
      } else onApply(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '图片处理失败，请重新选择');
    } finally {
      setProcessing(false);
    }
  };

  const rotate = async () => {
    if (!workingFile) return;
    setProcessing(true); setError('');
    try {
      const result = await renderProcessedImage(workingFile, { x: 0, y: 0, w: 100, h: 100 }, { brightness: 100, contrast: 100, sharpen: 0, grayscale: false }, 90);
      URL.revokeObjectURL(preview);
      setWorkingFile(result.file); setPreview(result.preview); setCrop({ x: 0, y: 0, w: 100, h: 100 });
    } catch (cause) { setError(cause instanceof Error ? cause.message : '图片旋转失败'); }
    finally { setProcessing(false); }
  };

  return (
    <div className="app-overlay-enter fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="app-large-dialog-enter grid max-h-[92dvh] w-full max-w-6xl grid-cols-1 gap-4 overflow-y-auto rounded-xl border border-border bg-bg-primary p-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><Crop className="h-4 w-4 text-accent" />{title}</div>
            <button type="button" onClick={onCancel} className="rounded p-1 text-text-secondary hover:text-text-primary"><X className="h-5 w-5" /></button>
          </div>
          <div ref={stageRef} className="relative mx-auto w-fit max-h-[65dvh] max-w-full overflow-hidden touch-none select-none rounded outline outline-1 outline-border bg-bg-secondary" onPointerDown={(event) => startDrag('draw', event)} onPointerMove={updateDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag}>
            <img onError={() => setError('图片无法预览，请转换为 JPEG 后重新选择')} src={preview} alt="待处理原图" draggable={false} className="block max-h-[65dvh] max-w-full w-auto select-none object-contain" style={{ filter: `brightness(${adjust.brightness}%) contrast(${adjust.contrast}%)${adjust.grayscale ? ' grayscale(100%)' : ''}` }} />
            <div className="absolute cursor-move border-2 border-accent bg-accent/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" style={{ left: `${crop.x}%`, top: `${crop.y}%`, width: `${crop.w}%`, height: `${crop.h}%` }} onPointerDown={(event) => startDrag('move', event)}>
              <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded bg-accent/85 px-2 py-1 text-[11px] font-medium text-white shadow-sm">拖动选框</div>
              {cropHandles.map((handle) => <div key={handle.mode} className={`absolute h-6 w-6 rounded-full border-2 border-white bg-accent shadow-sm ${handle.className}`} style={{ cursor: handle.cursor }} onPointerDown={(event) => startDrag(handle.mode, event)} />)}
            </div>
          </div>
          <div className="rounded-lg border border-border bg-bg-card px-3 py-2 text-xs leading-5 text-text-secondary">拖动选框或重新框选题目区域。右侧可增强对比度、亮度和锐度。{compressUpload && ' 上传前自动压缩，保存完整画面压缩副本及裁剪图，请检查小字与公式清晰度。'}</div>
        </div>
        <div className="space-y-4 rounded-xl border border-border bg-bg-card p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><SlidersHorizontal className="h-4 w-4 text-accent" />扫描增强</div>
          <button type="button" disabled={processing} onClick={() => void rotate()} className="app-secondary-button"><RotateCw className="h-4 w-4" />顺时针旋转</button>
          {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
          <MistakeRange label="亮度" value={adjust.brightness} min={70} max={150} onChange={(value) => setAdjust((current) => ({ ...current, brightness: value }))} />
          <MistakeRange label="对比度" value={adjust.contrast} min={80} max={200} onChange={(value) => setAdjust((current) => ({ ...current, contrast: value }))} />
          <MistakeRange label="锐化" value={adjust.sharpen} min={0} max={100} onChange={(value) => setAdjust((current) => ({ ...current, sharpen: value }))} />
          <label className="flex items-center gap-2 text-sm text-text-primary"><input type="checkbox" checked={adjust.grayscale} onChange={(event) => setAdjust((current) => ({ ...current, grayscale: event.target.checked }))} className="accent-accent" />黑白扫描效果</label>
          <button type="button" onClick={() => void apply()} disabled={processing || Boolean(error)} className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">{processing && <Loader2 className="h-4 w-4 animate-spin" />}{processing ? '处理中' : '使用该区域'}</button>
        </div>
      </div>
    </div>
  );
};

export default ProblemImageEditor;
