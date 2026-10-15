import {describe,expect,it} from 'vitest';
import {completionTransition} from './controllerState';
describe('completion panel transitions',()=>{
  it('reveals a newly completed task after confirmation',()=>{
    expect(completionTransition('',{id:'a',status:'completed'},false)).toEqual({identity:'a',reveal:true});
  });
  it('does not reopen an old completion during another queue command',()=>{
    const pending=completionTransition('a',{id:'a',status:'completed'},true);
    expect(pending).toEqual({identity:'a',reveal:false});
    expect(completionTransition(pending.identity,{id:'a',status:'completed'},false).reveal).toBe(false);
  });
  it('waits for the original command receipt before announcing completion',()=>{
    expect(completionTransition('',{id:'a',status:'completed'},true)).toEqual({identity:'',reveal:false});
    expect(completionTransition('',{id:'a',status:'completed'},false).reveal).toBe(true);
  });
  it('allows completing a reopened task to reveal a new transition',()=>{
    const reopened=completionTransition('a',{id:'a',status:'pending'},false);
    expect(completionTransition(reopened.identity,{id:'a',status:'completed'},false).reveal).toBe(true);
  });
});
