import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { get } from '../../../api/client';
import { useFocus, type FocusTask } from '../FocusContext';
export function useTaskQueue(goalId: string) {
  const location=useLocation(),routeActive=location.pathname==='/goals';
  const taskId=new URLSearchParams(location.search).get('task') || '';
  const [pageOffset,setPageOffset]=useState(0);
  const focus=useFocus(); const revision=focus.data?.revision;
  const [tasks,setTasks]=useState<FocusTask[]>([]), [next,setNext]=useState<number|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const epoch=useRef(0),offset=useRef(0);
  const load=useCallback(async (append=false,locate=true)=>{
    const generation=++epoch.current;setLoading(true);
    try {
      const response=await get(`/focus?goal_id=${encodeURIComponent(goalId)}&offset=${append?offset.current:0}${!append&&locate&&taskId?`&around_task_id=${encodeURIComponent(taskId)}`:''}`);
      if (generation!==epoch.current) return;
      const snapshot=response.data;
      if (!response.success) throw new Error('任务列表暂不可读取');
      setTasks(previous=>append?[...previous,...snapshot.tasks]:snapshot.tasks);setNext(snapshot.next_offset);if(!append)setPageOffset(snapshot.page_offset||0);offset.current=snapshot.next_offset || 0;setError('');
    } catch (reason) {if(generation===epoch.current)setError(reason instanceof Error?reason.message:'任务列表暂不可读取');}
    finally {if(generation===epoch.current)setLoading(false);}
  },[goalId,taskId]);
  const invalidate=useCallback(()=>{epoch.current++;},[]);
  useEffect(()=>{if(routeActive)void load();return invalidate;},[load,revision,invalidate,routeActive]);
  return {tasks,next,error,loading,reload:load,focus,pageOffset,taskId};
}
