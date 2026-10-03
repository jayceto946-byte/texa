import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ImagePlus, Loader2 } from 'lucide-react';
import { apiFetch, get, patch, post, IMAGE_RECOGNITION_TIMEOUT_MS } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import { useChatContext } from '../contexts/ChatContext';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';
import './MistakeIntakePage.css';

type Attachment = { id: string; filename: string };
type Draft = { id: string; revision: number; attachments?: Attachment[]; question_text?: string; user_answer?: string; correct_answer?: string; subject?: string; chapter?: string; source?: string; notes?: string; tags?: string[]; mistake_type?: string[]; ocr_text?: string; visual_ir?: Record<string, unknown>; content_complete?: boolean };
type Form = { question_text: string; user_answer: string; correct_answer: string; subject: string; chapter: string; source: string; notes: string; tags: string; mistake_type: string; content_complete: boolean };
const emptyForm: Form = { question_text: '', user_answer: '', correct_answer: '', subject: '数学', chapter: '', source: '', notes: '', tags: '', mistake_type: '', content_complete: false };

function formFromDraft(draft: Draft): Form {
  return { question_text: draft.question_text || '', user_answer: draft.user_answer || '', correct_answer: draft.correct_answer || '', subject: draft.subject || '数学', chapter: draft.chapter || '', source: draft.source || '', notes: draft.notes || '', tags: (draft.tags || []).join('、'), mistake_type: (draft.mistake_type || []).join('、'), content_complete: Boolean(draft.content_complete) };
}
function fieldsFromForm(form: Form) {
  return { ...form, tags: form.tags.split(/[、,，]/).map((item) => item.trim()).filter(Boolean), mistake_type: form.mistake_type.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) };
}

function IntakeChoice() {
  const { bookName, subject } = useChatContext();
  const navigate = useNavigate();
  const scope = new URLSearchParams(location.search).get('book_name') || bookName || 'default';
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [drafts, setDrafts] = useState<(Draft & { updated_at: string })[]>([]);
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
  return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="mistakes-back" to="/mistakes"><ArrowLeft className="h-4 w-4" />返回错题档案</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-intake-body"><h1>补录错题</h1><p>可以从图片识别后校对，也可以直接手动输入。草稿会保存在本地。</p><div className="mistakes-intake-choices"><button type="button" disabled={busy} onClick={() => begin('image')} className="app-secondary-button"><ImagePlus className="h-4 w-4" />从图片开始</button><button type="button" disabled={busy} onClick={() => begin('manual')} className="app-primary-button">手动输入</button></div>{error && <p role="alert" className="mistakes-intake-error">{error}</p>}{drafts.length > 0 && <section><h2>继续草稿</h2><ol className="mistakes-intake-draft-list">{drafts.map((draft) => <li key={draft.id}><Link to={`/mistakes/intake/${encodeURIComponent(draft.id)}?book_name=${encodeURIComponent(scope)}`}>{draft.question_text?.trim().slice(0, 70) || (draft.attachments?.length ? `图片错题 · ${draft.attachments.length} 张` : '未命名草稿')}</Link><span>{new Date(draft.updated_at).toLocaleDateString('zh-CN')}</span></li>)}</ol></section>}</div></main></div>;
}

