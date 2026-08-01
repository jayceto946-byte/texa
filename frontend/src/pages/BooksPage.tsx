import React, { useEffect, useRef, useState } from 'react';
import { Archive, FileText, Loader2, Upload } from 'lucide-react';
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

const BooksPage: React.FC = () => {
  const [importMode, setImportMode] = useState<'pdf' | 'bundle'>('pdf');
  const [file, setFile] = useState<File | null>(null);
  const [outputFile, setOutputFile] = useState<File | null>(null);
  const [tocPages, setTocPages] = useState('');
  const [subject, setSubject] = useState('');
  const [requireMineru, setRequireMineru] = useState(true);
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
    formData.append('require_mineru', String(requireMineru));
    formData.append('subject', subject);

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
        <section className="app-panel overflow-hidden">
          <div className="border-b border-border px-5 py-4">
            <h3 className="text-[18px] font-semibold leading-6 text-text-primary">选择导入方式</h3>
          </div>
          <div className="grid md:grid-cols-2">
            <button type="button" onClick={() => setImportMode('pdf')} className={`flex items-center gap-3 px-5 py-5 text-left md:border-r ${importMode === 'pdf' ? 'bg-[var(--accent-softer)]' : 'hover:bg-bg-secondary'}`}>
              <FileText className={`h-5 w-5 ${importMode === 'pdf' ? 'text-accent' : 'text-text-secondary'}`} />
              <span className="text-[16px] font-medium leading-6 text-text-primary">导入 PDF 教材</span>
            </button>
            <button type="button" onClick={() => setImportMode('bundle')} className={`flex items-center gap-3 border-t border-border px-5 py-5 text-left md:border-t-0 ${importMode === 'bundle' ? 'bg-[var(--accent-softer)]' : 'hover:bg-bg-secondary'}`}>
              <Archive className={`h-5 w-5 ${importMode === 'bundle' ? 'text-accent' : 'text-text-secondary'}`} />
              <span className="text-[16px] font-medium leading-6 text-text-primary">导入 MinerU 输出包</span>
            </button>
          </div>
        </section>

        {importMode === 'pdf' ? (
          <section className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
            <button type="button" onClick={() => inputRef.current?.click()} className="app-panel flex min-h-[280px] w-full flex-col items-center justify-center p-8 text-center hover:border-accent/60 hover:bg-[var(--accent-softer)]">
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
              <label className="flex items-start gap-2 rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-sm text-text-primary">
                <input type="checkbox" checked={requireMineru} onChange={(e) => setRequireMineru(e.target.checked)} className="mt-0.5 accent-accent" />
                <span><span className="block">扫描件必须完成高质量解析</span><span className="type-caption mt-0.5 block text-text-secondary">启用后不接受低质量文本降级结果。</span></span>
              </label>
              <button onClick={handleUpload} disabled={!file || uploading} className="app-primary-button w-full disabled:cursor-not-allowed disabled:opacity-50">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}{uploading ? '正在启动' : '开始导入'}
              </button>
            </div>
          </section>
        ) : (
          <section className="app-panel grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div>
              <h3 className="type-section-title text-text-primary">导入已解析结果</h3>
              <p className="type-body mt-2 max-w-2xl text-text-secondary">输出包应包含 Markdown、content_list 或 middle JSON，以及引用的图片资源。系统只整理章节并建立本地索引，不会再次执行 OCR。</p>
              <StatusBanner kind="info" title="适用于外部 MinerU 或 GPU 解析结果" description="请确认 zip 内保留原有目录结构。" />
            </div>
            <div className="space-y-3">
              <button type="button" onClick={() => outputInputRef.current?.click()} className="app-secondary-button min-h-[72px] w-full"><Upload className="h-4 w-4" />{outputFile ? outputFile.name : '选择输出 zip'}</button>
              <input ref={outputInputRef} type="file" accept=".zip,application/zip" onChange={handleOutputFileChange} className="hidden" />
              <button onClick={handleOutputUpload} disabled={!outputFile || uploading} className="app-primary-button w-full disabled:cursor-not-allowed disabled:opacity-50">{uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}{uploading ? '正在启动' : '导入输出包'}</button>
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
