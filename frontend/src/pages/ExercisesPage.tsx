import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, BookOpen, CheckCircle2, ChevronDown, ChevronRight, ClipboardList, Loader2, Pause, Pencil, Play, RotateCcw, Save, Scissors, Search, Shuffle, Sparkles, Upload, X } from 'lucide-react';
import { apiFetch, del, get, post } from '../api/client';
import ChatMessage from '../components/ChatMessage';
import ScopeSelector from '../components/ScopeSelector';
import { useChatContext } from '../contexts/ChatContext';
import {
  ExerciseDetail,

  exerciseStatusText as statusText,
} from '../features/exercises/components/ExercisePresentation';
import { useVisibleList } from '../hooks/useVisibleList';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';
import { useExerciseAnswerJob } from '../features/exercises/hooks/useExerciseAnswerJob';
import { useExerciseImportCandidates } from '../features/exercises/hooks/useExerciseImportCandidates';
import { usePracticeSession } from '../features/exercises/hooks/usePracticeSession';
import type { BookInfo, ExerciseCandidate, ExerciseImportBatch, ExercisePracticeSession, ExerciseRecord, ExerciseStats } from '../types';

function titleOf(record: ExerciseRecord) {
  const raw = record.question_text || record.source || '未命名习题';
  const line = raw.replace(/\$\$[\s\S]*?\$\$/g, ' ').replace(/\$(?:\\.|[^$\\])*?\$/g, ' ').split('\n').map((item) => item.trim()).find(Boolean) || raw;
  return line.length > 56 ? `${line.slice(0, 56)}...` : line;
}

function candidateToExercise(candidate: ExerciseCandidate) {
  return {
    question_text: candidate.question_text,
    answer: candidate.answer || '',
    explanation: candidate.explanation || '',
    source: candidate.source || '',
    subject: candidate.subject || '',
    chapter: candidate.chapter || '',
    tags: candidate.tags.join(', '),
    question_type: candidate.suggested_type || '',
    difficulty: candidate.difficulty || 3,
    linked_concepts: candidate.linked_concepts || [],
    origin_type: 'import_candidate',
    origin_id: candidate.id,
    status: 'needs_review',
    notes: candidate.reasons.join('; '),
  };
}

