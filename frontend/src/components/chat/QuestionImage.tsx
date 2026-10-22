import { useState } from 'react';
import { X } from 'lucide-react';
import { useAuthenticatedBlobUrl } from '../../hooks/useAuthenticatedBlobUrl';
import Dialog from '../ui/Dialog';
import './QuestionImage.css';

export default function QuestionImage({ path, previewPath, label = '题目图片' }: { path: string; previewPath?: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const [retry, setRetry] = useState(0);
  const preview = useAuthenticatedBlobUrl(previewPath || `${path}${path.includes('?') ? '&' : '?'}preview=true`, 'binary', retry);
  const original = useAuthenticatedBlobUrl(open ? path : '', 'binary', retry);
  return <div className="question-image-attachment">
    <button type="button" className="question-image-thumbnail" aria-label={`查看${label}原图`} onClick={() => setOpen(true)} disabled={!preview.url}>
      {preview.url ? <img src={preview.url} alt={label} /> : <span>{preview.error ? '图片未能加载' : '正在加载图片…'}</span>}
    </button>
    {preview.error && <button type="button" className="app-ghost-button" onClick={() => setRetry(value => value + 1)}>重试图片</button>}
    <Dialog open={open} title={label} onClose={() => setOpen(false)} dismissOnBackdrop className="question-image-viewer">
      <header><span>{label}</span><button type="button" className="app-icon-button" aria-label="关闭原图" onClick={() => setOpen(false)}><X size={20} /></button></header>
      <div className="question-image-original">
        {original.loading && <p role="status">正在读取原图…</p>}
        {original.error && <p role="alert">原图读取失败 <button className="app-secondary-button" onClick={() => setRetry(value => value + 1)}>重试</button></p>}
        {original.url && <img src={original.url} alt={label} />}
      </div>
    </Dialog>
  </div>;
}