function IntakeDraft({ draftId }: { draftId: string }) {
  const { bookName } = useChatContext();
  const navigate = useNavigate();
  const scope = new URLSearchParams(location.search).get('book_name') || bookName || 'default';
  const query = `?book_name=${encodeURIComponent(scope)}`;
  const [draft, setDraft] = useState<Draft | null>(null);
  const [form, setForm] = useState<Form>(emptyForm);
  const formRef = useRef(form);
  const [dirty, setDirty] = useState(false);
  const changeCounter = useRef(0);
  const savedCounter = useRef(0);
  const savingPromiseRef = useRef<Promise<number | null> | null>(null);
  const [status, setStatus] = useState('正在读取草稿…');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [ocrCandidate, setOcrCandidate] = useState('');
  const [uncertainties, setUncertainties] = useState<string[]>([]);
  const [activeAttachment, setActiveAttachment] = useState('');
  const image = useAuthenticatedBlobUrl(activeAttachment ? `/mistakes/drafts/${encodeURIComponent(draftId)}/attachments/${encodeURIComponent(activeAttachment)}${query}` : '');
  useEffect(() => {
    let active = true;
    get(`/mistakes/drafts/${encodeURIComponent(draftId)}${query}`).then((result) => {
      if (!active) return;
      if (!result?.success) throw new Error(result?.message || '草稿不存在');
      setDraft(result.data);
      const nextForm = formFromDraft(result.data);
      setForm(nextForm);
      formRef.current = nextForm;
      setActiveAttachment(result.data.attachments?.[0]?.id || '');
      setStatus('草稿已恢复');
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法读取草稿'); });
    return () => { active = false; };
  }, [draftId, query]);
  const change = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((current) => { const next = { ...current, [key]: value }; formRef.current = next; return next; });
    changeCounter.current += 1;
    setDirty(true);
    setStatus('草稿尚未保存');
  };
  const saveDraft = useCallback(async (): Promise<number | null> => {
    if (savingPromiseRef.current) return savingPromiseRef.current;
    if (!draft) return null;
    if (changeCounter.current === savedCounter.current) return draft.revision;
    const startCounter = changeCounter.current;
    setStatus('正在保存草稿…');
    const task = (async () => {
      try {
        const result = await patch(`/mistakes/drafts/${encodeURIComponent(draftId)}${query}`, { expected_revision: draft.revision, data: fieldsFromForm(formRef.current) });
        if (!result?.success) throw new Error(result?.message || '保存草稿失败');
        setDraft((current) => current ? { ...current, revision: result.data.revision } : current);
        savedCounter.current = startCounter;
        if (changeCounter.current === startCounter) { setDirty(false); setStatus('草稿已保存'); }
        return result.data.revision as number;
      } catch (cause) { setStatus('草稿保存失败'); setError(cause instanceof Error ? cause.message : '保存草稿失败'); return null; }
    })();
    savingPromiseRef.current = task;
    try { return await task; } finally { savingPromiseRef.current = null; }
  }, [draft, draftId, query]);
  useEffect(() => {
    if (!dirty || !draft) return;
    const timer = window.setTimeout(() => { void saveDraft(); }, 850);
    return () => window.clearTimeout(timer);
  }, [dirty, draft, form, saveDraft]);
  const recognize = async (attachmentId: string, revision: number) => {
    setStatus('正在识别图片…');
    try {
      const result = await post(`/mistakes/drafts/${encodeURIComponent(draftId)}/recognize${query}`, { expected_revision: revision, attachment_id: attachmentId }, IMAGE_RECOGNITION_TIMEOUT_MS);
      if (!result?.success) throw new Error(result?.message || '识别失败');
      const text = result.data.ocr_text || '';
      setOcrCandidate(text);
      setUncertainties(result.data.uncertainties || []);
      setStatus('识别完成，请对照原图校对');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '识别失败'); setStatus('原图已保存，可手动录入或重试识别'); }
  };
  const attach = async (file: File) => {
    if (!draft || busy) return;
    setBusy(true);
    setError('');
    const editVersion = changeCounter.current;
    const revision = await saveDraft();
    if (!revision || editVersion !== changeCounter.current) { setStatus('内容刚发生变化，请等待草稿保存后重试'); setBusy(false); return; }
    try {
      const body = new FormData();
      body.append('expected_revision', String(revision));
      body.append('file', file);
      const response = await apiFetch(`/mistakes/drafts/${encodeURIComponent(draftId)}/attachments${query}`, { method: 'POST', body });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || result.message || '图片保存失败');
      setDraft(result.data);
      const attachmentId = result.data.attachments.at(-1)?.id || '';
      setActiveAttachment(attachmentId);
      setStatus('原图已保存，正在识别…');
      if (attachmentId) await recognize(attachmentId, result.data.revision);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '图片保存失败'); }
    finally { setBusy(false); }
  };
  const finish = async () => {
    if (!draft || busy) return;
    setBusy(true);
    setError('');
    const editVersion = changeCounter.current;
    const revision = await saveDraft();
    if (!revision || editVersion !== changeCounter.current) { setStatus('内容刚发生变化，请等待草稿保存后重试'); setBusy(false); return; }
    try {
      const result = await post(`/mistakes/drafts/${encodeURIComponent(draftId)}/save${query}`, { expected_revision: revision, operation_id: `save-draft:${draftId}:${revision}` });
      if (!result?.success) throw new Error(result?.message || '保存错题失败');
      if (result.data.status === 'draft') { setStatus(result.data.reason || '草稿已保存，等待补全'); return; }
      navigate(`/mistakes/${encodeURIComponent(result.data.mistake_id)}${query}`, { replace: true });
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存错题失败'); }
    finally { setBusy(false); }
  };
  return <div className="management-workspace mistakes-intake-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题录入</h1><Link className="mistakes-back" to="/mistakes"><ArrowLeft className="h-4 w-4" />返回错题档案</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-intake-body"><div className="mistakes-intake-heading"><div><h1>补录与校对</h1><p role="status">{status}</p></div><button type="button" disabled={!dirty || busy} onClick={() => void saveDraft()} className="app-secondary-button">保存草稿</button></div>{error && <p role="alert" className="mistakes-intake-error">{error}</p>}
    <div className="mistakes-intake-layout"><section className="mistakes-intake-images" tabIndex={0} aria-label="题目原图，可粘贴或拖入图片" onPaste={(event) => { const file = Array.from(event.clipboardData.files).find((item) => item.type.startsWith('image/')); if (file) { event.preventDefault(); void attach(file); } }} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = Array.from(event.dataTransfer.files).find((item) => item.type.startsWith('image/')); if (file) void attach(file); }}><h2>题目原图</h2><label className="app-secondary-button"><ImagePlus className="h-4 w-4" />添加图片<input type="file" accept="image/*" className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; if (file) void attach(file); event.target.value = ''; }} /></label>{draft?.attachments?.length ? <div className="mistakes-intake-attachments">{draft.attachments.map((attachment) => <button key={attachment.id} type="button" aria-pressed={activeAttachment === attachment.id} onClick={() => setActiveAttachment(attachment.id)}>{attachment.filename}</button>)}</div> : <p>可粘贴或拖入图片；识别失败也不会丢失原图。</p>}{image.url && <img src={image.url} alt="错题原图" className="mistakes-intake-image" />}{image.error && <p role="status">原图预览暂不可用：{image.error}</p>}{activeAttachment && <button type="button" disabled={busy || !draft} className="app-secondary-button" onClick={() => draft && void recognize(activeAttachment, draft.revision)}>重新识别</button>}</section>
    <section className="mistakes-intake-editor"><h2>校对题目</h2>{ocrCandidate && <div className="mistakes-ocr-candidate"><p>识别候选文本不会覆盖你已编辑的内容。</p><div className="workspace-reading-content"><ChatMessage role="assistant" content={ocrCandidate} /></div><button type="button" className="app-secondary-button" onClick={() => { change('question_text', ocrCandidate); setOcrCandidate(''); }}>使用这版识别文本</button></div>}{uncertainties.length > 0 && <p className="mistakes-intake-warning">请重点核对：{uncertainties.join('；')}</p>}<label>题干与公式<textarea value={form.question_text} onChange={(event) => change('question_text', event.target.value)} className="app-field" rows={8} placeholder="完整题干、条件、选项与公式" /></label>{form.question_text && <details><summary>预览题目</summary><div className="workspace-reading-content"><ChatMessage role="assistant" content={form.question_text} /></div></details>}<label>我当时的作答或卡住位置<textarea value={form.user_answer} onChange={(event) => change('user_answer', event.target.value)} className="app-field" rows={4} placeholder="可写“不会做”或具体卡住的一步" /></label><label>参考答案（可选）<textarea value={form.correct_answer} onChange={(event) => change('correct_answer', event.target.value)} className="app-field" rows={4} /></label><label>修正做法或备注（可选）<textarea value={form.notes} onChange={(event) => change('notes', event.target.value)} className="app-field" rows={3} /></label><div className="mistakes-intake-metadata"><label>科目<input className="app-field" value={form.subject} onChange={(event) => change('subject', event.target.value)} /></label><label>章节<input className="app-field" value={form.chapter} onChange={(event) => change('chapter', event.target.value)} /></label><label>来源<input className="app-field" value={form.source} onChange={(event) => change('source', event.target.value)} /></label><label>知识点<input className="app-field" value={form.tags} onChange={(event) => change('tags', event.target.value)} placeholder="用顿号分隔" /></label><label>错因分类<input className="app-field" value={form.mistake_type} onChange={(event) => change('mistake_type', event.target.value)} placeholder="不确定可留空" /></label></div><label className="mistakes-intake-confirm"><input type="checkbox" checked={form.content_complete} onChange={(event) => change('content_complete', event.target.checked)} />题干、关键条件和附图已经核对完整</label><div className="mistakes-intake-actions"><button type="button" disabled={busy || !draft} className="app-secondary-button" onClick={() => void saveDraft()}>保存待处理</button><button type="button" disabled={busy || !draft || !form.question_text.trim()} className="app-primary-button" onClick={finish}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}保存并安排复习</button></div></section></div>
  </div></main></div>;
}

export default function MistakeIntakePage() {
  const { draftId } = useParams();
  return draftId ? <IntakeDraft draftId={draftId} /> : <IntakeChoice />;
}
