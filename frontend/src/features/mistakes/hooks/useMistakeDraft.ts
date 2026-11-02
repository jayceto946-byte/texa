import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch, get, patch, post, IMAGE_RECOGNITION_TIMEOUT_MS } from '../../../api/client';
import { readableVisualQuestion } from '../../../utils/visualQuestion';

type Attachment = { id: string; filename: string };
type Draft = { id: string; revision: number; attachments?: Attachment[]; question_text?: string; user_answer?: string; correct_answer?: string; subject?: string; chapter?: string; source?: string; notes?: string; tags?: string[]; mistake_type?: string[]; content_complete?: boolean };
type Form = { question_text: string; user_answer: string; correct_answer: string; subject: string; chapter: string; source: string; notes: string; tags: string; mistake_type: string; content_complete: boolean };
const emptyForm: Form = { question_text: '', user_answer: '', correct_answer: '', subject: '数学', chapter: '', source: '', notes: '', tags: '', mistake_type: '', content_complete: false };
const formFromDraft = (draft: Draft): Form => ({ question_text: readableVisualQuestion(draft.question_text || '', ''), user_answer: draft.user_answer || '', correct_answer: draft.correct_answer || '', subject: draft.subject || '数学', chapter: draft.chapter || '', source: draft.source || '', notes: draft.notes || '', tags: (draft.tags || []).join('、'), mistake_type: (draft.mistake_type || []).join('、'), content_complete: Boolean(draft.content_complete) });
const fieldsFromForm = (form: Form) => ({ ...form, tags: form.tags.split(/[、,，]/).map(item => item.trim()).filter(Boolean), mistake_type: form.mistake_type.split(/[、,，]/).map(item => item.trim()).filter(Boolean) });

