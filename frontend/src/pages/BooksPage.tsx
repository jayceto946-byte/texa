import React, { useEffect, useRef, useState } from 'react';
import { Archive, ArrowLeft, FileText, HelpCircle, Loader2, Upload } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import ConceptExtractionStatus from '../features/textbooks/ConceptExtractionStatus';
import ScopeSelector from '../components/ScopeSelector';
import { SegmentedControl } from '../components/ui/SelectionControls';
import { WorkspaceActionBar } from '../components/ui/WorkspaceActionBar';
import { ActionableIssue, StatusBanner, TaskStatus } from '../components/ui/AsyncState';

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
    chapter_count: number;
    used_mineru: boolean;
    indexed_chunks?: number;
    output_dir?: string;
    subject?: string;
    concept_job_id?: string;
    concept_extraction_warning?: string;
    ingestion_report?: { source_metadata?: { structure_quality?: { exercise_sections_without_units?: string[] } } };
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

  const stopPolling = () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    pollRef.current = null;
  };

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

  const pollJob = (jobId: string) => {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const res = await apiFetch(`/books/import-jobs/${jobId}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.message || '获取导入进度失败');
        setJob(data.data);
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(data.data.status)) {
          stopPolling();
          setUploading(false);
          if (data.data.status === 'completed') window.dispatchEvent(new CustomEvent('books:changed', {
            detail: { importedBook: data.data.result?.name, importedSubject: data.data.result?.subject || '' },
          }));
        }
      } catch (err) {
        stopPolling();
        setUploading(false);
        setError(err instanceof Error ? err.message : String(err));
      }
    }, 1200);
  };

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
      const response = await apiFetch(`/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.message || '取消请求尚未确认，请重试。');
      setJob((current) => current?.id === job.id ? { ...current, ...result.data } : current);
      pollJob(job.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '取消请求尚未确认，请重试。');
    } finally { setCancelBusy(false); }
  };

  return (
    <div className="management-workspace flex h-full min-w-0 flex-col bg-bg-primary">
      <header className="app-page-header window-drag-region border-b border-border bg-bg-card">
        <h2 className="app-page-title">导入教材</h2>
        <button type="button" onClick={() => navigate('/books')} className="app-ghost-button"><ArrowLeft className="h-4 w-4" />返回教材</button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto"><div className="management-page-content mx-auto w-full max-w-6xl space-y-5">
        <section className="border-y border-border py-4">
          <div className="mb-3 text-[18px] font-semibold text-text-primary">1. 选择来源</div>
          <SegmentedControl
            label="教材导入来源"
            value={importMode}
            options={[{ value: 'bundle', label: 'MinerU 输出包（推荐）', icon: <Archive className="h-4 w-4" /> }, { value: 'pdf', label: 'PDF 教材', icon: <FileText className="h-4 w-4" /> }]}
            onChange={(mode) => { if (!uploading) setImportMode(mode); }}
          />
        </section>

        {importMode === 'pdf' ? (
          <section>
            <h3 className="mb-3 text-[18px] font-semibold text-text-primary">2. 选择文件并设置参数</h3>
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <button type="button" disabled={uploading} onClick={() => inputRef.current?.click()} className="app-panel flex min-h-[190px] w-full flex-col items-center justify-center p-8 text-center hover:border-accent/60 hover:bg-[var(--accent-softer)]">
              <Upload className="mb-4 h-9 w-9 text-accent" />
              <span className="type-section-title text-text-primary">{file ? file.name : '选择 PDF 教材'}</span>
              <span className="type-caption mt-2 text-text-secondary">点击选择本地 PDF 文件</span>
            </button>
            <input ref={inputRef} type="file" accept=".pdf,application/pdf" onChange={handleFileChange} className="hidden" />

            <div className="app-panel space-y-4 p-5">
              <h3 className="text-[16px] font-semibold text-text-primary">解析参数</h3>
              <label className="block">
                <span className="mb-1.5 block type-caption text-text-secondary">目录页码范围，可选</span>
                <input value={tocPages} onChange={(e) => setTocPages(e.target.value)} placeholder="如 1-5" className="w-full app-field" />
              </label>
              <label className="block">
                <span className="mb-1.5 block type-caption text-text-secondary">所属科目</span>
                <ScopeSelector subject={subject} onSubjectChange={setSubject} bookMode="hidden" size="form" label="所属科目" fullWidth width="wide" />
              </label>
              <div className="border-t border-border pt-3">
                <div className="mb-2 type-caption text-text-secondary">{'\u89e3\u6790\u65b9\u5f0f'}</div>
                <div className="grid gap-2">
                  <div className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${parseMethod === 'mineru' ? 'border-accent bg-[var(--accent-softer)] text-text-primary' : 'border-border bg-bg-primary text-text-secondary'}`}>
                    <input id="parse-mineru" name="parse-method" type="radio" checked={parseMethod === 'mineru'} disabled={capabilitiesLoading || !mineru?.available} onChange={() => setParseMethod('mineru')} className="mt-0.5 accent-accent disabled:cursor-not-allowed" />
                    <label htmlFor="parse-mineru" className="flex-1">{'MinerU \u89e3\u6790'}</label>
                    <OptionHelp
                      title={'MinerU \u89e3\u6790'}
                      description={'\u9002\u5408\u626b\u63cf\u7248\u3001\u516c\u5f0f\u548c\u590d\u6742\u7248\u9762\uff0c\u9700\u8981\u5df2\u914d\u7f6e MinerU API \u6216 CLI\uff0c\u901f\u5ea6\u76f8\u5bf9\u8f83\u6162\u3002'}
                    />
                  </div>
                  <div className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${parseMethod === 'local' ? 'border-accent bg-[var(--accent-softer)] text-text-primary' : 'border-border bg-bg-primary text-text-secondary'}`}>
                    <input id="parse-local" name="parse-method" type="radio" checked={parseMethod === 'local'} onChange={() => setParseMethod('local')} className="mt-0.5 accent-accent" />
                    <label htmlFor="parse-local" className="flex-1">{'\u672c\u5730\u6587\u672c\u63d0\u53d6'}</label>
                    <OptionHelp
                      title={'\u672c\u5730\u6587\u672c\u63d0\u53d6'}
                      description={'\u76f4\u63a5\u8bfb\u53d6 PDF \u81ea\u5e26\u7684\u6587\u5b57\u5c42\uff0c\u4e0d\u6267\u884c OCR\u3002\u4ec5\u9002\u5408\u53ef\u590d\u5236\u6587\u5b57\u7684 PDF\uff1b\u626b\u63cf\u7248\u53ef\u80fd\u65e0\u6b63\u6587\u3002\u9009\u62e9\u540e\u4e0d\u4f1a\u8c03\u7528 MinerU\u3002'}
                    />
                  </div>
                  {capabilitiesLoading ? (
                    <p className="type-caption text-text-secondary">正在检查 MinerU 连接…</p>
                  ) : !mineru?.available ? (
                    <div className="border-l-2 border-[var(--warning)] pl-3">
                      <p className="type-caption text-[var(--warning-text)]">{mineruUnavailableText}，当前已选择本地文本提取。</p>
                      <p className="mt-1 type-caption text-text-secondary">扫描版或复杂版面教材请先完成外部解析，再导入输出包。</p>
                      <button type="button" disabled={uploading} onClick={() => setImportMode('bundle')} className="mt-2 text-xs font-medium text-accent hover:underline">转到 MinerU 输出包</button>
                    </div>
                  ) : (
                    <p className="type-caption text-[var(--success)]">MinerU {mineru.mode === 'api' ? 'API' : 'CLI'} 可用。</p>
                  )}
                </div>
              </div>
              <div className="flex items-start gap-2 rounded-lg border border-border bg-bg-primary p-3 text-sm text-text-primary">
                <input id="pdf-extract-concepts" type="checkbox" checked={extractConcepts} onChange={(e) => setExtractConcepts(e.target.checked)} className="mt-0.5 accent-accent" />
                <label htmlFor="pdf-extract-concepts">{'\u5bfc\u5165\u540e\u63d0\u53d6\u6559\u6750\u6982\u5ff5\u7d22\u5f15'}</label>
                <OptionHelp
                  title={'\u6559\u6750\u6982\u5ff5\u7d22\u5f15'}
                  description={'\u6559\u6750\u539f\u6587\u548c\u68c0\u7d22\u7d22\u5f15\u4f1a\u5148\u8fdb\u5165\u53ef\u7528\u72b6\u6001\uff1b\u968f\u540e\u5f02\u6b65\u628a\u7b5b\u9009\u540e\u7684\u6559\u6750\u7247\u6bb5\u53d1\u9001\u7ed9\u5df2\u914d\u7f6e\u7684\u5916\u90e8 LLM\uff0c\u7528\u4e8e\u5efa\u7acb\u6982\u5ff5\u3001\u5173\u7cfb\u548c\u51fa\u73b0\u4f4d\u7f6e\u3002\u8fc7\u7a0b\u53ef\u80fd\u8f83\u957f\uff0c\u4e0d\u963b\u585e\u6559\u6750\u95ee\u7b54\u3002'}
                />
              </div>
            </div>
            </div>
          </section>
        ) : (
          <section>
            <h3 className="mb-3 text-[18px] font-semibold text-text-primary">2. 选择已解析文件</h3>
            <div className="app-panel grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div>
              <h3 className="text-[16px] font-semibold text-text-primary">导入已解析结果</h3>
              <p className="type-body mt-2 max-w-2xl text-text-secondary">输出包应包含 Markdown、content_list 或 middle JSON，以及引用的图片资源。系统只整理章节并建立本地索引，不会再次执行 OCR。</p>
              <StatusBanner kind="info" title="适用于外部 MinerU 或 GPU 解析结果" description="请确认 zip 内保留原有目录结构。" />
            </div>
            <div className="space-y-3">
              <button type="button" disabled={uploading} onClick={() => outputInputRef.current?.click()} className="app-secondary-button min-h-[72px] w-full"><Upload className="h-4 w-4" />{outputFile ? outputFile.name : '选择输出 zip'}</button>
              <input ref={outputInputRef} type="file" accept=".zip,application/zip" onChange={handleOutputFileChange} className="hidden" />
              <label className="block"><span className="mb-1.5 block type-caption text-text-secondary">所属科目</span><ScopeSelector subject={subject} onSubjectChange={setSubject} bookMode="hidden" size="form" label="所属科目" placeholder="未分类（可选择科目）" fullWidth width="wide" /></label>
              <div className="flex items-start gap-2 rounded-lg border border-border bg-bg-primary p-3 text-sm text-text-primary">
                <input id="bundle-extract-concepts" type="checkbox" checked={extractConcepts} onChange={(e) => setExtractConcepts(e.target.checked)} className="mt-0.5 accent-accent" />
                <label htmlFor="bundle-extract-concepts">{'\u5bfc\u5165\u540e\u63d0\u53d6\u6559\u6750\u6982\u5ff5\u7d22\u5f15'}</label>
                <OptionHelp
                  title={'\u6559\u6750\u6982\u5ff5\u7d22\u5f15'}
                  description={'\u6559\u6750\u539f\u6587\u548c\u68c0\u7d22\u7d22\u5f15\u4f1a\u5148\u8fdb\u5165\u53ef\u7528\u72b6\u6001\uff1b\u968f\u540e\u5f02\u6b65\u628a\u7b5b\u9009\u540e\u7684\u6559\u6750\u7247\u6bb5\u53d1\u9001\u7ed9\u5df2\u914d\u7f6e\u7684\u5916\u90e8 LLM\uff0c\u7528\u4e8e\u5efa\u7acb\u6982\u5ff5\u3001\u5173\u7cfb\u548c\u51fa\u73b0\u4f4d\u7f6e\u3002\u8fc7\u7a0b\u53ef\u80fd\u8f83\u957f\uff0c\u4e0d\u963b\u585e\u6559\u6750\u95ee\u7b54\u3002'}
                />
              </div>
            </div>
            </div>
          </section>
        )}

        {error && <ActionableIssue title="教材没有导入成功" impact="这本教材暂时不能用于回答；已有教材和当前学习范围不受影响。" actions={<><button type="button" onClick={() => setError('')} className="app-secondary-button">重新选择文件</button><button type="button" onClick={() => navigate('/books')} className="app-secondary-button">返回教材</button></>} details={error} />}
        {job && <>
          <TaskStatus
            title={job.status === 'cancelled' ? '教材导入已取消' : job.status === 'cancelling' ? '正在取消教材导入' : isDone ? `${job.book_name || '教材'}已可用于学习` : isFailed ? `${job.book_name || '教材'}没有准备完成` : `正在准备${job.book_name ? `《${job.book_name}》` : '教材'}`}
            detail={job.status === 'cancelling' ? '取消请求已收到，等待后台停止确认。' : job.status === 'cancelled' ? '本次导入已停止，可重新选择材料；已有教材仍保留。' : isDone ? `已整理 ${job.result?.chapter_count || 0} 章内容。现在可以设为当前学习范围并开始提问。` : isFailed ? '这本教材暂时不能用于回答。请查看详细信息后重试。' : '正在整理教材内容，完成后即可用于有来源的回答。'}
            progress={progress}
            state={isFailed ? 'error' : isDone ? 'success' : 'loading'}
          />
          {isDone && unparsedExerciseSections > 0 && <p role="status" className="type-caption text-text-secondary">结构检查发现 {unparsedExerciseSections} 个习题范围尚未识别出题目。教材正文已保留用于检索，这些范围暂不能保证可抽题。</p>}
          <details className="border-b border-border px-4 py-3 type-caption text-text-secondary"><summary className="cursor-pointer">详细信息</summary><p className="mt-2">{stageLabels[job.stage] || job.stage} · {job.message}</p></details>
          {isDone && <ConceptExtractionStatus bookName={job.result?.name || job.book_name} jobId={job.result?.concept_job_id} />}
          {isDone && job.result?.concept_extraction_warning && <p role="status">概念抽取未能启动：{job.result.concept_extraction_warning}</p>}
          {isDone && <div className="flex justify-end"><button type="button" onClick={() => navigate('/books')} className="app-primary-button">查看教材状态</button></div>}
        </>}
      </div>
      </div>
      <WorkspaceActionBar status={job?.status === 'cancelling' ? '取消请求已收到，等待停止确认。' : uploading ? job ? '正在准备教材…' : '正在启动导入…' : error ? '导入未成功，请在上方查看详情并重试。' : importMode === 'pdf' ? !file ? '请先选择 PDF 文件。' : !subject.trim() ? '请选择所属科目。' : `准备导入 ${file.name}` : !outputFile ? '请先选择 zip 输出包。' : `准备导入 ${outputFile.name}`}>
        {job && ['queued', 'running', 'cancelling'].includes(job.status) && <button className="app-secondary-button" disabled={cancelBusy || job.status === 'cancelling'} onClick={() => void cancelImport()}>{cancelBusy || job.status === 'cancelling' ? '正在取消…' : '取消导入'}</button>}
        <button onClick={importMode === 'pdf' ? handleUpload : handleOutputUpload} disabled={uploading || (importMode === 'pdf' ? !file || !subject.trim() : !outputFile)} className="app-primary-button disabled:cursor-not-allowed disabled:opacity-50">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}{uploading ? job ? '导入进行中' : '正在启动' : importMode === 'pdf' ? '开始导入' : '导入输出包'}
        </button>
      </WorkspaceActionBar>
    </div>
  );
};

export default BooksPage;
