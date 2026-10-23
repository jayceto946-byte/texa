import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowUpRight, Check, Pause, Play, Square, Timer, X } from 'lucide-react';
import Dialog from '../../components/ui/Dialog';
import { panelPlacement } from './panelPlacement';
import { completionTransition } from './controllerState';
import { get } from '../../api/client';
import { focusDuration, focusTime, useFocus, type FocusMode, type FocusTask } from './FocusContext';
import { focusPreference } from './preferences';

export default function FocusController() {
  const focus = useFocus(), navigate = useNavigate(), location = useLocation();
  const panelId = useId();
  const [header, setHeader] = useState<HTMLElement | null>(null);
  const [placement, setPlacement] = useState({ sheet: false, top: 56, right: 16, maxHeight: 560 });
  const [open, setOpen] = useState(false), [resting, setResting] = useState(false), [choosing, setChoosing] = useState(false), [otherGoals, setOtherGoals] = useState(false);
  const [choices, setChoices] = useState<FocusTask[]>([]), [nextOffset, setNextOffset] = useState<number | null>(null), [choiceError, setChoiceError] = useState('');
  const preference = focusPreference();
  const [mode, setMode] = useState<FocusMode>(preference?.mode || 'countdown'), [minutes, setMinutes] = useState(preference?.minutes || 25);
  const controller = useRef<HTMLDivElement>(null), panelRef = useRef<HTMLElement>(null), toggle = useRef<HTMLButtonElement>(null), returnFocus = useRef<HTMLElement | null>(null), lastSession = useRef(''), lastStatus = useRef('');
  const [announcement, setAnnouncement] = useState('');
  const announcedOvertime = useRef(''), lastCompletedTask = useRef('');
  const task = focus.setupTask || focus.data?.current_task;
  const session = focus.setupTask && focus.setupTask.id !== focus.data?.current_task?.id ? null : focus.data?.current_session;
  const active = session && session.status !== 'ended';
  const running = active && focus.data?.status === 'running';
  const done = task?.status === 'completed' && !focus.pending;
  const over = active && session?.target_seconds != null && focus.remaining === 0;
  const disabled = focus.busy || focus.pending;
  const close = () => {
    setOpen(false); setChoosing(false); focus.prepareStart(null);
    if (returnFocus.current?.isConnected && !returnFocus.current.closest('[hidden]')) returnFocus.current.focus();
    else toggle.current?.focus();
  };

  // One global controller follows the active route's header; it consumes no canvas height.
  useLayoutEffect(() => {
    const stage = controller.current?.closest('.workspace-main')?.querySelector('.app-route-stage');
    if (!stage) return;
    const update = () => setHeader(stage.querySelector<HTMLElement>('.persistent-route-panel:not([hidden]) :is(.learning-workspace-header,.goals-header,.app-page-header,.library-workspace-header,.note-page-header)'));
    const observer = new MutationObserver(update);
    observer.observe(stage, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden'] });
    update();
    return () => observer.disconnect();
  }, [location.pathname]);
  useEffect(() => {
    if (focus.setupTask) {
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setResting(false); setOpen(true);
    }
  }, [focus.setupTask]);
  useEffect(() => {
    const id = focus.data?.current_session?.id || '', status = focus.data?.status || '';
    if (id !== lastSession.current || status !== lastStatus.current) {
      setAnnouncement(status === 'running' ? '专注已开始' : status === 'paused' ? '计时已暂停' : status === 'finished' ? '本次专注已保存' : '');
      lastSession.current = id; lastStatus.current = status;
    }
    const completion = completionTransition(lastCompletedTask.current, task, focus.pending);
    lastCompletedTask.current = completion.identity;
    if (completion.reveal && !resting) setOpen(true);
  }, [focus.data?.current_session?.id, focus.data?.status, resting, task, focus.pending]);
  useEffect(() => {
    if (over && session && announcedOvertime.current !== session.id) {
      announcedOvertime.current = session.id; setAnnouncement('时间到，可以继续学习，实际时间仍在记录。');
    }
  }, [over, session]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panelRef.current?.contains(target) && !toggle.current?.contains(target) && !(event.target as HTMLElement).closest('.focus-sheet')) close();
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !(event.target as HTMLElement)?.closest('[aria-modal="true"]')) { event.preventDefault(); close(); }
    };
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', keyboard);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', keyboard); };
  });
  useLayoutEffect(() => {
    if (!open || !header) return;
    const container = controller.current?.closest('.workspace-main');
    const route = container?.querySelector('.persistent-route-panel:not([hidden])');
    const observed = new Set<HTMLElement>();
    const update = () => {
      const rect = header.getBoundingClientRect(), main = container?.getBoundingClientRect();
      if (!main) return;
      const blockers = Array.from(route?.querySelectorAll<HTMLElement>('.chat-composer,.review-session-actions,.exercise-practice-actions') || []);
      blockers.forEach(node => { if (!observed.has(node)) { observed.add(node); observer.observe(node); } });
      const visible = blockers.map(node => node.getBoundingClientRect()).filter(value => value.height > 0 && value.top > rect.bottom && value.top < main.bottom);
      const next = panelPlacement({ width: window.innerWidth, mainWidth: main.width, headerBottom: rect.bottom, headerRight: rect.right, contentBottom: visible.length ? Math.min(...visible.map(value => value.top)) : Math.min(main.bottom, window.innerHeight) });
      setPlacement(previous => previous.sheet === next.sheet && previous.top === next.top && previous.right === next.right && previous.maxHeight === next.maxHeight ? previous : next);
    };
    const observer = new ResizeObserver(update);
    observer.observe(header); if (container) observer.observe(container);
    const contentObserver = new MutationObserver(update);
    if (route) contentObserver.observe(route, { subtree: true, childList: true });
    window.addEventListener('resize', update); route?.addEventListener('scroll', update, true); update();
    return () => { observer.disconnect(); contentObserver.disconnect(); window.removeEventListener('resize', update); route?.removeEventListener('scroll', update, true); };
  }, [open, header, task?.id]);
  useLayoutEffect(() => {
    if (!open || placement.sheet) return;
    const frame = requestAnimationFrame(() => panelRef.current?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [open, placement.sheet]);

  const loadChoices = async (offset = 0) => {
    try {
      const response = await get(`/focus?task_status=pending&offset=${offset}${!otherGoals && task ? `&goal_id=${encodeURIComponent(task.goal_id)}` : ''}`);
      setChoices(previous => offset ? [...previous, ...response.data.tasks] : response.data.tasks);
      setNextOffset(response.data.next_offset); setChoiceError('');
    } catch { setChoiceError('任务队列暂不可读取，请重试。'); }
  };
  useEffect(() => { if (choosing) void loadChoices(); }, [choosing, otherGoals, task?.goal_id, focus.data?.revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const begin = (value: FocusTask) => { const recent = focusPreference(); if (recent) void focus.startTask(value, recent.mode, recent.minutes); else focus.prepareStart(value); };
  const number = active ? over ? `+${focusTime(Math.max(0, focus.elapsed - (session?.target_seconds || 0)))}` : session?.mode === 'stopwatch' ? focusTime(focus.elapsed) : focusTime(focus.remaining || 0) : done ? focusTime((session?.active_ms || 0) / 1000) : mode === 'stopwatch' ? '00:00' : focusTime(minutes * 60);
  const status = focus.pending ? '保存结果待核对' : done ? '任务已完成' : active ? !running ? '已暂停' : over ? '时间到 · 已继续' : '专注中' : session ? '本次已结束' : '准备开始';
  const currentSession = focus.data?.current_session;
  const currentActive = currentSession && currentSession.status !== 'ended';
  const currentOver = currentActive && currentSession.target_seconds != null && focus.remaining === 0;
  const currentNumber = currentOver ? `+${focusTime(Math.max(0, focus.elapsed - (currentSession.target_seconds || 0)))}` : currentSession?.mode === 'stopwatch' ? focusTime(focus.elapsed) : focusTime(focus.remaining || 0);
  const showTrigger = Boolean(currentActive || focus.pending || focus.error);
  const total = task ? focusDuration(task.active_ms + (active ? focus.elapsed * 1000 - (focus.data?.active_ms || 0) : 0)) : '';
  const manage = () => { close(); navigate(task ? `/goals?goal=${encodeURIComponent(task.goal_id)}&task=${encodeURIComponent(task.id)}` : '/goals'); };
  const rest = () => { close(); setResting(true); };
  const panel = <section ref={panelRef} id={panelId} tabIndex={-1} role={placement.sheet ? undefined : 'dialog'} className="focus-mini-panel" data-status={status} style={placement.sheet ? undefined : { top: placement.top, right: placement.right, maxHeight: placement.maxHeight }} aria-label="当前专注控制面板">
    <header>
      <span title={task?.goal_title}>{task?.goal_title || '专注'}</span>
      <button className="app-ghost-button focus-manage-link" onClick={manage}>任务管理<ArrowUpRight size={12} aria-hidden="true" /></button>
      <button className="app-icon-button" aria-label="关闭专注面板" onClick={close}><X size={16} /></button>
    </header>
    {task && <h3 title={task.title}>{task.title}</h3>}
    {task?.content && <p className="focus-task-content">{task.content}</p>}
    {focus.error && <p className="focus-sync-error" role="alert">{focus.error}</p>}
    {focus.pending && <button className="app-primary-button" disabled={focus.busy} onClick={() => void focus.reconcile()}>核对未确认操作</button>}
    {!focus.pending && focus.error && <button className="app-ghost-button" onClick={() => void focus.refresh()}>重新读取状态</button>}
    {focus.data?.reason === 'interrupted' && <p className="focus-sync-error">上次专注中断，已记录至 {focus.data.checkpoint_at ? new Date(focus.data.checkpoint_at * 1000).toLocaleTimeString() : '最后检查点'}。未确认尾段未补计。</p>}
    {focus.data?.reason === 'legacy_interrupted' && <p className="goals-muted">保留旧版累计，未包含旧时段未结算部分。</p>}
    {task && !choosing && <>
      <div className="focus-clock">
        <p className="focus-mode-label">{done ? <Check size={14} aria-hidden="true" /> : <Timer size={14} aria-hidden="true" />}{active ? session.mode === 'stopwatch' ? '正计时' : '倒计时' : done ? '本次专注' : mode === 'stopwatch' ? '正计时' : '倒计时'}<span>· {status}</span></p>
        <div className="focus-number" data-long={number.length > 7} aria-label={done ? `本次专注 ${number}` : `计时 ${number}`}>{number}</div>
        {(active || done || session) && <div className="focus-session-total"><span>本次 <strong>{focusDuration((active ? focus.elapsed * 1000 : session?.active_ms) || 0)}</strong></span><span>任务累计 <strong>{total}</strong></span></div>}
      </div>
      {active ? <>
        {over && focus.data?.reason !== 'overtime_acknowledged' && <div className="focus-overtime"><span>时间到，实际投入继续记录</span><button className="app-ghost-button" disabled={disabled} onClick={() => void focus.command({ operation: 'acknowledge' })}>继续学习</button></div>}
        <div className="focus-primary-actions">
          <button className="app-primary-button" disabled={disabled} onClick={() => running ? void focus.command({ operation: 'pause' }) : void focus.startTask(task, session.mode, (session.target_seconds || 1500) / 60)}>{running ? <Pause size={16} /> : <Play size={16} />}{running ? '暂停' : '继续'}</button>
          <button className="app-secondary-button" disabled={disabled} onClick={() => void focus.command({ operation: 'finish' })}><Square size={14} />结束本次</button>
        </div>
        <footer className="focus-footer"><button className="app-ghost-button" disabled={disabled} onClick={() => setChoosing(true)}>切换任务</button><button className="app-ghost-button" disabled={disabled} onClick={() => void focus.command({ operation: 'complete', task_id: task.id })}><Check size={14} />完成任务</button></footer>
      </> : done ? <>
        {focus.data?.next_task ? <div className="focus-next-task"><span>下一项</span><strong>{focus.data.next_task.title}</strong><button className="app-primary-button" disabled={disabled} onClick={() => begin(focus.data!.next_task!)}><Play size={16} />开始下一项</button></div> : <p className="focus-completion-note">本目标暂无待办，检查目标完成条件。</p>}
        <div className="focus-actions"><button className="app-ghost-button" onClick={() => setChoosing(true)}>选择其他任务</button><button className="app-ghost-button" onClick={rest}>先休息</button></div>
        <footer className="focus-footer"><button className="app-ghost-button" disabled={disabled} onClick={() => void focus.command({ operation: 'reopen', task_id: task.id })}>撤销完成</button></footer>
      </> : <>
        <div className="focus-mode-options" aria-label="计时方式"><button aria-pressed={mode === 'countdown'} onClick={() => setMode('countdown')}>倒计时</button><button aria-pressed={mode === 'stopwatch'} onClick={() => setMode('stopwatch')}>正计时</button></div>
        {mode === 'countdown' && <div className="focus-duration-options">{[25, 50].map(value => <button key={value} aria-pressed={minutes === value} className="app-ghost-button" onClick={() => setMinutes(value)}>{value} 分</button>)}<label>自定义<input className="app-field" aria-label="专注分钟" type="number" min={1} max={120} value={minutes} onChange={event => setMinutes(Number(event.target.value))} />分</label></div>}
        {session && <p className="focus-completion-note">投入已保存，开始后记录新一段专注。</p>}
        <div className="focus-primary-actions is-start"><button className="app-primary-button" disabled={disabled || (mode === 'countdown' && (!Number.isInteger(minutes) || minutes < 1 || minutes > 120))} onClick={() => void focus.startTask(task, mode, mode === 'stopwatch' ? 25 : minutes)}><Play size={16} />{task.goal_status === 'draft' ? '开始学习' : task.goal_status === 'paused' ? '恢复目标并开始' : session ? '开始新一段' : '开始专注'}</button></div>
        <footer className="focus-footer"><button className="app-ghost-button" onClick={() => setChoosing(true)}>选择其他任务</button><button className="app-ghost-button" disabled={disabled} onClick={() => void focus.command({ operation: 'complete', task_id: task.id })}><Check size={14} />完成任务</button></footer>
      </>}
    </>}
    {choosing && <div className="focus-task-chooser"><div className="focus-actions"><button className="app-ghost-button" onClick={() => setChoosing(false)}>返回计时</button><button className="app-secondary-button" aria-pressed={otherGoals} onClick={() => setOtherGoals(!otherGoals)}>{otherGoals ? '全部目标' : '其他目标'}</button></div><p className="goals-muted">选择只切换任务，计时由你开始。</p><div className="focus-task-choices">{choices.map(item => <button className="app-ghost-button" key={item.id} disabled={disabled} onClick={() => void focus.selectTask(item).then(ok => { if (ok) { setChoosing(false); focus.prepareStart(null); } })}><span>{item.title}</span><small>{item.goal_title}</small></button>)}</div>{nextOffset !== null && <button className="app-ghost-button" onClick={() => void loadChoices(nextOffset)}>更多任务</button>}{choiceError && <p role="alert">{choiceError}<button className="app-ghost-button" onClick={() => void loadChoices()}>重试</button></p>}</div>}
  </section>;
  return <div className="focus-controller" ref={controller} role="group" aria-label="专注" aria-owns={open && !placement.sheet ? panelId : undefined}>
    <p className="sr-only" role="status">{announcement}</p>
    {header && showTrigger && createPortal(<div className="focus-tray" aria-label="专注控制器"><button ref={toggle} className="focus-docked" data-paused={focus.data?.status === 'paused'} aria-label={`展开专注面板：${focus.data?.current_task?.title || '专注'}，${focus.pending ? '保存结果待核对' : focus.error ? '尚未同步' : focus.data?.status === 'paused' ? '已暂停' : '专注中'} ${currentNumber}`} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? panelId : undefined} title={focus.data?.current_task?.title || '专注'} onClick={() => { returnFocus.current = toggle.current; setOpen(!open); }}><Timer size={15} aria-hidden="true" /><span className="focus-docked-time">{focus.pending ? '待核对' : focus.error ? '待同步' : currentNumber}</span>{focus.data?.status === 'paused' && !focus.pending && <Pause size={11} aria-label="已暂停" />}</button></div>, header.querySelector('.learning-header-focus-slot') || header)}
    {placement.sheet ? <Dialog open={open} title="专注控制" onClose={close} dismissOnBackdrop className="focus-sheet">{panel}</Dialog> : open && createPortal(panel, document.body)}
  </div>;
}
