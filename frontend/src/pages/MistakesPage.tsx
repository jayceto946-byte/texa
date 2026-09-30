import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, BookOpen, ClipboardList, ImagePlus, Loader2, Search } from 'lucide-react';
import { get, getAuthenticatedBlob, patch, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import { SimpleMarkdown } from '../components/chat/MarkdownMessage';
import ScopeSelector, { type ScopeBookOption } from '../components/ScopeSelector';
import { ActionableIssue } from '../components/ui/AsyncState';
import { useChatContext } from '../contexts/ChatContext';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';
import type { MistakeRecord } from '../types';
import './MistakesPage.css';

type Filter = 'all' | 'pending' | 'due' | 'repeated' | 'mastered';
type ProjectedMistake = MistakeRecord & { pending_reason?: string; review_status?: string; mastery_status?: string; mastery_source?: string; repeat_wrong?: boolean };
type Candidate = { id: string; revision: number; question_text?: string; user_answer?: string; correct_answer?: string; source?: string; subject?: string; content_complete?: boolean };
const filters: { id: Filter; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'pending', label: '待处理' },
  { id: 'due', label: '待复习' },
  { id: 'repeated', label: '反复出错' },
  { id: 'mastered', label: '已掌握' },
];

function recordTitle(record: MistakeRecord) {
  const source = record.question_text || record.ocr_text || record.source || '未命名错题';
  const firstLine = source.split('\n').map((line) => line.trim()).find(Boolean) || source;
  return firstLine.length > 90 ? `${firstLine.slice(0, 90)}…` : firstLine;
}

function displayDate(value?: string) {
  if (!value) return '时间未记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(date);
}

function nextAction(record: ProjectedMistake) {
  if (record.pending_reason) return record.pending_reason;
  if (record.review_status === 'due') return '今天到期';
  if (record.mastery_status === 'mastered') return record.mastery_source === 'manual' ? '手动标记掌握' : '查看掌握依据';
  if (record.repeat_wrong) return '最近重做反复出错';
  if (!record.user_answer?.trim()) return '未留当时作答';
  return record.next_review ? `下次复习 ${displayDate(record.next_review)}` : '查看档案';
}

function MistakeAttachment({ mistakeId, attachmentId, bookName }: { mistakeId: string; attachmentId: string; bookName: string }) {
  const image = useAuthenticatedBlobUrl(`/mistakes/${encodeURIComponent(mistakeId)}/attachments/${encodeURIComponent(attachmentId)}?book_name=${encodeURIComponent(bookName)}`);
  return image.url ? <img className="mistakes-original-image" src={image.url} alt="错题附图" /> : image.error ? <p className="mistakes-detail-note">附图暂时无法读取</p> : null;
}

