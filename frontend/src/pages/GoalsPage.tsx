import FocusHistory from '../features/focus/FocusHistory';
import { useFocus, focusDuration } from '../features/focus/FocusContext';
import GoalEditor from '../features/goals/GoalEditor';
import FocusPanel from '../features/focus/FocusPanel';
import WorkspaceSkeleton from '../components/ui/WorkspaceSkeleton';
import { getBookList } from '../features/books/bookList';
import { useLocation, useNavigate } from 'react-router-dom';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CalendarClock, Loader2, Play, Plus, ArrowLeft } from 'lucide-react';
import { get, post } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { LearningTaskState, AssistantSource } from '../types';
import type { TextbookRecord } from '../utils/textbookScopes';
import { buildTextbookScopeOptions } from '../utils/textbookScopes';
import { goalListState, selectedGoalAfterChange, visibleGoals as filterGoals, type GoalFilter, type GoalListStatus, acceptRuntimeSnapshot } from '../features/goals/goalViewState';
import { goalEventText, goalErrorText } from '../features/goals/runtimePresentation';
import type { ExecutionEvent } from '../types';
import ScopeSelector from '../components/ScopeSelector';
import LearningTaskActions from '../components/chat/LearningTaskActions';
import ChatMessage from '../components/ChatMessage';

type Goal = { id: string; title: string; objective: string; status: string; revision: number;
  success_criteria: Array<{id: string; description?: string}>; scope: { book_name?: string; subject?: string };
  next_action?: { kind: string; due_at: string; interval_hours: number } | null };
type View = 'create' | 'detail';
type ComposerStep = 'edit' | 'review';
const goalLabels: Record<string, string> = { active: '进行中', paused: '已搁置', draft: '待开始', completed: '已完成', cancelled: '已取消' };
const labels: Record<string, string> = { completed: '已完成', paused: '已暂停',
  running: 'AI 正在执行', waiting_for_input: '等待你的补充', waiting_for_confirmation: '等待确认', interrupted: 'AI 执行已停止', failed: '执行失败', degraded: '结果待核验' };

