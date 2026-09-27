import { useLocation } from 'react-router-dom';
import { useCallback, useEffect, useState } from 'react';
import { ArrowUp, CalendarClock, Check, Circle, Loader2, Pause, Play, Plus, Target } from 'lucide-react';
import { get, post } from '../api/client';
import { useChatContext } from '../contexts/ChatContext';
import type { LearningTaskState, AssistantSource } from '../types';
import LearningTaskActions from '../components/chat/LearningTaskActions';
import ChatMessage from '../components/ChatMessage';

type Goal = { id: string; title: string; objective: string; status: string; revision: number;
  success_criteria: Array<{id: string; description?: string}>; scope: { book_name?: string; subject?: string };
  next_action?: { kind: string; due_at: string; interval_hours: number } | null };
const labels: Record<string, string> = { active: '进行中', paused: '已暂停', draft: '待开始', completed: '已完成', cancelled: '已取消',
  running: '正在执行', waiting_for_input: '等待你的补充', waiting_for_confirmation: '等待确认', interrupted: '已停止', failed: '执行失败', degraded: '结果待核验' };

export default function GoalsPage() {
  const location = useLocation();
  const { bookName, subject } = useChatContext();
  const [goals, setGoals] = useState<Goal[]>([]);
  const [selected, setSelected] = useState('');
  const [text, setText] = useState(() => String((location.state as {goalDraft?: string} | null)?.goalDraft || '').slice(0,2000));
  const [proposal, setProposal] = useState<Partial<Goal> | null>(null);
  const [runtime, setRuntime] = useState<LearningTaskState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'all' | 'scheduled'>('all');
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [due, setDue] = useState('');
  const [interval, setInterval] = useState(0);
  const active = goals.find((goal) => goal.id === selected);
  const update = (goal: Goal) => setGoals((current) => [goal, ...current.filter((item) => item.id !== goal.id)]);
  const load = useCallback(async () => {
    setLoading(true);
    try { const response = await get('/goals?limit=100'); if (!response.success || !Array.isArray(response.data)) throw new Error(); setGoals(response.data); }
    catch { setError('目标暂时无法读取，请重试。'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const draft = (location.state as {goalDraft?: string} | null)?.goalDraft;
    if (typeof draft === 'string') { setText(draft.slice(0, 2000)); setSelected(''); setProposal(null); }
  }, [location.key, location.state]);
  useEffect(() => {
    let cancelled = false;
    setRuntime(null);
    const poll = async () => {
      if (!selected) return;
      try { const response = await get(`/goals/${encodeURIComponent(selected)}/runtime`); if (!cancelled) { setRuntime(response.data || null); if (response.goal) setGoals((current) => current.map((goal) => goal.id === response.goal.id ? response.goal : goal)); } }
      catch { if (!cancelled) setError('运行状态暂不可用，请刷新。'); }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [selected]);
  const action = async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); } catch (reason) { setError(reason instanceof Error ? reason.message : '操作未完成，请重试。'); }
    finally { setBusy(false); }
  };
  const summarize = () => action(async () => {
    const response = await post('/goals/intake/summarize', {text, book_name: bookName, subject}, 40000);
    if (!response.success) throw new Error('目标未整理完成'); setProposal(response.data);
  });
  const create = (original = false) => action(async () => {
    const value = original ? { title: text.trim().slice(0, 80), objective: text.trim(), success_criteria: [], scope: { book_name: bookName, subject } } : proposal;
    const response = await post('/goals', value);
    if (!response.success) throw new Error('目标未保存'); update(response.data); setSelected(response.data.id); setText(''); setProposal(null);
  });
  const run = (resume?: LearningTaskState) => action(async () => {
    if (!active) return;
    const response = await post(`/goals/${active.id}/run`, { expected_revision: active.revision, request_key: crypto.randomUUID(), task_id: resume?.id || '' }, 40000);
    if (!response.success) throw new Error('目标未开始'); setRuntime(response.data); await load();
  });
  const command = (operation: string) => action(async () => {
    if (!active) return;
    const response = await post(`/goals/${active.id}/commands`, {operation, expected_revision: active.revision,
      ...(operation === 'measure' ? {user_confirms_completion: true} : {})});
    if (!response.success) throw new Error('操作未保存'); update(response.data);
    if (operation === 'pause' && runtime?.interruptible) setRuntime({...runtime, status: 'interrupted', interruptible: false, resumable: true});
  });
  return <div className="goals-workspace">
    <header className="goals-header window-drag-region"><div><h1>目标与任务</h1><p>由你发起，让 Texa 持续推进。</p></div><button className="app-secondary-button" onClick={() => {setSelected(''); setProposal(null); setScheduleOpen(false);}}><Plus size={16} />新目标</button></header>
    <div className="goals-body"><aside className="goals-index" aria-label="目标列表"><div className="goals-tabs"><button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>全部目标</button><button aria-pressed={filter === 'scheduled'} onClick={() => setFilter('scheduled')}>定时任务</button></div>
      {loading && <p role="status">正在读取…</p>}{!loading && !goals.length && <p className="goals-muted">还没有目标。写下你想完成的事。</p>}
      {goals.filter((goal) => filter === 'all' || goal.next_action?.kind === 'schedule').map((goal) => <button key={goal.id} className={`goal-list-item ${selected === goal.id ? 'selected' : ''}`} onClick={() => {setSelected(goal.id); setScheduleOpen(false); setError('');}}><Target size={16} /><span><strong>{goal.title}</strong><small>{labels[goal.status]}{goal.next_action?.kind === 'schedule' ? ' · 已定时' : ''}</small></span></button>)}
    </aside><main className="goal-detail">
      {error && <div role="alert" className="goal-error">{error}<button className="app-ghost-button" onClick={() => void load()}>刷新状态</button></div>}
      {!active ? <section className="goal-intake"><div className="goal-intake-symbol"><Target size={26} /></div><h2>你想完成什么？</h2><p>说明你的目标、范围和完成条件。Texa 会整理成可执行的目标，由你确认后开始。</p><textarea aria-label="描述学习目标" placeholder="例如：帮我整理这一章的薄弱知识点，找到对应教材例题，并准备一组复习练习。" value={text} maxLength={2000} onChange={(event) => {setText(event.target.value); setProposal(null);}} disabled={busy} /><div className="goal-intake-footer"><span>{bookName || '不限教材'}{subject && ` · ${subject}`}</span><button className="app-primary-button" disabled={busy || !text.trim()} onClick={() => void summarize()}>{busy ? <Loader2 className="animate-spin" size={16} /> : <ArrowUp size={16} />}整理目标</button></div>
      {proposal ? <div className="goal-proposal"><p className="goal-eyebrow">确认这个目标</p><h3>{proposal.title}</h3><p>{proposal.objective}</p><ul>{proposal.success_criteria?.map((item) => <li key={item.id}>{item.description}</li>)}</ul><button className="app-primary-button" disabled={busy} onClick={() => void create()}>保存目标</button><button className="app-ghost-button" disabled={busy} onClick={() => setProposal(null)}>重新描述</button></div> : <button className="app-ghost-button" disabled={busy || !text.trim()} onClick={() => void create(true)}>先保存原始目标</button>}</section> : <section className="goal-session"><div className="goal-eyebrow">{labels[active.status]} · {active.scope.book_name || '不限教材'}</div><h2>{active.title}</h2><p className="goal-objective">{active.objective}</p>{!!active.success_criteria.length && <div className="goal-criteria"><h3>完成条件</h3>{active.success_criteria.map((item) => <p key={item.id}><Circle size={12} />{item.description}</p>)}</div>}
      <div className="goal-controls">{['draft', 'paused'].includes(active.status) && <button className="app-primary-button" disabled={busy} onClick={() => void command('activate')}><Play size={15} />启用目标</button>}{active.status === 'active' && <><button className="app-primary-button" disabled={busy || runtime?.status === 'running' || runtime?.confirmation_required} onClick={() => void run(runtime?.resumable ? runtime : undefined)}><Play size={15} />{runtime?.resumable ? '继续执行' : '开始执行'}</button><button className="app-secondary-button" disabled={busy} onClick={() => void command('pause')}><Pause size={15} />暂停</button><button className="app-ghost-button" onClick={() => setScheduleOpen(!scheduleOpen)}><CalendarClock size={15} />定时执行</button></>}
      {active.status === 'active' && runtime?.terminal && <button className="app-secondary-button" disabled={busy} onClick={() => {if (window.confirm('你确认这个目标的完成条件已经满足吗？')) void command('measure');}}><Check size={15} />确认目标完成</button>}</div>
      {active.next_action?.kind === 'schedule' && <p className="goals-muted">下次执行：{new Date(active.next_action.due_at).toLocaleString()} · {active.next_action.interval_hours ? `每 ${active.next_action.interval_hours} 小时` : '仅一次'}</p>}
      {scheduleOpen && <div className="goal-schedule"><h3>安排下一次执行</h3><label>执行时间<input className="app-field" type="datetime-local" aria-label="执行时间" value={due} onChange={(event) => setDue(event.target.value)} /></label><label>重复<select className="app-field" aria-label="重复间隔" value={interval} onChange={(event) => setInterval(Number(event.target.value))}><option value={0}>仅一次</option><option value={24}>每 24 小时</option><option value={168}>每 7 天</option></select></label><p className="goals-muted">仅在 Texa 开启时执行。遇到输入缺失或写入确认会停下来等待你；关闭后错过的执行会在下次启动时处理。</p><button className="app-primary-button" disabled={busy || !due} onClick={() => void action(async () => { const response = await post(`/goals/${active.id}/schedule`, {expected_revision: active.revision, due_at: new Date(due).toISOString(), interval_hours: interval}); update(response.data); setScheduleOpen(false); })}>保存定时任务</button>{active.next_action && <button className="app-ghost-button" disabled={busy} onClick={() => void action(async () => {const response = await post(`/goals/${active.id}/schedule`, {expected_revision: active.revision}); update(response.data); setScheduleOpen(false);})}>取消定时</button>}</div>}
      <section className="goal-run" aria-label="目标执行状态"><h3>{runtime ? labels[runtime.status] || runtime.status : '准备开始'}</h3>{!runtime && <p className="goals-muted">开始后持续执行检索、工具与答案验证。需要你提供信息或确认写入时，会在这里等待。</p>}{runtime && <><LearningTaskActions key={`${runtime.id}:${runtime.active_run_id}:${runtime.status}`} initialTask={runtime} onResume={(task) => void run(task)} />{runtime.required_inputs?.map((input, index) => <p key={index} className="goals-muted">{String(input.reason || input.name || '请补充关键输入')}</p>)}{Boolean(runtime.artifacts?.final_answer) && <ChatMessage role="assistant" content={String(runtime.artifacts?.final_answer)} sources={(runtime.artifacts?.evidence_sources || []) as AssistantSource[]} />}<details className="goal-events"><summary>执行记录</summary><ul>{((runtime.artifacts?.execution_events || []) as Array<{seq: number; summary: string}>).map((event) => <li key={event.seq}>{event.summary}</li>)}</ul></details></>}</section>
      </section>}
    </main></div>
  </div>;
}
