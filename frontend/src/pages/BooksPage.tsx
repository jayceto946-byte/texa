import React, { useEffect, useRef, useState } from 'react';
import { Archive, FileText, HelpCircle, Loader2, Upload } from 'lucide-react';
import { apiFetch } from '../api/client';
import ScopeSelector from '../components/ScopeSelector';
import { StatusBanner, TaskStatus } from '../components/ui/AsyncState';

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
  } | null;
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
  const [importMode, setImportMode] = useState<'pdf' | 'bundle'>('pdf');
  const [file, setFile] = useState<File | null>(null);
  const [outputFile, setOutputFile] = useState<File | null>(null);
  const [tocPages, setTocPages] = useState('');
  const [subject, setSubject] = useState('');
  const [parseMethod, setParseMethod] = useState<'mineru' | 'local'>('mineru');
  const [extractConcepts, setExtractConcepts] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState('');
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
          if (data.data.status === 'completed') window.dispatchEvent(new Event('books:changed'));
        }
      } catch (err) {
        stopPolling();
        setUploading(false);
        setError(err instanceof Error ? err.message : String(err));
      }
    }, 1200);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = e.target.files?.[0] || null;
    setFile(nextFile);
    setJob(null);
    setError('');
  };

  const handleOutputFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextFile = e.target.files?.[0] || null;
    setOutputFile(nextFile);
    setJob(null);
    setError('');
  };

  const handleUpload = async () => {
    if (!file || uploading) return;
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
  const isFailed = ['failed', 'cancelled', 'interrupted'].includes(job?.status || '');

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-bg-primary">
      <header className="app-page-header border-b border-border bg-bg-card">
        <h2 className="app-page-title">教材导入</h2>
      </header>

      <div className="mx-auto w-full max-w-6xl space-y-5 p-6">
        <section className="border-y border-border py-4">
          <div className="mb-3 text-sm font-semibold text-text-primary">1. 选择来源</div>
          <div className="inline-flex rounded-lg border border-border bg-bg-card p-1">
            <button type="button" onClick={() => setImportMode('pdf')} className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${importMode === 'pdf' ? 'bg-[var(--accent-soft)] font-medium text-accent' : 'text-text-secondary hover:text-text-primary'}`}>
              <FileText className="h-4 w-4" />PDF 教材
            </button>
            <button type="button" onClick={() => setImportMode('bundle')} className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${importMode === 'bundle' ? 'bg-[var(--accent-soft)] font-medium text-accent' : 'text-text-secondary hover:text-text-primary'}`}>
              <Archive className="h-4 w-4" />MinerU 输出包
            </button>
          </div>
        </section>

        {importMode === 'pdf' ? (
          <section>
            <h3 className="mb-3 text-sm font-semibold text-text-primary">2. 选择文件并设置参数</h3>
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <button type="button" onClick={() => inputRef.current?.click()} className="app-panel flex min-h-[190px] w-full flex-col items-center justify-center p-8 text-center hover:border-accent/60 hover:bg-[var(--accent-softer)]">
              <Upload className="mb-4 h-9 w-9 text-accent" />
              <span className="type-section-title text-text-primary">{file ? file.name : '选择 PDF 教材'}</span>
              <span className="type-caption mt-2 text-text-secondary">点击选择本地 PDF 文件</span>
            </button>
            <input ref={inputRef} type="file" accept=".pdf,application/pdf" onChange={handleFileChange} className="hidden" />

            <div className="app-panel space-y-4 p-5">
              <h3 className="type-section-title text-text-primary">解析参数</h3>
              <label className="block">
                <span className="mb-1.5 block type-caption text-text-secondary">目录页码范围，可选</span>
                <input value={tocPages} onChange={(e) => setTocPages(e.target.value)} placeholder="如 1-5" className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
              </label>
              <label className="block">
                <span className="mb-1.5 block type-caption text-text-secondary">所属科目</span>
                <ScopeSelector subject={subject} onSubjectChange={setSubject} bookMode="hidden" label="所属科目" fullWidth width="wide" />
              </label>
              <div className="border-t border-border pt-3">
                <div className="mb-2 type-caption text-text-secondary">{'\u89e3\u6790\u65b9\u5f0f'}</div>
                <div className="grid gap-2">
                  <div className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${parseMethod === 'mineru' ? 'border-accent bg-[var(--accent-softer)] text-text-primary' : 'border-border bg-bg-primary text-text-secondary'}`}>
                    <input id="parse-mineru" name="parse-method" type="radio" checked={parseMethod === 'mineru'} onChange={() => setParseMethod('mineru')} className="mt-0.5 accent-accent" />
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
              {!file && <p className="type-caption text-text-secondary">请先选择 PDF 文件。</p>}
              {file && !subject.trim() && <p className="type-caption text-[var(--warning-text)]">请选择所属科目。</p>}
              <button onClick={handleUpload} disabled={!file || !subject.trim() || uploading} className="app-primary-button w-full disabled:cursor-not-allowed disabled:opacity-50">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}{uploading ? '正在启动' : '开始导入'}
              </button>
            </div>
            </div>
          </section>
        ) : (
          <section>
            <h3 className="mb-3 text-sm font-semibold text-text-primary">2. 选择已解析文件</h3>
            <div className="app-panel grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div>
              <h3 className="type-section-title text-text-primary">导入已解析结果</h3>
              <p className="type-body mt-2 max-w-2xl text-text-secondary">输出包应包含 Markdown、content_list 或 middle JSON，以及引用的图片资源。系统只整理章节并建立本地索引，不会再次执行 OCR。</p>
              <StatusBanner kind="info" title="适用于外部 MinerU 或 GPU 解析结果" description="请确认 zip 内保留原有目录结构。" />
            </div>
            <div className="space-y-3">
              <button type="button" onClick={() => outputInputRef.current?.click()} className="app-secondary-button min-h-[72px] w-full"><Upload className="h-4 w-4" />{outputFile ? outputFile.name : '选择输出 zip'}</button>
              <input ref={outputInputRef} type="file" accept=".zip,application/zip" onChange={handleOutputFileChange} className="hidden" />
              <div className="flex items-start gap-2 rounded-lg border border-border bg-bg-primary p-3 text-sm text-text-primary">
                <input id="bundle-extract-concepts" type="checkbox" checked={extractConcepts} onChange={(e) => setExtractConcepts(e.target.checked)} className="mt-0.5 accent-accent" />
                <label htmlFor="bundle-extract-concepts">{'\u5bfc\u5165\u540e\u63d0\u53d6\u6559\u6750\u6982\u5ff5\u7d22\u5f15'}</label>
                <OptionHelp
                  title={'\u6559\u6750\u6982\u5ff5\u7d22\u5f15'}
                  description={'\u6559\u6750\u539f\u6587\u548c\u68c0\u7d22\u7d22\u5f15\u4f1a\u5148\u8fdb\u5165\u53ef\u7528\u72b6\u6001\uff1b\u968f\u540e\u5f02\u6b65\u628a\u7b5b\u9009\u540e\u7684\u6559\u6750\u7247\u6bb5\u53d1\u9001\u7ed9\u5df2\u914d\u7f6e\u7684\u5916\u90e8 LLM\uff0c\u7528\u4e8e\u5efa\u7acb\u6982\u5ff5\u3001\u5173\u7cfb\u548c\u51fa\u73b0\u4f4d\u7f6e\u3002\u8fc7\u7a0b\u53ef\u80fd\u8f83\u957f\uff0c\u4e0d\u963b\u585e\u6559\u6750\u95ee\u7b54\u3002'}
                />
              </div>
              {!outputFile && <p className="type-caption text-text-secondary">请先选择 zip 输出包。</p>}
              <button onClick={handleOutputUpload} disabled={!outputFile || uploading} className="app-primary-button w-full disabled:cursor-not-allowed disabled:opacity-50">{uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}{uploading ? '正在启动' : '导入输出包'}</button>
            </div>
            </div>
          </section>
        )}

        {error && <StatusBanner kind="error" title="导入失败" description={error} />}
        {job && <TaskStatus title={job.book_name || '教材导入任务'} detail={`${stageLabels[job.stage] || job.stage} / ${job.message}`} progress={progress} state={isFailed ? 'error' : isDone ? 'success' : 'loading'} />}
      </div>
    </div>
  );
};

export default BooksPage;
