export function completionTransition(previous: string, task: {id:string;status:string}|null|undefined, pending: boolean) {
  if (pending) return {identity:previous,reveal:false};
  const identity=task?.status==='completed'?task.id:'';
  return {identity,reveal:Boolean(identity&&identity!==previous)};
}
