import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Dialog from '../../components/ui/Dialog';
import { notesApi, noteRequest } from './api';
import type { Preflight } from './types';
import type { NoteCommandTarget } from './NoteCommandContext';
import './notes.css';

export default function NotePreflight({ conversationId, title, busy = false, onClose }: NoteCommandTarget & { onClose: () => void }) {
  const navigate = useNavigate();
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [hint, setHint] = useState('auto');
  const [selected, setSelected] = useState<string[] | undefined>();
  const [turns, setTurns] = useState<{ turn_id: string; label: string }[]>([]);
  const [turnCursor, setTurnCursor] = useState<number | null>(null);
  const [completedOnly, setCompletedOnly] = useState(busy);
  const [error, setError] = useState('');
  const [turnError, setTurnError] = useState('');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const operation = useRef<string | null>(null);
  const alive = useRef(true);
  const submitted = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const loadTurns = useCallback(async (cursor?: number) => {
    setTurnError('');
    try {
      const page = await noteRequest<{ items: typeof turns; next_cursor: number | null }>(`/turns?conversation_id=${encodeURIComponent(conversationId)}${cursor ? `&cursor=${cursor}` : ''}`);
      if (!alive.current) return;
      setTurns(old => cursor ? [...old, ...page.items] : page.items);
      setTurnCursor(page.next_cursor);
    } catch (e) { if (alive.current) setTurnError(e instanceof Error ? e.message : '读取轮次失败'); }
  }, [conversationId]);
  useEffect(() => { void loadTurns(); }, [loadTurns]);
  useEffect(() => {
    let active = true;
    operation.current = null;
    setLoading(true); setPreflight(null); setError('');
    void notesApi.preflight({ conversation_id: conversationId, ...(selected ? { turn_ids: selected } : {}) }, hint, completedOnly)
      .then(value => { if (active) setPreflight(value); })
      .catch(e => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [conversationId, selected, hint, completedOnly, refresh]);
  const close = useCallback(() => { if (!submitted.current) onClose(); }, [onClose]);
  // Invalidate immediately; the old fingerprint cannot be submitted before effects run.
  const invalidate = () => { setPreflight(null); setLoading(true); operation.current = null; };
  const generate = async () => {
    if (!preflight || loading || submitted.current) return;
    submitted.current = true; setGenerating(true); setError('');
    operation.current ||= crypto.randomUUID();
    try {
      const receipt = await notesApi.generate({ operation_id: operation.current, selection: preflight.selection, preflight_fingerprint: preflight.fingerprint, structure_hint: hint });
      if (!alive.current) return;
      onClose(); navigate(`/notes/drafts/${receipt.draft_id}`);
    } catch (e) { if (alive.current) setError(e instanceof Error ? e.message : '生成申请失败'); }
    finally { submitted.current = false; if (alive.current) setGenerating(false); }
  };
  return <Dialog open title="整理为笔记" onClose={close} dismissOnBackdrop className="note-dialog">
    <div className="note-toolbar"><h2>整理为笔记</h2><button className="app-ghost-button" disabled={generating} onClick={close}>取消</button></div>
    <p>根据会话内容整理，生成后可修改并保存。</p>
    {title && <p className="note-preflight-origin">{title}</p>}
    {busy && <p className="note-caption">本次默认只包含已完成内容。</p>}
    {loading && <p role="status">正在读取会话内容…</p>}
    {error && <div role="alert" className="note-warning"><p>{error}</p>{!generating && <button className="app-secondary-button" onClick={() => setRefresh(v => v + 1)}>重新检查</button>}</div>}
    {preflight && !loading && <>
      <p className="note-caption">共 {preflight.turn_count} 轮 · {selected ? `自选范围 ${selected.length} 轮` : '全部完整学习轮次'}</p>
      {preflight.existing_drafts.items.map(d => <Link className="note-existing-draft app-primary-button" key={d.id} to={`/notes/drafts/${d.id}`} onClick={onClose}>继续已有草稿 · {d.content?.title || title || '本会话笔记'}</Link>)}
    </>}
    <details className="note-preflight-settings"><summary>整理设置</summary>
      <label>整理侧重<select value={hint} disabled={generating} onChange={e => { invalidate(); setHint(e.target.value); }}>{[['auto', '按实际内容'], ['concept', '概念理解'], ['derivation', '推导'], ['problem', '解题'], ['comparison', '比较'], ['review', '复习']].map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label className="note-checkbox"><input type="checkbox" disabled={generating} checked={completedOnly} onChange={e => { invalidate(); setCompletedOnly(e.target.checked); }}/>只整理已完成的轮次</label>
      <p className="note-caption">{selected ? `自选 ${selected.length} 轮；只包含勾选的轮次，更早轮次需加载后选择。` : '当前包含全部轮次（包括尚未加载的更早内容）。'}</p>
      <div className="note-actions"><button className="app-ghost-button" disabled={generating} onClick={() => { invalidate(); setSelected(undefined); }}>全部内容</button><button className="app-ghost-button" disabled={generating} onClick={() => { invalidate(); setSelected([]); }}>自选范围</button></div>
      <div className="note-turn-selection">{turns.map(turn => <label key={turn.turn_id}><input type="checkbox" disabled={generating || selected === undefined} checked={selected === undefined || selected.includes(turn.turn_id)} onChange={e => { invalidate(); setSelected(e.target.checked ? [...(selected || []), turn.turn_id] : (selected || []).filter(t => t !== turn.turn_id)); }}/>{turn.label}</label>)}</div>
      {turnError && <p role="alert">{turnError} <button className="app-ghost-button" onClick={() => void loadTurns(turnCursor || undefined)}>重试</button></p>}
      {turnCursor && <button disabled={generating} className="app-ghost-button" onClick={() => void loadTurns(turnCursor)}>加载更早轮次</button>}
    </details>
    {preflight && !loading && <details><summary>整理范围</summary><p className="note-caption">{preflight.message_count} 条消息 · 预计 {preflight.batches} 批 · 整理至 {new Date(preflight.captured_at).toLocaleString()}</p>{preflight.existing_notes.items.map(n => <Link className="app-ghost-button" key={n.id} to={`/notes/${n.id}`} onClick={onClose}>已有笔记 · {n.title}</Link>)}</details>}
    <div className="note-preflight-footer"><button className={preflight?.existing_drafts.items.length ? "app-secondary-button" : "app-primary-button"} disabled={generating || loading || !preflight || preflight.turn_count === 0} onClick={() => void generate()}>{generating ? '正在创建草稿…' : '生成草稿'}</button></div>
  </Dialog>;
}
