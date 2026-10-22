import { readableVisualQuestion } from '../utils/visualQuestion';
import WorkspaceSkeleton from '../components/ui/WorkspaceSkeleton';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ImagePlus, Loader2 } from 'lucide-react';
import { get, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import { useChatContext } from '../contexts/ChatContext';
import type { MistakeRecord } from '../types';
import './ReviewSessionPage.css';
import QuestionImage from '../components/chat/QuestionImage';
import { useReviewSession } from '../features/mistakes/hooks/useReviewSession';

function ReviewSessionStart() {
  const { bookName, subject } = useChatContext();
  const navigate = useNavigate();
  const [items, setItems] = useState<MistakeRecord[]>([]);
  const [error, setError] = useState('');
  const [readError, setReadError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setReadError('');
    setError('');
    setItems([]);
    const query = new URLSearchParams({ book_name: bookName || 'default', subject });
    get(`/mistakes/due?${query}`).then((result) => {
      if (!active) return;
      if (result?.success) setItems(result.data || []);
      else setReadError(result?.message || '无法读取到期错题');
    }).catch((cause) => { if (active) setReadError(cause instanceof Error ? cause.message : '无法读取到期错题'); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [bookName, subject, reloadKey]);
  const start = async () => {
    if (starting || loading || readError || !items.length) return;
    setStarting(true);
    setError('');
    try {
      const result = await post('/review/sessions', { book_name: bookName || 'default', mistake_ids: items.map((item) => item.id) });
      if (!result?.success) throw new Error(result?.message || '无法创建复习会话');
      navigate(`/learning/review/${encodeURIComponent(result.data.id)}?book_name=${encodeURIComponent(bookName || 'default')}`, { replace: true });
    } catch (cause) { setError(cause instanceof Error ? cause.message : '无法创建复习会话'); setStarting(false); }
  };
  return <div className="management-workspace review-session-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题复习</h1><Link to="/learning" className="review-session-back"><ArrowLeft className="h-4 w-4" />返回复习</Link></header><main className="management-page-content flex-1 overflow-y-auto"><div className="review-session-body"><h1>本次错题复习</h1>{loading ? <WorkspaceSkeleton label="正在读取到期错题" header={false} /> : !readError && <p>当前范围有 {items.length} 道到期错题。开始后题目顺序固定，退出后可继续同一会话。</p>}{readError && <div role="alert" className="review-session-error"><p>{readError}</p><button type="button" className="app-secondary-button" onClick={() => setReloadKey(key => key + 1)}>重试读取</button></div>}{error && <p role="alert" className="review-session-error">{error}</p>}{!loading && !readError && items.length > 0 && <button type="button" onClick={start} disabled={starting} className="app-primary-button">{starting && <Loader2 className="h-4 w-4 animate-spin" />}开始复习</button>}{!loading && !readError && items.length === 0 && <Link to="/mistakes" className="app-secondary-button">查看错题档案</Link>}</div></main></div>;
}

function ReviewSessionRun({ sessionId }: { sessionId: string }) {
  const { bookName } = useChatContext();
  const navigate = useNavigate();
  const scope = new URLSearchParams(location.search).get('book_name') || bookName || 'default';
  const { session, answer, setAnswer, error, loading, busy, refresh, saveAnswer, reveal, upload, removeImage, submit } = useReviewSession(sessionId, scope);
  const imageInput = useRef<HTMLInputElement>(null);
  return <div className="management-workspace review-session-workspace flex h-full flex-col"><header className="app-page-header border-b border-border"><h1 className="app-page-title">错题复习</h1><button type="button" className="review-session-back" onClick={() => navigate('/learning')}><ArrowLeft className="h-4 w-4" />返回复习</button></header><main className="management-page-content flex-1 overflow-y-auto"><div className="review-session-body">
    {loading && <p role="status">正在恢复复习会话…</p>}
    {error && <p role="alert" className="review-session-error">{error} <button type="button" onClick={() => void refresh()}>重试读取</button></p>}
    {session && <><p className="review-session-progress">第 {Math.min(session.index + 1, session.items.length)} / {session.items.length} 题</p>{session.current_item ? <>
      <h1>独立重做</h1><section className="review-session-question"><ChatMessage role="assistant" content={readableVisualQuestion(session.current_item.question_text)} /></section>
      {!session.revealed ? <section className="review-answer-composer" onPaste={event => {
        const image = Array.from(event.clipboardData.files).find(file => file.type.startsWith('image/'));
        if (image) { event.preventDefault(); void upload(image); }
      }}>
        <label htmlFor="review-answer">写下答案，或上传手写解答</label>
        {session.feedback?.verdict === 'unreadable' && <p className="review-answer-hint" role="status">{session.feedback.summary} 请更换清晰、完整的图片后再提交。</p>}
        <textarea id="review-answer" value={answer} disabled={busy} onChange={event => setAnswer(event.target.value)} className="app-field review-session-answer" placeholder="可写步骤、结果，或记录卡住的位置" />
        {session.current_submission && <div className="review-photo-submission" key={session.current_submission.image_url + session.revision}>
          <QuestionImage path={session.current_submission.image_url} label="作答图片" />
          <button type="button" className="app-ghost-button" disabled={busy} onClick={() => void removeImage()}>移除图片</button>
        </div>}
        <input ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp,image/bmp" hidden aria-label="选择手写解答图片" onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void upload(file); }} />
        <div className="review-session-actions">
          <button type="button" className="app-secondary-button" disabled={busy} onClick={() => imageInput.current?.click()}><ImagePlus size={16} />{session.current_submission ? '更换图片' : '上传解答'}</button>
          <button type="button" onClick={() => void saveAnswer()} disabled={busy || answer === session.current_answer} className="app-secondary-button">保存草稿</button>
          <button type="button" onClick={() => void reveal()} disabled={busy} className="app-primary-button">{busy ? <><Loader2 size={15} className="animate-spin" />正在处理…</> : session.current_submission ? '提交作答并批改' : '提交作答并查看反馈'}</button>
        </div>
        <p className="review-answer-hint">支持粘贴解答图片。照片提交后展示批改意见，复习结果由你确认。</p>
      </section> : <section>
        {session.current_answer && <div className="review-session-saved-answer"><h2>本次作答</h2><ChatMessage role="assistant" content={session.current_answer} /></div>}
        {session.current_submission && <QuestionImage path={session.current_submission.image_url} label="作答图片" />}
        {session.feedback && <div className="review-feedback">
          <h2>AI 批改 <span>{({ correct: '解答正确', partial: '部分正确', wrong: '需要修改', unreadable: '需要更清晰的图片' })[session.feedback.verdict]}</span></h2>
          <ChatMessage role="assistant" content={session.feedback.summary} />
          {!!session.feedback.issues.length && <><h3>问题与原因</h3>{session.feedback.issues.map((text, index) => <ChatMessage key={index} role="assistant" content={text} />)}</>}
          {!!session.feedback.suggestions.length && <><h3>修改建议</h3>{session.feedback.suggestions.map((text, index) => <ChatMessage key={index} role="assistant" content={text} />)}</>}
        </div>}
        <h2>参考答案</h2><div className="workspace-reading-content"><ChatMessage role="assistant" content={session.current_item.correct_answer || '未保存参考答案，请根据已保存解析自评。'} /></div>
        {session.current_item.explanation && <details><summary>查看已保存解析</summary><div className="workspace-reading-content"><ChatMessage role="assistant" content={session.current_item.explanation} /></div></details>}
        <h2>确认这次结果</h2><div className="review-session-actions">{[['wrong', '不会或做错'], ['partial', '部分完成'], ['prompted_correct', '有提示后做对'], ['independent_correct', '独立做对']].map(([value, label]) => <button key={value} type="button" disabled={busy || value === 'independent_correct' && !session.current_answer.trim() && !session.current_submission} onClick={() => void submit(value)} className="app-secondary-button">{label}</button>)}</div>
      </section>}

    </> : <><h1>本次复习完成</h1><p>已记录 {Object.keys(session.results).length} 次复习。答案、揭示和自评保留在同一会话中。</p><Link to="/learning" className="app-primary-button">返回复习队列</Link></>}</>}
  </div></main></div>;
}

export default function ReviewSessionPage() {
  const { sessionId } = useParams();
  return sessionId ? <ReviewSessionRun sessionId={sessionId} /> : <ReviewSessionStart />;
}
