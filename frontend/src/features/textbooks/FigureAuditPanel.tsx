import { useEffect, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { apiFetch } from '../../api/client';
import { useAuthenticatedBlobUrl } from '../../hooks/useAuthenticatedBlobUrl';

type Category = '' | 'error' | 'suspect' | 'unverifiable';
type Finding = { finding_id: string; rule: string; category: Exclude<Category, ''>; block_ids: string[]; pages: number[]; evidence: Record<string, unknown> };
type Audit = {
  canonical_hash: string; status: string; total_findings: number;
  summary: { figure_blocks: number; assets_checked: number; errors: number; suspects: number; unverifiable: number };
  findings: Finding[];
};
const categoryLabels = { error: '确定的结构错误', suspect: '疑似问题', unverifiable: '证据不足' };
const ruleLabels: Record<string, string> = {
  duplicate_block_identity: '裁片标识重复', invalid_caption_node: '图题记录损坏', invalid_caption_provenance: '图题来源或坐标无效',
  caption_text_not_supported_by_ir: '原始图题与教材记录不一致', prose_in_caption: '正文可能混入图题', invalid_normalized_bbox: '裁片坐标无效',
  invalid_physical_page: '来源页码无效', geometry_unavailable: '缺少可比较的页内坐标', asset_unavailable: '缺少原始裁片记录',
  asset_path_outside_book: '裁片路径越界', asset_missing: '原始裁片文件缺失', asset_hash_mismatch: '裁片文件与来源哈希不一致',
  asset_hash_unavailable: '缺少来源文件哈希', caption_parent_geometry_mismatch: '图题可能归到了另一裁片',
  ambiguous_figure_caption: '多个图题归属难以区分', unbounded_figure_layout: '组合范围过大',
  subcaption_sequence_gap: '子图标签序列不连续', group_number_conflict: '组合候选的图号冲突',
  group_crosses_source_boundary: '组合跨越来源页或章节', neighboring_crops_without_group: '相邻裁片可能属于同一幅图',
  referenced_subcaption_not_observed: '正文引用的子图标签未在图题中识别到', source_page_pixels_not_compared: '尚未与完整原页比较',
};

function OriginalCrop({ bookName, blockId }: { bookName: string; blockId: string }) {
  const image = useAuthenticatedBlobUrl(`/api/books/${encodeURIComponent(bookName)}/figures/${encodeURIComponent(blockId)}/image`);
  return <div className="min-w-0 rounded border border-border p-2">
    {image.loading && <p className="type-caption">正在读取原始裁片…</p>}
    {image.error && <p role="alert" className="type-caption text-text-secondary">{image.error}</p>}
    {image.url && <img src={image.url} alt={`原始裁片 ${blockId}`} className="max-h-60 max-w-full object-contain" />}
  </div>;
}

export default function FigureAuditPanel({ bookName, onClose }: { bookName: string; onClose: () => void }) {
  const [category, setCategory] = useState<Category>('suspect');
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<Audit | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setResult(null);
    setExpanded('');
    apiFetch(`/books/${encodeURIComponent(bookName)}/figure-audit?category=${category}&offset=${offset}&limit=20`, { signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok || !payload.success) throw new Error(payload.detail || payload.message || '教材图片审核失败');
        if (!controller.signal.aborted) setResult(payload.data as Audit);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '教材图片审核失败');
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [bookName, category, offset, revision]);

  return <section style={{ gridColumn: '1 / -1' }} className="min-w-0 border-t border-border pt-4" aria-label={`${bookName}图片审核`}>
    <header className="flex flex-wrap items-center justify-between gap-2">
      <h5 className="type-section-title">教材图片审核</h5>
      <div className="flex gap-2"><button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)} className="app-secondary-button"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />重新审核</button><button type="button" onClick={onClose} className="app-icon-button" aria-label="关闭图片审核"><X className="h-4 w-4" /></button></div>
    </header>
    <p className="type-caption mt-2 text-text-secondary">自动检查裁片文件、坐标、图题归属和正文引用。标签可能已在图片内；疑似问题不等于缺图，原页完整性和文字正确性仍需核对。</p>
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="图片审核类别">
      {(['suspect', 'error', 'unverifiable', ''] as Category[]).map((value) => <button type="button" key={value} aria-pressed={category === value} className={category === value ? 'app-primary-button' : 'app-secondary-button'} onClick={() => { setOffset(0); setCategory(value); }}>{value ? categoryLabels[value] : '全部'}</button>)}
    </div>
    {loading && <p role="status" className="type-body mt-3">正在审核教材图片…</p>}
    {error && <p role="alert" className="type-body mt-3 text-text-secondary">{error} · 可重新审核。</p>}
    {result && <>
      <p className="type-body mt-3">{result.summary.figure_blocks} 个裁片 · 已校验 {result.summary.assets_checked} 个文件 · {result.summary.errors} 条结构错误 · {result.summary.suspects} 条疑似问题</p>
      {!result.findings.length && <p className="type-body mt-3 text-text-secondary">此类别未发现问题。自动检查不能证明图片完整或 OCR 正确。</p>}
      <div className="mt-3 max-h-80 space-y-3 overflow-y-auto pr-2">
        {result.findings.map((finding) => <article key={finding.finding_id} className="min-w-0 border-b border-border pb-3">
          <p className="type-control font-medium">{ruleLabels[finding.rule] || finding.rule} <span className="type-caption text-text-secondary">· {categoryLabels[finding.category]}</span></p>
          <p className="type-caption mt-1 break-words text-text-secondary">{finding.rule === 'source_page_pixels_not_compared' ? '全书：现有裁片无法证明原页是否有被漏裁的内容。' : `来源第 ${finding.pages.join('、') || '?'} 页 · 涉及 ${finding.block_ids.length} 个裁片`}</p>
          {typeof finding.evidence.caption === 'string' && <p className="type-body mt-1 whitespace-pre-wrap break-words">{finding.evidence.caption}</p>}
          {finding.block_ids.length > 0 && finding.block_ids.length <= 16 && <button type="button" className="app-ghost-button mt-1" aria-expanded={expanded === finding.finding_id} onClick={() => setExpanded(expanded === finding.finding_id ? '' : finding.finding_id)}>{expanded === finding.finding_id ? '收起原始裁片' : '查看原始裁片'}</button>}
          {expanded === finding.finding_id && <div className="mt-2 grid min-w-0 gap-2 sm:grid-cols-2">{finding.block_ids.map((bid) => <OriginalCrop key={bid} bookName={bookName} blockId={bid} />)}</div>}
        </article>)}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 type-caption">
        <span>{result.total_findings} 条信号 · 第 {Math.floor(offset / 20) + 1} 页</span>
        <div className="flex gap-2"><button type="button" disabled={offset === 0} className="app-secondary-button disabled:opacity-50" onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button><button type="button" disabled={offset + 20 >= result.total_findings} className="app-secondary-button disabled:opacity-50" onClick={() => setOffset(offset + 20)}>下一页</button></div>
      </div>
    </>}
  </section>;
}
