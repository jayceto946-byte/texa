import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { BookMarked, CheckCircle2, Circle, ExternalLink, FolderOpen, Loader2, RefreshCw, Square, Trash2, X } from 'lucide-react';
import { del, get, post } from '../api/client';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';

type BookOption = { name: string };
type HighlightScopeStatus = {
  highlight_status?: string;
  generated_at?: string;
  message?: string;
  html_url?: string;
  html_path?: string;
  markdown_path?: string;
  storage_dir?: string;
};
type ChapterSectionOption = HighlightScopeStatus & { id: string; title: string; page?: number; end_page?: number; is_auxiliary?: boolean };
type ChapterOption = HighlightScopeStatus & { id: string; title: string; page?: number; end_page?: number; subsections?: ChapterSectionOption[] };
type HighlightJob = {
  id: string;
  status: string;
  stage: string;
  progress: number;
  message: string;
  book_name?: string;
  chapter_id?: string;
  section_id?: string;
  result?: { book_name?: string; chapter_id?: string; chapter_title?: string; section_id?: string; scope_id?: string; scope_type?: string; scope_title?: string; html_url?: string } | null;
};
type ActiveJobTarget = { bookName: string; chapterId: string; sectionId: string; title: string };
type ProgressState = { status: string; message: string; progress?: number; target?: ActiveJobTarget };
type CompletionNotice = { title: string; url: string; bookName: string; chapterId: string; sectionId: string };

type HighlightRepositoryDialogProps = {
  open: boolean;
  books: BookOption[];
  currentBookName: string;
  onClose: () => void;
};

const terminalJobStatuses = new Set(['completed', 'failed', 'cancelled', 'interrupted']);
const runningJobStatuses = new Set(['queued', 'running', 'cancelling']);

const isGenerated = (item?: HighlightScopeStatus | null) => item?.highlight_status === 'succeeded';
const isOpenable = (item?: HighlightScopeStatus | null) => item?.highlight_status === 'succeeded' || item?.highlight_status === 'stale' || Boolean(item?.html_url);

const statusLabel = (item?: HighlightScopeStatus | null) => {
  const status = item?.highlight_status || 'not_generated';
  if (status === 'succeeded') return '已生成';
  if (status === 'stale') return '需要更新';
  if (status === 'running' || status === 'queued' || status === 'cancelling') return '生成中';
  if (status === 'failed') return '失败';
  if (status === 'cancelled' || status === 'interrupted') return '已终止';
  return '未生成';
};

const statusClass = (item?: HighlightScopeStatus | null) => {
  const status = item?.highlight_status || 'not_generated';
  if (status === 'succeeded') return 'status-success';
  if (status === 'stale') return 'status-warning';
  if (status === 'running' || status === 'queued' || status === 'cancelling') return 'border-accent/30 bg-[var(--accent-softer)] text-accent';
  if (status === 'failed') return 'border-red-200 bg-red-50 text-[var(--danger)]';
  return 'border-border bg-bg-card text-text-secondary';
};

const StatusIcon = ({ item }: { item?: HighlightScopeStatus | null }) => {
  const status = item?.highlight_status || 'not_generated';
  if (status === 'succeeded') return <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />;
  if (status === 'stale') return <RefreshCw className="h-4 w-4 text-[var(--warning)]" />;
  if (status === 'running' || status === 'queued' || status === 'cancelling') return <Loader2 className="h-4 w-4 animate-spin text-accent" />;
  return <Circle className="h-4 w-4 text-text-secondary/55" />;
};

const highlightQueryFor = (sectionId: string, force = false) => {
  const params = new URLSearchParams();
  if (sectionId && sectionId !== 'all') params.set('section_id', sectionId);
  if (force) params.set('force', 'true');
  const query = params.toString();
  return query ? `?${query}` : '';
};

const highlightAppUrlFor = (bookName: string, chapterId: string, sectionId: string) => {
  const params = new URLSearchParams({ book_name: bookName, chapter_id: chapterId });
  if (sectionId && sectionId !== 'all') params.set('section_id', sectionId);
  return `/highlights?${params.toString()}`;
};

function openPreview(url: string) {
  if (url.startsWith('/highlights')) {
    window.history.pushState({}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
    return;
  }
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) window.location.href = url;
}