function useMistakeScope() {
  const { bookName, setBookName, subject, setSubject } = useChatContext();
  const [books, setBooks] = useState<ScopeBookOption[]>([]);
  useEffect(() => {
    let active = true;
    get('/books/list').then((result) => {
      if (active && result?.success) setBooks(result.data || []);
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  const switchBook = async (name: string) => {
    if (!name) { setBookName(''); return; }
    try {
      const result = await get(`/books/switch/${encodeURIComponent(name)}`);
      if (result?.success) {
        setBookName(result.data.name);
        if (result.data.subject) setSubject(result.data.subject);
        return;
      }
    } catch { /* Keep the selected scope available when the switch endpoint is unavailable. */ }
    setBookName(name);
  };
  return { bookName, subject, books, setSubject, switchBook };
}

export function MistakeCollectionPage() {
  const { bookName, subject, books, setSubject, switchBook } = useMistakeScope();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const filter = filters.some((entry) => entry.id === params.get('filter')) ? params.get('filter') as Filter : 'all';
  const search = params.get('q') || '';
  const [records, setRecords] = useState<ProjectedMistake[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [editingCandidate, setEditingCandidate] = useState('');
  const [candidateEdit, setCandidateEdit] = useState({ question_text: '', user_answer: '', correct_answer: '', content_complete: false });
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [moreLoading, setMoreLoading] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());
  const bookQuery = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const scope = { subject, search: search.trim(), filter, limit: 30 };
    Promise.allSettled([
      post(`/mistakes/query${bookQuery}`, scope),
      get(`/mistakes/candidates?book_name=${encodeURIComponent(bookName || 'default')}&subject=${encodeURIComponent(subject)}`),
    ]).then(([listResult, candidateResult]) => {
      if (!active) return;
      if (listResult.status === 'fulfilled' && listResult.value?.success) {
        setRecords(listResult.value.data.items || []);
        setCursor(listResult.value.data.next_cursor || null);
      } else setError('错题档案暂时无法加载');
      setCandidates(candidateResult.status === 'fulfilled' && candidateResult.value?.success ? candidateResult.value.data || [] : []);
      setLoading(false);
    });
    return () => { active = false; };
  }, [bookQuery, bookName, subject, search, filter, reloadKey]);

  const loadMore = async () => {
    if (!cursor || moreLoading) return;
    setMoreLoading(true);
    try {
      const result = await post(`/mistakes/query${bookQuery}`, { subject, search: search.trim(), filter, cursor, limit: 30 });
      if (!result?.success) throw new Error(result?.message || '加载更多失败');
      setRecords((current) => [...current, ...(result.data.items || [])]);
      setCursor(result.data.next_cursor || null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '加载更多失败'); }
    finally { setMoreLoading(false); }
  };

  const resolveCandidate = async (candidate: Candidate, accept: boolean) => {
    try {
      const result = await post(`/mistakes/candidates/${encodeURIComponent(candidate.id)}/${accept ? 'accept' : 'dismiss'}${bookQuery}`, { expected_revision: candidate.revision, operation_id: `${accept ? 'accept' : 'dismiss'}:${candidate.id}:${candidate.revision}` });
      if (!result?.success) throw new Error(result?.message || '处理候选失败');
      setReloadKey((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '处理候选失败'); }
  };
  const saveCandidate = async (candidate: Candidate) => {
    try {
      const result = await patch(`/mistakes/candidates/${encodeURIComponent(candidate.id)}${bookQuery}`, { expected_revision: candidate.revision, changes: candidateEdit });
      if (!result?.success) throw new Error(result?.message || '校对候选失败');
      setEditingCandidate('');
      setReloadKey((value) => value + 1);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '校对候选失败'); }
  };

  useEffect(() => {
    const restore = sessionStorage.getItem('mistakes:return-focus');
    if (!restore || loading) return;
    const target = rowRefs.current.get(restore);
    if (target) { target.focus(); sessionStorage.removeItem('mistakes:return-focus'); }
  }, [loading, records]);

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };
  const openRecord = (record: MistakeRecord) => {
    sessionStorage.setItem('mistakes:return-focus', record.id);
    const next = new URLSearchParams({ book_name: bookName || 'default', return: `${location.pathname}${location.search}` });
    navigate(`/mistakes/${encodeURIComponent(record.id)}?${next}`);
  };

  return <div className="management-workspace mistakes-workspace flex h-full flex-col">
    <header className="app-page-header border-b border-border bg-bg-primary">
      <h1 className="app-page-title">错题本</h1>
      <div className="window-drag-region" aria-hidden="true" />
      <ScopeSelector subject={subject} bookName={bookName} books={books} suggestions={books.map((book) => book.subject || '').filter(Boolean)} onSubjectChange={setSubject} onBookChange={switchBook} allowAllSubjects align="right" width="wide" />
    </header>
    <main className="management-page-content flex-1 overflow-y-auto">
      <div className="mistakes-collection">
        <div className="mistakes-heading">
          <div><h2 className="workspace-management-title">错题档案</h2><p className="workspace-interface-text text-text-secondary">回看当时的错误，整理修正，再检验能否独立做对。</p></div>
          <div className="mistakes-heading-actions"><Link className="app-secondary-button" to="/mistakes/diagnosis">错误诊断</Link><Link className="app-primary-button" to="/mistakes/intake"><ImagePlus className="h-4 w-4" />补录错题</Link></div>
        </div>
        <div className="mistakes-filters" aria-label="错题筛选">
          {filters.map((item) => <button key={item.id} type="button" aria-pressed={filter === item.id} className={filter === item.id ? 'is-active' : ''} onClick={() => updateParam('filter', item.id === 'all' ? '' : item.id)}>{item.label}{filter === item.id && <span>{records.length}{cursor ? '+' : ''}{item.id === 'pending' && candidates.length ? ` · ${candidates.length} 候选` : ''}</span>}</button>)}
        </div>
        <div className="mistakes-search"><Search className="h-4 w-4" /><input aria-label="搜索题干、知识点、错因" placeholder="搜索题干、知识点、错因" value={search} onChange={(event) => updateParam('q', event.target.value)} /></div>
        {cursor && <p className="mistakes-result-note">已加载 {records.length} 条档案；继续加载可查看更多。</p>}
        {loading && <p className="mistakes-result-note" role="status"><Loader2 className="inline h-4 w-4 animate-spin" /> 正在更新档案…</p>}
        {error && <ActionableIssue title={error} impact="请重试读取本地记录。" actions={<button type="button" className="app-secondary-button" onClick={() => setReloadKey((value) => value + 1)}>重新加载</button>} />}
        {!error && <div className="workspace-register">
          {(filter === 'all' || filter === 'pending') && candidates.map((candidate) => <div key={candidate.id} className="workspace-register-row mistakes-row mistakes-candidate-row"><div className="mistakes-row-main"><strong className="mistakes-row-title">{candidate.question_text || '题干待校对'}</strong><span className="mistakes-row-meta">待确认收录{candidate.source ? ` · ${candidate.source}` : ''}{candidate.content_complete === false ? ' · 关键内容待补全' : ''}</span>{editingCandidate === candidate.id && <div className="mistakes-candidate-editor"><label>题干与条件<textarea className="app-field" value={candidateEdit.question_text} onChange={(event) => setCandidateEdit((current) => ({ ...current, question_text: event.target.value }))} rows={5} /></label><label>当时作答<textarea className="app-field" value={candidateEdit.user_answer} onChange={(event) => setCandidateEdit((current) => ({ ...current, user_answer: event.target.value }))} rows={3} /></label><label>参考答案<textarea className="app-field" value={candidateEdit.correct_answer} onChange={(event) => setCandidateEdit((current) => ({ ...current, correct_answer: event.target.value }))} rows={3} /></label><label><input type="checkbox" checked={candidateEdit.content_complete} onChange={(event) => setCandidateEdit((current) => ({ ...current, content_complete: event.target.checked }))} />题干、关键条件与附图已核对完整</label><button type="button" onClick={() => void saveCandidate(candidate)} className="app-primary-button">保存校对</button></div>}</div><div className="mistakes-heading-actions"><button type="button" onClick={() => resolveCandidate(candidate, false)} className="app-secondary-button">忽略</button><button type="button" onClick={() => { setEditingCandidate(candidate.id); setCandidateEdit({ question_text: candidate.question_text || '', user_answer: candidate.user_answer || '', correct_answer: candidate.correct_answer || '', content_complete: candidate.content_complete !== false }); }} className="app-secondary-button">校对</button><button type="button" disabled={!candidate.question_text || candidate.content_complete === false} onClick={() => resolveCandidate(candidate, true)} className="app-primary-button">确认收录</button></div></div>)}
          {records.map((record) => <div key={record.id} className="workspace-register-row mistakes-row">
            <button ref={(element) => { if (element) rowRefs.current.set(record.id, element); else rowRefs.current.delete(record.id); }} type="button" onClick={() => openRecord(record)} className="mistakes-row-button">
              <div className="mistakes-row-main"><div className="mistakes-row-title"><SimpleMarkdown content={recordTitle(record)} /></div><span className="mistakes-row-meta">{[record.subject || '未分类', record.chapter, record.mistake_type?.join('、'), record.source].filter(Boolean).join(' · ') || '来源未记录'}</span></div>
              <span className="mistakes-row-end"><span className="mistakes-row-status">{nextAction(record)}</span><ArrowRight className="h-4 w-4" /></span>
            </button>
          </div>)}
          {!loading && records.length === 0 && candidates.length === 0 && !search && filter === 'all' && <div className="mistakes-empty"><h3>还没有错题档案</h3><p>练习中的错误可以带着作答一起收录；也可以补录已有错题。</p><div><Link className="app-primary-button" to="/exercises">去练习</Link><Link className="app-secondary-button" to="/mistakes/intake">补录错题</Link></div></div>}
          {!loading && records.length === 0 && (filter !== 'all' || Boolean(search)) && <div className="mistakes-empty"><h3>当前条件下没有档案</h3><p>可以调整筛选或搜索条件。</p><button className="app-secondary-button" onClick={() => { setParams({}); }}>清除筛选</button></div>}
        </div>}
        {cursor && !error && <div className="mistakes-load-more"><button type="button" disabled={moreLoading} className="app-secondary-button" onClick={loadMore}>{moreLoading ? '加载中…' : '加载更多'}</button></div>}
      </div>
    </main>
  </div>;
}

export function MistakeDetailPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { bookName } = useChatContext();
  const [record, setRecord] = useState<ProjectedMistake | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState({ question_text: '', user_answer: '', correct_answer: '', notes: '', mistake_type: '', tags: '' });
  const [meaningChanged, setMeaningChanged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [imageUrl, setImageUrl] = useState('');
  const scope = params.get('book_name') || bookName || 'default';
  const returnPath = params.get('return')?.startsWith('/mistakes') ? params.get('return')! : '/mistakes';
  const load = useCallback(() => {
    if (!id) return;
    let active = true;
    setLoading(true);
    get(`/mistakes/${encodeURIComponent(id)}?book_name=${encodeURIComponent(scope)}`).then((result) => {
      if (!active) return;
      if (result?.success) {
        const next = result.data as ProjectedMistake;
        setRecord(next);
        setEdit({ question_text: next.question_text, user_answer: next.user_answer, correct_answer: next.correct_answer, notes: (next as ProjectedMistake & { notes?: string }).notes || '', mistake_type: (next.mistake_type || []).join('、'), tags: (next.tags || []).join('、') });
        setError('');
      }
      else setError(result?.message || '找不到这道错题');
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '读取错题失败'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id, scope]);
  useEffect(() => load(), [load]);
  useEffect(() => {
    if (!record?.image_path || !id) return;
    let active = true;
    let objectUrl = '';
    getAuthenticatedBlob(`/mistakes/${encodeURIComponent(id)}/image?book_name=${encodeURIComponent(scope)}`)
      .then((blob) => { objectUrl = URL.createObjectURL(blob); if (active) setImageUrl(objectUrl); else URL.revokeObjectURL(objectUrl); })
      .catch(() => { if (active) setImageUrl(''); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); setImageUrl(''); };
  }, [id, record?.image_path, scope]);
  const runAction = async (action: string) => {
    if (!record?.revision || busy) return;
    setBusy(true);
    try {
      const result = await post(`/mistakes/${encodeURIComponent(record.id)}/actions?book_name=${encodeURIComponent(scope)}`, { expected_revision: record.revision, operation_id: `${action}:${record.id}:${record.revision}`, action });
      if (!result?.success) throw new Error(result?.message || '更新失败');
      load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '更新失败'); }
    finally { setBusy(false); }
  };
  const saveEdit = async () => {
    if (!record?.revision || busy) return;
    setBusy(true);
    try {
      const result = await patch(`/mistakes/${encodeURIComponent(record.id)}?book_name=${encodeURIComponent(scope)}`, {
        expected_revision: record.revision, operation_id: `edit:${record.id}:${crypto.randomUUID()}`,
        meaning_changed: meaningChanged,
        changes: { question_text: edit.question_text, user_answer: edit.user_answer, correct_answer: edit.correct_answer, notes: edit.notes,
          mistake_type: edit.mistake_type.split(/[、,，]/).map((item) => item.trim()).filter(Boolean), tags: edit.tags.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
          diagnosis_status: edit.mistake_type.trim() ? 'confirmed' : 'deferred' },
      });
      if (!result?.success) throw new Error(result?.message || '保存失败');
      setEditing(false);
      setMeaningChanged(false);
      load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败'); }
    finally { setBusy(false); }
  };
  const startRedo = async () => {
    if (!record || busy) return;
    setBusy(true);
    try {
      const result = await post('/review/sessions', { book_name: scope, mistake_ids: [record.id] });
      if (!result?.success) throw new Error(result?.message || '无法开始重做');
      navigate(`/learning/review/${encodeURIComponent(result.data.id)}?book_name=${encodeURIComponent(scope)}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法开始重做'); setBusy(false); }
  };
  return <div className="management-workspace mistakes-workspace flex h-full flex-col">
    <header className="app-page-header border-b border-border bg-bg-primary"><Link to={returnPath} className="mistakes-back"><ArrowLeft className="h-4 w-4" />返回档案</Link><div className="window-drag-region" aria-hidden="true" /></header>
    <main className="management-page-content flex-1 overflow-y-auto"><article className="mistakes-detail">
      {loading && <p role="status" className="workspace-interface-text text-text-secondary">正在读取档案…</p>}
      {error && <ActionableIssue title="档案暂时无法打开" impact={error} actions={<button className="app-secondary-button" onClick={() => load()}>重试</button>} />}
      {!loading && record && !error && <>
        <div className="mistakes-detail-intro"><p className="workspace-meta-text text-text-secondary">{[record.subject || '未分类', record.chapter, record.source, displayDate(record.created_at)].filter(Boolean).join(' · ')}</p><h1><SimpleMarkdown content={recordTitle(record)} /></h1><p className="workspace-interface-text text-text-secondary">{nextAction(record)}{record.mastery_status === 'mastered' ? ` · ${record.mastery_source === 'manual' ? '手动标记，未有重做证据' : '有独立重做证据'}` : ''}</p><div className="mistakes-heading-actions"><button type="button" disabled={busy || record.content_status === 'needs_correction'} onClick={startRedo} className="app-primary-button">现在重做</button><button type="button" onClick={() => setEditing((value) => !value)} className="app-secondary-button">{editing ? '取消编辑' : '编辑档案'}</button><button type="button" disabled={busy} onClick={() => runAction(record.visibility === 'archived' ? 'restore' : 'archive')} className="app-secondary-button">{record.visibility === 'archived' ? '恢复档案' : '归档'}</button></div><details className="mistakes-detail-more"><summary>更多管理操作</summary><div className="mistakes-heading-actions">{record.content_status === 'needs_correction' && <button type="button" disabled={busy} onClick={() => runAction('confirm_content')} className="app-secondary-button">确认题目已校对</button>}{record.diagnosis_status === 'missing' && <button type="button" disabled={busy} onClick={() => runAction('defer_diagnosis')} className="app-secondary-button">暂不确定错因</button>}{record.mastery_status !== 'mastered' && <button type="button" disabled={busy} onClick={() => runAction('mark_mastered')} className="app-secondary-button">手动标记掌握</button>}</div></details></div>
        {editing && <section className="mistakes-detail-edit"><h2>校正档案</h2><label>题目<textarea className="app-field" rows={6} value={edit.question_text} onChange={(event) => setEdit((current) => ({ ...current, question_text: event.target.value }))} /></label><label>当时作答或事后补充<textarea className="app-field" rows={4} value={edit.user_answer} onChange={(event) => setEdit((current) => ({ ...current, user_answer: event.target.value }))} /></label><label>参考答案<textarea className="app-field" rows={4} value={edit.correct_answer} onChange={(event) => setEdit((current) => ({ ...current, correct_answer: event.target.value }))} /></label><label>修正做法<textarea className="app-field" rows={3} value={edit.notes} onChange={(event) => setEdit((current) => ({ ...current, notes: event.target.value }))} /></label><label>错因分类（用顿号分隔）<input className="app-field" value={edit.mistake_type} onChange={(event) => setEdit((current) => ({ ...current, mistake_type: event.target.value }))} /></label><label>知识点（用顿号分隔）<input className="app-field" value={edit.tags} onChange={(event) => setEdit((current) => ({ ...current, tags: event.target.value }))} /></label>{(edit.question_text !== record.question_text || edit.correct_answer !== record.correct_answer) && <label className="mistakes-edit-impact"><input type="checkbox" checked={meaningChanged} onChange={(event) => setMeaningChanged(event.target.checked)} />这次修改改变题意或参考答案，重新计算掌握依据</label>}<button type="button" disabled={busy || !edit.question_text.trim()} onClick={saveEdit} className="app-primary-button">保存修改</button></section>}
        <section><h2>题目</h2><div className="workspace-reading-content"><ChatMessage role="assistant" content={record.question_text || record.ocr_text || '题干尚未记录'} linkedConcepts={record.linked_concepts || []} /></div>{record.attachments?.length ? <details><summary>对照原图与附图（{record.attachments.length} 张）</summary>{record.attachments.map((attachment) => <MistakeAttachment key={attachment.id} mistakeId={record.id} attachmentId={attachment.id} bookName={scope} />)}</details> : imageUrl && <details><summary>对照原图</summary><img className="mistakes-original-image" src={imageUrl} alt="错题原图" /></details>}{record.image_path && !imageUrl && !record.attachments?.length && <p className="mistakes-detail-note">原图暂时无法读取，已保存的题干仍可查看。</p>}</section>
        {record.source_ref && Object.keys(record.source_ref).length > 0 && <section><h2>来源</h2><p className="mistakes-detail-note">{String(record.source_ref.type || '记录来源')} · {String(record.source_ref.exercise_id || record.source_ref.message_id || record.source_ref.page || '已保存来源快照')}</p><Link className="app-secondary-button" to={record.source_ref.type === 'chat' ? '/' : String(record.source_ref.type || '').startsWith('exercise') ? '/exercises' : '/books'}>打开来源工作区</Link></section>}
        <section><h2>我当时怎么做</h2>{record.user_answer ? <div className="workspace-reading-content"><ChatMessage role="assistant" content={record.user_answer} /></div> : <p className="mistakes-detail-note">未保留当时的作答。现有记录无法还原具体错误步骤。</p>}</section>
        <section><h2>应怎样修正</h2>{record.mistake_type?.length ? <p className="mistakes-detail-note">错因分类：{record.mistake_type.join('、')}</p> : <p className="mistakes-detail-note">尚未整理错因，可暂不确定。</p>}{record.tags?.length > 0 && <p className="mistakes-detail-note">相关知识点：{record.tags.join('、')}</p>}{(record as ProjectedMistake & { notes?: string }).notes && <div className="workspace-reading-content"><ChatMessage role="assistant" content={(record as ProjectedMistake & { notes?: string }).notes || ''} /></div>}{record.correct_answer && <details><summary>查看参考答案</summary><div className="workspace-reading-content"><ChatMessage role="assistant" content={record.correct_answer} /></div></details>}{record.explanation && <details><summary>查看已保存解析</summary><div className="workspace-reading-content"><ChatMessage role="assistant" content={record.explanation} /></div></details>}</section>
        <section><h2>后续重做</h2>{record.recent_attempts?.length ? <ol className="mistakes-history">{record.recent_attempts.map((attempt) => <li key={attempt.id}><span>{displayDate(attempt.created_at)}</span><strong>{attempt.kind === 'occurrence' ? '再次出错' : attempt.result === 'independent_correct' ? '独立做对' : attempt.result === 'prompted_correct' ? '有提示后做对' : attempt.result === 'partial' ? '部分完成' : '做错'}</strong><span>{attempt.judgement_source === 'deterministic' ? '确定性校验' : '用户确认'}{attempt.answer ? ` · 作答：${attempt.answer.slice(0, 80)}` : ''}</span></li>)}</ol> : <p className="mistakes-detail-note">还没有保存独立重做记录。</p>}{record.review_history?.length ? <details><summary>旧版复习自评（不计入掌握证据）</summary><ol className="mistakes-history">{[...record.review_history].reverse().map((item, index) => <li key={`${item.date}-${index}`}><span>{displayDate(item.date)}</span><strong>自评 {item.quality}/5</strong><span>下次复习 {displayDate(item.next_review)}</span></li>)}</ol></details> : null}{record.next_review && <p className="mistakes-detail-note">当前安排：{displayDate(record.next_review)}</p>}<Link to="/learning" className="app-secondary-button"><BookOpen className="h-4 w-4" />前往全局复习</Link></section>
      </>}
    </article></main>
  </div>;
}

export function MistakeDiagnosisPage() {
  const { bookName, subject } = useMistakeScope();
  type Diagnosis = { record_count: number; groups: { name: string; mistake_ids: string[]; recent_wrong: number; recent_attempts: number; recent_correct: number }[]; reasons: { name: string; mistake_ids: string[]; example: string }[]; unconfirmed_diagnosis_count: number; comparison: { cohort_mistake_ids: string[]; prior_correct: number; prior_total: number; recent_correct: number; recent_total: number; comparable: boolean }; actions: { mistake_id: string; reason: string }[]; scope: { prior_start: string; recent_start: string; end: string } };
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ book_name: bookName || 'default', subject });
    setLoading(true);
    get(`/mistakes/diagnosis?${query}`).then((result) => {
      if (!active) return;
      if (result?.success) { setDiagnosis(result.data); setError(''); }
      else setError('诊断数据暂时无法读取');
      setLoading(false);
    }).catch(() => { if (active) { setError('诊断数据暂时无法读取'); setLoading(false); } });
    return () => { active = false; };
  }, [bookName, subject, reloadKey]);
  const queryBook = `book_name=${encodeURIComponent(bookName || 'default')}`;
  return <div className="management-workspace mistakes-workspace flex h-full flex-col"><header className="app-page-header border-b border-border bg-bg-primary"><Link className="mistakes-back" to="/mistakes"><ArrowLeft className="h-4 w-4" />返回错题档案</Link><div className="window-drag-region" aria-hidden="true" /></header><main className="management-page-content flex-1 overflow-y-auto"><div className="mistakes-detail"><h1>错误诊断</h1><p className="mistakes-detail-note">当前范围内已收录 {loading || error ? '—' : diagnosis?.record_count ?? '—'} 道错题。仅统计已收录档案；缺少全部练习作答分母，不能据此判断知识点错误率。</p>
    {loading && <p role="status" className="mistakes-detail-note">正在读取诊断数据…</p>}
    {error && <ActionableIssue title={error} impact="错题档案仍可使用。" actions={<button className="app-secondary-button" onClick={() => setReloadKey((value) => value + 1)}>重试</button>} />}
    {!error && !loading && diagnosis && <><section><h2>哪里容易错</h2><p className="mistakes-detail-note">近 30 天独立重做；同一题可关联多个知识点。错误次数只来自已保存的有效重做。</p>{diagnosis.groups.length ? <ol className="mistakes-diagnosis-list">{diagnosis.groups.slice(0, 8).map((group) => <li key={group.name}><Link to={`/mistakes?q=${encodeURIComponent(group.name)}`}>{group.name}</Link><span>{group.mistake_ids.length} 道题 · {group.recent_wrong}/{group.recent_attempts} 次重做未独立做对</span></li>)}</ol> : <p className="mistakes-detail-note">当前范围没有知识点标注。</p>}</section><section><h2>为什么错</h2>{diagnosis.reasons.length ? <ol className="mistakes-diagnosis-list">{diagnosis.reasons.slice(0, 8).map((reason) => <li key={reason.name}><Link to={`/mistakes?q=${encodeURIComponent(reason.name)}`}>{reason.name}</Link><span>{reason.mistake_ids.length} 道已确认{reason.example ? ` · ${reason.example.slice(0, 48)}` : ''}</span></li>)}</ol> : <p className="mistakes-detail-note">还没有经确认的具体错因。</p>}<p className="mistakes-detail-note">另有 {diagnosis.unconfirmed_diagnosis_count} 道题的归因尚未确认或已暂缓。</p></section><section><h2>是否改善</h2><p className="mistakes-detail-note">仅比较前后两个 30 天窗口都出现的同一组 {diagnosis.comparison.cohort_mistake_ids.length} 道题；排除提示作答与旧版 quality 自评。</p><p>前一窗口独立正确 {diagnosis.comparison.prior_correct}/{diagnosis.comparison.prior_total} 次；近 30 天 {diagnosis.comparison.recent_correct}/{diagnosis.comparison.recent_total} 次。</p><p className="mistakes-detail-note">{diagnosis.comparison.comparable ? (diagnosis.comparison.recent_correct / diagnosis.comparison.recent_total > diagnosis.comparison.prior_correct / diagnosis.comparison.prior_total ? '同题组近期独立正确比例上升；这只是已收录重做的观察。' : '同题组近期独立正确比例没有上升。') : '两窗口需各有至少 5 次有效独立作答且覆盖至少 3 道题，才能比较趋势；目前仅列出事实。'}</p></section><section><h2>下一步做什么</h2>{diagnosis.actions.length ? <ol className="mistakes-diagnosis-list">{diagnosis.actions.map((action) => <li key={action.mistake_id}><Link to={`/mistakes/${encodeURIComponent(action.mistake_id)}?${queryBook}`}>{action.reason}</Link><span>打开对应档案</span></li>)}</ol> : <p className="mistakes-detail-note">当前没有待校对或到期的档案。</p>}<div className="mistakes-diagnosis-actions"><Link className="app-secondary-button" to="/mistakes?filter=pending"><ClipboardList className="h-4 w-4" />查看待处理</Link><Link className="app-secondary-button" to="/learning"><BookOpen className="h-4 w-4" />查看复习队列</Link></div></section></>}
  </div></main></div>;
}

export default function MistakesPage() {
  const [params] = useSearchParams();
  const focusedId = params.get('mistake_id');
  if (focusedId) {
    const next = new URLSearchParams();
    if (params.get('book_name')) next.set('book_name', params.get('book_name')!);
    return <Navigate replace to={`/mistakes/${encodeURIComponent(focusedId)}${next.size ? `?${next}` : ''}`} />;
  }
  if (params.get('tab') === 'review') return <Navigate replace to="/learning/review" />;
  if (params.get('tab') === 'capture' || params.get('tab') === 'entry') return <Navigate replace to="/mistakes/intake" />;
  return <MistakeCollectionPage />;
}
