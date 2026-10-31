import { TexaBack } from '../components/icons';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Archive, BookOpen, CheckCircle2, FileText, HelpCircle, Upload } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import ConceptExtractionStatus from '../features/textbooks/ConceptExtractionStatus';
import ScopeSelector from '../components/ScopeSelector';
import { SegmentedControl } from '../components/ui/SelectionControls';
import { WorkspaceActionBar } from '../components/ui/WorkspaceActionBar';
import { TaskStatus } from '../components/ui/AsyncState';
import OutlineCalibrationPanel from '../features/textbooks/OutlineCalibrationPanel';
import '../features/textbooks/textbookImport.css';
import type { BookReadiness } from '../components/settings/LibraryWorkbench';

type ImportJob = {
  id: string;
  status: 'running' | 'completed' | 'failed' | string;
  stage: string;
  progress: number;
  message: string;
  book_name: string;
  subject?: string;
  result?: {
    name: string;
    review_required?: boolean;
    chapter_count: number;
    used_mineru: boolean;
    indexed_chunks?: number;
    output_dir?: string;
    subject?: string;
    concept_job_id?: string;
    concept_extraction_warning?: string;
    ingestion_report?: { source_metadata?: { structure_quality?: { exercise_sections_without_units?: string[] } } };
    readiness?: BookReadiness;
  } | null;
};

type ImportCapabilities = {
  mineru: {
    configured: boolean;
    available: boolean;
    mode: 'api' | 'cli' | 'none';
    reason: 'ready' | 'api_error' | 'api_unreachable' | 'cli_missing' | 'not_configured' | string;
  };
  local_pdf: { available: boolean; limitation: string };
  output_bundle: { available: boolean };
};

const stageLabels: Record<string, string> = {
  queued: '排队',
  started: '准备',
  mineru_submit: '提交 MinerU',
  mineru_running: 'MinerU 解析',
  mineru_download: '下载结果',
  extract: '解压结果包',
  structure: '整理结构',
  indexing: '建立索引',
  completed: '完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
};

const OptionHelp = ({ title, description }: { title: string; description: string }) => {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex shrink-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="rounded p-0.5 text-text-secondary hover:text-accent"
        title={`${title}\u8bf4\u660e`}
        aria-label={`${title}\u8bf4\u660e`}
        aria-expanded={open}
      >
        <HelpCircle className="h-4 w-4" />
      </button>
      {open && (
        <span role="note" className="app-popover-enter absolute right-0 top-7 z-20 w-[min(340px,calc(100vw-72px))] rounded-xl border border-border bg-bg-primary p-3 text-xs shadow-lg">
          <span className="block font-semibold text-text-primary">{title}</span>
          <span className="mt-1 block leading-5 text-text-secondary">{description}</span>
        </span>
      )}
    </span>
  );
};