const sameScope = (target: ActiveJobTarget | undefined, bookName: string, chapterId: string, sectionId: string) => (
  Boolean(target)
  && target?.bookName === bookName
  && target?.chapterId === chapterId
  && (target?.sectionId || 'all') === (sectionId || 'all')
);

const mergeRunningStatus = <T extends HighlightScopeStatus>(item: T | null | undefined, isRunning: boolean): T | null | undefined => {
  if (!item || !isRunning) return item;
  return { ...item, highlight_status: 'running' };
};

const HighlightRepositoryDialog: React.FC<HighlightRepositoryDialogProps> = ({ open, books, currentBookName, onClose }) => {
  const [highlightBookName, setHighlightBookName] = useState('');
  const [chapters, setChapters] = useState<ChapterOption[]>([]);
  const [selectedChapterId, setSelectedChapterId] = useState('');
  const [selectedSectionId, setSelectedSectionId] = useState('all');
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [viewUrl, setViewUrl] = useState('');
  const [staticHtmlUrl, setStaticHtmlUrl] = useState('');
  const [operation, setOperation] = useState<'start' | 'cancel' | 'delete' | ''>('');
  const [activeJobId, setActiveJobId] = useState('');
  const [activeJobTarget, setActiveJobTarget] = useState<ActiveJobTarget | undefined>();
  const [completionNotice, setCompletionNotice] = useState<CompletionNotice | null>(null);
  const staticHtmlAsset = useAuthenticatedBlobUrl(open ? staticHtmlUrl : '', 'html');

  useEffect(() => {
    if (!open) return;
    setHighlightBookName((prev) => currentBookName || prev || books[0]?.name || '');
  }, [books, currentBookName, open]);

  useEffect(() => {
    if (!open || !highlightBookName) {
      setChapters([]);
      setSelectedChapterId('');
      setSelectedSectionId('all');
      return;
    }

    let alive = true;
    const load = async () => {
      try {
        const res = await get(`/books/${encodeURIComponent(highlightBookName)}/chapter-highlights`, 30000);
        if (!alive) return;
        const nextChapters: ChapterOption[] = res?.data?.chapters || [];
        setChapters(nextChapters);
        setSelectedChapterId((prev) => (prev && nextChapters.some((chapter) => chapter.id === prev) ? prev : nextChapters[0]?.id || ''));
        setSelectedSectionId('all');
      } catch {
        if (!alive) return;
        setChapters([]);
        setSelectedChapterId('');
        setSelectedSectionId('all');
      }
    };
    load();
    return () => { alive = false; };
  }, [highlightBookName, open]);

  useEffect(() => {
    setSelectedSectionId('all');
  }, [selectedChapterId]);

  useEffect(() => {
    const targetBook = highlightBookName || currentBookName;
    const selectedIsActive = sameScope(activeJobTarget, targetBook, selectedChapterId, selectedSectionId);
    if (!selectedIsActive) {
      setViewUrl('');
      setStaticHtmlUrl('');
    }
  }, [activeJobTarget, currentBookName, highlightBookName, selectedChapterId, selectedSectionId]);

  const selectedChapter = chapters.find((chapter) => chapter.id === selectedChapterId) || null;
  const sections = useMemo(() => (selectedChapter?.subsections || []).filter((section) => !section.is_auxiliary), [selectedChapter]);
  const selectedSection = selectedSectionId === 'all' ? null : sections.find((section) => section.id === selectedSectionId) || null;
  const selectedScopeRaw = selectedSection || selectedChapter;
  const selectedScopeTitle = selectedSection?.title || (selectedChapter ? `${selectedChapter.title}（整章）` : '');
  const targetBookName = highlightBookName || currentBookName;
  const selectedScopeIsRunning = sameScope(activeJobTarget, targetBookName, selectedChapterId, selectedSectionId) && runningJobStatuses.has(progress?.status || '');
  const selectedScope = mergeRunningStatus(selectedScopeRaw, selectedScopeIsRunning);
  const selectedLocalPath = selectedScope?.html_path || selectedScope?.markdown_path || selectedScope?.storage_dir || '';
  const actionBusy = Boolean(operation);
  const showSelectedProgress = Boolean(progress?.target && sameScope(progress.target, targetBookName, selectedChapterId, selectedSectionId));

  const refreshChapters = useCallback(async (targetBook = highlightBookName) => {
    if (!targetBook) return;
    try {
      const res = await get(`/books/${encodeURIComponent(targetBook)}/chapter-highlights`, 30000);
      if (res?.success) setChapters(res.data?.chapters || []);
    } catch {
      // The existing local artifact may still be openable; keep the current view.
    }
  }, [highlightBookName]);

  useEffect(() => {
    if (!activeJobId) return;
    let alive = true;
    let timer: number | null = null;
    let consecutiveFailures = 0;

    const poll = async () => {
      try {
        const res = await get(`/books/chapter-highlight-jobs/${activeJobId}`, 60000);
        if (!alive) return;
        if (!res?.success) throw new Error(res?.message || '获取章节重点生成进度失败');
        const job: HighlightJob = res.data;
        consecutiveFailures = 0;
        const target = activeJobTarget || {
          bookName: job.book_name || highlightBookName || currentBookName,
          chapterId: job.chapter_id || selectedChapterId,
          sectionId: job.section_id || selectedSectionId || 'all',
          title: selectedScopeTitle || '章节重点',
        };
        setProgress({
          status: job.status,
          message: job.message || '正在生成章节重点',
          progress: typeof job.progress === 'number' ? job.progress : undefined,
          target,
        });

        if (terminalJobStatuses.has(job.status)) {
          setActiveJobId('');
          setActiveJobTarget(undefined);
          void refreshChapters(target.bookName);
          if (job.status === 'completed') {
            const result = job.result || {};
            const resultBook = result.book_name || job.book_name || target.bookName;
            const resultChapter = result.chapter_id || job.chapter_id || target.chapterId;
            const resultSection = result.scope_id || result.section_id || job.section_id || target.sectionId || 'all';
            const noticeTitle = result.scope_title || target.title || '章节重点';
            if (resultBook && resultChapter) {
              const appUrl = highlightAppUrlFor(resultBook, resultChapter, resultSection);
              setViewUrl(appUrl);
              setStaticHtmlUrl(result.html_url || `/api/books/${encodeURIComponent(resultBook)}/chapter-highlights/${encodeURIComponent(resultChapter)}/html${highlightQueryFor(resultSection)}`);
              setCompletionNotice({ title: noticeTitle, url: appUrl, bookName: resultBook, chapterId: resultChapter, sectionId: resultSection });
              if (resultBook !== target.bookName) void refreshChapters(resultBook);
            }
          }
          return;
        }
      } catch (err) {
        if (!alive) return;
        consecutiveFailures += 1;
        if (consecutiveFailures >= 8) {
          setActiveJobId('');
          setActiveJobTarget(undefined);
          setProgress((prev) => ({ status: 'interrupted', message: '网络连接持续不可用，已停止轮询。网络恢复后可再次点击生成以继续。', progress: prev?.progress, target: prev?.target || activeJobTarget }));
          void refreshChapters(activeJobTarget?.bookName || highlightBookName || currentBookName);
          return;
        }
        setProgress((prev) => ({
          status: 'running',
          message: `进度刷新失败，稍后重试：${err instanceof Error ? err.message : String(err)}`,
          progress: prev?.progress,
          target: prev?.target || activeJobTarget,
        }));
      }
      timer = window.setTimeout(poll, consecutiveFailures ? Math.min(12000, 1500 * (2 ** consecutiveFailures)) : 1500);
    };

    timer = window.setTimeout(poll, 800);
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeJobId, activeJobTarget, currentBookName, highlightBookName, refreshChapters, selectedChapterId, selectedSectionId, selectedScopeTitle]);

  const startHighlightJob = async (chapterId = selectedChapterId, sectionId = selectedSectionId, force = false) => {
    if (actionBusy) return;
    const targetBook = highlightBookName || currentBookName;
    const chapter = chapters.find((item) => item.id === chapterId);
    const section = sectionId === 'all' ? null : chapter?.subsections?.find((item) => item.id === sectionId);
    if (!targetBook || !chapter) {
      setProgress({ status: 'failed', message: '请先选择教材和章节。' });
      return;
    }

    const target = { bookName: targetBook, chapterId, sectionId: sectionId || 'all', title: section?.title || `${chapter.title}（整章）` };
    setSelectedChapterId(chapterId);
    setSelectedSectionId(sectionId || 'all');
    setActiveJobTarget(target);
    setCompletionNotice(null);
    setViewUrl('');
    setStaticHtmlUrl('');
    setOperation('start');
    setProgress({ status: 'queued', message: force ? '正在启动重新生成任务...' : '正在启动生成任务...', progress: 0, target });

    try {
      const start = await post(`/books/${encodeURIComponent(targetBook)}/chapter-highlights/${encodeURIComponent(chapterId)}/jobs${highlightQueryFor(sectionId || 'all', force)}`, {}, 60000);
      if (!start?.success) throw new Error(start?.message || '启动章节重点生成失败');
      const jobId = start.job_id || start.data?.id;
      if (!jobId) throw new Error('后台未返回任务编号');
      setActiveJobId(jobId);
      setProgress({
        status: start.data?.status || 'queued',
        message: `${force ? '重新生成' : '生成'}任务已启动；可以关闭窗口、继续对话，完成后会提示你打开结果。${jobId ? ` 任务：${jobId}` : ''}`,
        progress: typeof start.data?.progress === 'number' ? start.data.progress : 0,
        target,
      });
      window.setTimeout(() => refreshChapters(targetBook), 1200);
    } catch (err) {
      setActiveJobId('');
      setActiveJobTarget(undefined);
      setProgress({ status: 'failed', message: `启动失败：${err instanceof Error ? err.message : String(err)}`, target });
      void refreshChapters(targetBook);
    } finally {
      setOperation('');
    }
  };

  const cancelHighlightJob = async () => {
    if (!activeJobId || operation) return;
    const jobId = activeJobId;
    setOperation('cancel');
    setProgress((prev) => ({
      status: 'cancelling',
      message: '正在终止章节重点生成...',
      progress: prev?.progress,
      target: prev?.target || activeJobTarget,
    }));
    try {
      const res = await post(`/jobs/${encodeURIComponent(jobId)}/cancel`, {}, 30000);
      if (!res?.success) throw new Error(res?.message || '终止生成失败');
    } catch (err) {
      setProgress((prev) => ({
        status: 'running',
        message: `终止请求失败：${err instanceof Error ? err.message : String(err)}`,
        progress: prev?.progress,
        target: prev?.target || activeJobTarget,
      }));
    } finally {
      setOperation('');
    }
  };

  const openSelectedHighlight = async (chapterId = selectedChapterId, sectionId = selectedSectionId) => {
    const targetBook = highlightBookName || currentBookName;
    const chapter = chapters.find((item) => item.id === chapterId);
    if (!targetBook || !chapter) {
      setProgress({ status: 'failed', message: '请先选择教材和章节。' });
      return;
    }
    const scope = sectionId === 'all' ? chapter : sections.find((section) => section.id === sectionId) || chapter;
    if (!isOpenable(scope)) {
      await startHighlightJob(chapterId, sectionId, false);
      return;
    }
    const appUrl = highlightAppUrlFor(targetBook, chapterId, sectionId || 'all');
    const fallbackHtmlUrl = `/api/books/${encodeURIComponent(targetBook)}/chapter-highlights/${encodeURIComponent(chapterId)}/html${highlightQueryFor(sectionId || 'all')}`;
    setViewUrl(appUrl);
    setStaticHtmlUrl(scope.html_url || fallbackHtmlUrl);
    setProgress({ status: 'completed', message: '已打开本地重点。', progress: 100, target: { bookName: targetBook, chapterId, sectionId: sectionId || 'all', title: scope.title || '章节重点' } });
    openPreview(appUrl);
    await refreshChapters(targetBook);
  };

  const deleteSelectedHighlight = async () => {
    if (actionBusy) return;
    const targetBook = highlightBookName || currentBookName;
    const chapter = chapters.find((item) => item.id === selectedChapterId);
    if (!targetBook || !chapter || !selectedScope) {
      setProgress({ status: 'failed', message: '请先选择要删除的重点范围。' });
      return;
    }

    setOperation('delete');
    setProgress({ status: 'running', message: '正在删除旧重点产物...', progress: 0, target: { bookName: targetBook, chapterId: selectedChapterId, sectionId: selectedSectionId || 'all', title: selectedScopeTitle } });
    try {
      const res = await del(`/books/${encodeURIComponent(targetBook)}/chapter-highlights/${encodeURIComponent(selectedChapterId)}${highlightQueryFor(selectedSectionId || 'all')}`, 30000);
      if (!res?.success) throw new Error(res?.message || '删除旧重点失败');
      setViewUrl('');
      setStaticHtmlUrl('');
      setProgress({ status: 'completed', message: res.message || '已删除旧重点，可重新生成。', progress: 100, target: { bookName: targetBook, chapterId: selectedChapterId, sectionId: selectedSectionId || 'all', title: selectedScopeTitle } });
      await refreshChapters(targetBook);
    } catch (err) {
      setProgress({ status: 'failed', message: `删除失败：${err instanceof Error ? err.message : String(err)}` });
    } finally {
      setOperation('');
    }
  };

  const openNotice = (notice: CompletionNotice) => {
    setHighlightBookName(notice.bookName);
    setSelectedChapterId(notice.chapterId);
    setSelectedSectionId(notice.sectionId || 'all');
    setCompletionNotice(null);
    openPreview(notice.url);
  };

  const dialog = open ? (
    <div className="app-overlay-enter fixed inset-0 z-[1200] flex items-center justify-center bg-black/25 p-2 sm:p-4 lg:p-6">
      <div role="dialog" aria-modal="true" aria-label="章节重点仓库" className="app-large-dialog-enter flex h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-none flex-col overflow-hidden rounded-lg border border-border bg-bg-card shadow-xl sm:h-[min(88dvh,780px)] lg:max-w-6xl">
        <div className="flex min-h-12 items-center justify-between border-b border-border px-3 py-2 sm:px-4 sm:py-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-text-primary"><BookMarked className="h-4 w-4 flex-shrink-0 text-accent" /><span className="truncate">章节重点仓库</span></div>
          <button type="button" onClick={onClose} className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-text-secondary hover:bg-bg-secondary hover:text-text-primary" title="关闭">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-rows-[minmax(170px,34dvh)_minmax(0,1fr)] lg:grid-cols-[280px_minmax(0,1fr)] lg:grid-rows-none">
          <aside className="flex min-h-0 flex-col border-b border-border bg-[var(--surface-subtle)] p-3 sm:p-4 lg:border-b-0 lg:border-r">
            <label className="text-xs font-medium text-text-secondary">
              教材
              <select value={highlightBookName} onChange={(e) => setHighlightBookName(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-border bg-bg-card px-3 text-sm text-text-primary outline-none focus:border-accent">
                {!books.length && <option value="">暂无教材</option>}
                {books.map((book) => <option key={book.name} value={book.name}>{book.name}</option>)}
              </select>
            </label>

            <div className="mt-3 flex items-center justify-between text-xs font-medium text-text-secondary sm:mt-4">
              <span>一级章节</span>
              <span>{chapters.filter(isGenerated).length}/{chapters.length}</span>
            </div>
            <div className="mt-2 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
              {chapters.length ? chapters.map((chapter) => {
                const chapterRunning = sameScope(activeJobTarget, targetBookName, chapter.id, 'all') && runningJobStatuses.has(progress?.status || '');
                const chapterItem = mergeRunningStatus(chapter, chapterRunning);
                return (
                  <button
                    key={chapter.id}
                    type="button"
                    onClick={() => setSelectedChapterId(chapter.id)}
                    className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${selectedChapterId === chapter.id ? 'border-accent/45 bg-[var(--accent-softer)] text-text-primary' : 'border-transparent text-text-secondary hover:border-border hover:bg-bg-card hover:text-text-primary'}`}
                  >
                    <span className="min-w-0 flex-1 truncate">{chapter.title}</span>
                    {chapterRunning && <span className="hidden text-[11px] text-accent sm:inline">生成中</span>}
                    <StatusIcon item={chapterItem} />
                  </button>
                );
              }) : <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-text-secondary">暂无可用章节</div>}
            </div>
          </aside>

          <main className="flex min-h-0 flex-col p-3 sm:p-4">
            {selectedChapter ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-3">
                  <div className="min-w-0">
                    <div className="truncate text-base font-semibold text-text-primary">{selectedChapter.title}</div>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-text-secondary">
                      <span>页码 {selectedChapter.page || '-'}{selectedChapter.end_page ? `-${selectedChapter.end_page}` : ''}</span>
                      <span>{sections.length} 个二级标题</span>
                    </div>
                  </div>
                  <span className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs ${statusClass(selectedScope)}`}>
                    <StatusIcon item={selectedScope} /> {statusLabel(selectedScope)}
                  </span>
                </div>

                <div className="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 sm:mt-4">
                  <ScopeRow
                    title="整章重点"
                    subtitle="按目录小节组织生成，适合整章复习"
                    item={mergeRunningStatus(selectedChapter, sameScope(activeJobTarget, targetBookName, selectedChapter.id, 'all') && runningJobStatuses.has(progress?.status || ''))}
                    active={selectedSectionId === 'all'}
                    loading={actionBusy}
                    onSelect={() => setSelectedSectionId('all')}
                    onOpen={() => openSelectedHighlight(selectedChapter.id, 'all')}
                    onGenerate={() => startHighlightJob(selectedChapter.id, 'all', false)}
                  />
                  {sections.map((section) => {
                    const sectionRunning = sameScope(activeJobTarget, targetBookName, selectedChapter.id, section.id) && runningJobStatuses.has(progress?.status || '');
                    return (
                      <ScopeRow
                        key={section.id}
                        title={section.title}
                        subtitle={`页码 ${section.page || '-'}${section.end_page ? `-${section.end_page}` : ''}`}
                        item={mergeRunningStatus(section, sectionRunning)}
                        active={selectedSectionId === section.id}
                        loading={actionBusy}
                        onSelect={() => setSelectedSectionId(section.id)}
                        onOpen={() => openSelectedHighlight(selectedChapter.id, section.id)}
                        onGenerate={() => startHighlightJob(selectedChapter.id, section.id, false)}
                      />
                    );
                  })}
                </div>

                <div className="mt-3 rounded-lg border border-border bg-[var(--surface-subtle)] px-3 py-2 text-xs leading-5 text-text-secondary">
                  <div>当前范围：{selectedScopeTitle}</div>
                  <div>保存方式：生成后写入本机 `data/progress/教材/chapter_highlights/...`，下次可直接打开。</div>
                  {selectedLocalPath && <div className="break-all">本地文件：{selectedLocalPath}</div>}
                </div>
              </>
            ) : (
              <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-border text-sm text-text-secondary">请选择教材和章节</div>
            )}
          </main>
        </div>

        {progress && showSelectedProgress && (
          <div className={`border-t px-3 py-3 text-xs sm:px-4 ${['failed', 'cancelled', 'interrupted'].includes(progress.status) ? 'border-red-200 bg-red-50 text-red-700' : 'border-border bg-[var(--accent-softer)] text-text-primary'}`}>
            <div className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate">{progress.message}</span>
              {typeof progress.progress === 'number' && <span className="flex-shrink-0 text-text-secondary">{progress.progress}%</span>}
            </div>
            {typeof progress.progress === 'number' && (
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-secondary">
                <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.max(0, Math.min(100, progress.progress))}%` }} />
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-3 sm:px-4">
          <div className="flex min-w-0 flex-wrap gap-2">
            {viewUrl && <button type="button" onClick={() => openPreview(viewUrl)} className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-bg-card px-3 py-2 text-xs font-medium text-accent hover:bg-[var(--accent-softer)]"><FolderOpen className="h-3.5 w-3.5" /> 打开应用内重点</button>}
            {staticHtmlUrl && <a href={staticHtmlAsset.url || undefined} target="_blank" rel="noreferrer" aria-disabled={!staticHtmlAsset.url} title={staticHtmlAsset.error || undefined} className={`inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 py-2 text-xs text-text-secondary hover:border-accent/40 hover:text-accent ${staticHtmlAsset.url ? '' : 'pointer-events-none opacity-55'}`}>{staticHtmlAsset.loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />} {staticHtmlAsset.error ? 'HTML 加载失败' : '静态 HTML'}</a>}
          </div>
          <div className="flex flex-1 flex-wrap justify-end gap-2 sm:flex-none">
            <button type="button" onClick={onClose} className="rounded-lg border border-border bg-bg-card px-3 py-2 text-xs text-text-secondary hover:text-text-primary">关闭</button>
            {selectedScopeIsRunning && (
              <button type="button" onClick={cancelHighlightJob} disabled={Boolean(operation)} className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-bg-card px-3 py-2 text-xs font-medium text-[var(--danger)] hover:bg-red-50 disabled:opacity-50">
                {operation === 'cancel' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
                {operation === 'cancel' ? '正在终止' : '终止生成'}
              </button>
            )}
            {isOpenable(selectedScope) && (
              <button type="button" onClick={deleteSelectedHighlight} disabled={actionBusy || !highlightBookName || !selectedChapterId} className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-bg-card px-3 py-2 text-xs font-medium text-[var(--danger)] hover:bg-red-50 disabled:opacity-50">
                <Trash2 className="h-3.5 w-3.5" /> 删除旧重点
              </button>
            )}
            <button type="button" onClick={() => startHighlightJob(selectedChapterId, selectedSectionId, isOpenable(selectedScope))} disabled={actionBusy || !highlightBookName || !selectedChapterId || selectedScopeIsRunning} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50">
              {operation === 'start' || selectedScopeIsRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookMarked className="h-3.5 w-3.5" />}
              {selectedScopeIsRunning ? '生成中' : isOpenable(selectedScope) ? '重新生成重点' : '生成重点'}
            </button>
            {isOpenable(selectedScope) && (
              <button type="button" onClick={() => openSelectedHighlight()} disabled={actionBusy || !highlightBookName || !selectedChapterId} className="inline-flex items-center gap-2 rounded-lg border border-accent/30 bg-bg-card px-3 py-2 text-xs font-medium text-accent hover:bg-[var(--accent-softer)] disabled:opacity-50">
                {operation ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderOpen className="h-3.5 w-3.5" />}
                {operation ? '处理中' : '打开重点'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  ) : null;

  const notice = completionNotice ? (
    <div className="app-toast-enter fixed bottom-4 right-4 z-[1300] w-[min(360px,calc(100vw-2rem))] rounded-lg border border-accent/25 bg-bg-card p-3 text-sm text-text-primary shadow-xl">
      <div className="font-medium">{completionNotice.title}重点已生成</div>
      <div className="mt-1 text-xs text-text-secondary">点击跳转到生成结果。</div>
      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={() => setCompletionNotice(null)} className="rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary">稍后</button>
        <button type="button" onClick={() => openNotice(completionNotice)} className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover">点击跳转</button>
      </div>
    </div>
  ) : null;

  return createPortal(<>{dialog}{notice}</>, document.body);
};

const ScopeRow = ({ title, subtitle, item, active, loading, onSelect, onOpen, onGenerate }: {
  title: string;
  subtitle: string;
  item?: HighlightScopeStatus | null;
  active: boolean;
  loading: boolean;
  onSelect: () => void;
  onOpen: () => void;
  onGenerate: () => void;
}) => {
  const running = runningJobStatuses.has(item?.highlight_status || '');
  return (
    <div className={`flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors sm:gap-3 ${active ? 'border-accent/45 bg-[var(--accent-softer)]' : 'border-border bg-bg-card hover:border-accent/35'}`}>
      <button type="button" onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        <StatusIcon item={item} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-text-primary">{title}</span>
          <span className="block truncate text-xs text-text-secondary">{subtitle}</span>
        </span>
      </button>
      <span className={`hidden rounded-md border px-2 py-0.5 text-[11px] sm:inline ${statusClass(item)}`}>{statusLabel(item)}</span>
      {isOpenable(item) ? (
        <button type="button" disabled={loading || running} onClick={onOpen} className="inline-flex flex-shrink-0 items-center gap-1 rounded-lg border border-accent/30 bg-bg-card px-2.5 py-1.5 text-xs text-accent hover:bg-[var(--accent-softer)] disabled:opacity-50">
          <FolderOpen className="h-3.5 w-3.5" /> 打开
        </button>
      ) : (
        <button type="button" disabled={loading || running} onClick={onGenerate} className="inline-flex flex-shrink-0 items-center gap-1 rounded-lg border border-border bg-bg-card px-2.5 py-1.5 text-xs text-text-secondary hover:border-accent/40 hover:text-accent disabled:opacity-50">
          {running || loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookMarked className="h-3.5 w-3.5" />} {running ? '生成中' : '生成重点'}
        </button>
      )}
    </div>
  );
};

export default HighlightRepositoryDialog;