export function useMistakeDraft(draftId: string, query: string) {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<Draft | null>(null);
  const draftRef = useRef<Draft | null>(null);
  const [form, setForm] = useState<Form>(emptyForm);
  const formRef = useRef(form);
  const [dirty, setDirty] = useState(false);
  const changeCounter = useRef(0);
  const savedCounter = useRef(0);
  const savingPromise = useRef<Promise<number | null> | null>(null);
  const [status, setStatus] = useState('正在读取草稿…');
  const [error, setError] = useState('');
  const [readState, setReadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [reloadKey, setReloadKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [ocrCandidate, setOcrCandidate] = useState('');
  const [uncertainties, setUncertainties] = useState<string[]>([]);
  const [activeAttachment, setActiveAttachment] = useState('');
  const storeDraft = (next: Draft) => { draftRef.current = next; setDraft(next); };

  useEffect(() => {
    let active = true;
    get(`/mistakes/drafts/${encodeURIComponent(draftId)}${query}`).then(result => {
      if (!active) return;
      if (!result?.success) throw new Error(result?.message || '草稿不存在');
      storeDraft(result.data);
      const next = formFromDraft(result.data);
      formRef.current = next;
      setForm(next);
      setActiveAttachment(result.data.attachments?.[0]?.id || '');
      setStatus('草稿已恢复');
      setReadState('ready');
    }).catch(cause => {
      if (!active) return;
      setError(cause instanceof Error ? cause.message : '无法读取草稿');
      setStatus('草稿读取失败');
      setReadState('error');
    });
    return () => { active = false; };
  }, [draftId, query, reloadKey]);

  const change = <K extends keyof Form>(key: K, value: Form[K]) => {
    const next = { ...formRef.current, [key]: value };
    formRef.current = next;
    setForm(next);
    changeCounter.current += 1;
    setDirty(true);
    setStatus('草稿尚未保存');
  };
  const saveDraft = useCallback(async (): Promise<number | null> => {
    if (savingPromise.current) return savingPromise.current;
    const current = draftRef.current;
    if (!current) return null;
    if (changeCounter.current === savedCounter.current) return current.revision;
    const startCounter = changeCounter.current;
    setStatus('正在保存草稿…');
    const task = (async () => {
      try {
        const result = await patch(`/mistakes/drafts/${encodeURIComponent(draftId)}${query}`, { expected_revision: current.revision, data: fieldsFromForm(formRef.current) });
        if (!result?.success) throw new Error(result?.message || '保存草稿失败');
        storeDraft({ ...draftRef.current!, revision: result.data.revision });
        savedCounter.current = startCounter;
        setError('');
        if (changeCounter.current === startCounter) { setDirty(false); setStatus('草稿已保存'); }
        return result.data.revision as number;
      } catch (cause) {
        setStatus('草稿保存失败');
        setError(cause instanceof Error ? cause.message : '保存草稿失败');
        return null;
      }
    })();
    savingPromise.current = task;
    try { return await task; } finally { savingPromise.current = null; }
  }, [draftId, query]);
  useEffect(() => {
    if (!dirty || readState !== 'ready' || busy) return;
    const timer = window.setTimeout(() => { void saveDraft(); }, 850);
    return () => window.clearTimeout(timer);
  }, [dirty, form, readState, busy, saveDraft]);

  // Save current edits before a revisioned attachment or final-save operation.
  const prepare = async () => {
    const version = changeCounter.current;
    const revision = await saveDraft();
    if (revision && version !== changeCounter.current) {
      setStatus('内容刚发生变化，请等待草稿保存后重试');
      return null;
    }
    return revision;
  };
  const recognizeImage = async (attachmentId: string, revision: number) => {
    setRecognizing(true);
    setStatus('正在识别图片…');
    try {
      const result = await post(`/mistakes/drafts/${encodeURIComponent(draftId)}/recognize${query}`, { expected_revision: revision, attachment_id: attachmentId }, IMAGE_RECOGNITION_TIMEOUT_MS);
      if (!result?.success) throw new Error(result?.message || '识别失败');
      setOcrCandidate(readableVisualQuestion(result.data.ocr_text || ''));
      setUncertainties(result.data.uncertainties || []);
      setStatus('识别完成，请对照原图校对');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '识别失败');
      setStatus('识别失败，原图和编辑内容已保留');
    } finally { setRecognizing(false); }
  };
  const recognize = async () => {
    if (!draft || busy || !activeAttachment) return;
    setBusy(true); setError('');
    try { const revision = await prepare(); if (revision) await recognizeImage(activeAttachment, revision); }
    finally { setBusy(false); }
  };
  const attach = async (file: File) => {
    if (!draft || busy) return;
    setBusy(true); setError('');
    try {
      const revision = await prepare(); if (!revision) return;
      const body = new FormData(); body.append('expected_revision', String(revision)); body.append('file', file);
      const response = await apiFetch(`/mistakes/drafts/${encodeURIComponent(draftId)}/attachments${query}`, { method: 'POST', body });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.detail || result.message || '图片保存失败');
      storeDraft(result.data);
      const id = result.data.attachments.at(-1)?.id || '';
      setActiveAttachment(id);
      setOcrCandidate(''); setUncertainties([]);
      if (id) await recognizeImage(id, result.data.revision);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '图片保存失败'); }
    finally { setBusy(false); }
  };
  const removeAttachment = async () => {
    if (!draft || busy || !activeAttachment) return;
    setBusy(true); setError('');
    try {
      const revision = await prepare(); if (!revision) return;
      const result = await post(`/mistakes/drafts/${encodeURIComponent(draftId)}/attachments/${encodeURIComponent(activeAttachment)}/remove${query}`, { expected_revision: revision });
      if (!result?.success) throw new Error(result?.message || '图片移除失败');
      storeDraft(result.data);
      setActiveAttachment(result.data.attachments?.[0]?.id || '');
      setOcrCandidate(''); setUncertainties([]);
      setStatus('图片已移除，题干和作答已保留');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '图片移除失败'); }
    finally { setBusy(false); }
  };
  const finish = async () => {
    if (!draft || busy) return;
    setBusy(true); setError('');
    try {
      const revision = await prepare(); if (!revision) return;
      const result = await post(`/mistakes/drafts/${encodeURIComponent(draftId)}/save${query}`, { expected_revision: revision, operation_id: `save-draft:${draftId}:${revision}` });
      if (!result?.success) throw new Error(result?.message || '保存错题失败');
      if (result.data.status === 'draft') { setStatus(result.data.reason || '草稿已保存，等待补全'); return; }
      navigate(`/mistakes/${encodeURIComponent(result.data.mistake_id)}${query}`, { replace: true });
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存错题失败'); }
    finally { setBusy(false); }
  };
  const retryRead = () => { setReadState('loading'); setError(''); setStatus('正在读取草稿…'); setReloadKey(v => v + 1); };
  return { draft, form, dirty, status, error, readState, busy, recognizing, ocrCandidate, uncertainties, activeAttachment,
    setActiveAttachment, clearError: () => setError(''), change, saveDraft, recognize, attach, removeAttachment, finish, retryRead,
    adoptOcr: () => { change('question_text', ocrCandidate); setOcrCandidate(''); setUncertainties([]); } };
}
