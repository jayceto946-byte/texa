import { useLocation } from 'react-router-dom';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CalendarClock, Check, Circle, Loader2, Pause, Play, Plus, ArrowLeft } from 'lucide-react';
import { get, post } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { LearningTaskState, AssistantSource } from '../types';
import type { TextbookRecord } from '../utils/textbookScopes';
import { buildTextbookScopeOptions } from '../utils/textbookScopes';
import { goalListState, selectedGoalAfterChange, visibleGoals as filterGoals, type GoalFilter, type GoalListStatus } from '../features/goals/goalViewState';
import ScopeSelector from '../components/ScopeSelector';
import LearningTaskActions from '../components/chat/LearningTaskActions';
import ChatMessage from '../components/ChatMessage';

type Goal = { id: string; title: string; objective: string; status: string; revision: number;
  success_criteria: Array<{id: string; description?: string}>; scope: { book_name?: string; subject?: string };
  next_action?: { kind: string; due_at: string; interval_hours: number } | null };
type View = 'create' | 'detail';
type ComposerStep = 'edit' | 'review';
const labels: Record<string, string> = { active: '进行中', paused: '已暂停', draft: '待开始', completed: '已完成', cancelled: '已取消',
  running: '正在执行', waiting_for_input: '等待你的补充', waiting_for_confirmation: '等待确认', interrupted: '已停止', failed: '执行失败', degraded: '结果待核验' };

