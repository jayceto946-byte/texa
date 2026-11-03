import { TexaBack, TexaImage } from '../components/icons';
import { readableVisualQuestion } from '../utils/visualQuestion';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { get, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import { SimpleMarkdown } from '../components/chat/MarkdownMessage';
import { useChatContext } from '../contexts/ChatContext';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';
import { WorkspaceActionBar } from '../components/ui/WorkspaceActionBar';
import { useMistakeDraft } from '../features/mistakes/hooks/useMistakeDraft';
import { MathContentField } from '../features/reading/RenderedMathEditor';
import { ActionableIssue, StatusBanner } from '../components/ui/AsyncState';
import WorkspaceSkeleton from '../components/ui/WorkspaceSkeleton';
import './MistakeIntakePage.css';

type DraftSummary = { id: string; question_text?: string; attachments?: { id: string }[]; updated_at: string };

function IntakeChoice() {
  const { bookName, subject } = useChatContext();
  const navigate = useNavigate();
  const scope = new URLSearchParams(location.search).get('book_name') || bookName || 'default';
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  useEffect(() => {
    let active = true;
    get(`/mistakes/drafts?book_name=${encodeURIComponent(scope)}`).then((result) => {
      if (active && result?.success) setDrafts(result.data || []);
    }).catch(() => { if (active) setError('草稿列表暂时无法读取，仍可新建草稿。'); });
    return () => { active = false; };
  }, [scope]);
  const begin = async (kind: 'image' | 'manual') => {
    setBusy(true);
    try {
      const result = await post(`/mistakes/drafts?book_name=${encodeURIComponent(scope)}`, { data: { subject: subject || '数学', content_complete: kind === 'manual' } });
      if (!result?.success) throw new Error(result?.message || '无法创建草稿');
      navigate(`/mistakes/intake/${encodeURIComponent(result.data.id)}?book_name=${encodeURIComponent(scope)}${kind === 'image' ? '&mode=image' : ''}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法创建草稿'); setBusy(false); }
  };
  return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="app-ghost-button workspace-back-control" to="/mistakes"><TexaBack className="h-4 w-4" />返回错题档案</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-intake-body"><div className="mistakes-intake-choices"><button type="button" disabled={busy} onClick={() => begin('image')} className="app-secondary-button"><TexaImage className="h-4 w-4" />从图片开始</button><button type="button" disabled={busy} onClick={() => begin('manual')} className="app-primary-button">手动输入</button></div>{error && <StatusBanner kind="error" title={error} description="已有草稿仍保留，可重试刚才的操作。" />}{drafts.length > 0 && <section><h2>继续草稿</h2><ol className="mistakes-intake-draft-list">{drafts.map((draft) => <li key={draft.id}><Link to={`/mistakes/intake/${encodeURIComponent(draft.id)}?book_name=${encodeURIComponent(scope)}`}><div className="mistakes-intake-draft-title"><SimpleMarkdown content={readableVisualQuestion(draft.question_text?.trim() || (draft.attachments?.length ? `图片错题 · ${draft.attachments.length} 张` : '未命名草稿'))} /></div></Link><span>{new Date(draft.updated_at).toLocaleDateString('zh-CN')}</span></li>)}</ol></section>}</div></main></div>;
}

function IntakeDraft({ draftId }: { draftId: string }) {
  const { bookName } = useChatContext();
  const scope = new URLSearchParams(location.search).get('book_name') || bookName || 'default';
  const query = `?book_name=${encodeURIComponent(scope)}`;
  const state = useMistakeDraft(draftId, query);
  const { draft, form, dirty, status, error, readState, busy, recognizing, ocrCandidate, uncertainties, activeAttachment,
    setActiveAttachment, clearError, change, saveDraft, recognize, attach, removeAttachment, finish, retryRead, adoptOcr } = state;
  const image = useAuthenticatedBlobUrl(activeAttachment ? `/mistakes/drafts/${encodeURIComponent(draftId)}/attachments/${encodeURIComponent(activeAttachment)}${query}` : '');
  if (readState !== 'ready') return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col">
    <header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="app-ghost-button workspace-back-control" to="/mistakes"><TexaBack className="h-4 w-4" />返回错题档案</Link></header>
    <main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-intake-body">{readState === 'loading' ? <WorkspaceSkeleton label="正在读取草稿" header={false} /> : <ActionableIssue title={error} impact="草稿尚未读取，未覆盖已保存的内容。" actions={<button className="app-secondary-button" onClick={retryRead}>重新读取草稿</button>} />}</div></main>
  </div>;
  const uploadControl = <label className="app-ghost-button mistake-upload-control" aria-disabled={busy} title="添加图片，也可粘贴或拖入图片">
    <TexaImage size={16} />添加图片<input type="file" accept="image/*" disabled={busy} className="sr-only" onChange={event => { const file = event.target.files?.[0]; if (file) void attach(file); event.target.value = ''; }} />
  </label>;
  const hasImages = Boolean(draft?.attachments?.length);
  return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col">
    <header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="app-ghost-button workspace-back-control" to="/mistakes"><TexaBack className="h-4 w-4" />返回错题档案</Link></header>
    <main className="management-page-content flex-1 overflow-y-auto">
      <div className={`mistakes-intake-body ${hasImages ? 'has-images' : ''}`}>
        <p className="sr-only" role="status">{status}</p>
        {error && <StatusBanner kind="error" title={error} description="已编辑内容仍保留，可重试刚才的操作。" action={<button className="app-secondary-button" onClick={clearError}>关闭提示</button>} />}
        <div className={`mistakes-intake-layout ${hasImages ? 'has-images' : 'no-images'}`} onPaste={event => {
          const file = Array.from(event.clipboardData.files).find(item => item.type.startsWith('image/'));
          if (file) { event.preventDefault(); void attach(file); }
        }} onDragOver={event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }} onDrop={event => {
          const file = Array.from(event.dataTransfer.files).find(item => item.type.startsWith('image/'));
          if (file) { event.preventDefault(); void attach(file); }
        }}>
          {hasImages && <section className="mistakes-intake-images" tabIndex={0} aria-label="题目图片，可粘贴或拖入图片">
            <header className="mistakes-intake-image-heading"><h2>题目图片</h2>{uploadControl}</header>
            <div className="mistakes-intake-attachments">{draft?.attachments?.map(attachment => <button key={attachment.id} type="button" aria-pressed={activeAttachment === attachment.id} disabled={busy} onClick={() => setActiveAttachment(attachment.id)}>{attachment.filename}</button>)}</div>
            {image.url && <img src={image.url} alt="错题原图" className="mistakes-intake-image" />}
            {image.error && <p role="status">图片暂不可用：{image.error}</p>}
            {activeAttachment && <div className="mistakes-intake-image-actions"><button type="button" disabled={busy} className="app-secondary-button" onClick={() => void recognize()}>{recognizing ? <><Loader2 className="h-4 w-4 animate-spin" />正在识别…</> : '重新识别'}</button><button type="button" disabled={busy} className="app-ghost-button" onClick={() => void removeAttachment()}>移除图片</button></div>}
          </section>}
          <section className="mistakes-intake-editor">
            {ocrCandidate && <section className="mistakes-ocr-candidate"><h2>识别结果</h2><div className="workspace-reading-content"><ChatMessage role="assistant" content={ocrCandidate} /></div><button type="button" className="app-secondary-button" onClick={adoptOcr}>采用识别结果</button></section>}
            {uncertainties.length > 0 && <aside className="mistakes-intake-warning"><h3>需要核对</h3><ul>{uncertainties.map(item => <li key={item}>{item}</li>)}</ul></aside>}
            <MathContentField disabled={busy && !recognizing} label="题目" actions={!hasImages ? uploadControl : undefined} value={form.question_text} onChange={value => change('question_text', value)} />
            <MathContentField disabled={busy && !recognizing} label="我的作答" value={form.user_answer} onChange={value => change('user_answer', value)} />
            <MathContentField disabled={busy && !recognizing} label="参考答案（可选）" value={form.correct_answer} onChange={value => change('correct_answer', value)} />
            <MathContentField disabled={busy && !recognizing} label="修正与备注（可选）" value={form.notes} onChange={value => change('notes', value)} />
            <details className="mistakes-intake-classification"><summary>分类与来源</summary><div className="mistakes-intake-metadata">
              {([['subject','科目'],['chapter','章节'],['source','来源'],['tags','知识点'],['mistake_type','错因']] as const).map(([key,label]) => <label key={key}>{label}<input disabled={busy && !recognizing} value={form[key]} onChange={event => change(key, event.target.value)} /></label>)}
            </div></details>
            <label className="mistakes-intake-confirm"><input type="checkbox" disabled={busy && !recognizing} checked={form.content_complete} onChange={event => change('content_complete', event.target.checked)} />题干、关键条件和附图已经核对完整</label>
          </section>
        </div>
      </div>
    </main>
    <WorkspaceActionBar status={busy || status === '正在保存草稿…' ? status : null}>
      <button type="button" disabled={!dirty || busy || !draft} className="app-secondary-button" onClick={() => void saveDraft()}>保存草稿</button>
      <button type="button" disabled={busy || !draft || !form.question_text.trim() || !form.content_complete} className="app-primary-button" onClick={finish}>保存并安排复习</button>
    </WorkspaceActionBar>
  </div>;
}

export default function MistakeIntakePage() {
  const { draftId } = useParams();
  return draftId ? <IntakeDraft key={draftId} draftId={draftId} /> : <IntakeChoice />;
}
