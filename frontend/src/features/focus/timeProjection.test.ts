import { describe, expect, it } from 'vitest';
import { acceptFocusSnapshot, projectFocus } from './timeProjection';
import { focusTime, type FocusSnapshot } from './FocusContext';
const snapshot={revision:3,runtime_id:'process-1',snapshot_sequence:4,status:'running',active_ms:20_000,current_session:{target_seconds:60}} as FocusSnapshot;
describe('focus clock projection and authoritative snapshots',()=>{
  it('projects elapsed and overdue time without capping actual input or mutating data',()=>{expect(projectFocus(snapshot,1000,43_000)).toEqual({elapsed:62,remaining:0,overtime:2});expect(snapshot.active_ms).toBe(20_000);});
  it('does not count a paused interval or invent remaining time for a stopwatch',()=>{expect(projectFocus({...snapshot,status:'paused'},1000,301_000).elapsed).toBe(20);expect(projectFocus({...snapshot,current_session:{...snapshot.current_session!,target_seconds:null}},1000,11_000)).toEqual({elapsed:30,remaining:null,overtime:0});});
  it('rejects older revisions and older same-revision snapshots even if wall clock advanced',()=>{expect(acceptFocusSnapshot(snapshot,{...snapshot,revision:2,server_time:999999})).toBe(false);expect(acceptFocusSnapshot(snapshot,{...snapshot,snapshot_sequence:3})).toBe(false);expect(acceptFocusSnapshot(snapshot,{...snapshot,snapshot_sequence:5,server_time:0})).toBe(true);expect(acceptFocusSnapshot(snapshot,{...snapshot,runtime_id:'new-process',snapshot_sequence:1})).toBe(true);});
  it('formats hours and keeps boundary seconds monotonic',()=>{expect(focusTime(3800)).toBe('1:03:20');expect(focusTime(59.9)).toBe('00:59');expect(focusTime(-1)).toBe('00:00');});
});
