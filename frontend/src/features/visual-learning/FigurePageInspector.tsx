import { useState } from 'react';
import { useAuthenticatedBlobUrl } from '../../hooks/useAuthenticatedBlobUrl';
import type { FigureArtifact } from '../../types';

export default function FigurePageInspector({ figure }: { figure: FigureArtifact }) {
  const [showPdf, setShowPdf] = useState(false);
  const image = useAuthenticatedBlobUrl(figure.image_url);
  const pdf = useAuthenticatedBlobUrl(showPdf ? figure.pdf_url : '');
  return (
    <div className="figure-page-inspector">
      <div className="figure-page-metadata">
        <div>{figure.caption || '无图注 Figure'}</div>
        <span>{figure.page ? `p.${figure.page}` : '未标页'} · {figure.section_path.join(' › ') || figure.book_name}</span>
      </div>
      {image.loading && <div className="figure-source-status">正在读取 Figure…</div>}
      {image.error && <div className="figure-source-status is-error">{image.error}</div>}
      {image.url && <img src={image.url} alt={figure.caption || `教材 Figure ${figure.figure_id}`} />}
      {figure.pdf_url && (
        <button type="button" className="app-secondary-button" onClick={() => setShowPdf((value) => !value)}>
          {showPdf ? '收起教材页' : `打开教材第 ${figure.page || '?'} 页`}
        </button>
      )}
      {showPdf && pdf.loading && <div className="figure-source-status">正在读取教材 PDF…</div>}
      {showPdf && pdf.error && <div className="figure-source-status is-error">{pdf.error}</div>}
      {showPdf && pdf.url && <iframe title="教材 PDF 来源页" src={`${pdf.url}#page=${Math.max(1, figure.page || 1)}`} />}
    </div>
  );
}