export default function GoalsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const focus = useFocus();
  const appliedGoalQuery = useRef('');
  const [detailTab, setDetailTab] = useState<'tasks'|'history'|'ai'>('tasks');
  const [editingGoal, setEditingGoal] = useState(false);
  const [manualTitle, setManualTitle] = useState('');
  const [newTaskGoal, setNewTaskGoal] = useState('');
  const [manualCriteria, setManualCriteria] = useState('');
  const routeActive = location.pathname === '/goals';
  const { bookName, subject } = useChatContext();
  const incomingDraft = (location.state as {goalDraft?: string} | null)?.goalDraft;
  const [goals, setGoals] = useState<Goal[]>([]);
  const [listStatus, setListStatus] = useState<GoalListStatus>('loading');
  const [view, setView] = useState<View>(incomingDraft ? 'create' : 'detail');
  const [selected, setSelected] = useState('');
  const [filter, setFilter] = useState<GoalFilter>('active');
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
  const pollEpoch = useRef(0);
  const listEpoch = useRef(0);
  const actionBusy = useRef(false);
  const latestRuntime = useRef<LearningTaskState | null>(null);
  const selectedGoalId = useRef('');
  const acceptRuntime = (task: LearningTaskState | null) => {
    if (!acceptRuntimeSnapshot(latestRuntime.current, task)) return;
    latestRuntime.current = task;
    setRuntime(task);
  };
  const update = (goal: Goal) => setGoals((current) => {
    const previous = current.find((item) => item.id === goal.id);
    return previous && previous.revision > goal.revision ? current : [goal, ...current.filter((item) => item.id !== goal.id)];
  });

  const load = useCallback(async (silent = false) => {
    if (!silent) setListStatus('loading');
    const epoch = ++listEpoch.current;
    try {
      const response = await get('/goals?limit=100');
      if (!response.success || !Array.isArray(response.data)) throw new Error();
      if (epoch !== listEpoch.current) return;
      setGoals((current) => response.data.sort((a: Goal & {updated_at?:string},b: Goal & {updated_at?:string})=>(b.updated_at||'').localeCompare(a.updated_at||'')).map((goal: Goal) => {
        const previous = current.find((item) => item.id === goal.id);
        return previous && previous.revision > goal.revision ? previous : goal;
      }));
      setListStatus('ready');
    } catch {
      if (epoch !== listEpoch.current) return;
      if (silent) setActionError('目标列表暂时无法更新，请稍后重试。');
      else setListStatus('error');
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    let cancelled = false;
    getBookList().then((response) => { if (!cancelled && response?.success) setBooks(response.data || []); }).catch(() => {});
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
    let timer: number | undefined;
    pollEpoch.current += 1;
    selectedGoalId.current = selected;
    latestRuntime.current = null;
    setRuntime(null);
    const poll = async () => {
      if (!routeActive || !selected || view !== 'detail' || cancelled) return;
      if (document.visibilityState !== 'visible') { timer=window.setTimeout(()=>void poll(),5000); return; }
      const epoch = pollEpoch.current;
      if (actionBusy.current) { timer = window.setTimeout(() => void poll(), 1500); return; }
      try {
        const response = await get(`/goals/${encodeURIComponent(selected)}/runtime`);
        if (!cancelled && epoch === pollEpoch.current) {
          acceptRuntime(response.data || null);
          if (response.goal) setGoals((current) => current.map((goal) => goal.id === response.goal.id && goal.revision <= response.goal.revision ? response.goal : goal));
        }
      } catch { if (!cancelled && epoch === pollEpoch.current) setActionError('运行状态暂不可用，请刷新。'); }
      if (!cancelled) timer = window.setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); }; // Each poll completes before the next begins.
  }, [selected, view, routeActive]);
  const action = async (fn: () => Promise<void>) => {
    if (actionBusy.current) return;
    pollEpoch.current += 1; listEpoch.current += 1; actionBusy.current = true;
    setBusy(true); setActionError('');
    try { await fn(); } catch (reason) { setActionError(goalErrorText(reason)); }
    finally { pollEpoch.current += 1; listEpoch.current += 1; actionBusy.current = false; setBusy(false); }
  };
  const changeScope = (change: Partial<typeof draftScope>) => {
    setDraftScope((current) => ({...current, ...change}));
    setProposal(null); setStep('edit'); setIntakeFailed(false); setActionError('');
  };
  const summarize = () => action(async () => {
    setIntakeFailed(false);
    try {
      const response = await post('/goals/intake/summarize', {text: [manualTitle.trim(),text.trim(),manualCriteria.trim()].filter(Boolean).join('\n'), book_name: draftScope.bookName, subject: draftScope.subject}, 40000);
      if (!response.success) throw new Error('目标未整理完成，请重试。');
      setProposal(response.data); setStep('review');
    } catch (reason) {
      setIntakeFailed(true);
      throw reason;
    }
  });
  const create = (original = false) => action(async () => {
    if (original && manualCriteria.split('\n').filter(value=>value.trim()).length>12) throw new Error('最多保存12条完成条件，请合并后再保存。');
    const value = original ? {title: (manualTitle.trim() || text.trim()).slice(0, 200), objective: text.trim(), success_criteria: manualCriteria.split('\n').map(value=>value.trim()).filter(Boolean).slice(0,12).map(description=>({id:crypto.randomUUID(),description})), scope: {book_name: draftScope.bookName, subject: draftScope.subject}} : proposal;
    const response = await post('/goals', value);
    if (!response.success) throw new Error('目标未保存，请重试。');
    setNewTaskGoal(response.data.id); update(response.data); navigate(`/goals?goal=${encodeURIComponent(response.data.id)}`,{replace:true}); setSelected(response.data.id); setFilter('all'); setView('detail'); setMobilePane('workspace');
    setText(''); setManualTitle(''); setManualCriteria(''); setProposal(null); setStep('edit'); setIntakeFailed(false);
  });
  const run = (resume?: LearningTaskState) => action(async () => {
    if (!active) return;
    if (!resume && runtime?.resume_block_reason && !window.confirm("旧任务不能继续，已有结果保留。按当前目标开始一次新的执行吗？")) return;
    const response = await post(`/goals/${active.id}/run`, { expected_revision: active.revision, request_key: crypto.randomUUID(), task_id: resume?.id || '' }, 40000);
    if (!response.success) throw new Error('目标未开始');
    if (selectedGoalId.current === active.id) acceptRuntime(response.data);
    await load(true);
  });
  const command = (operation: string) => action(async () => {
    if (!active) return;
    const currentFocus = focus.data?.current_task?.goal_id===active.id && focus.data.current_session?.status!=='ended' && Boolean(focus.data.current_session);
    if (operation==='pause' && currentFocus && !window.confirm('结束本次专注并搁置目标？这会停止该目标的 AI 执行和后续安排。')) return;
    if (operation==='activate' && active.next_action?.kind==='schedule' && !window.confirm('恢复目标时，同时恢复已设置的 AI 定时安排。可在 AI 学习任务视图取消安排。继续恢复？')) return;
    const response = await post(`/goals/${active.id}/commands`, {operation, expected_revision: active.revision,
      ...(operation === 'measure' ? {user_confirms_completion: true} : {})});
    if (!response.success) throw new Error('操作未保存'); update(response.data);
    await focus.refresh();
    const snapshot = await get(`/goals/${active.id}/runtime`);
    if (selectedGoalId.current === active.id) acceptRuntime(snapshot.data || null);
  });
  useEffect(()=>{const signature=`${location.key}:${location.search}`;if(appliedGoalQuery.current===signature)return;const id=new URLSearchParams(location.search).get('goal');if(id&&goals.some(goal=>goal.id===id)){appliedGoalQuery.current=signature;setFilter('all');setSelected(id);setView('detail');setMobilePane('workspace');setDetailTab('tasks');}},[location.key,location.search,goals]);
  const openGoal = (goal: Goal) => {
    setNewTaskGoal('');
    navigate(`/goals?goal=${encodeURIComponent(goal.id)}`,{replace:true});
    setDetailTab('tasks'); setEditingGoal(false); setSelected(goal.id); setView('detail'); setMobilePane('workspace'); setScheduleOpen(false); setActionError('');
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
    {listStatus === 'loading' ? <WorkspaceSkeleton label="正在读取目标" header={false} />
      : listStatus === 'error' ? <div className="goals-page-state" role="alert"><h2>目标暂时无法读取</h2><p>请检查连接后重试。</p><button className="app-secondary-button" onClick={() => void load()}>重试读取</button></div>
      : <div className={`goals-body ${mobilePane === 'list' ? 'goals-show-list' : 'goals-show-workspace'}`}>
        {zeroGoals ? <div className="goals-zero-count">目标 · 0</div> : <aside className="goals-index" aria-label="目标列表">
          <div className="goals-tabs" aria-label="筛选目标"><button ref={allFilterButton} aria-pressed={filter === 'active'} onClick={() => setFilter('active')}>进行中</button><button aria-pressed={filter === 'completed'} onClick={() => setFilter('completed')}>已完成</button></div><label className="sr-only" htmlFor="goal-more-filter">更多目标筛选</label><select id="goal-more-filter" className="app-field" value={filter} onChange={event=>setFilter(event.target.value as GoalFilter)}><option value="active">进行中</option><option value="completed">已完成</option><option value="paused">已搁置 / 已取消</option><option value="scheduled">AI 定时安排</option><option value="all">全部目标</option></select>
          {visibleGoals.length ? visibleGoals.map((goal) => <button key={goal.id} ref={goal.id === selected ? selectedListButton : undefined} aria-current={goal.id === selected ? 'true' : undefined} className={`goal-list-item ${goal.id === selected ? 'selected' : ''}`} onClick={() => openGoal(goal)}><span><strong>{goal.title}</strong><small>{focus.data?.goal_stats.find(item=>item.goal_id===goal.id) ? `${focus.data.goal_stats.find(item=>item.goal_id===goal.id)!.completed_count} / ${focus.data.goal_stats.find(item=>item.goal_id===goal.id)!.task_count} · ${focusDuration(focus.data.goal_stats.find(item=>item.goal_id===goal.id)!.active_ms)}` : goalLabels[goal.status] || goal.status}{goal.next_action?.kind === 'schedule' ? ' · 已安排定时' : ''}</small></span></button>)
            : <div className="goals-filter-empty goals-filter-empty-list"><p>0 个目标</p><button className="app-ghost-button" onClick={() => setFilter('all')}>查看全部目标</button></div>}
        </aside>}
        <main className="goal-detail" aria-label="目标工作区">
          {view === 'detail' && actionError && <div role="alert" className="goal-error">{actionError}<button className="app-ghost-button" onClick={() => void load(true)}>刷新状态</button></div>}
          {view === 'create' ? <section className="goal-intake">
            {goals.length > 0 && <button className="goal-back app-ghost-button" onClick={showDetail}><ArrowLeft size={15} />返回目标</button>}
            {step === 'edit' ? <><h2>新建目标</h2><p>先写下想学会什么，再添加具体任务。</p><div className="goal-manual-fields"><label>目标标题<input className="app-field" required maxLength={200} value={manualTitle} placeholder="例如：学习偏导数" onChange={event=>setManualTitle(event.target.value)} /></label><label>说明（可选）</label></div>
              <textarea aria-label="描述学习目标" placeholder="简短说明想达到的结果……" value={text} maxLength={2000} onChange={(event) => {setText(event.target.value); setProposal(null); setIntakeFailed(false); setActionError('');}} disabled={busy} />
              <div className="goal-manual-fields"><label>完成条件（可选，每行一项，最多12项）<textarea aria-label="目标完成条件" value={manualCriteria} maxLength={10000} onChange={event=>setManualCriteria(event.target.value)} /></label></div>
              {actionError && <div role="alert" className="goal-error">{actionError}</div>}
              <div className="goal-intake-footer"><ScopeSelector size="form" subject={draftScope.subject} bookName={draftScope.bookName} books={scopeBooks} suggestions={books.map((book) => book.subject || '').filter(Boolean)} onSubjectChange={(value) => changeScope({subject: value})} onBookChange={(value) => changeScope({bookName: value})} label="目标范围" emptyBookLabel="不限教材" width="compact" disabled={busy} />
                <button className="app-primary-button" disabled={busy || !(manualTitle.trim() || text.trim())} onClick={()=>void create(true)}>保存目标</button><button className="app-ghost-button" disabled={busy || !(manualTitle.trim() || text.trim())} onClick={() => void summarize()}>{busy && !intakeFailed ? <Loader2 className="animate-spin" size={16} /> : null}{busy ? '正在整理…' : intakeFailed ? '重新整理' : '帮我整理'}</button></div>
              {intakeFailed && <div className="goal-intake-recovery"><p className="goals-muted">整理暂不可用。也可以先保存为待开始目标，稍后再启用。</p><button className="app-ghost-button" disabled={busy || !text.trim()} onClick={() => void create(true)}>保存为待开始目标</button></div>}
            </> : <><p className="goal-eyebrow">确认目标</p><h2>{proposal?.title}</h2>{actionError && <div role="alert" className="goal-error">{actionError}</div>}<p className="goal-objective">{proposal?.objective}</p>
              {!!proposal?.success_criteria?.length && <div className="goal-criteria"><h3>完成条件</h3><ul>{proposal.success_criteria.map((item) => <li key={item.id}>{item.description}</li>)}</ul></div>}
              <p className="goals-muted">范围：{proposal?.scope?.subject || '全部学科'} · {proposal?.scope?.book_name || '不限教材'}</p>
              <div className="goal-review-actions"><button className="app-primary-button" disabled={busy} onClick={() => void create()}>{busy ? <Loader2 className="animate-spin" size={16} /> : null}保存目标</button><button className="app-ghost-button" disabled={busy} onClick={() => {setStep('edit'); setActionError('');}}>返回修改</button></div>
            </>}
          </section> : active ? <section className="goal-session">
            <button ref={listReturnButton} className="goal-list-return app-ghost-button" onClick={showList}><ArrowLeft size={15} />目标列表</button>
            <div className="goal-eyebrow">{goalLabels[active.status] || active.status} · {active.scope.subject || '全部学科'} · {active.scope.book_name || '不限教材'}</div><h2>{active.title}</h2>
            <section className="goal-overview"><p className="goal-objective">{active.objective}</p><details className="goal-criteria"><summary>完成条件 · {active.success_criteria.length}</summary>{active.success_criteria.length ? <ul>{active.success_criteria.map((item) => <li key={item.id}>{item.description}</li>)}</ul> : <p className="goals-muted">尚未设置完成条件，请依据实际学习结果确认目标是否完成。</p>}</details></section>
            <p className="goal-summary-progress">{focus.data?.goal_stats.find(item=>item.goal_id===active.id) ? `${focus.data.goal_stats.find(item=>item.goal_id===active.id)!.completed_count} / ${focus.data.goal_stats.find(item=>item.goal_id===active.id)!.task_count} 项完成 · 已投入 ${focusDuration(focus.data.goal_stats.find(item=>item.goal_id===active.id)!.active_ms)}` : focus.error?'任务统计暂不可读取':focus.data?'尚无任务记录':'正在读取任务统计…'}</p>
            <div className="goal-management-actions"><button className="app-secondary-button" onClick={()=>setEditingGoal(!editingGoal)}>编辑目标与条件</button>{active.status==='active'&&<button className="app-secondary-button" disabled={busy} onClick={()=>void command('pause')}>搁置目标</button>}{active.status==='paused'&&<button className="app-secondary-button" disabled={busy} onClick={()=>void command('activate')}>恢复目标</button>}{!['completed','cancelled'].includes(active.status)&&<button className="app-secondary-button" disabled={busy} onClick={()=>{if(window.confirm('你确认目标完成条件已经满足吗？任务与专注记录会保留。'))void command('measure');}}>确认目标完成</button>}</div>
            {editingGoal&&<GoalEditor key={`${active.id}:${active.revision}`} goal={active} busy={busy} onClose={()=>setEditingGoal(false)} onSave={async changes=>{let saved=false;await action(async()=>{const response=await post(`/goals/${active.id}/commands`,{operation:'update',expected_revision:active.revision,changes});if(!response.success)throw new Error('目标修改未保存');update(response.data);await focus.refresh();saved=true;});return saved;}}/>}
            <nav className="goal-detail-tabs" aria-label="目标详情视图"><button aria-pressed={detailTab==='tasks'} onClick={()=>setDetailTab('tasks')}>任务</button><button aria-pressed={detailTab==='history'} onClick={()=>setDetailTab('history')}>专注记录</button><button aria-pressed={detailTab==='ai'} onClick={()=>setDetailTab('ai')}>AI 学习任务</button></nav>
            {(runtime?.confirmation_required||runtime?.input_action_required)&&detailTab!=='ai'&&<div className="goal-ai-notice">AI {runtime.confirmation_required?'等待确认':'等待补充'}<button className="app-ghost-button" onClick={()=>setDetailTab('ai')}>查看并处理</button></div>}
            {detailTab==='tasks'&&<FocusPanel key={active.id} goalId={active.id} criteria={active.success_criteria} focusNewTask={newTaskGoal===active.id}/>}{detailTab==='history'&&<FocusHistory key={active.id} goalId={active.id}/>}{detailTab==='ai'&&<section className="goal-assistance"><section className="goal-run" aria-label="AI 执行与结果"><div className="goal-run-heading"><h3>按目标准备学习内容</h3>{runtime && <span role="status">{labels[runtime.status] || runtime.status}</span>}</div><p className="goal-assistance-description">根据目标与完成条件，检索教材、整理讲解或提出练习建议。结果保留在这里，目标是否完成由你确认。</p>            {runtime?.resume_block_reason && <p role="status" className="goals-muted">{runtime.resume_block_reason}</p>}<div className="goal-execution-controls"><div className="goal-controls">{['draft', 'paused'].includes(active.status) && <button className="app-primary-button" disabled={busy} onClick={() => void command('activate')}><Play size={15} />开始学习</button>}{active.status === 'active' && <><button className="app-primary-button" disabled={busy || runtime?.status === 'running' || runtime?.confirmation_required || runtime?.input_action_required} onClick={() => void run(runtime?.resumable ? runtime : undefined)}><Play size={15} />{busy ? '正在提交…' : runtime?.status === 'running' ? 'AI 正在执行' : runtime?.confirmation_required ? '等待确认' : runtime?.input_action_required ? '等待补充输入' : runtime?.resumable ? '继续 AI 学习任务' : '运行 AI 学习任务'}</button><button className="app-secondary-button" aria-expanded={scheduleOpen} onClick={() => setScheduleOpen(!scheduleOpen)}><CalendarClock size={15} />AI 定时安排</button></>}
</div>
              {active.status === 'active' && runtime?.status === 'running' && <p id="goal-pause-impact" className="goals-muted">搁置目标会停止当前 AI 执行和后续安排，已取得的结果保留。</p>}
              {active.next_action?.kind === 'schedule' && <p className="goals-muted">下次执行：{new Date(active.next_action.due_at).toLocaleString()} · {active.next_action.interval_hours ? `每 ${active.next_action.interval_hours} 小时` : '仅一次'}</p>}
              {scheduleOpen && <div className="goal-schedule"><h4>安排下一次执行</h4><label>执行时间<input className="app-field" type="datetime-local" value={due} onChange={(event) => setDue(event.target.value)} /></label><label>重复<select className="app-field" value={interval} onChange={(event) => setInterval(Number(event.target.value))}><option value={0}>仅一次</option><option value={24}>每 24 小时</option><option value={168}>每 7 天</option></select></label><p className="goals-muted">仅在本地后端运行时执行。遇到写入会等待确认；缺少关键输入时会暂停并等待你补充；关闭后错过的执行会在下次启动时处理。</p><button className="app-primary-button" disabled={busy || !due} onClick={() => void action(async () => {const response = await post(`/goals/${active.id}/schedule`, {expected_revision: active.revision, due_at: new Date(due).toISOString(), interval_hours: interval}); if (!response.success) throw new Error('定时未保存'); update(response.data); setScheduleOpen(false);})}>保存定时安排</button>{active.next_action && <button className="app-ghost-button" disabled={busy} onClick={() => void action(async () => {const response = await post(`/goals/${active.id}/schedule`, {expected_revision: active.revision}); if (!response.success) throw new Error('取消定时失败'); update(response.data); setScheduleOpen(false);})}>取消定时</button>}</div>}</div>
{!runtime && <p className="goals-muted">还未执行。</p>}{runtime && <><LearningTaskActions key={`${runtime.id}:${runtime.active_run_id}:${runtime.status}`} initialTask={runtime} onTaskChange={(task) => { if (selectedGoalId.current === active.id) { pollEpoch.current += 1; acceptRuntime(task); } }} onResume={(task) => { if (selectedGoalId.current === active.id) void run(task); }} />{runtime.required_inputs?.map((input, index) => <p key={index} className="goals-muted">{String(input.reason || input.name || '请补充关键输入')}</p>)}{Boolean(runtime.artifacts?.final_answer) && <ChatMessage role="assistant" content={String(runtime.artifacts?.final_answer)} sources={(runtime.artifacts?.evidence_sources || []) as AssistantSource[]} />}<details className="goal-events"><summary>执行记录</summary><ul>{((runtime.artifacts?.execution_events || []) as ExecutionEvent[]).map((event) => <li key={event.seq}>{goalEventText(event)}</li>)}</ul></details></>}</section></section>}

          </section> : <div className="goals-filter-empty"><p>暂无已安排定时的目标</p><button className="app-ghost-button" onClick={() => setFilter('all')}>查看全部目标</button></div>}
        </main>
      </div>}
  </div>;
}
