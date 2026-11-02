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
  return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="app-ghost-button workspace-back-control" to="/mistakes"><TexaBack className="h-4 w-4" />返回错题档案</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-intake-body"><p>草稿保存在本地，校对后再收录。</p><div className="mistakes-intake-choices"><button type="button" disabled={busy} onClick={() => begin('image')} className="app-secondary-button"><TexaImage className="h-4 w-4" />从图片开始</button><button type="button" disabled={busy} onClick={() => begin('manual')} className="app-primary-button">手动输入</button></div>{error && <StatusBanner kind="error" title={error} description="已有草稿仍保留，可重试刚才的操作。" />}{drafts.length > 0 && <section><h2>继续草稿</h2><ol className="mistakes-intake-draft-list">{drafts.map((draft) => <li key={draft.id}><Link to={`/mistakes/intake/${encodeURIComponent(draft.id)}?book_name=${encodeURIComponent(scope)}`}><div className="mistakes-intake-draft-title"><SimpleMarkdown content={readableVisualQuestion(draft.question_text?.trim() || (draft.attachments?.length ? `图片错题 · ${draft.attachments.length} 张` : '未命名草稿'))} /></div></Link><span>{new Date(draft.updated_at).toLocaleDateString('zh-CN')}</span></li>)}</ol></section>}</div></main></div>;
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
  return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="app-ghost-button workspace-back-control" to="/mistakes"><TexaBack className="h-4 w-4" />返回错题档案</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-intake-body"><div className="mistakes-intake-heading"><div><h2>补录与校对</h2><p role="status">{status}</p></div></div>{error && <StatusBanner kind="error" title={error} description="已编辑内容仍保留，可重试刚才的操作。" action={<button className="app-secondary-button" onClick={clearError}>关闭提示</button>} />}
    <div className={`mistakes-intake-layout ${draft?.attachments?.length ? 'has-images' : 'no-images'}`}><section className="mistakes-intake-images" tabIndex={0} aria-label="题目原图，可粘贴或拖入图片" onPaste={(event) => { const file = Array.from(event.clipboardData.files).find((item) => item.type.startsWith('image/')); if (file) { event.preventDefault(); void attach(file); } }} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = Array.from(event.dataTransfer.files).find((item) => item.type.startsWith('image/')); if (file) void attach(file); }}><h2>题目原图</h2><label className="app-secondary-button" aria-disabled={busy}><TexaImage className="h-4 w-4" />添加图片<input type="file" accept="image/*" disabled={busy} className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; if (file) void attach(file); event.target.value = ''; }} /></label>{draft?.attachments?.length ? <div className="mistakes-intake-attachments">{draft.attachments.map((attachment) => <button key={attachment.id} type="button" aria-pressed={activeAttachment === attachment.id} disabled={busy} onClick={() => setActiveAttachment(attachment.id)}>{attachment.filename}</button>)}</div> : <p>可粘贴或拖入图片；识别失败也不会丢失原图。</p>}{image.url && <img src={image.url} alt="错题原图" className="mistakes-intake-image" />}{image.error && <p role="status">原图预览暂不可用：{image.error}</p>}{activeAttachment && <div className="mistakes-intake-image-actions"><button type="button" disabled={busy} className="app-secondary-button" onClick={() => void recognize()}>{recognizing ? <><Loader2 className="h-4 w-4 animate-spin" />正在识别…</> : '重新识别'}</button><button type="button" disabled={busy} className="app-secondary-button" onClick={() => void removeAttachment()}>移除当前图片</button></div>}</section>
    <section className="mistakes-intake-editor"><h2>校对题目</h2>{ocrCandidate && <div className="mistakes-ocr-candidate"><p>识别候选文本不会覆盖你已编辑的内容。</p><div className="workspace-reading-content"><ChatMessage role="assistant" content={ocrCandidate} /></div><button type="button" className="app-secondary-button" onClick={adoptOcr}>使用这版识别文本</button></div>}{uncertainties.length > 0 && <p className="mistakes-intake-warning">请重点核对：{uncertainties.join('；')}</p>}<MathContentField disabled={busy && !recognizing} label="题干与公式" value={form.question_text} onChange={value => change('question_text', value)} />{form.question_text && <details><summary>预览题目</summary><div className="workspace-reading-content"><ChatMessage role="assistant" content={form.question_text} /></div></details>}<h2 className="workspace-form-section">作答与参考</h2><MathContentField disabled={busy && !recognizing} label="我当时的作答或卡住位置" value={form.user_answer} onChange={value => change('user_answer', value)} /><MathContentField disabled={busy && !recognizing} label="参考答案（可选）" value={form.correct_answer} onChange={value => change('correct_answer', value)} /><MathContentField disabled={busy && !recognizing} label="修正做法或备注（可选）" value={form.notes} onChange={value => change('notes', value)} /><h2 className="workspace-form-section">分类与来源</h2><div className="mistakes-intake-metadata"><label>科目<input disabled={busy && !recognizing} className="app-field" value={form.subject} onChange={(event) => change('subject', event.target.value)} /></label><label>章节<input disabled={busy && !recognizing} className="app-field" value={form.chapter} onChange={(event) => change('chapter', event.target.value)} /></label><label>来源<input disabled={busy && !recognizing} className="app-field" value={form.source} onChange={(event) => change('source', event.target.value)} /></label><label>知识点<input disabled={busy && !recognizing} className="app-field" value={form.tags} onChange={(event) => change('tags', event.target.value)} placeholder="用顿号分隔" /></label><label>错因分类<input disabled={busy && !recognizing} className="app-field" value={form.mistake_type} onChange={(event) => change('mistake_type', event.target.value)} placeholder="不确定可留空" /></label></div><label className="mistakes-intake-confirm"><input type="checkbox" disabled={busy && !recognizing} checked={form.content_complete} onChange={(event) => change('content_complete', event.target.checked)} />题干、关键条件和附图已经核对完整</label></section></div>
  </div></main><WorkspaceActionBar status={(!form.question_text.trim() ? '请填写完整题干。' : !form.content_complete ? '请核对题干、关键条件和附图；未完成时可保存草稿。' : '题干已核对，可保存并安排复习。')}><button type="button" disabled={!dirty || busy || !draft} className="app-secondary-button" onClick={() => void saveDraft()}>保存草稿</button><button type="button" disabled={busy || !draft || !form.question_text.trim() || !form.content_complete} className="app-primary-button" onClick={finish}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}保存并安排复习</button></WorkspaceActionBar></div>;
}

export default function MistakeIntakePage() {
  const { draftId } = useParams();
  return draftId ? <IntakeDraft key={draftId} draftId={draftId} /> : <IntakeChoice />;
}
