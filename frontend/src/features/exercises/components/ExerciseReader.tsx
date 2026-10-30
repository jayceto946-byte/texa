import { useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ReadingMarkdown as SimpleMarkdown } from '../../reading/ReadingMarkdown';
import { useUnsavedWorkGuard } from '../../reading/useUnsavedWorkGuard';
import { QuestionReadingLayout, type ReadingPane } from '../../reading/QuestionReadingLayout';
import { useExerciseAnswerJob } from '../hooks/useExerciseAnswerJob';
import { exerciseStatusText } from './ExercisePresentation';
import type { ExerciseRecord } from '../../../types';
import { SourceStructure } from './SourceStructure';
export function ExerciseReader({ record, bookQuery, title, actions, attempt, footer, onSaved, onMessage, onStatus, onDelete }: { record: ExerciseRecord; bookQuery: string; title: string; actions: ReactNode; attempt?: ReactNode; footer?: ReactNode; onSaved: (record: ExerciseRecord) => void; onMessage: (message: string) => void; onStatus?: (status: string) => void; onDelete?: () => void }) {
  const [pane, setPane] = useState<ReadingPane>('question');
  const [editing, setEditing] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const changePane = (next: ReadingPane) => { setPane(next); if (next !== 'question') setRevealed(true); };
  const job = useExerciseAnswerJob({ exercise: record, bookQuery, onRecordSaved: onSaved, onMessage });
  useUnsavedWorkGuard(Boolean(job.answerDraft), 'AI 草稿尚未保存，退出后会丢失。确定退出 Texa 吗？');
  const protect = (event: React.MouseEvent) => { if (job.answerDraft && !window.confirm('当前 AI 草稿尚未保存，离开或继续将结束此阅读。放弃草稿并继续吗？')) { event.preventDefault(); event.stopPropagation(); } };
  const generate = () => { if (job.answerDraft && !window.confirm('重新生成会替换当前未保存草稿，继续吗？')) return; setEditing(false); void job.generateStandardAnswer(); };
  return <QuestionReadingLayout title={title} meta={[record.subject, record.chapter].filter(Boolean).join(' · ')} actions={<div className="exercise-row" onClickCapture={protect}>{actions}</div>} pane={pane} onPaneChange={changePane} questionLabel={attempt ? '题目与作答' : '题目与来源'} footer={footer && (revealed ? <div className="exercise-reader-footer" onClickCapture={protect}>{footer}</div> : <>
    <span>先独立作答，再核对答案</span>
    <button className="app-primary-button" onClick={() => changePane('reference')}>查看参考答案</button>
  </>)} question={<>
    <h2>题目</h2>
    {record.image_path && <p className="question-reading-status is-warning">原图暂不可读取，请对照来源文件。</p>}<SimpleMarkdown content={record.question_text} />{attempt && <section className="question-reading-section">
      <h3>我的作答</h3>{attempt}</section>}<section className="question-reading-section question-reading-facts">
      <h3>题目信息</h3>
      <SourceStructure value={record.source_structure} />
      <p>{record.question_type || '未定题型'} · 难度 {record.difficulty}</p>
      <p>{record.tags.join(' · ')}</p>
      <details>
        <summary>查看来源</summary>
        <p>{record.source || '来源未记录'}</p>

      </details>{onStatus && <details>
        <summary>题目管理</summary>
        <p>当前题干只读，可编辑参考答案。</p>
        <div className="exercise-row">{Object.entries(exerciseStatusText).map(([v, l]) => <button key={v} className="app-secondary-button" onClick={event => { protect(event); if (!event.isPropagationStopped()) onStatus(v); }}>{l}</button>)}<button className="app-secondary-button" onClick={event => { protect(event); if (!event.isPropagationStopped()) onDelete?.(); }}>删除题目</button>
        </div>
      </details>}</section>
  </>} reference={<>
    <div className="question-reading-status">{job.saveMessage === '已保存到题库' ? job.saveMessage : record.answer?.trim() ? '已保存参考答案' : '参考答案'}</div>{record.answer ? <SimpleMarkdown content={record.answer} /> : <p>暂无参考答案，可使用 AI 解题生成草稿。</p>}{record.explanation && <section className="question-reading-section">
      <h2>已保存解析</h2>
      <SimpleMarkdown content={record.explanation} />
    </section>}</>} ai={<>
      <p role={job.answerStatus === 'failed' ? 'alert' : 'status'} className={`question-reading-status ${['failed', 'unavailable'].includes(job.answerStatus) ? 'is-warning' : ''}`}>{job.answerStatusMessage}</p>{job.answerDraft ? <>
        <div className="question-reading-draft-toolbar">
          <span>未保存草稿 · 保存后成为题库答案；关闭题目、刷新或退出会丢失编辑</span>
          <button className="app-ghost-button" disabled={job.answerBusy || job.saving} onClick={() => setEditing(!editing)}>{editing ? '阅读预览' : '编辑草稿'}</button>
          <button className="app-secondary-button" disabled={job.saving || job.answerBusy} onClick={async () => { if (await job.saveStandardAnswer()) { setEditing(false); changePane('reference'); } }}>{job.saving ? '正在保存…' : '保存到题库'}</button>
        </div>{editing ? <textarea aria-label="答案草稿" value={job.answerDraft} onChange={e => job.setAnswerDraft(e.target.value)} /> : <SimpleMarkdown content={job.answerDraft} />}</> : !job.answerBusy && <>
          <h2>AI 解题</h2>
          <p>生成后可阅读、编辑，明确保存后写入题库。</p>
        </>}{job.saveMessage && job.saveMessage !== '已保存到题库' && <p role="status" className="question-reading-status is-warning">{job.saveMessage}</p>}{job.answerStatus === 'unavailable' ? <button className="app-secondary-button" onClick={() => void job.reconnect(true)}>重新读取任务状态</button> : <div className="question-reading-end">
          {job.modelReady === false ? <><p className="question-reading-status is-warning">回答模型尚未就绪，请先完成模型与凭证配置。</p><button className="app-secondary-button" onClick={() => navigate(location.pathname, { replace: true, state: { openSettings: true } })}>配置模型</button><button className="app-ghost-button" onClick={() => void job.checkModel()}>重新检查配置</button></> : <button className="app-secondary-button" disabled={job.answerBusy || job.saving} onClick={generate}>{job.answerBusy ? '正在生成…' : job.answerDraft ? '重新生成' : '生成解答'}</button>}
        </div>}</>} />;
}
