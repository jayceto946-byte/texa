import { useState } from 'react';
type Criterion={id:string;description?:string};
export default function GoalEditor({goal,busy,onSave,onClose}:{goal:{title:string;objective:string;success_criteria:Criterion[]};busy:boolean;onSave:(changes:{title:string;objective:string;success_criteria:Criterion[]})=>Promise<boolean>;onClose:()=>void}) {
  const [title,setTitle]=useState(goal.title),[objective,setObjective]=useState(goal.objective),[criteria,setCriteria]=useState(goal.success_criteria.map(item=>({...item})));
  return <form className="goal-contract-editor" onSubmit={event=>{event.preventDefault();void onSave({title:title.trim(),objective:objective.trim(),success_criteria:criteria.filter(item=>item.description?.trim()).map(item=>({...item,description:item.description?.trim()}))}).then(ok=>{if(ok)onClose();});}}>
    <label>目标标题<input className="app-field" maxLength={200} required value={title} onChange={event=>setTitle(event.target.value)}/></label><label>说明<textarea className="app-field" maxLength={2000} value={objective} onChange={event=>setObjective(event.target.value)}/></label>
    <p className="goals-muted">修改目标条件不会改写已有任务。关键修改会结束当前专注并停止 AI 执行。</p>
    {criteria.map((item,index)=><label key={item.id}>完成条件 {index+1}<input className="app-field" value={item.description||''} maxLength={1000} onChange={event=>setCriteria(previous=>previous.map((value,i)=>index===i?{...value,description:event.target.value}:value))}/></label>)}
    <div className="focus-actions"><button type="button" className="app-ghost-button" disabled={criteria.length>=12} onClick={()=>setCriteria([...criteria,{id:crypto.randomUUID(),description:''}])}>添加条件</button><button className="app-primary-button" disabled={busy||!title.trim()}>保存修改</button><button type="button" className="app-ghost-button" onClick={onClose}>取消</button></div>
  </form>;
}