const BooksPage: React.FC = () => {
  const navigate = useNavigate();
  const [importMode, setImportMode] = useState<'pdf' | 'bundle'>('bundle');
  const [file, setFile] = useState<File | null>(null);
  const [outputFile, setOutputFile] = useState<File | null>(null);
  const [tocPages, setTocPages] = useState('');
  const [subject, setSubject] = useState('');
  const [parseMethod, setParseMethod] = useState<'mineru' | 'local'>('local');
  const [capabilities, setCapabilities] = useState<ImportCapabilities | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [extractConcepts, setExtractConcepts] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState('');
  const [cancelBusy, setCancelBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const outputInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const [reviewOpen, setReviewOpen] = useState(false);
  const activeImportRef = useRef('');
  const stopPolling = useCallback(() => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = null; activeImportRef.current = '';
  }, []);

  useEffect(() => () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    let active = true;
    apiFetch('/books/import-capabilities')
      .then((response) => response.json())
      .then((payload) => {
        if (!active) return;
        const next = payload?.success ? payload.data as ImportCapabilities : null;
        setCapabilities(next);
        setParseMethod(next?.mineru?.available ? 'mineru' : 'local');
      })
      .catch(() => {
        if (active) setCapabilities(null);
      })
      .finally(() => {
        if (active) setCapabilitiesLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const pollJob = useCallback((jobId: string) => {
    stopPolling(); activeImportRef.current = jobId;
    pollRef.current = window.setInterval(async () => {
      try {
        const res = await apiFetch(`/books/import-jobs/${jobId}`);
        const data = await res.json();
        if (activeImportRef.current !== jobId) return;
        if (!data.success) throw new Error(data.message || '获取导入进度失败');
        setJob(data.data);
        if (data.data.status === 'waiting_for_review') {
          stopPolling(); setUploading(false); setReviewOpen(true);
        }
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(data.data.status)) {
          stopPolling();
          setUploading(false);
          if (['completed','cancelled'].includes(data.data.status)) localStorage.removeItem('texa:pending-book-import');
          if (data.data.status === 'completed') window.dispatchEvent(new CustomEvent('books:changed', {
            detail: { importedBook: data.data.result?.name, importedSubject: data.data.result?.subject || '' },
          }));
        }
      } catch (err) {
        if (activeImportRef.current !== jobId) return;
        stopPolling();
        setUploading(false);
        setError(err instanceof Error ? err.message : String(err));
      }
    }, 1200);
  }, [stopPolling]);

  useEffect(() => {
    const pending = localStorage.getItem('texa:pending-book-import');
    if (pending) pollJob(pending);
    return stopPolling;
  }, [pollJob, stopPolling]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (uploading) return;
    const nextFile = e.target.files?.[0] || null;
    setFile(nextFile);
    setJob(null);
    setError('');
  };

  const handleOutputFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (uploading) return;
    const nextFile = e.target.files?.[0] || null;
    setOutputFile(nextFile);
    setJob(null);
    setError('');
  };

  const handleUpload = async () => {
    if (!file || uploading) return;
    if (parseMethod === 'mineru' && !capabilities?.mineru.available) {
      setError('MinerU 当前不可用。请选择本地文本提取，或导入已解析的 MinerU 输出包。');
      return;
    }
    setUploading(true);
    setError('');
    setJob(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('toc_pages', tocPages);
    formData.append('pre_read', 'false');
    formData.append('parse_method', parseMethod);
    formData.append('subject', subject);
    formData.append('extract_concepts', String(extractConcepts));

    try {
      const res = await apiFetch('/books/import-job', { method: 'POST', body: formData });
      const data = await res.json();
      if (!data.success) throw new Error(data.message || '启动导入失败');
      setJob(data.data);
      localStorage.setItem('texa:pending-book-import', data.job_id);
      pollJob(data.job_id);
    } catch (err) {
      setUploading(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleOutputUpload = async () => {
    if (!outputFile || uploading) return;
    setUploading(true);
    setError('');
    setJob(null);

    const formData = new FormData();
    formData.append('file', outputFile);
    formData.append('book_name', outputFile.name.replace(/\.zip$/i, ''));
    formData.append('subject', subject);
    formData.append('extract_concepts', String(extractConcepts));

    try {
      const res = await apiFetch('/books/import-mineru-output', { method: 'POST', body: formData });
      const data = await res.json();
      if (!data.success) throw new Error(data.message || '启动输出包导入失败');
      setJob(data.data);
      localStorage.setItem('texa:pending-book-import', data.job_id);
      pollJob(data.job_id);
    } catch (err) {
      setUploading(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const progress = Math.max(0, Math.min(100, job?.progress ?? 0));
  const isDone = job?.status === 'completed';
  const unparsedExerciseSections = job?.result?.ingestion_report?.source_metadata?.structure_quality?.exercise_sections_without_units?.length || 0;
  const isFailed = ['failed', 'cancelled', 'interrupted'].includes(job?.status || '');
  const mineru = capabilities?.mineru;
  const mineruUnavailableText = !mineru?.configured
    ? 'MinerU 未配置'
    : mineru.reason === 'api_unreachable' || mineru.reason === 'api_error'
      ? 'MinerU API 当前无法连接'
      : mineru.reason === 'cli_missing'
        ? 'MinerU CLI 当前不可执行'
        : '无法确认 MinerU 状态';

  const cancelImport = async () => {
    if (!job || cancelBusy) return;
    setCancelBusy(true);
    try {
      const response = await apiFetch(`/books/import-jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.message || '取消请求尚未确认，请重试。');
      setJob((current) => current?.id === job.id ? { ...current, ...result.data } : current);
      pollJob(job.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '取消请求尚未确认，请重试。');
    } finally { setCancelBusy(false); }
  };

  const awaitingReview = job?.status === 'waiting_for_review';
  const canReview = awaitingReview || Boolean(['failed','interrupted'].includes(job?.status || '') && job?.result?.review_required);
  const hasTask = Boolean(job || uploading);
  const bookTitle = job?.result?.name || job?.book_name || '教材';
  const warnings = job?.result?.readiness?.retrieval?.warnings || [];
  const startAnother = async () => {
    if (awaitingReview && job) await apiFetch(`/books/import-jobs/${job.id}/cancel`, {method:'POST'});
    stopPolling(); localStorage.removeItem('texa:pending-book-import');
    setJob(null); setFile(null); setOutputFile(null); setError(''); setUploading(false); setReviewOpen(false);
  };

  return <div className="management-workspace textbook-import-workspace flex h-full min-w-0 flex-col bg-bg-primary">
    <header className="app-page-header window-drag-region border-b border-border bg-bg-card"><h2 className="app-page-title">导入教材</h2><button type="button" onClick={()=>navigate('/books')} className="app-ghost-button"><TexaBack className="h-4 w-4"/>返回教材</button></header>
    <div className="textbook-import-scroll"><div className="textbook-import-content">
      <ol className="textbook-import-steps" aria-label="导入步骤">{['选择文件','确认目录','完成'].map((label,index)=><li key={label} aria-current={(isDone?2:hasTask?1:0)===index?'step':undefined}><span>{index+1}</span>{label}</li>)}</ol>
      {!hasTask && <section className="textbook-import-form" aria-label="选择教材文件">
        <SegmentedControl label="教材导入来源" value={importMode} options={[{value:'bundle',label:'MinerU 输出包',icon:<Archive size={16}/>},{value:'pdf',label:'PDF 教材',icon:<FileText size={16}/>}]} onChange={setImportMode}/>
        <button type="button" className="textbook-file-picker" onClick={()=>importMode==='pdf'?inputRef.current?.click():outputInputRef.current?.click()}>
          <Upload size={28}/><strong>{importMode==='pdf'?(file?.name||'选择 PDF 教材'):(outputFile?.name||'选择 MinerU 输出包')}</strong>
          <span>{importMode==='pdf'?'支持本地 PDF 文件':'选择保留目录和图片的 ZIP 文件'}</span>
        </button>
        <input aria-label="PDF 教材文件" ref={inputRef} type="file" accept=".pdf,application/pdf" onChange={handleFileChange} className="hidden"/>
        <input aria-label="MinerU 输出包文件" ref={outputInputRef} type="file" accept=".zip,application/zip" onChange={handleOutputFileChange} className="hidden"/>
        <div className="textbook-import-fields"><label className="textbook-import-subject"><span>所属科目</span><ScopeSelector subject={subject} onSubjectChange={setSubject} bookMode="hidden" size="form" label="所属科目" placeholder="选择科目" fullWidth width="wide"/></label>
          {importMode==='pdf' && <div className="textbook-import-method"><span>解析方式</span>{capabilitiesLoading?<p>正在检查…</p>:mineru?.available?<SegmentedControl label="PDF 解析方式" value={parseMethod} options={[{value:'local',label:'本地文本'},{value:'mineru',label:'MinerU'}]} onChange={setParseMethod}/>:<div><span>本地文本提取</span><button type="button" onClick={()=>setImportMode('bundle')}>扫描件使用输出包</button></div>}</div>}
        </div>
        <details className="textbook-import-options"><summary>更多选项</summary><div>
          {importMode==='pdf' && <label className="textbook-import-toc">目录所在物理页<input aria-label="目录所在物理页" placeholder="自动识别，或填写 6-7" value={tocPages} onChange={e=>setTocPages(e.target.value)}/></label>}
          <label className="textbook-import-concepts"><input type="checkbox" checked={extractConcepts} onChange={e=>setExtractConcepts(e.target.checked)}/>导入后提取概念索引<OptionHelp title="概念索引" description="确认导入后，将教材片段发送至已配置的外部模型，提取概念和关系；不影响本地索引的建立。"/></label>
          <p>{importMode==='bundle'?'输出包可包含 structured_content、content_list、middle JSON 或 Markdown，以及对应图片。':mineru?.available?'本地文本适用于可复制文字的 PDF；扫描件请选择 MinerU。':`${mineruUnavailableText}。本地文本仅适用于可复制文字的 PDF。`}</p>
        </div></details>
      </section>}
      {error && <div className="textbook-import-error" role="alert">{error}</div>}
      {hasTask && <section className={`textbook-import-result ${isDone?'is-success':''}`} aria-label="教材导入状态">
        {isDone?<>
          <CheckCircle2 size={36}/><h3>教材已导入</h3><p className="textbook-import-book-title">{bookTitle}</p><p>{job?.result?.chapter_count || 0} 章 · 目录已确认</p>
          <div className="textbook-import-result-actions"><button type="button" className="app-secondary-button" onClick={()=>navigate('/books')}>查看教材</button><button type="button" className="app-primary-button" onClick={()=>navigate('/')}>开始学习</button></div>
          {Boolean(warnings.length || unparsedExerciseSections) && <details className="textbook-import-checks"><summary>查看需核对项目</summary>{warnings.map(warning=><p key={warning}>{warning}</p>)}{unparsedExerciseSections>0&&<p>{unparsedExerciseSections} 个习题范围尚未识别出题目，可在教材中继续核对。</p>}</details>}
          {job?.result?.concept_job_id && <ConceptExtractionStatus bookName={bookTitle} jobId={job.result.concept_job_id}/>}
          {job?.result?.concept_extraction_warning && <p>概念索引：{job.result.concept_extraction_warning}</p>}
        </>:canReview?<>
          <BookOpen size={36}/><h3>请确认教材目录</h3><p className="textbook-import-book-title">{bookTitle}</p><p>已整理 {job?.result?.chapter_count||0} 章，可补建标题、拆分章节或调整页码。</p>
          <button type="button" className="app-primary-button" onClick={()=>setReviewOpen(true)}>查看并确认目录</button>
        </>:isFailed || job?.status==='cancelled'?<>
          <h3>{job?.status==='cancelled'?'已取消导入':'导入未完成'}</h3><p>{bookTitle}</p><details className="textbook-import-checks"><summary>查看原因</summary><p>{job?.message || error}</p></details>
        </>:<TaskStatus title={job?.status==='cancelling'?'正在取消导入':job?.stage==='indexing'?'正在建立教材索引':'正在解析教材'} detail={job?.status==='cancelling'?'等待后台停止确认':job?.book_name || '正在准备文件…'} progress={progress} state="loading"/>}
      </section>}
    </div></div>
    <WorkspaceActionBar status={isDone?'':awaitingReview?'确认目录后正式导入':uploading?(stageLabels[job?.stage||'']||'正在准备…'):hasTask?'':'解析完成后可校正目录'}>
      {hasTask && !uploading && <button type="button" className="app-secondary-button" onClick={()=>void startAnother()}>{isDone?'导入另一本':'重新选择文件'}</button>}
      {uploading && job && <button type="button" className="app-secondary-button" disabled={cancelBusy||job.status==='cancelling'} onClick={()=>void cancelImport()}>{cancelBusy||job.status==='cancelling'?'正在取消…':'取消导入'}</button>}
      {!hasTask && <button type="button" onClick={importMode==='pdf'?handleUpload:handleOutputUpload} disabled={importMode==='pdf'?!file||!subject.trim():!outputFile} className="app-primary-button"><Upload size={16}/>解析并检查目录</button>}
    </WorkspaceActionBar>
    {reviewOpen && job && <OutlineCalibrationPanel key={job.id} bookName={bookTitle} importJobId={job.id} onClose={()=>setReviewOpen(false)} onConfirmed={id=>{setReviewOpen(false);setUploading(true);setJob({...job,status:'running',stage:'indexing',progress:50});pollJob(id);}}/>}
  </div>;
};

export default BooksPage;