export default function GoalsPage() {
  const location = useLocation();
  const { bookName, subject } = useChatContext();
  const incomingDraft = (location.state as {goalDraft?: string} | null)?.goalDraft;
  const [goals, setGoals] = useState<Goal[]>([]);
  const [listStatus, setListStatus] = useState<GoalListStatus>('loading');
  const [view, setView] = useState<View>(incomingDraft ? 'create' : 'detail');
  const [selected, setSelected] = useState('');
  const [filter, setFilter] = useState<GoalFilter>('all');
  const [mobilePane, setMobilePane] = useState<'list' | 'workspace'>('workspace');
  const [text, setText] = useState(() => String(incomingDraft || '').slice(0, 2000));
  const [draftScope, setDraftScope] = useState(() => ({bookName, subject}));
  const [books, setBooks] = useState<TextbookRecord[]>([]);
  const [proposal, setProposal] = useState<Partial<Goal> | null>(null);
  const [step, setStep] = useState<ComposerStep>('edit');
  const [intakeFailed, setIntakeFailed] = useState(false);
  const [runtime, setRuntime] = useState<LearningTaskState | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [due, setDue] = useState('');
  const [interval, setInterval] = useState(0);
  const selectedListButton = useRef<HTMLButtonElement>(null);
  const allFilterButton = useRef<HTMLButtonElement>(null);
  const listReturnButton = useRef<HTMLButtonElement>(null);
  const scopeBooks = useMemo(() => buildTextbookScopeOptions(books), [books]);
  const visibleGoals = useMemo(() => filterGoals(goals, filter), [goals, filter]);
  const listState = goalListState(listStatus, goals.length, visibleGoals.length);
  const active = goals.find((goal) => goal.id === selected);
  const zeroGoals = listState === 'zero';
  const update = (goal: Goal) => setGoals((current) => [goal, ...current.filter((item) => item.id !== goal.id)]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setListStatus('loading');
    try {
      const response = await get('/goals?limit=100');
      if (!response.success || !Array.isArray(response.data)) throw new Error();
      setGoals(response.data);
      setListStatus('ready');
    } catch {
      if (silent) setActionError('目标列表暂时无法更新，请稍后重试。');
      else setListStatus('error');
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    let cancelled = false;
    get('/books/list').then((response) => { if (!cancelled && response?.success) setBooks(response.data || []); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (typeof incomingDraft === 'string') {
      setText(incomingDraft.slice(0, 2000)); setProposal(null); setStep('edit'); setIntakeFailed(false);
      setView('create'); setMobilePane('workspace');
    }
  }, [location.key, incomingDraft]);
  useEffect(() => {
    if (listStatus !== 'ready') return;
    if (!goals.length) { setView('create'); setSelected(''); return; }
    const visible = filterGoals(goals, filter);
    setSelected((current) => selectedGoalAfterChange(visible, current));
  }, [goals, filter, listStatus]);
  useEffect(() => {
    let cancelled = false;
    setRuntime(null);
    const poll = async () => {
      if (!selected || view !== 'detail') return;
      try {
        const response = await get(`/goals/${encodeURIComponent(selected)}/runtime`);
        if (!cancelled) {
          setRuntime(response.data || null);
          if (response.goal) setGoals((current) => current.map((goal) => goal.id === response.goal.id ? response.goal : goal));
        }
      } catch { if (!cancelled) setActionError('运行状态暂不可用，请刷新。'); }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [selected, view]);
  const action = async (fn: () => Promise<void>) => {
    setBusy(true); setActionError('');
    try { await fn(); } catch (reason) { setActionError(reason instanceof Error ? reason.message : '操作未完成，请重试。'); }
    finally { setBusy(false); }
  };
  const changeScope = (change: Partial<typeof draftScope>) => {
    setDraftScope((current) => ({...current, ...change}));
    setProposal(null); setStep('edit'); setIntakeFailed(false); setActionError('');
  };
  const summarize = () => action(async () => {
    setIntakeFailed(false);
    try {
      const response = await post('/goals/intake/summarize', {text: text.trim(), book_name: draftScope.bookName, subject: draftScope.subject}, 40000);
      if (!response.success) throw new Error('目标未整理完成，请重试。');
      setProposal(response.data); setStep('review');
    } catch (reason) {
      setIntakeFailed(true);
      throw reason;
    }
  });
  const create = (original = false) => action(async () => {
    const value = original ? {title: text.trim().slice(0, 80), objective: text.trim(), success_criteria: [], scope: {book_name: draftScope.bookName, subject: draftScope.subject}} : proposal;
    const response = await post('/goals', value);
    if (!response.success) throw new Error('目标未保存，请重试。');
    update(response.data); setSelected(response.data.id); setFilter('all'); setView('detail'); setMobilePane('workspace');
    setText(''); setProposal(null); setStep('edit'); setIntakeFailed(false);
  });
  const run = (resume?: LearningTaskState) => action(async () => {
    if (!active) return;
    const response = await post(`/goals/${active.id}/run`, { expected_revision: active.revision, request_key: crypto.randomUUID(), task_id: resume?.id || '' }, 40000);
    if (!response.success) throw new Error('目标未开始'); setRuntime(response.data); await load(true);
  });
  const command = (operation: string) => action(async () => {
    if (!active) return;
    const response = await post(`/goals/${active.id}/commands`, {operation, expected_revision: active.revision,
      ...(operation === 'measure' ? {user_confirms_completion: true} : {})});
    if (!response.success) throw new Error('操作未保存'); update(response.data);
    if (operation === 'pause' && runtime?.interruptible) setRuntime({...runtime, status: 'interrupted', interruptible: false, resumable: true});
  });
  const openGoal = (goal: Goal) => {
    setSelected(goal.id); setView('detail'); setMobilePane('workspace'); setScheduleOpen(false); setActionError('');
    requestAnimationFrame(() => listReturnButton.current?.focus());
  };
  const showList = () => {
    setMobilePane('list');
    requestAnimationFrame(() => (selectedListButton.current || allFilterButton.current)?.focus());
  };
  const showCreate = () => { setView('create'); setMobilePane('workspace'); setScheduleOpen(false); setActionError(''); };
  const showDetail = () => { setView('detail'); setMobilePane('workspace'); setActionError(''); };

  return <div className={`goals-workspace ${zeroGoals ? 'goals-zero' : ''}`}>
    <header className="goals-header window-drag-region"><h1>目标与任务</h1>
      {listStatus === 'ready' && goals.length > 0 && view === 'detail' && <button className="app-secondary-button" onClick={showCreate}><Plus size={16} />新目标</button>}
    </header>
    {listStatus === 'loading' ? <div className="goals-page-state" role="status">正在读取目标…</div>
      : listStatus === 'error' ? <div className="goals-page-state" role="alert"><h2>目标暂时无法读取</h2><p>请检查连接后重试。</p><button className="app-secondary-button" onClick={() => void load()}>重试读取</button></div>
      : <div className={`goals-body ${mobilePane === 'list' ? 'goals-show-list' : 'goals-show-workspace'}`}>
        {zeroGoals ? <div className="goals-zero-count">目标 · 0</div> : <aside className="goals-index" aria-label="目标列表">
          <div className="goals-tabs" aria-label="筛选目标"><button ref={allFilterButton} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>全部目标</button><button aria-pressed={filter === 'scheduled'} onClick={() => setFilter('scheduled')}>已安排定时</button></div>
          {visibleGoals.length ? visibleGoals.map((goal) => <button key={goal.id} ref={goal.id === selected ? selectedListButton : undefined} aria-current={goal.id === selected ? 'true' : undefined} className={`goal-list-item ${goal.id === selected ? 'selected' : ''}`} onClick={() => openGoal(goal)}><span><strong>{goal.title}</strong><small>{labels[goal.status] || goal.status}{goal.next_action?.kind === 'schedule' ? ' · 已安排定时' : ''}</small></span></button>)
            : <div className="goals-filter-empty goals-filter-empty-list"><p>0 个目标</p><button className="app-ghost-button" onClick={() => setFilter('all')}>查看全部目标</button></div>}
        </aside>}
        <main className="goal-detail" aria-label="目标工作区">
          {view === 'detail' && actionError && <div role="alert" className="goal-error">{actionError}<button className="app-ghost-button" onClick={() => void load(true)}>刷新状态</button></div>}
          {view === 'create' ? <section className="goal-intake">
            {goals.length > 0 && <button className="goal-back app-ghost-button" onClick={showDetail}><ArrowLeft size={15} />返回目标</button>}
            {step === 'edit' ? <><h2>新建目标</h2><p>描述目标和完成条件，整理后确认保存。</p>
              <textarea aria-label="描述学习目标" placeholder="描述学习目标……" value={text} maxLength={2000} onChange={(event) => {setText(event.target.value); setProposal(null); setIntakeFailed(false); setActionError('');}} disabled={busy} />
              {actionError && <div role="alert" className="goal-error">{actionError}</div>}
              <div className="goal-intake-footer"><ScopeSelector subject={draftScope.subject} bookName={draftScope.bookName} books={scopeBooks} suggestions={books.map((book) => book.subject || '').filter(Boolean)} onSubjectChange={(value) => changeScope({subject: value})} onBookChange={(value) => changeScope({bookName: value})} label="目标范围" emptyBookLabel="不限教材" width="compact" disabled={busy} />
                <button className="app-primary-button" disabled={busy || !text.trim()} onClick={() => void summarize()}>{busy && !intakeFailed ? <Loader2 className="animate-spin" size={16} /> : null}{busy ? '正在整理…' : intakeFailed ? '重新整理' : '整理目标'}</button></div>
              {intakeFailed && <div className="goal-intake-recovery"><p className="goals-muted">整理暂不可用。也可以先保存为待开始目标，稍后再启用。</p><button className="app-ghost-button" disabled={busy || !text.trim()} onClick={() => void create(true)}>保存为待开始目标</button></div>}
            </> : <><p className="goal-eyebrow">确认目标</p><h2>{proposal?.title}</h2>{actionError && <div role="alert" className="goal-error">{actionError}</div>}<p className="goal-objective">{proposal?.objective}</p>
              {!!proposal?.success_criteria?.length && <div className="goal-criteria"><h3>完成条件</h3>{proposal.success_criteria.map((item) => <p key={item.id}><Circle size={12} />{item.description}</p>)}</div>}
              <p className="goals-muted">范围：{proposal?.scope?.subject || '全部学科'} · {proposal?.scope?.book_name || '不限教材'}</p>
              <div className="goal-review-actions"><button className="app-primary-button" disabled={busy} onClick={() => void create()}>{busy ? <Loader2 className="animate-spin" size={16} /> : null}保存目标</button><button className="app-ghost-button" disabled={busy} onClick={() => {setStep('edit'); setActionError('');}}>返回修改</button></div>
            </>}
          </section> : active ? <section className="goal-session">
            <button ref={listReturnButton} className="goal-list-return app-ghost-button" onClick={showList}><ArrowLeft size={15} />目标列表</button>
            <div className="goal-eyebrow">{labels[active.status] || active.status} · {active.scope.subject || '全部学科'} · {active.scope.book_name || '不限教材'}</div><h2>{active.title}</h2>
            <section className="goal-section"><h3>目标说明</h3><p className="goal-objective">{active.objective}</p></section>
            {!!active.success_criteria.length && <section className="goal-section goal-criteria"><h3>完成条件</h3>{active.success_criteria.map((item) => <p key={item.id}><Circle size={12} />{item.description}</p>)}</section>}
            <section className="goal-section"><h3>执行与定时安排</h3><div className="goal-controls">{['draft', 'paused'].includes(active.status) && <button className="app-primary-button" disabled={busy} onClick={() => void command('activate')}><Play size={15} />启用目标</button>}{active.status === 'active' && <><button className="app-primary-button" disabled={busy || runtime?.status === 'running' || runtime?.confirmation_required} onClick={() => void run(runtime?.resumable ? runtime : undefined)}><Play size={15} />{runtime?.resumable ? '继续执行' : '开始执行'}</button><button className="app-secondary-button" disabled={busy} onClick={() => void command('pause')}><Pause size={15} />暂停</button><button className="app-ghost-button" onClick={() => setScheduleOpen(!scheduleOpen)}><CalendarClock size={15} />定时执行</button></>}
              {active.status === 'active' && runtime?.terminal && <button className="app-secondary-button" disabled={busy} onClick={() => {if (window.confirm('你确认这个目标的完成条件已经满足吗？')) void command('measure');}}><Check size={15} />确认目标完成</button>}</div>
              {active.next_action?.kind === 'schedule' && <p className="goals-muted">下次执行：{new Date(active.next_action.due_at).toLocaleString()} · {active.next_action.interval_hours ? `每 ${active.next_action.interval_hours} 小时` : '仅一次'}</p>}
              {scheduleOpen && <div className="goal-schedule"><h4>安排下一次执行</h4><label>执行时间<input className="app-field" type="datetime-local" value={due} onChange={(event) => setDue(event.target.value)} /></label><label>重复<select className="app-field" value={interval} onChange={(event) => setInterval(Number(event.target.value))}><option value={0}>仅一次</option><option value={24}>每 24 小时</option><option value={168}>每 7 天</option></select></label><p className="goals-muted">仅在 Texa 开启时执行。遇到输入缺失或写入确认会停下来等待你；关闭后错过的执行会在下次启动时处理。</p><button className="app-primary-button" disabled={busy || !due} onClick={() => void action(async () => {const response = await post(`/goals/${active.id}/schedule`, {expected_revision: active.revision, due_at: new Date(due).toISOString(), interval_hours: interval}); if (!response.success) throw new Error('定时未保存'); update(response.data); setScheduleOpen(false);})}>保存定时安排</button>{active.next_action && <button className="app-ghost-button" disabled={busy} onClick={() => void action(async () => {const response = await post(`/goals/${active.id}/schedule`, {expected_revision: active.revision}); if (!response.success) throw new Error('取消定时失败'); update(response.data); setScheduleOpen(false);})}>取消定时</button>}</div>}</section>
            <section className="goal-run" aria-label="当前任务与结果"><h3>当前任务{runtime ? ` · ${labels[runtime.status] || runtime.status}` : ''}</h3>{!runtime && <p className="goals-muted">尚无当前任务。开始执行后，任务结果和验证状态会显示在这里。</p>}{runtime && <><LearningTaskActions key={`${runtime.id}:${runtime.active_run_id}:${runtime.status}`} initialTask={runtime} onResume={(task) => void run(task)} />{runtime.required_inputs?.map((input, index) => <p key={index} className="goals-muted">{String(input.reason || input.name || '请补充关键输入')}</p>)}{Boolean(runtime.artifacts?.final_answer) && <ChatMessage role="assistant" content={String(runtime.artifacts?.final_answer)} sources={(runtime.artifacts?.evidence_sources || []) as AssistantSource[]} />}<details className="goal-events"><summary>执行记录</summary><ul>{((runtime.artifacts?.execution_events || []) as Array<{seq: number; summary: string}>).map((event) => <li key={event.seq}>{event.summary}</li>)}</ul></details></>}</section>
          </section> : <div className="goals-filter-empty"><p>暂无已安排定时的目标</p><button className="app-ghost-button" onClick={() => setFilter('all')}>查看全部目标</button></div>}
        </main>
      </div>}
  </div>;
}