const ExercisesPage: React.FC = () => {
  const { bookName, setBookName, subject, setSubject } = useChatContext();
  const [books, setBooks] = useState<BookInfo[]>([]);
  const [workspaceMode, setWorkspaceMode] = useState<'practice' | 'bank' | 'import'>('practice');
  const [targetName, setTargetName] = useState(bookName || '');
  const [targetSubject, setTargetSubject] = useState(subject || '\u6570\u5b66');
  const activeName = targetName.trim() || bookName || 'default';
  const bookQuery = activeName && activeName !== 'default' ? `?book_name=${encodeURIComponent(activeName)}` : '';


  const [records, setRecords] = useState<ExerciseRecord[]>([]);
  const [stats, setStats] = useState<ExerciseStats | null>(null);
  const [searchKw, setSearchKw] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [expandedId, setExpandedId] = useState('');
  const [practiceSession, setPracticeSession] = useState<ExercisePracticeSession | null>(null);
  const [singlePracticeActive, setSinglePracticeActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [answerFile, setAnswerFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importSource, setImportSource] = useState('');
  const [importChapter, setImportChapter] = useState('');
  const [textbookChapter, setTextbookChapter] = useState('');
  const [textbookPageStart, setTextbookPageStart] = useState('');
  const [textbookPageEnd, setTextbookPageEnd] = useState('');
  const [pdfOpen, setPdfOpen] = useState(false);
  const [pdfPage, setPdfPage] = useState('1');
  const sourcePdfPath = activeName && activeName !== 'default' ? `/api/books/${encodeURIComponent(activeName)}/source-pdf` : '';
  const sourcePdfAsset = useAuthenticatedBlobUrl(pdfOpen ? sourcePdfPath : '');
  const [textbookSourceMode, setTextbookSourceMode] = useState('exercise_sections');
  const [useLlmRepair, setUseLlmRepair] = useState(false);
  const [extractedPreview, setExtractedPreview] = useState('');
  const [lastImportBatch, setLastImportBatch] = useState<ExerciseImportBatch | null>(null);
  const searchKwRef = useRef(searchKw);
  const {
    candidates,
    selectedIds,
    candidateFilter,
    setCandidateFilter,
    editingCandidateId,
    setEditingCandidateId,
    importSummary,
    filteredCandidates,
    resetImportCandidates,
    updateCandidate,
    replaceCandidates,
    removeSelectedCandidates,
    selectAllCandidates,
    clearCandidateSelection,
    mergeSelectedCandidates,
    splitCandidate,
    toggleCandidate,
  } = useExerciseImportCandidates({ onMessage: setMessage });

  useEffect(() => {
    searchKwRef.current = searchKw;
  }, [searchKw]);


  const recordList = useVisibleList(records, 30, `${activeName}|${targetSubject}|${statusFilter}|${searchKw}`);
  const candidateList = useVisibleList(filteredCandidates, 20, `${activeName}|${importFile?.name || ''}|${textbookChapter}|${textbookPageStart}|${textbookPageEnd}|${importSummary.total}|${candidateFilter}`);

  const loadBooks = useCallback(async () => {
    try {
      const res = await get('/books/list');
      if (res?.success) setBooks(res.data || []);
    } catch {
      setBooks([]);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const overview = await post(`/exercises/overview${bookQuery}`, {
        search_kw: searchKwRef.current,
        subject: targetSubject,
        status: statusFilter,
        limit: 100,
      });
      if (overview?.success) {
        setRecords(overview.data?.records || []);
        setStats(overview.data?.stats || null);
        setPracticeSession(overview.data?.practice_session || null);
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [bookQuery, statusFilter, targetSubject]);

  const {
    practicePool,
    currentPractice,
    practiceAnswer,
    setPracticeAnswer,
    practiceSolutionOpen,
    setPracticeSolutionOpen,
    practiceMessage,
    showPracticeMessage,
    sessionLimit,
    setSessionLimit,
    sessionShuffle,
    setSessionShuffle,
    sessionBusy,
    startPracticeSession,
    changePracticeSessionStatus,
    selectPractice,
    submitPractice,

    clearDeletedPractice,
  } = usePracticeSession({
    records,
    setRecords,
    practiceSession,
    setPracticeSession,
    bookQuery,
    targetSubject,
    statusFilter,
    refreshOverview: load,
  });
  const startConfiguredPractice = () => {
    setSinglePracticeActive(false);
    void startPracticeSession();
  };

  const startSinglePractice = (record: ExerciseRecord) => {
    selectPractice(record);
    setSinglePracticeActive(true);
    setWorkspaceMode('practice');
  };

  const leaveSinglePractice = () => {
    setSinglePracticeActive(false);
    setPracticeAnswer('');
    setPracticeSolutionOpen(false);
  };

  const handleAnswerSaved = useCallback((saved: ExerciseRecord) => {
    setRecords((items) => items.map((item) => item.id === saved.id ? saved : item));
  }, []);
  const {
    answerDraft,
    setAnswerDraft,
    answerBusy,
    generateStandardAnswer,
    saveStandardAnswer,
  } = useExerciseAnswerJob({
    exercise: currentPractice,

    bookQuery,
    onMessage: showPracticeMessage,
    onRecordSaved: handleAnswerSaved,
  });

  useEffect(() => {
    loadBooks();
  }, [loadBooks]);

  useEffect(() => {
    if (bookName) setTargetName(bookName);
  }, [bookName]);

  useEffect(() => {
    if (subject) setTargetSubject(subject);
  }, [subject]);

  useEffect(() => {
    load();
  }, [load]);



  const resetImportPreview = () => {
    resetImportCandidates();
    setExtractedPreview('');
  };

  const updateTargetName = async (value: string) => {
    setTargetName(value);
    if (!value) {
      setBookName('');
      resetImportPreview();
      return;
    }
    if (books.some((book) => book.name === value)) {
      try {
        const res = await get(`/books/switch/${encodeURIComponent(value)}`);
        if (res?.success) {
          setBookName(res.data.name);
          if (res.data.subject) updateTargetSubject(res.data.subject);
        } else {
          setBookName(value);
        }
      } catch {
        setBookName(value);
      }
    }
    resetImportPreview();
    setPdfPage(textbookPageStart || '1');
    setPdfOpen(true);
  };

  const updateTargetSubject = (value: string) => {
    setTargetSubject(value);
    setSubject(value);
    resetImportPreview();
  };

  const analyzeImportFile = async () => {
    if (!importFile) {
      setMessage('请选择 Word 或 PDF 文件');
      return;
    }
    setImporting(true);
    setMessage('');
    try {
      const fd = new FormData();
      fd.append('file', importFile);
      if (answerFile) fd.append('answer_file', answerFile);
      fd.append('source', importSource || importFile.name);
      fd.append('subject', targetSubject || activeName);
      fd.append('chapter', importChapter);
      fd.append('limit', '200');
      fd.append('use_llm', useLlmRepair ? 'true' : 'false');
      fd.append('llm_max_items', '20');
      const res = await apiFetch(`/exercises/upload-analyze${bookQuery}`, { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || !data?.success) {
        setMessage(data?.message || `文件导入失败：${res.status}`);
        return;
      }
      const next = data.data || [];
      replaceCandidates(next);
      setExtractedPreview(data.extract?.text || '');
      const warnings = data.extract?.warnings?.length ? `；${data.extract.warnings.join('；')}` : '';
      const paired = answerFile ? `；答案匹配 ${data.summary?.paired_answers || 0}/${next.length}` : '';
      setMessage(`${data.message || `已分析 ${next.length} 道候选题`}${paired}${warnings}`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  };

  const analyzeTextbookExercises = async () => {
    if (!activeName || activeName === 'default') {
      setMessage('请先选择已导入教材');
      return;
    }
    setImporting(true);
    setMessage('');
    try {
      const res = await post(`/exercises/textbook-analyze${bookQuery}`, {
        book_name: activeName,
        subject: targetSubject || activeName,
        chapter: textbookChapter,
        page_start: textbookPageStart ? Number(textbookPageStart) : null,
        page_end: textbookPageEnd ? Number(textbookPageEnd) : null,
        source_mode: textbookSourceMode,
        limit: 200,
        use_llm: useLlmRepair,
        llm_max_items: 20,
      }, 60000);
      if (!res?.success) {
        const warnings = res?.extract?.warnings?.length ? `（${res.extract.warnings.join('；')}）` : '';
        setMessage(`${res?.message || '教材抽题失败'}${warnings}`);
        setExtractedPreview(res?.extract?.text || '');
        return;
      }
      const next = res.data || [];
      replaceCandidates(next);
      setExtractedPreview(res.extract?.text || '');
      const warnings = res.extract?.warnings?.length ? `（${res.extract.warnings.join('；')}）` : '';
      setMessage(`${res.message || `已从教材抽取 ${next.length} 道候选题`}${warnings}`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  };
  const importSelected = async () => {
    const selected = candidates.filter((item) => selectedIds.has(item.id));
    if (selected.length === 0) {
      setMessage('请至少选择一道候选题');
      return;
    }
    setImporting(true);
    try {
      const res = await post(`/exercises/batch-add${bookQuery}`, {
        exercises: selected.map(candidateToExercise),
        source_label: importSource || importFile?.name || `${activeName} 教材抽题`,
        allow_duplicates: false,
      });
      if (!res?.success) {
        setMessage(res?.message || '批量导入失败');
        return;
      }
      setMessage(res.message || `已导入 ${selected.length} 道候选题`);
      const batchRes = await get(`/exercises/import-batches${bookQuery ? `${bookQuery}&limit=1` : '?limit=1'}`);
      if (batchRes?.success) setLastImportBatch(batchRes.data?.[0] || null);
      removeSelectedCandidates();
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  };

  const rollbackLastImport = async () => {
    if (!lastImportBatch || lastImportBatch.status !== 'active') return;
    if (!window.confirm(`确定回滚本批次导入的 ${lastImportBatch.exercise_ids.length} 道习题吗？`)) return;
    const res = await post(`/exercises/import-batches/rollback${bookQuery}`, { batch_id: lastImportBatch.id });
    if (!res?.success) {
      setMessage(res?.message || '回滚失败');
      return;
    }
    setLastImportBatch(res.data);
    setMessage(res.message || '导入批次已回滚');
    await load();
  };

  const updateStatus = async (id: string, status: string) => {
    const res = await post(`/exercises/status${bookQuery}`, { id, status });
    if (!res?.success) {
      setMessage(res?.message || '状态更新失败');
      return;
    }
    setRecords((prev) => prev.map((item) => (item.id === id ? res.data : item)));
    await load();
  };

  const deleteExercise = async (id: string) => {
    if (!window.confirm('确定删除这道习题吗？')) return;
    try {
      const res = await del(`/exercises/${encodeURIComponent(id)}${bookQuery}`, 20000);
      if (!res?.success) {
        setMessage(res?.message || '删除习题失败');
        return;
      }
      setRecords((prev) => prev.filter((item) => item.id !== id));
      if (expandedId === id) setExpandedId('');
      clearDeletedPractice(id);
      setMessage(res.message || '已删除习题');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="flex h-full flex-col">
      <div className="app-page-header border-b border-border bg-bg-primary">
        <h2 className="app-page-title">习题工作区</h2>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border bg-bg-card p-0.5">
            {([['practice', '练习'], ['bank', '题库'], ['import', '导入']] as const).map(([mode, label]) => (
              <button key={mode} type="button" onClick={() => setWorkspaceMode(mode)} className={`rounded-md px-3 py-1.5 text-sm ${workspaceMode === mode ? 'bg-[var(--surface-black)] text-white' : 'text-text-secondary hover:text-text-primary'}`}>{label}</button>
            ))}
          </div>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 rounded-xl border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary hover:border-accent disabled:opacity-50">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} 刷新
        </button>
      </div>
      </div>
      <div className={`grid min-h-0 flex-1 grid-cols-1 overflow-hidden ${workspaceMode === 'import' ? 'lg:grid-cols-[380px_minmax(0,1fr)] 2xl:grid-cols-[400px_minmax(0,1fr)]' : ''}`}>
        <aside className={`${workspaceMode === 'import' ? 'block' : 'hidden'} overflow-y-auto border-b border-border bg-bg-secondary/95 p-4 lg:border-b-0 lg:border-r`}>
          <div className="space-y-4">
            <section className="space-y-3 rounded-xl border border-border bg-bg-card p-4">
              <div>
                <div className="text-sm font-medium text-text-primary">选择范围</div>

              </div>
              <ScopeSelector
                subject={targetSubject}
                bookName={books.some((book) => book.name === targetName) ? targetName : ''}
                books={books}
                suggestions={books.map((book) => book.subject || '').filter(Boolean)}
                onSubjectChange={updateTargetSubject}
                onBookChange={updateTargetName}
                fullWidth
                width="wide"
              />
            </section>

            <section className="space-y-3 rounded-xl border border-border bg-bg-card p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><ClipboardList className="h-4 w-4 text-accent" /> 从当前教材抽题</div>
              {sourcePdfPath && (
                <button type="button" onClick={() => { setPdfPage(textbookPageStart || '1'); setPdfOpen(true); }} className="flex w-full items-center justify-center gap-2 rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm hover:border-accent">
                  <BookOpen className="h-4 w-4 text-accent" /> 弹窗打开教材 PDF 并选择页码
                </button>
              )}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
                <input placeholder="章节名/章节序号，可留空" value={textbookChapter} onChange={(e) => setTextbookChapter(e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
                <select value={textbookSourceMode} onChange={(e) => setTextbookSourceMode(e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent">
                  <option value="exercise_sections">习题页优先</option>
                  <option value="examples">章节例题</option>
                  <option value="all_pages">整页文本</option>
                </select>
                <input type="number" min="1" placeholder="起始页" value={textbookPageStart} onChange={(e) => setTextbookPageStart(e.target.value)} onBlur={() => { if (textbookPageStart) { setPdfPage(textbookPageStart); setPdfOpen(true); } }} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
                <input type="number" min="1" placeholder="结束页" value={textbookPageEnd} onChange={(e) => setTextbookPageEnd(e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
              </div>
              <button onClick={analyzeTextbookExercises} disabled={importing || !activeName || activeName === 'default'} className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
                {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} 抽取教材候选题
              </button>
            </section>
            <section className="space-y-3 rounded-xl border border-border bg-bg-card p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-text-primary"><Sparkles className="h-4 w-4 text-accent" /> Word/PDF 导入</div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
                <input placeholder="来源，如 2025 模拟卷" value={importSource} onChange={(e) => setImportSource(e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
                <input placeholder="章节，可留空" value={importChapter} onChange={(e) => setImportChapter(e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
              </div>
              <button onClick={() => fileInputRef.current?.click()} className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-bg-primary px-3 py-4 text-sm text-text-primary hover:border-accent">
                <Upload className="h-4 w-4" /> {importFile ? importFile.name : '选择 Word/PDF 文件'}
              </button>
              <input ref={fileInputRef} type="file" accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => setImportFile(e.target.files?.[0] || null)} className="hidden" />
              <label className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-bg-primary px-3 py-3 text-sm text-text-primary hover:border-accent">
                <Upload className="h-4 w-4" /> {answerFile ? `答案：${answerFile.name}` : '可选：选择独立答案 Word/PDF'}
                <input type="file" accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => setAnswerFile(e.target.files?.[0] || null)} className="hidden" />
              </label>
              <label className="flex items-start gap-2 rounded-xl border border-border bg-bg-primary px-3 py-2 text-xs text-text-secondary">
                <input type="checkbox" checked={useLlmRepair} onChange={(e) => setUseLlmRepair(e.target.checked)} className="mt-0.5 h-4 w-4 flex-shrink-0 accent-accent" />
                <span className="min-w-0 leading-5">
                  <span className="block text-text-primary">低置信候选用文本 LLM 修复（默认 DeepSeek，不做 OCR）</span>
                  <span className="block">Word/可复制 PDF 先规则切题；开启后仅把低置信文本片段交给当前文本推理后端。扫描 PDF 请先走 OCR/MinerU/Kimi。</span>
                </span>
              </label>
              <button onClick={analyzeImportFile} disabled={importing || !importFile} className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50">
                {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} 分析文件
              </button>
              {extractedPreview && <div className="space-y-2">
                <div className="text-xs font-medium text-text-primary">导入原文对照</div>
                <pre className="max-h-60 whitespace-pre-wrap overflow-y-auto rounded border border-border bg-bg-secondary p-3 text-xs leading-5 text-text-secondary">{extractedPreview}</pre>
              </div>}
              {message && <div className="rounded border border-border bg-bg-primary px-3 py-2 text-xs text-text-secondary">{message}</div>}
            </section>

            {workspaceMode === 'import' && candidates.length > 0 && (
              <section className="space-y-3 rounded-xl border border-border bg-bg-card p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-text-primary">候选题确认</div>
                    <div className="mt-1 text-xs text-text-secondary">{importSummary.total} 道 · {importSummary.issues} 道异常 · {importSummary.duplicates} 道重复</div>
                  </div>
                  <button onClick={selectAllCandidates} className="rounded border border-border px-2.5 py-1 text-xs hover:border-accent">全选</button>
                </div>
                <button onClick={importSelected} disabled={importing || selectedIds.size === 0} className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"><CheckCircle2 className="h-4 w-4" /> 导入选中 {selectedIds.size}</button>
                <div className="grid grid-cols-2 gap-2">
                  <button onClick={mergeSelectedCandidates} disabled={selectedIds.size < 2} className="rounded-xl border border-border px-3 py-2 text-xs hover:border-accent disabled:opacity-50">合并选中</button>
                  <button onClick={clearCandidateSelection} disabled={selectedIds.size === 0} className="rounded-xl border border-border px-3 py-2 text-xs hover:border-accent disabled:opacity-50">取消选择</button>
                </div>
              </section>
            )}
                {lastImportBatch?.status === 'active' && <button onClick={rollbackLastImport} className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#e3c98f] bg-[#fff6df] px-3 py-2 text-xs text-[var(--warning)] hover:border-[var(--warning)]">
                  <RotateCcw className="h-3.5 w-3.5" /> 回滚最近导入（{lastImportBatch.exercise_ids.length} 题）
                </button>}
          </div>
        </aside>

        <main className="overflow-y-auto p-4 lg:p-6">
          <div className={`mx-auto w-full space-y-5 ${workspaceMode === 'practice' ? 'max-w-[1180px]' : ''}`}>
            {workspaceMode === 'import' && candidates.length === 0 && (
              <section className="app-panel px-6 py-8">
                <h3 className="type-section-title text-text-primary">导入流程</h3>
                <ol className="type-body mt-3 space-y-3 text-text-secondary">
                  <li><span className="font-medium text-text-primary">1. 选择范围</span>，确定题目归属的科目与教材。</li>
                  <li><span className="font-medium text-text-primary">2. 选择来源</span>，从教材页抽取，或导入 Word/PDF 题目。</li>
                  <li><span className="font-medium text-text-primary">3. 校对候选题</span>，确认题干、答案和重复项后再写入题库。</li>
                </ol>
                <p className="type-caption mt-5 border-t border-border pt-4 text-text-secondary">候选题会显示在这里，未经确认不会写入正式题库。</p>
              </section>
            )}
            <div className={`${workspaceMode === 'import' ? 'hidden' : 'flex'} flex-wrap items-center gap-x-5 gap-y-1 border-y border-border px-1 py-3 text-sm text-text-secondary`}>
              <span>总习题 <strong className="font-semibold text-text-primary">{stats?.total || 0}</strong></span>
              <span>需复习 <strong className="font-semibold text-[var(--warning-text)]">{stats?.by_status?.needs_review || 0}</strong></span>
              <span>已掌握 <strong className="font-semibold text-[var(--success-text)]">{stats?.by_status?.mastered || 0}</strong></span>
            </div>

            <section className={`${workspaceMode === 'practice' ? 'block' : 'hidden'} overflow-hidden border-y border-border bg-bg-card`}>
              <header className="border-b border-border px-5 py-3 sm:px-6">
                <h3 className="text-[16px] font-semibold text-text-primary">专注练习</h3>
              </header>

              {practiceSession && ['active', 'paused'].includes(practiceSession.status) ? (
                <div className="border-b border-border bg-[var(--accent-softer)] px-5 py-3 sm:px-6">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-sm font-semibold text-white">{Math.min(practiceSession.current_index + 1, practiceSession.summary.total)}</div>
                      <div>
                        <div className="text-sm font-medium text-text-primary">连续练习进行中</div>
                        <div className="mt-0.5 text-xs text-text-secondary">共 {practiceSession.summary.total} 题，已完成 {practiceSession.summary.answered} 题</div>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {practiceSession.status === 'active' ? <button onClick={() => changePracticeSessionStatus('pause')} disabled={sessionBusy} className="flex items-center gap-1 rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs"><Pause className="h-3.5 w-3.5" />暂停</button> : <button onClick={() => changePracticeSessionStatus('resume')} disabled={sessionBusy} className="flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-xs text-white"><Play className="h-3.5 w-3.5" />继续</button>}
                      <button onClick={() => changePracticeSessionStatus('abandon')} disabled={sessionBusy} className="rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs">结束本轮</button>
                    </div>
                  </div>
                  <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/75"><div className="h-full bg-accent transition-all" style={{ width: `${practiceSession.summary.total ? (practiceSession.summary.answered / practiceSession.summary.total) * 100 : 0}%` }} /></div>
                </div>
              ) : singlePracticeActive ? (
                <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3 sm:px-6">
                  <span className="text-sm font-medium text-text-primary">单题练习</span>
                  <button onClick={leaveSinglePractice} className="app-secondary-button">返回练习设置</button>
                </div>
              ) : (
                <div className="border-b border-border px-5 py-5 sm:px-6">
                  <h4 className="text-sm font-semibold text-text-primary">设置本轮练习</h4>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-sm text-text-secondary">题数<input type="number" min="1" max="200" value={sessionLimit} onChange={(e) => setSessionLimit(Math.max(1, Math.min(200, Number(e.target.value) || 1)))} className="h-9 w-16 rounded-lg border border-border bg-bg-card px-2 text-sm text-text-primary" /></label>
                    <button onClick={() => setSessionShuffle((value) => !value)} className={`flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm ${sessionShuffle ? 'border-accent bg-accent/10 text-accent' : 'border-border bg-bg-card text-text-primary'}`}><Shuffle className="h-3.5 w-3.5" />{sessionShuffle ? '随机顺序' : '优先复习'}</button>
                    <button onClick={startConfiguredPractice} disabled={sessionBusy || practicePool.length === 0} className="app-primary-button">{sessionBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}开始练习</button>
                  </div>
                  {practiceSession?.status === 'completed' && <p className="mt-3 text-xs text-text-secondary">上轮完成 {practiceSession.summary.answered} 题，平均自评 {practiceSession.summary.average_quality}</p>}
                </div>
              )}

              {((practiceSession && ['active', 'paused'].includes(practiceSession.status)) || singlePracticeActive) && currentPractice ? (
                <div>
                  <article className="border-b border-border px-5 py-5 sm:px-6 sm:py-6">
                    <div className="text-xs text-text-secondary">
                      {practiceSession ? <>第 {Math.min(practiceSession.current_index + 1, practiceSession.summary.total)} / {practiceSession.summary.total} 题</> : <>单题练习</>}
                      {currentPractice.chapter && <> · {currentPractice.chapter}</>}
                      {currentPractice.tags?.[0] && <> / {currentPractice.tags[0]}</>}
                      {' · '}练习 {currentPractice.practice_count || 0} 次
                    </div>
                    <div className="mt-4 min-w-0 text-[16px] leading-7">
                      <ChatMessage variant="document" role="assistant" content={currentPractice.question_text} linkedConcepts={currentPractice.linked_concepts || []} />
                    </div>
                  </article>

                  <section className="px-5 py-5 sm:px-6">
                    <h4 className="text-sm font-semibold text-text-primary">你的作答</h4>
                    <textarea value={practiceAnswer} onChange={(e) => setPracticeAnswer(e.target.value)} placeholder="输入思路、公式或关键步骤" className="mt-3 min-h-[112px] w-full resize-y rounded-lg border border-border bg-bg-primary px-4 py-3 text-sm leading-6 text-text-primary outline-none transition-colors focus:border-accent focus:bg-bg-card" />
                    <div className="mt-3 flex justify-end">
                      <button onClick={() => setPracticeSolutionOpen((open) => !open)} className={practiceSolutionOpen ? 'app-secondary-button' : 'app-primary-button'}>
                        {practiceSolutionOpen ? '收起解析' : '提交并查看解析'}
                      </button>
                    </div>

                    {practiceSolutionOpen && (
                      <div className="mt-5 grid gap-4 border-t border-border pt-5 lg:grid-cols-2">
                        <section className="min-w-0 rounded-xl border border-border bg-bg-secondary/55 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <h4 className="text-sm font-semibold text-text-primary">标准答案</h4>
                              <p className="mt-0.5 text-xs text-text-secondary">可编辑并保存到题库。</p>
                            </div>
                            <Sparkles className="h-4 w-4 text-accent" />
                          </div>
                          <textarea value={answerDraft} onChange={(e) => setAnswerDraft(e.target.value)} placeholder="暂无答案，可基于教材 RAG 生成草稿" className="mt-3 min-h-[180px] w-full resize-y rounded-lg border border-border bg-bg-card px-3 py-2.5 text-sm leading-6 text-text-primary outline-none focus:border-accent" />
                          <div className="mt-3 flex flex-wrap gap-2">
                            <button onClick={generateStandardAnswer} disabled={answerBusy} className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-3 py-1.5 text-xs hover:border-accent hover:text-accent disabled:opacity-50">
                              {answerBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} 基于教材 RAG 生成
                            </button>
                            <button onClick={saveStandardAnswer} disabled={answerBusy || !answerDraft.trim()} className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs text-white disabled:opacity-50">
                              <Save className="h-3.5 w-3.5" /> 保存答案
                            </button>
                          </div>
                        </section>
                        <section className="min-w-0 rounded-xl border border-border bg-bg-secondary/55 p-4">
                          <div className="flex items-center gap-2">
                            <BookOpen className="h-4 w-4 text-accent" />
                            <h4 className="text-sm font-semibold text-text-primary">解析</h4>
                          </div>
                          <div className="mt-3 min-h-[180px] rounded-lg border border-border bg-bg-card p-3">
                            {currentPractice.explanation ? <ChatMessage variant="document" role="assistant" content={currentPractice.explanation} linkedConcepts={currentPractice.linked_concepts || []} /> : <span className="text-sm text-text-secondary">暂无解析。生成标准答案后，可继续补充解题思路。</span>}
                          </div>
                        </section>
                      </div>
                    )}
                  </section>

                  {practiceSolutionOpen && <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-4 sm:px-6">
                    <div>
                      <div className="text-sm font-medium text-text-primary">核对后，你掌握得怎么样？</div>
                    </div>
                    <div className="grid min-w-[360px] grid-cols-3 gap-2 max-sm:min-w-0 max-sm:w-full">
                      <button onClick={() => submitPractice(1, true)} disabled={sessionBusy || practiceSession?.status === 'paused'} className="rounded-lg border border-[#e6b2a9] bg-[#fff1ed] px-3 py-2 text-xs font-medium text-[var(--danger)] hover:border-[var(--danger)] disabled:opacity-50">没掌握</button>
                      <button onClick={() => submitPractice(3)} disabled={sessionBusy || practiceSession?.status === 'paused'} className="rounded-lg border border-[#e3c98f] bg-[#fff6df] px-3 py-2 text-xs font-medium text-[var(--warning)] hover:border-[var(--warning)] disabled:opacity-50">基本理解</button>
                      <button onClick={() => submitPractice(5)} disabled={sessionBusy || practiceSession?.status === 'paused'} className="rounded-lg border border-[#c9d8bd] bg-[#eef5e8] px-3 py-2 text-xs font-medium text-[var(--success)] hover:border-[var(--success)] disabled:opacity-50">已掌握</button>
                    </div>
                  </footer>}
                  {practiceMessage && <div className="border-t border-border bg-bg-card px-5 py-3 text-xs text-text-secondary sm:px-6">{practiceMessage}</div>}
                </div>
              ) : practicePool.length === 0 ? (
                <div className="px-5 py-12 text-center sm:px-6">
                  <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-bg-secondary"><ClipboardList className="h-5 w-5 text-text-secondary" /></div>
                  <div className="mt-3 text-sm font-medium text-text-primary">暂无可练习习题</div>
                  <div className="mt-1 text-xs text-text-secondary">请先从 Word、PDF 或教材中导入题目。</div>
                </div>
              ) : null}
            </section>
            {workspaceMode === 'import' && candidates.length > 0 && (
              <section className="space-y-3 rounded-xl border border-border bg-bg-card p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-text-primary">待确认候选题</h3>
                  <span className="text-xs text-text-secondary">{selectedIds.size} / {candidates.length} 已选</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => setCandidateFilter('all')} className={`rounded-lg border px-3 py-1 text-xs ${candidateFilter === 'all' ? 'border-accent bg-accent/10 text-accent' : 'border-border'}`}>全部 {candidates.length}</button>
                  <button onClick={() => setCandidateFilter('issues')} className={`rounded-lg border px-3 py-1 text-xs ${candidateFilter === 'issues' ? 'border-accent bg-accent/10 text-accent' : 'border-border'}`}>异常 {importSummary.issues}</button>
                  <button onClick={() => setCandidateFilter('duplicates')} className={`rounded-lg border px-3 py-1 text-xs ${candidateFilter === 'duplicates' ? 'border-accent bg-accent/10 text-accent' : 'border-border'}`}>重复 {importSummary.duplicates}</button>
                </div>
                <div className="space-y-2">
                  {candidateList.visibleItems.map((candidate) => (
                    <article key={candidate.id} className={`rounded-xl border bg-bg-primary p-3 ${(candidate.validation_issues || []).length ? 'border-[#e3c98f]' : 'border-border'}`}>
                      <div className="flex items-start gap-3">
                        <input type="checkbox" checked={selectedIds.has(candidate.id)} onChange={() => toggleCandidate(candidate.id)} className="mt-1 h-4 w-4 accent-accent" />
                        <div className="min-w-0 flex-1 space-y-3">
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="rounded border border-border px-2 py-0.5 text-text-secondary">{candidate.suggested_type || '未定题型'}</span>
                            <span className="rounded border border-border px-2 py-0.5 text-text-secondary">难度 {candidate.difficulty}</span>
                            <span className={`rounded border px-2 py-0.5 ${candidate.needs_llm ? 'border-[#e3c98f] bg-[#fff6df] text-[var(--warning)]' : 'border-[#c9d8bd] bg-[#eef5e8] text-[var(--success)]'}`}>置信度 {Math.round(candidate.confidence * 100)}%</span>
                            <button onClick={() => setEditingCandidateId(editingCandidateId === candidate.id ? '' : candidate.id)} className="ml-auto flex items-center gap-1 rounded border border-border px-2 py-0.5 hover:border-accent"><Pencil className="h-3 w-3" />{editingCandidateId === candidate.id ? '收起' : '编辑'}</button>
                            <button onClick={() => splitCandidate(candidate)} className="flex items-center gap-1 rounded border border-border px-2 py-0.5 hover:border-accent"><Scissors className="h-3 w-3" />拆分</button>
                          </div>
                          {(candidate.validation_issues || []).length > 0 && <div className="flex flex-wrap gap-1.5">{candidate.validation_issues!.map((issue) => <span key={issue} className="flex items-center gap-1 rounded bg-[#fff6df] px-2 py-1 text-xs text-[var(--warning)]"><AlertTriangle className="h-3 w-3" />{issue}</span>)}</div>}
                          {candidate.duplicate_of && <div className="text-xs text-[var(--warning)]">重复于题库记录 {candidate.duplicate_of}，默认导入时会跳过。</div>}
                          {editingCandidateId === candidate.id ? (
                            <div className="space-y-2 rounded-lg border border-border bg-bg-secondary p-3">
                              <textarea value={candidate.question_text} onChange={(e) => updateCandidate(candidate.id, { question_text: e.target.value, duplicate_of: '' })} className="min-h-32 w-full rounded-lg border border-border bg-bg-primary p-2 text-sm" />
                              <div className="grid gap-2 sm:grid-cols-3">
                                <input value={candidate.suggested_type} onChange={(e) => updateCandidate(candidate.id, { suggested_type: e.target.value })} placeholder="题型" className="rounded-lg border border-border bg-bg-primary px-2 py-1.5 text-xs" />
                                <input type="number" min="1" max="5" value={candidate.difficulty} onChange={(e) => updateCandidate(candidate.id, { difficulty: Math.max(1, Math.min(5, Number(e.target.value) || 3)) })} className="rounded-lg border border-border bg-bg-primary px-2 py-1.5 text-xs" />
                                <input value={candidate.tags.join(', ')} onChange={(e) => updateCandidate(candidate.id, { tags: e.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} placeholder="知识点标签" className="rounded-lg border border-border bg-bg-primary px-2 py-1.5 text-xs" />
                              </div>
                              <textarea value={candidate.answer} onChange={(e) => updateCandidate(candidate.id, { answer: e.target.value })} placeholder="标准答案（可留空）" className="min-h-20 w-full rounded-lg border border-border bg-bg-primary p-2 text-xs" />
                              <textarea value={candidate.explanation} onChange={(e) => updateCandidate(candidate.id, { explanation: e.target.value })} placeholder="解析（可留空）" className="min-h-20 w-full rounded-lg border border-border bg-bg-primary p-2 text-xs" />
                              <div className="grid gap-2 sm:grid-cols-2">
                                <input value={candidate.source} onChange={(e) => updateCandidate(candidate.id, { source: e.target.value })} placeholder="来源" className="rounded-lg border border-border bg-bg-primary px-2 py-1.5 text-xs" />
                                <input value={candidate.chapter} onChange={(e) => updateCandidate(candidate.id, { chapter: e.target.value })} placeholder="章节" className="rounded-lg border border-border bg-bg-primary px-2 py-1.5 text-xs" />
                              </div>
                            </div>
                          ) : <p className="line-clamp-4 whitespace-pre-wrap text-sm text-text-primary">{candidate.question_text}</p>}
                          <div className="flex flex-wrap gap-2 text-xs text-text-secondary">
                            {(candidate.tags.length ? candidate.tags : ['未识别知识点']).map((tag) => <span key={tag} className="rounded bg-bg-secondary px-2 py-0.5">{tag}</span>)}
                          </div>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
                {candidateList.hasMore && (
                  <button onClick={candidateList.showMore} className="w-full rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm text-text-secondary hover:border-accent hover:text-text-primary">
                    加载更多候选题（已显示 {candidateList.visibleCount} / {candidateList.totalCount}）
                  </button>
                )}
              </section>
            )}

            <section className={`${workspaceMode === 'bank' ? 'block' : 'hidden'} rounded-xl border border-border bg-bg-card p-4`}>
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <input value={searchKw} onChange={(e) => setSearchKw(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') load(); }} placeholder="搜索题干/答案/解析/标签" className="min-w-[260px] flex-1 rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent" />
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-xl border border-border bg-bg-primary px-3 py-2 text-sm outline-none focus:border-accent">
                  <option value="">全部状态</option>
                  {Object.entries(statusText).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <button onClick={load} className="rounded-xl border border-border px-3 py-2 text-sm hover:border-accent">搜索</button>
              </div>

              <div className="space-y-3">
                {recordList.visibleItems.map((record) => {
                  const expanded = expandedId === record.id;
                  return (
                    <article key={record.id} className="rounded-xl border border-border bg-bg-primary p-4">
                      <button onClick={() => setExpandedId(expanded ? '' : record.id)} className="flex w-full items-start justify-between gap-3 text-left">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                            {expanded ? <ChevronDown className="h-4 w-4 text-accent" /> : <ChevronRight className="h-4 w-4 text-text-secondary" />}
                            <span className="truncate">{titleOf(record)}</span>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-3 text-xs text-text-secondary">
                            <span>{record.subject || targetSubject || activeName}</span>
                            {record.chapter && <span>{record.chapter}</span>}
                            <span>{record.tags.join(', ') || '无标签'}</span>
                            <span>{record.question_type || '未标题型'}</span>
                            <span>练习 {record.practice_count || 0} 次</span>
                          </div>
                        </div>
                        <span className="rounded border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent-hover">{statusText[record.status] || record.status}</span>
                      </button>
                      {expanded && <ExerciseDetail record={record} onStatus={(status) => updateStatus(record.id, status)} onPractice={() => startSinglePractice(record)} onDelete={() => deleteExercise(record.id)} />}
                    </article>
                  );
                })}
                {recordList.hasMore && (
                  <div className="flex justify-center pt-1">
                    <button onClick={recordList.showMore} className="rounded-xl border border-border bg-bg-primary px-4 py-2 text-sm text-text-secondary hover:border-accent hover:text-text-primary">
                      加载更多习题（已显示 {recordList.visibleCount} / {recordList.totalCount}）
                    </button>
                  </div>
                )}
                {records.length === 0 && <div className="py-12 text-center text-sm text-text-secondary"><ClipboardList className="mx-auto mb-2 h-6 w-6" />暂无习题，请先导入 Word/PDF</div>}
              </div>
            </section>
          </div>
        </main>
      {pdfOpen && sourcePdfPath && (
        <div className="app-overlay-enter fixed inset-0 z-[80] flex items-center justify-center bg-black/55 p-3 sm:p-6" role="dialog" aria-modal="true" aria-label="教材 PDF 选页">
          <div className="app-dialog-enter flex h-[64vh] w-[min(900px,92vw)] flex-col overflow-hidden rounded-2xl border border-border bg-bg-card shadow-2xl">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div><div className="text-sm font-semibold text-text-primary">{activeName} · PDF 选页</div><div className="text-xs text-text-secondary">输入 PDF 页码后预览；“用作起始页”会回填抽题范围。</div></div>
              <div className="flex items-center gap-2">
                <input type="number" min="1" value={pdfPage} onChange={(e) => setPdfPage(e.target.value)} className="w-24 rounded-lg border border-border bg-bg-primary px-2.5 py-1.5 text-sm outline-none focus:border-accent" />
                <button onClick={() => setPdfPage((value) => String(Math.max(1, Number(value || 1) - 1)))} className="rounded-lg border border-border px-2.5 py-1.5 text-xs hover:border-accent">上一页</button>
                <button onClick={() => setPdfPage((value) => String(Number(value || 1) + 1))} className="rounded-lg border border-border px-2.5 py-1.5 text-xs hover:border-accent">下一页</button>
                <button onClick={() => { const selectedPage = pdfPage || '1'; setTextbookPageStart(selectedPage); setTextbookPageEnd(selectedPage); setPdfOpen(false); }} className="rounded-lg bg-accent px-3 py-1.5 text-xs text-white">{"\u62bd\u53d6\u5f53\u524d\u9875"}</button>
                <button onClick={() => setPdfOpen(false)} aria-label="关闭 PDF" className="rounded-lg border border-border p-1.5 hover:border-accent"><X className="h-4 w-4" /></button>
              </div>
            </div>
            {sourcePdfAsset.loading && <div className="flex min-h-0 flex-1 items-center justify-center gap-2 text-sm text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" />正在安全加载教材 PDF...</div>}
            {!sourcePdfAsset.loading && sourcePdfAsset.error && <div className="m-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">PDF 加载失败：{sourcePdfAsset.error}</div>}
            {sourcePdfAsset.url && <iframe key={sourcePdfAsset.url + '#page=' + (pdfPage || '1')} title={"\u6559\u6750 PDF \u9884\u89c8"} src={sourcePdfAsset.url + '#page=' + Math.max(1, Number(pdfPage || 1))} className="min-h-0 flex-1 bg-white" />}
          </div>
        </div>
      )}
      </div>
    </div>
  );
};

export default ExercisesPage;
