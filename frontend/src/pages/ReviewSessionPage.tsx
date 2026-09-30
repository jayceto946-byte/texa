import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { get, patch, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import { useChatContext } from '../contexts/ChatContext';
import type { MistakeRecord } from '../types';
import './ReviewSessionPage.css';

type ReviewItem = Pick<MistakeRecord, 'id' | 'question_text' | 'correct_answer' | 'explanation' | 'source' | 'subject' | 'chapter'>;
type Session = { id: string; revision: number; items: string[]; index: number; results: Record<string, string>; current_answer: string; revealed: boolean; current_item: ReviewItem | null };

function ReviewSessionStart() {
  const { bookName, subject } = useChatContext();
  const navigate = useNavigate();
  const [items, setItems] = useState<MistakeRecord[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ book_name: bookName || 'default', subject });
    get(`/mistakes/due?${query}`).then((result) => {
      if (!active) return;
      if (result?.success) setItems(result.data || []);
      else setError(result?.message || '无法读取到期错题');
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : '无法读取到期错题'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [bookName, subject]);
  const start = async () => {
    if (starting || !items.length) return;
    setStarting(true);
    setError('');
    try {
      const result = await post('/review/sessions', { book_name: bookName || 'default', mistake_ids: items.map((item) => item.id) });
      if (!result?.success) throw new Error(result?.message || '无法创建复习会话');
      navigate(`/learning/review/${encodeURIComponent(result.data.id)}?book_name=${encodeURIComponent(bookName || 'default')}`, { replace: true });
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法创建复习会话'); setStarting(false); }
  };
  return <div className="management-workspace review-session-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><Link to="/learning" className="review-session-back"><ArrowLeft className="h-4 w-4" />返回复习</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="review-session-body"><h1>本次错题复习</h1>{loading ? <p role="status">正在读取到期错题…</p> : <p>当前范围有 {items.length} 道到期错题。开始后题目顺序固定，退出后可继续同一会话。</p>}{error && <p role="alert" className="review-session-error">{error}</p>}{!loading && items.length > 0 && <button type="button" onClick={start} disabled={starting} className="app-primary-button">{starting && <Loader2 className="h-4 w-4 animate-spin" />}开始复习</button>}{!loading && items.length === 0 && <Link to="/mistakes" className="app-secondary-button">查看错题档案</Link>}</div></main></div>;
}

function ReviewSessionRun({ sessionId }: { sessionId: string }) {
  const { bookName } = useChatContext();
  const navigate = useNavigate();
  const scope = new URLSearchParams(location.search).get('book_name') || bookName || 'default';
  const [session, setSession] = useState<Session | null>(null);
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const query = `?book_name=${encodeURIComponent(scope)}`;
  const load = useCallback(async () => {
    try {
      const result = await get(`/review/sessions/${encodeURIComponent(sessionId)}${query}`);
      if (!result?.success) throw new Error(result?.message || '无法恢复复习会话');
      setSession(result.data as Session);
      setAnswer(result.data.current_answer || '');
      setError('');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法恢复复习会话'); }
    finally { setLoading(false); }
  }, [query, sessionId]);
  useEffect(() => { void load(); }, [load]);
  const saveAnswer = async () => {
    if (!session || busy || session.revealed) return;
    setBusy(true);
    setError('');
    try {
      const result = await patch(`/review/sessions/${encodeURIComponent(session.id)}${query}`, { expected_revision: session.revision, answer, revealed: false });
      if (!result?.success) throw new Error(result?.message || '保存作答失败');
      setSession((current) => current ? { ...current, ...result.data } : current);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存作答失败'); }
    finally { setBusy(false); }
  };
  const reveal = async () => {
    if (!session || busy) return;
    setBusy(true);
    setError('');
    try {
      let revision = session.revision;
      if (answer !== session.current_answer) {
        const saved = await patch(`/review/sessions/${encodeURIComponent(session.id)}${query}`, { expected_revision: revision, answer, revealed: false });
        if (!saved?.success) throw new Error(saved?.message || '保存作答失败');
        revision = saved.data.revision;
      }
      const revealed = await patch(`/review/sessions/${encodeURIComponent(session.id)}${query}`, { expected_revision: revision, answer: '', revealed: true });
      if (!revealed?.success) throw new Error(revealed?.message || '读取反馈失败');
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '读取反馈失败'); }
    finally { setBusy(false); }
  };
  const submit = async (result: string) => {
    if (!session || busy) return;
    setBusy(true);
    setError('');
    try {
      const operationId = `review:${session.id}:${session.index}`;
      const response = await post(`/review/sessions/${encodeURIComponent(session.id)}/results${query}`, { expected_revision: session.revision, operation_id: operationId, result, hint_used: result === 'prompted_correct', judgement_source: 'user_confirmed' });
      if (!response?.success) throw new Error(response?.message || '记录复习结果失败');
      setAnswer('');
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : '记录复习结果失败'); }
    finally { setBusy(false); }
  };
  return <div className="management-workspace review-session-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><button type="button" className="review-session-back" onClick={() => navigate('/learning')}><ArrowLeft className="h-4 w-4" />返回复习</button></header><main className="management-page-content flex-1 overflow-y-auto"><div className="review-session-body">
    {loading && <p role="status">正在恢复复习会话…</p>}
    {error && <p role="alert" className="review-session-error">{error} <button type="button" onClick={() => load()}>重试读取</button></p>}
    {session && <><p className="review-session-progress">第 {Math.min(session.index + 1, session.items.length)} / {session.items.length} 题</p>{session.current_item ? <>
      <h1>独立重做</h1><section className="review-session-question"><ChatMessage role="assistant" content={session.current_item.question_text} /></section>
      {!session.revealed ? <section><label htmlFor="review-answer">先写下本次答案，再查看参考与反馈</label><textarea id="review-answer" value={answer} onChange={(event) => setAnswer(event.target.value)} className="app-field review-session-answer" placeholder="可写步骤、结果，或记录卡住的位置" /><div className="review-session-actions"><button type="button" onClick={saveAnswer} disabled={busy || answer === session.current_answer} className="app-secondary-button">保存草稿</button><button type="button" onClick={reveal} disabled={busy} className="app-primary-button">提交作答并查看反馈</button></div></section> : <section><p className="review-session-saved-answer">本次作答：{session.current_answer || '未填写；本次不能计为独立正确'}</p><h2>参考答案</h2><div className="workspace-reading-content"><ChatMessage role="assistant" content={session.current_item.correct_answer || '未保存参考答案，请根据已保存解析自评；结果会标记为用户确认。'} /></div>{session.current_item.explanation && <details><summary>查看已保存解析</summary><div className="workspace-reading-content"><ChatMessage role="assistant" content={session.current_item.explanation} /></div></details>}<h2>确认这次结果</h2><div className="review-session-actions">{[['wrong', '不会或做错'], ['partial', '部分完成'], ['prompted_correct', '有提示后做对'], ['independent_correct', '独立做对']].map(([value, label]) => <button key={value} type="button" disabled={busy || value === 'independent_correct' && !session.current_answer.trim()} onClick={() => submit(value)} className="app-secondary-button">{label}</button>)}</div></section>}
    </> : <><h1>本次复习完成</h1><p>已记录 {Object.keys(session.results).length} 次复习。答案、揭示和自评保留在同一会话中。</p><Link to="/learning" className="app-primary-button">返回复习队列</Link></>}</>}
  </div></main></div>;
}

export default function ReviewSessionPage() {
  const { sessionId } = useParams();
  return sessionId ? <ReviewSessionRun sessionId={sessionId} /> : <ReviewSessionStart />;
}
