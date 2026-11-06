import Dialog from '../components/ui/Dialog';
import Selector from '../components/ui/Selector';
import { TexaTextbook, TexaExercises, TexaSearch, TexaClose } from '../components/icons';
import { getBookList } from '../features/books/bookList';
import ManualExerciseDialog from '../features/exercises/ManualExerciseDialog';
import { exercisePreview } from '../features/exercises/exercisePreview';
import '../features/exercises/exercises.css';
import { useUnsavedWorkGuard } from '../features/reading/useUnsavedWorkGuard';
import { HelpHint } from '../features/exercises/components/HelpHint';
import { ExerciseScopeFilters } from '../features/exercises/components/ExerciseScopeFilters';
import { exerciseSubjectMatches } from '../features/exercises/exerciseSource';
import { CandidateReviewWorkspace } from '../features/exercises/components/CandidateReviewWorkspace';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Loader2, Upload } from 'lucide-react';
import { apiFetch, get, post, ApiError } from '../api/client';
import { SimpleMarkdown } from '../components/chat/MarkdownRenderer';
import { ExerciseReader } from '../features/exercises/components/ExerciseReader';
import { PracticeAssessment } from '../features/exercises/components/PracticeAssessment';
import ScopeSelector from '../components/ScopeSelector';
import { SegmentedControl } from '../components/ui/SelectionControls';
import { useChatContext } from '../contexts/ChatContext';
import { ExerciseBankList } from '../features/exercises/components/ExerciseBankList';
import { ExerciseDeleteDialog } from '../features/exercises/components/ExerciseDeleteDialog';
import { useExerciseDeletion } from '../features/exercises/hooks/useExerciseDeletion';
import { useVisibleList } from '../hooks/useVisibleList';
import { useAuthenticatedBlobUrl } from '../hooks/useAuthenticatedBlobUrl';
import { useTextbookImportOutline } from '../features/exercises/hooks/useTextbookImportOutline';
import { useExerciseImportCandidates } from '../features/exercises/hooks/useExerciseImportCandidates';
import { usePracticeSession } from '../features/exercises/hooks/usePracticeSession';
import type { BookInfo, ExerciseCandidate, ExerciseImportBatch, ExercisePracticeSession, ExerciseRecord, ExerciseStats } from '../types';

function titleOf(record: ExerciseRecord) {
  const raw = record.question_text || record.source || '未命名习题';
  return exercisePreview(raw, 160, 160);
}

function candidateToExercise(candidate: ExerciseCandidate, sourceCategory = '', importConfirmed = false) {
  return {
    source_category: sourceCategory,
    ...(candidate.projection ? { candidate_context: { projection: candidate.projection, review: candidate.review || null, import_confirmed: importConfirmed } } : {}),
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
  const [manualOpen, setManualOpen] = useState(false);
  const [workspaceMode, setWorkspaceMode] = useState<'practice' | 'bank' | 'import'>('practice');
  const [targetName, setTargetName] = useState(bookName || '');
  const [targetSubject, setTargetSubject] = useState(subject || '\u6570\u5b66');
  const [importScopeSnapshot, setImportScopeSnapshot] = useState<{ book: string; subject: string } | null>(null);
  const [candidateSourceLabel, setCandidateSourceLabel] = useState('');
  const activeName = importScopeSnapshot?.book || targetName.trim() || bookName || 'default';
  const bookQuery = activeName && activeName !== 'default' ? `?book_name=${encodeURIComponent(activeName)}` : '';


  const [records, setRecords] = useState<ExerciseRecord[]>([]);
  const [stats, setStats] = useState<ExerciseStats | null>(null);
  const [searchKw, setSearchKw] = useState('');
  const statusFilter = '';
  const [filterChapter, setFilterChapter] = useState('');
  const [filterExamSource, setFilterExamSource] = useState('');
  const [filterAuthoredFocus, setFilterAuthoredFocus] = useState('');
  const [sourceFacets, setSourceFacets] = useState<{ exam_source: Record<string,number>; authored_focus: Record<string,number>; chapters?: Record<string,number> }>({ exam_source: {}, authored_focus: {} });
  const [practiceState, setPracticeState] = useState('');
  const [fileSourceCategory, setFileSourceCategory] = useState('exercise');
  const [candidateSourceCategory, setCandidateSourceCategory] = useState('');
  const [expandedId, setExpandedId] = useState('');
  const [practiceSession, setPracticeSession] = useState<ExercisePracticeSession | null>(null);
  const [singlePracticeActive, setSinglePracticeActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState('');
  const [candidateError, setCandidateError] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [filePageStart, setFilePageStart] = useState('');
  const [filePageEnd, setFilePageEnd] = useState('');
  const [answerFile, setAnswerFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const answerFileRef = useRef<HTMLInputElement>(null);
  const [importOptionsOpen, setImportOptionsOpen] = useState(false);
  const [importSource, setImportSource] = useState('');
  const [importChapter, setImportChapter] = useState('');
  const [textbookChapter, setTextbookChapter] = useState('');
  const [textbookPageStart, setTextbookPageStart] = useState('');
  const [textbookPageEnd, setTextbookPageEnd] = useState('');
  const [pdfOpen, setPdfOpen] = useState(false);
  const [pdfPage, setPdfPage] = useState('1');
  const textbookBook = books.find(book => book.name === activeName || book.book_id === activeName);
  const textbookSourceName = textbookBook?.name || '';
  const textbookOutline = useTextbookImportOutline(textbookSourceName);
  const hasSourcePdf = books.find((book) => book.name === activeName || book.book_id === activeName)?.has_pdf === true;
  const sourcePdfPath = hasSourcePdf ? `/api/books/${encodeURIComponent(activeName)}/source-pdf` : '';
  const sourcePdfAsset = useAuthenticatedBlobUrl(pdfOpen ? sourcePdfPath : '', 'pdf');
  const [textbookSourceMode, setTextbookSourceMode] = useState('exercise_sections');
  const [reviewPreparationOpen, setReviewPreparationOpen] = useState(false);
  const [sourceKind, setSourceKind] = useState<'textbook' | 'file'>('textbook');
  const [receipt, setReceipt] = useState<{ count: number; skipped: number; batchId: string } | null>(null);
  const [commitUnknown, setCommitUnknown] = useState(false);
  const importLock = useRef(false);
  const importScope = useRef('');
  useEffect(() => { importScope.current = `${activeName}|${targetSubject}`; }, [activeName, targetSubject]);
  const [loadError, setLoadError] = useState('');
  const loadRevision = useRef(0);
  const scopeRevision = useRef(0);
  const [inspectedBatches, setInspectedBatches] = useState<ExerciseImportBatch[]>([]);
  const [lastImportBatch, setLastImportBatch] = useState<ExerciseImportBatch | null>(null);
  const [lastImportedCandidateIds, setLastImportedCandidateIds] = useState<Set<string>>(new Set());
  const searchKwRef = useRef(searchKw);
  const candidateState = useExerciseImportCandidates({ onMessage: setCandidateError });
  const {
    candidates,
    resetImportCandidates,
    replaceCandidates,
    markImportedCandidates,
    restoreImportedCandidates,
    submittableCandidates,
  } = candidateState;

  useEffect(() => {
    searchKwRef.current = searchKw;
  }, [searchKw]);


  const recordList = useVisibleList(records, 30, `${activeName}|${targetSubject}|${filterChapter}|${filterExamSource}|${filterAuthoredFocus}|${practiceState}|${searchKw}`);
  const scopeChapters = Array.from(new Set([...textbookOutline.chapters.map(chapter => chapter.title), ...Object.keys(sourceFacets.chapters || {}), ...records.map(record => record.chapter || ''), filterChapter].filter(Boolean)));
  useEffect(() => {
    setTextbookChapter('');
    setTextbookPageStart('');
    setTextbookPageEnd('');
    setPdfOpen(false);
  }, [activeName]);
  useEffect(() => { setFilterExamSource(''); setFilterAuthoredFocus(''); }, [activeName, targetSubject, filterChapter]);



  const loadBooks = useCallback(async () => {
    try {
      const res = await getBookList();
      if (res?.success) setBooks(res.data || []);
    } catch {
      // Keep the successful snapshot when a read is superseded or unavailable.
    }
  }, []);

  const load = useCallback(async () => {
    const revision = ++loadRevision.current;
    setLoading(true);
    setLoadError('');
    try {
      const overview = await post(`/exercises/overview${bookQuery}`, {
        search_kw: searchKwRef.current,
        subject: targetSubject,
        status: statusFilter,
        chapter: filterChapter,
        exam_source: filterExamSource,
        authored_focus: filterAuthoredFocus,
        practice_state: practiceState,
        limit: 100,
      });
      if (revision !== loadRevision.current) return;
      if (overview?.success) {
        setRecords(overview.data?.records || []);
        setSourceFacets(overview.data?.source_facets || { exam_source: {}, authored_focus: {} });
        setStats(overview.data?.stats || null);
        setPracticeSession(overview.data?.practice_session || null);
      } else setLoadError(overview?.message || '暂时无法读取题库');
    } catch (e) {
      if (revision === loadRevision.current) setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      if (revision === loadRevision.current) setLoading(false);
    }
  }, [bookQuery, statusFilter, targetSubject, filterChapter, filterExamSource, filterAuthoredFocus, practiceState]);

  const {
    practicePool,
    currentPractice,
    practiceAnswer,
    setPracticeAnswer,
    setPracticeSolutionOpen,
    practiceMessage,
    candidateId,
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
    pendingDirectAnswer,

    clearDeletedPractice,
  } = usePracticeSession({
    records,
    setRecords,
    practiceSession,
    setPracticeSession,
    bookQuery,
    targetSubject,
    statusFilter,
    searchKw,
    chapter: filterChapter,
    examSource: filterExamSource,
    authoredFocus: filterAuthoredFocus,
    practiceState,
    singlePracticeActive,
    refreshOverview: load,
  });
  useEffect(() => {
    if (stats && stats.total > 0 && !statusFilter && !searchKw.trim())
      setSessionLimit(limit => Math.min(limit, stats.total));
  }, [stats, statusFilter, searchKw, setSessionLimit]);

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
    setPracticeSession(current => current?.current_exercise?.id === saved.id ? { ...current, current_exercise: saved } : current);
  }, []);

  useEffect(() => {
    void loadBooks();
    const refresh = () => { void loadBooks(); };
    window.addEventListener('books:changed', refresh);
    return () => window.removeEventListener('books:changed', refresh);
  }, [loadBooks]);

  useEffect(() => {
    if (bookName && !importScopeSnapshot) setTargetName(bookName);
  }, [bookName, importScopeSnapshot]);

  useEffect(() => {
    if (subject && !importScopeSnapshot) setTargetSubject(subject);
  }, [subject, importScopeSnapshot]);

  useEffect(() => {
    setRecords([]);
    setExpandedId('');
    load();
  }, [load]);



  useUnsavedWorkGuard(Boolean(candidates.length || importing || commitUnknown), '候选、编辑或未确认的入库结果仅在本页面内存中保留。确定退出 Texa 吗？');

  const resetImportPreview = () => {
    resetImportCandidates();
    setReceipt(null); setLastImportBatch(null); setInspectedBatches([]); setImportScopeSnapshot(null); setCandidateSourceLabel('');
  };

  const updateTargetName = async (value: string, selectedSubject?: string) => {
    if (value === targetName) return;
    if (importing || commitUnknown || (candidates.length && !window.confirm('更换范围将丢弃尚未入库的候选，继续吗？'))) return;
    const revision = ++scopeRevision.current;
    resetImportPreview();
    setTargetName(value);
    setFilterChapter('');
    const nextSubject = selectedSubject ?? books.find(book => book.name === value)?.subject;
    if (nextSubject !== undefined) { setTargetSubject(nextSubject); setSubject(nextSubject); }
    if (!value) {
      setBookName('');
      return;
    }
    if (books.some((book) => book.name === value)) {
      try {
        const res = await get(`/books/switch/${encodeURIComponent(value)}`);
        if (revision !== scopeRevision.current) return;
        if (res?.success) {
          setBookName(res.data.name);
        } else {
          setBookName(value);
        }
      } catch {
        if (revision === scopeRevision.current) setBookName(value);
      }
    }
    setPdfOpen(false);
  };

  const updateTargetSubject = (value: string) => {
    if (value === targetSubject) return;
    if (importing || commitUnknown || (candidates.length && !window.confirm('更换学科将丢弃尚未入库的候选，继续吗？'))) return;
    scopeRevision.current += 1;
    setTargetSubject(value);
    setSubject(value);
    setFilterChapter('');
    const selectedBook = books.find(book => book.name === targetName);
    if (selectedBook && !exerciseSubjectMatches(selectedBook.subject || '', value)) { setTargetName(''); setBookName(''); }
    resetImportPreview();
  };

  const analyzeImportFile = async () => {
    if (importLock.current || commitUnknown) return;
    if (candidates.length && !window.confirm('重新解析将替换当前候选及其编辑，继续吗？')) return;
    const requestedScope = importScope.current;
    if (!importFile) {
      setCandidateError('请选择 Word、PDF 或 MinerU 解析包');
      return;
    }
    importLock.current = true;
    setImportScopeSnapshot({ book: activeName, subject: targetSubject });
    setImporting(true);
    setReceipt(null);
    setMessage(''); setCandidateError('');
    try {
      const fd = new FormData();
      fd.append('file', importFile);
      if (answerFile) fd.append('answer_file', answerFile);
      fd.append('source', importSource || importFile.name);
      fd.append('subject', targetSubject || activeName);
      fd.append('chapter', importChapter);
      fd.append('limit', '500');
      fd.append('use_llm', 'false');
      fd.append('candidate_contract_version', '1');
      if (filePageStart) fd.append('page_start', filePageStart);
      if (filePageEnd) fd.append('page_end', filePageEnd);
      fd.append('llm_max_items', '20');
      const res = await apiFetch(`/exercises/upload-analyze${bookQuery}`, { method: 'POST', body: fd }, 5 * 60 * 1000);
      const data = await res.json();
      if (requestedScope !== importScope.current) return;
      if (!res.ok || !data?.success) {
        setCandidateError(data?.message || `文件导入失败：${res.status}`);
        return;
      }
      if (requestedScope !== importScope.current) return;
      const next = data.data || [];
      setCandidateSourceCategory(fileSourceCategory);
      if (data.candidate_contract_version !== 1 || !data.extract?.canonical_hash || !data.extract?.source_id || !Array.isArray(data.extract?.source_blocks) || next.some((c: ExerciseCandidate) => !c.projection || !c.issues || c.projection.canonical_hash !== data.extract.canonical_hash || c.projection.source_id !== data.extract.source_id)) {
        setCandidateError('文件解析结果不完整，请重新分析。'); return;
      }
      setCandidateSourceLabel(importSource || importFile?.name || '导入文件');
      replaceCandidates(next, data.extract);
      setReviewPreparationOpen(false);
      setCandidateError(next.length || data.extract?.source_coverage?.some((p: {status:string})=>p.status==='missing') ? '' : '未找到候选题，请调整范围后重试。');
      const paired = answerFile ? `；答案匹配 ${data.summary?.paired_answers || 0}/${next.length}` : '';
      setMessage(`${next.length ? data.message || `已分析 ${next.length} 道候选题` : '未找到候选题，请调整范围后重试。'}${paired}${data.summary?.llm_refined ? `；已辅助修复 ${data.summary.llm_refined} 道` : ''}`);
    } catch (e) {
      setCandidateError(e instanceof Error ? e.message : String(e));
    } finally {
      importLock.current = false;
      setImporting(false);
    }
  };

  const analyzeTextbookExercises = async () => {
    if (importLock.current || commitUnknown) return;
    if (candidates.length && !window.confirm('重新解析将替换当前候选及其编辑，继续吗？')) return;
    const requestedScope = importScope.current;
    if (!textbookSourceName) {
      setCandidateError('请先选择已导入教材');
      return;
    }
    importLock.current = true;
    setImportScopeSnapshot({ book: activeName, subject: targetSubject });
    setImporting(true);
    setReceipt(null);
    setMessage(''); setCandidateError('');
    try {
      const res = await post(`/exercises/textbook-analyze${bookQuery}`, {
        book_name: activeName,
        subject: targetSubject || activeName,
        chapter: textbookChapter,
        page_start: textbookPageStart ? Number(textbookPageStart) : null,
        page_end: textbookPageEnd ? Number(textbookPageEnd) : null,
        source_mode: textbookSourceMode,
        limit: 200,
        candidate_contract_version: 1,
        use_llm: false,
        llm_max_items: 20,
      }, 60000);
      if (requestedScope !== importScope.current) return;
      if (!res?.success) {
        const warnings = res?.extract?.warnings?.length ? `（${res.extract.warnings.join('；')}）` : '';
        setCandidateError(`${res?.message || '教材抽题失败'}${warnings}`);
        return;
      }
      if (requestedScope !== importScope.current) return;
      if (res.candidate_contract_version !== 1 || !res.extract?.canonical_hash || !Array.isArray(res.extract?.source_blocks) || res.data?.some((c: ExerciseCandidate) => !c.projection || !c.issues || c.projection.canonical_hash !== res.extract.canonical_hash)) {
        setCandidateError('教材解析结果不完整，请重新分析。');
        return;
      }
      const next = res.data || [];
      setCandidateSourceCategory(textbookSourceMode === 'examples' ? 'textbook_example' : 'exercise');
      setCandidateSourceLabel(`${activeName}${textbookChapter ? ` · ${textbookChapter}` : ''}`);
      replaceCandidates(next, res.extract);
      setReviewPreparationOpen(false);
      setCandidateError(next.length ? '' : '未找到候选题，请调整范围后重试。');
      setMessage(next.length ? res.message || `已从教材抽取 ${next.length} 道候选题` : '未找到候选题，请调整范围后重试。');
    } catch (e) {
      setCandidateError(e instanceof Error ? e.message : String(e));
    } finally {
      importLock.current = false;
      setImporting(false);
    }
  };
  const importSelected = async () => {
    if (importLock.current || commitUnknown) return;
    if (candidateState.confirmingId) return;
    const selected = submittableCandidates;
    if (!selected.length || selected.some(item => !item.question_text.trim())) return;
    importLock.current = true; setImporting(true); setCandidateError('');
    const fail = (text: string) => { setMessage(text); setCandidateError(text); };
    try {
      const v1 = Boolean(candidateState.sourceRegistry);
      const submittedIds = new Set(selected.map(c => c.id));
      const res = await post(`/exercises/${v1 ? 'candidates/batch-add' : 'batch-add'}${bookQuery}`, { ...(v1 ? { candidate_contract_version: 1 } : {}), exercises: selected.map(candidate => candidateToExercise(candidate, candidateSourceCategory, true)), source_label: candidateSourceLabel || `${activeName} 教材抽题`, allow_duplicates: true });
      if (!res?.success) { fail(res?.message || '入库被拒绝，候选仍保留'); return; }
      const acknowledged = [...(res.data || []).map((r: ExerciseRecord) => r.origin_id), ...(res.skipped || []).map((r: { origin_id: string }) => r.origin_id)];
      const receiptsValid = !v1 || (res.candidate_contract_version === 1 && Array.isArray(res.candidate_receipts) && res.candidate_receipts.length === res.count && res.data?.every((r: ExerciseRecord) => res.candidate_receipts.some((receipt: { exercise_id: string; origin_id: string }) => receipt.exercise_id === r.id && receipt.origin_id === r.origin_id)));
      if (!res.batch_id || !Array.isArray(res.data) || typeof res.count !== 'number' || res.count !== res.data.length || res.count + (res.skipped?.length || 0) !== selected.length || new Set(acknowledged).size !== selected.length || acknowledged.some(id => !submittedIds.has(id)) || !receiptsValid) {
        setCommitUnknown(true); fail('入库回执不完整，候选仍保留。请先核对题库与导入批次，勿重复提交。'); return;
      }
      setReceipt({ count: res.count, skipped: res.skipped?.length || 0, batchId: res.batch_id });
      setLastImportBatch({ id: res.batch_id, source_label: candidateSourceLabel || activeName, exercise_ids: res.data.map((r: ExerciseRecord) => r.id), skipped: res.skipped || [], candidate_receipts: res.candidate_receipts || [], skipped_candidate_receipts: res.skipped_candidate_receipts || [], created_at: '', status: 'active' });
      setLastImportedCandidateIds(submittedIds);
      markImportedCandidates(submittedIds); setMessage(''); await load();
    } catch (error) {
      if (error instanceof ApiError && [404, 409, 422].includes(error.status)) { fail(`导入未完成：${error.message}。候选和选择已保留。`); return; }
      setCommitUnknown(true); fail('连接中断，入库结果未知。候选仍保留；先核对题库与批次，不能自动重发。');
    } finally { importLock.current = false; setImporting(false); }
  };

  const saveStructureExample = async (candidate: ExerciseCandidate) => {
    if (importLock.current || commitUnknown) return;
    importLock.current = true; setImporting(true);
    try {
      const res = await post(`/exercises/structure-examples${bookQuery}`, candidateToExercise(candidate, candidateSourceCategory));
      setMessage(res.message || '分离样例保存失败，请保留当前候选后重试。');
    } catch (error) { setMessage(error instanceof Error ? error.message : String(error)); }
    finally { importLock.current = false; setImporting(false); }
  };

  const inspectImportBatches = async () => {
    try {
      const r = await get(`/exercises/import-batches${bookQuery}`);
      if (r?.success) setInspectedBatches(r.data || []);
      setMessage(r?.success ? '已读取最近导入记录。请对照题库确认本次题目是否已加入，避免重复导入。' : '导入记录读取失败');
    } catch { setMessage('批次读取失败，请检查连接'); }
  };

  const rollbackLastImport = async () => {
    if (!lastImportBatch || lastImportBatch.status !== 'active' || importLock.current) return;
    if (!window.confirm(`撤回本批次导入的 ${lastImportBatch.exercise_ids.length} 道题目？这些题目将从题库移除。`)) return;
    importLock.current = true; setImporting(true);
    try {
      const res = await post(`/exercises/import-batches/rollback${bookQuery}`, { batch_id: lastImportBatch.id });
      if (!res?.success || res.data?.id !== lastImportBatch.id || res.data?.status !== 'rolled_back') { setMessage(res?.message || '撤回尚未确认，请核对本次导入'); return; }
      setLastImportBatch(res.data);
      restoreImportedCandidates(lastImportedCandidateIds);
      setCandidateError('');
      setMessage('本批次导入已撤回'); await load();
    } catch { setMessage('撤回结果尚未确认，请核对本次导入，勿重复操作。'); }
    finally { importLock.current = false; setImporting(false); }
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

  const deletion = useExerciseDeletion({ bookQuery, onDeleted: async (ids, notice) => {
    setRecords(previous => previous.filter(record => !ids.has(record.id)));
    if (ids.has(expandedId)) setExpandedId('');
    ids.forEach(clearDeletedPractice);
    setMessage(notice);
    await load();
  } });
  return (
    <div className="management-workspace flex h-full flex-col">
      <ExerciseDeleteDialog records={deletion.pending} deleting={deletion.deleting} error={deletion.error} onCancel={deletion.cancel} onConfirm={() => void deletion.confirm()} />
      {manualOpen && <ManualExerciseDialog scope={activeName} subject={targetSubject} onClose={() => setManualOpen(false)} onSaved={() => { void load(); }} />}
      <div className="app-page-header border-b border-border bg-bg-primary">
        <h2 className="app-page-title shrink-0 whitespace-nowrap">练习</h2>
        <div className="window-drag-region" aria-hidden="true" />
        <div className="flex min-w-0 items-center gap-2">
          {(workspaceMode !== 'practice' || !stats?.total) && <button className="app-secondary-button shrink-0 whitespace-nowrap" onClick={() => setManualOpen(true)}>手动录入</button>}
          <SegmentedControl
            className="shrink-0 whitespace-nowrap"
            label="练习工作区视图"
            value={workspaceMode}
            options={[{ value: 'practice', label: '练习' }, { value: 'bank', label: '题库' }, { value: 'import', label: '导入' }]}
            onChange={setWorkspaceMode}
          />
        </div>
      </div>
      <div className="exercise-workspace-body">
        {workspaceMode === 'import' && receipt && !commitUnknown && <section className="exercise-import-receipt" role="status">
          <div><strong>{lastImportBatch?.status === 'rolled_back' ? '本次导入已撤回' : `已导入 ${receipt.count} 道题目`}</strong><p>{lastImportBatch?.status === 'rolled_back' ? '候选和选择已恢复，可直接修改或重新导入。' : '候选及编辑仍保留，已入库题目已取消勾选。'}</p></div>
          <div><button className="app-secondary-button" onClick={() => setWorkspaceMode('bank')}>查看题库</button>{lastImportBatch?.status === 'active' && <button className="app-secondary-button" disabled={importing} onClick={rollbackLastImport}>撤回本次导入（{lastImportBatch.exercise_ids.length} 题）</button>}<button className="app-ghost-button" onClick={() => { resetImportPreview(); setReceipt(null); }}>导入其他文件</button></div>
        </section>}
        {workspaceMode === 'import' && commitUnknown && <section className="exercise-receipt" role="status"><h1>入库结果待核对</h1><p>{message}</p>{inspectedBatches.map(batch => <p key={batch.id}>{batch.source_label || '最近导入'} · {batch.exercise_ids.length} 题</p>)}<div className="exercise-receipt-actions"><button className="app-primary-button" onClick={() => void inspectImportBatches()}>核对导入批次</button><button className="app-secondary-button" onClick={() => setWorkspaceMode('bank')}>查看题库</button></div></section>}

        <section hidden={workspaceMode !== 'import' || commitUnknown} className="exercise-import-panel">
          <div hidden={(Boolean(candidateState.sourceRegistry)||candidates.length>0) && !reviewPreparationOpen} className="exercise-import-setup">

            <h1>导入题目<HelpHint label="导入题目">选中题目后点击“导入选中”保存，待核对提示可随题保留。支持 Word、PDF 和 MinerU 解析包。</HelpHint>
            </h1>
            {candidates.length > 0 && <button className="app-secondary-button" onClick={() => setReviewPreparationOpen(false)}>继续校对 {candidates.length} 道候选</button>}
            <div className="exercise-source-tabs">
              <button aria-pressed={sourceKind === 'textbook'} onClick={() => setSourceKind('textbook')}>从教材抽取</button>
              <button aria-pressed={sourceKind === 'file'} onClick={() => setSourceKind('file')}>上传文件 / MinerU 包</button>
            </div>
            <fieldset className="exercise-import-fields" disabled={importing || commitUnknown}>
              {sourceKind === 'file' && <>
                <label className="exercise-field">题目来源<Selector ariaLabel="题目来源" value={fileSourceCategory} onChange={value => setFileSourceCategory(value)} options={[{ value: "exercise", label: "习题" }, { value: "exam", label: "真题" }, { value: "textbook_example", label: "教材例题" }]}/></label>
                <button className={`exercise-upload ${importFile ? 'has-file' : ''}`} onClick={() => fileInputRef.current?.click()}>
                  <Upload size={24} />
                  <strong>{importFile?.name || '选择 Word、PDF 或 MinerU 解析包'}</strong>
                </button>
                <input ref={fileInputRef} type="file" accept=".docx,.pdf,.zip" aria-label="题目文件" onChange={e => { setImportFile(e.target.files?.[0] || null); setFilePageStart(''); setFilePageEnd(''); }} hidden />
                <div className="exercise-two">
                  <label className="exercise-field"><span>起始物理页<HelpHint label="物理页范围">填写文件阅读器显示的页码，留空则导入全部页面。</HelpHint></span><input type="number" min="1" aria-label="文件起始物理页" placeholder="首页" disabled={importFile?.name.toLowerCase().endsWith('.docx')} value={filePageStart} onChange={e => setFilePageStart(e.target.value)} /></label>
                  <label className="exercise-field">结束物理页<input type="number" min="1" aria-label="文件结束物理页" placeholder="末页" disabled={importFile?.name.toLowerCase().endsWith('.docx')} value={filePageEnd} onChange={e => setFilePageEnd(e.target.value)} /></label>
                </div>

                <div className="exercise-answer-file"><span>独立答案<HelpHint label="独立答案">题目和答案分成两个文件时，可另外上传答案文件；同一文件已包含答案时无需选择。</HelpHint></span><input ref={answerFileRef} type="file" accept=".docx,.pdf,.zip" aria-label="独立答案文件" hidden onChange={e => setAnswerFile(e.target.files?.[0] || null)} /><button className="app-secondary-button" onClick={() => answerFileRef.current?.click()}>{answerFile?.name || '添加答案文件'}</button>{answerFile && <button className="app-secondary-button" onClick={() => { setAnswerFile(null); if (answerFileRef.current) answerFileRef.current.value = ''; }}>移除</button>}</div>
              </>}
              <div className="exercise-field">
                <span>{sourceKind === 'textbook' ? '选择教材' : '归属范围'}<HelpHint label="教材抽取">从已导入教材内容抽取，无需源 PDF；未选择教材时不能抽取。</HelpHint>
                </span>
                {sourceKind === 'textbook' ? <Selector ariaLabel="选择教材" value={textbookSourceName} onChange={value => {
                  const selected = books.find(book => book.name === value);
                  void updateTargetName(value, selected?.subject || '');
                }} options={[{ value: "", label: "请选择已导入教材" }, ...books.map((book) => ({ value: book.name, label: [book.displayName || book.name, book.subject ? ` · ${book.subject}` : ' · 未分类'].join('') }))]}/> : <ScopeSelector size="form" subject={targetSubject} bookName={textbookSourceName} books={books} suggestions={books.map(b => b.subject || '').filter(Boolean)} onSubjectChange={updateTargetSubject} onBookChange={updateTargetName} disabled={importing} fullWidth width="wide" />}
              </div>
              {sourceKind === 'textbook' ? <>
                {!textbookSourceName && <p className="exercise-feedback">请先选择已导入教材。<Link to="/books">前往教材库</Link>
                </p>}
                {textbookOutline.error && <p role="status" className="exercise-feedback">{textbookOutline.error}。请重新选择教材或刷新教材库。</p>}
                <div className="exercise-two">
                  <label className="exercise-field">教材章节{textbookOutline.chapters.length ? <Selector ariaLabel="教材章节" value={textbookChapter} onChange={value => setTextbookChapter(value)} options={[{ value: "", label: "全部章节（保留每题来源）" }, ...textbookOutline.chapters.flatMap((chapter) => [{ value: chapter.title, label: chapter.title, group: chapter.title }, ...(chapter.subsections || []).map((section) => ({ value: section.heading_block_id ? `heading:${section.heading_block_id}` : section.title, label: section.title, group: chapter.title }))])]}/> : <input aria-label="教材章节" placeholder="章节名或序号，可留空" value={textbookChapter} onChange={e => setTextbookChapter(e.target.value)} />}</label>
                  <label className="exercise-field">抽取内容<Selector ariaLabel="抽取内容" value={textbookSourceMode} onChange={value => setTextbookSourceMode(value)} options={[{ value: "exercise_sections", label: "习题页优先" }, { value: "examples", label: "章节例题" }]}/>
                  </label>
                </div>
              </> : null}
              <div className="exercise-import-options">
                <button className="app-secondary-button" aria-expanded={importOptionsOpen} onClick={() => setImportOptionsOpen(!importOptionsOpen)}>{sourceKind === 'textbook' ? '设置物理页范围' : '来源设置'}</button>
                {importOptionsOpen && <div className="exercise-import-extra">
                {sourceKind === 'textbook' && <>

                  <div className="exercise-two">
                    <label className="exercise-field">起始物理页<input type="number" min="1" aria-label="起始物理页" value={textbookPageStart} onChange={e => setTextbookPageStart(e.target.value)} />
                    </label>
                    <label className="exercise-field">结束物理页<input type="number" min="1" aria-label="结束物理页" value={textbookPageEnd} onChange={e => setTextbookPageEnd(e.target.value)} />
                    </label>
                  </div>{sourcePdfPath && <button className="app-secondary-button" onClick={() => { setPdfPage(textbookPageStart || '1'); setPdfOpen(true); }}>查看教材 PDF</button>}</>}
                {sourceKind === 'file' && <div className="exercise-two">
                  <label className="exercise-field">来源<input value={importSource} onChange={e => setImportSource(e.target.value)} placeholder="如 2025 模拟卷" />
                  </label>
                  <label className="exercise-field">章节（可选）<input value={importChapter} onChange={e => setImportChapter(e.target.value)} />
                  </label>
                </div>}
                </div>}
              </div>
              <div className="exercise-import-submit">
                <button className="app-primary-button" disabled={importing || (sourceKind === 'file' ? !importFile : !textbookSourceName)} onClick={sourceKind === 'file' ? analyzeImportFile : analyzeTextbookExercises}>{importing ? <>
                  <Loader2 size={16} className="animate-spin" />正在分析…</> : sourceKind === 'file' ? '分析文件' : '抽取教材候选题'}<ChevronRight size={16} />
                </button>
              </div>
            </fieldset>
            {candidateError && <p role="alert" className="exercise-feedback">{candidateError}</p>}

            <button className="app-ghost-button" onClick={() => setManualOpen(true)}>手动录入一道题</button>
          </div>
          <div hidden={!candidateState.sourceRegistry && candidates.length===0 || reviewPreparationOpen} className="exercise-review-panel">
            <CandidateReviewWorkspace bookName={activeName} state={candidateState} source={candidateSourceLabel || activeName} busy={importing || commitUnknown} notice={candidateError} onReviewed={() => setCandidateError('')} onBack={() => setReviewPreparationOpen(true)} onSubmit={importSelected} onSaveExample={saveStructureExample} />
          </div>
        </section>
        <div hidden={workspaceMode !== 'bank' || !expandedId} className="exercise-bank-reader">{records.find(r => r.id === expandedId) && <ExerciseReader key={expandedId} record={records.find(r => r.id === expandedId)!} bookQuery={bookQuery} title="习题详情" actions={<>
          <button className="app-primary-button" onClick={() => startSinglePractice(records.find(r => r.id === expandedId)!)}>练习这道题</button>
          <button className="app-ghost-button" onClick={() => setExpandedId('')}>返回题库</button>
        </>} onSaved={handleAnswerSaved} onMessage={setMessage} onStatus={status => void updateStatus(expandedId, status)} onDelete={() => deletion.request(records.filter(record => record.id === expandedId))} />}</div>
        <main hidden={workspaceMode === 'import' || (workspaceMode === 'bank' && Boolean(expandedId))} className="exercise-main">
          <div className="exercise-main-inner">
            {(workspaceMode === 'bank' || (!singlePracticeActive && !['active', 'paused'].includes(practiceSession?.status || ''))) && <ExerciseScopeFilters subject={targetSubject} bookName={activeName} books={books} chapter={filterChapter} chapters={scopeChapters} examSource={filterExamSource} authoredFocus={filterAuthoredFocus} sourceFacets={sourceFacets} onExamSource={setFilterExamSource} onAuthoredFocus={setFilterAuthoredFocus} practiceState={practiceState} onSubject={updateTargetSubject} onBook={value => void updateTargetName(value)} onChapter={setFilterChapter} onPracticeState={setPracticeState} />}
            <section className={`exercise-practice-panel ${workspaceMode !== 'practice' ? 'is-hidden' : ''} ${singlePracticeActive || ['active', 'paused'].includes(practiceSession?.status || '') ? 'is-reading' : ''}`}>
              {!singlePracticeActive && !['active', 'paused'].includes(practiceSession?.status || '') && <div className="exercise-preparation">
                <p className="exercise-eyebrow">{targetSubject} / {activeName === 'default' ? '独立题库' : textbookBook?.displayName || activeName}</p>
                <h1>{loadError ? '题库暂时无法读取' : loading && !records.length ? '正在读取题库…' : practicePool.length ? '开始一轮练习' : (searchKw || filterChapter || filterExamSource || filterAuthoredFocus || practiceState) ? '当前范围暂无符合条件的题目' : '当前范围暂无题目'}</h1>{loadError ? <div role="alert">
                  <p>{loadError}</p>
                  <button className="app-secondary-button" onClick={load}>重试读取</button>
                </div> : <div className="exercise-prep-columns">
                  <div>
                    {practicePool.length > 0 ? <>
                      <section className="exercise-setup-group">
                        <h2>本次题量<HelpHint label="本次题量">1–200 题；实际题量以当前范围和筛选内可用题目为准。</HelpHint>
                        </h2>
                        <div className="exercise-quantity">{[5, 10, 20].map(n => <button key={n} aria-pressed={sessionLimit === n} onClick={() => setSessionLimit(n)}>{n} 题</button>)}<input aria-label="本次题量" type="number" min="1" max="200" value={sessionLimit} onChange={e => setSessionLimit(Math.max(1, Math.min(200, +e.target.value || 1)))} />题</div>
                      </section>
                      <section className="exercise-setup-group">
                        <h2>出题顺序<HelpHint label="出题顺序">优先复习按题目状态和练习次数排列；随机顺序由现有练习会话选题。</HelpHint>
                        </h2>
                        <SegmentedControl label="练习顺序" value={sessionShuffle ? 'random' : 'review'} options={[{ value: 'review', label: '优先复习' }, { value: 'random', label: '随机顺序' }]} onChange={v => setSessionShuffle(v === 'random')} />
                      </section>
                      <button className="app-primary-button" onClick={startConfiguredPractice} disabled={sessionBusy || loading}>开始练习 · {sessionLimit} 题</button>
                    </> : <div className="exercise-empty-paths">
                      <button onClick={() => { setSourceKind('textbook'); setWorkspaceMode('import'); }}>
                        <TexaTextbook size={22} /><span><strong>从教材抽取</strong><small>选择已导入教材，校对后加入题库</small></span><ChevronRight size={16} />
                      </button>
                      <button onClick={() => { setSourceKind('file'); setWorkspaceMode('import'); }}>
                        <Upload size={22} /><span><strong>上传文件 / MinerU 包</strong><small>导入真题、习题册或已有解析结果</small></span><ChevronRight size={16} />
                      </button>
                      <button onClick={() => setManualOpen(true)}>手动录入</button></div>}{practiceSession?.status === 'completed' && <p>上轮完成 {practiceSession.summary.answered} 题，平均自评 {practiceSession.summary.average_quality}</p>}</div>{practicePool.length > 0 && <aside className="exercise-resource-summary">
                        <h2>当前题目</h2>
                        <p className="exercise-count">{records.length}<small> 道已加载</small>
                        </p>
                        <p>其中 {stats?.by_status?.needs_review || 0} 道需复习</p>
                        <h2>题目示例<HelpHint label="题目示例">查看当前范围的题目示例。</HelpHint>
                        </h2>{records.slice(0, 3).map(r => <article key={r.id}>
                          <SimpleMarkdown content={titleOf(r)} />
                          <small>{r.chapter} · {r.question_type}</small>
                        </article>)}<button className="app-ghost-button" onClick={() => setWorkspaceMode('bank')}>查看题库 →</button>
                        <button className="app-ghost-button" onClick={() => setWorkspaceMode('import')}>导入题目</button>
                      </aside>}</div>}</div>}
              {((practiceSession && ['active', 'paused'].includes(practiceSession.status)) || singlePracticeActive) && currentPractice && <div className="exercise-practice-reader">
                <ExerciseReader key={currentPractice.id} record={currentPractice} bookQuery={bookQuery} title={!singlePracticeActive && practiceSession ? `第 ${practiceSession.current_index + 1} / ${practiceSession.summary.total} 题` : '单题练习'} actions={singlePracticeActive ? <button className="app-ghost-button" onClick={leaveSinglePractice}>返回练习设置</button> : <>
                  <button className="app-secondary-button" disabled={sessionBusy} onClick={() => changePracticeSessionStatus(practiceSession?.status === 'active' ? 'pause' : 'resume')}>{practiceSession?.status === 'active' ? '暂停' : '继续'}</button>
                  <button className="app-ghost-button" disabled={sessionBusy} onClick={() => { if (window.confirm('结束本轮练习？当前未提交作答将丢弃。')) void changePracticeSessionStatus('abandon'); }}>结束本轮</button>
                </>} onSaved={handleAnswerSaved} onMessage={showPracticeMessage} attempt={<textarea id="exercise-practice-answer" aria-label="我的作答" value={practiceAnswer} onChange={e => setPracticeAnswer(e.target.value)} placeholder="输入思路、公式或关键步骤" />} footer={<>
                  <PracticeAssessment key={currentPractice.id} disabled={sessionBusy || (!singlePracticeActive && practiceSession?.status === 'paused')} continuous={!singlePracticeActive && Boolean(practiceSession)} onSubmit={quality => void submitPractice(quality)} />{pendingDirectAnswer && <button disabled={sessionBusy} className="app-secondary-button" onClick={() => submitPractice(pendingDirectAnswer.quality, pendingDirectAnswer.add_to_mistake, true)}>恢复未确认作答</button>}{practiceMessage && <p role="status">{practiceMessage}{candidateId && <Link to="/mistakes?filter=pending">确认收录</Link>}</p>}</>} />
              </div>}
              {!singlePracticeActive && !['active', 'paused'].includes(practiceSession?.status || '') && practiceMessage && <p className="exercise-feedback" role="status">{practiceMessage}</p>}
            </section>
            <div className={`${workspaceMode !== 'bank' || !stats?.total ? 'hidden' : 'flex'} flex-wrap items-center gap-x-5 gap-y-1 border-t border-border px-1 py-3 type-caption text-text-secondary`}>
              <span>总习题 <strong className="font-semibold text-text-primary">{stats?.total || 0}</strong>
              </span>
              <span>需复习 <strong className="font-semibold text-[var(--warning-text)]">{stats?.by_status?.needs_review || 0}</strong>
              </span>
              <span>已掌握 <strong className="font-semibold text-[var(--success-text)]">{stats?.by_status?.mastered || 0}</strong>
              </span>
              <button onClick={load} disabled={loading} className="ml-auto inline-flex items-center gap-1 text-text-secondary hover:text-text-primary">
                <TexaSearch className="h-4 w-4" />刷新</button>
            </div>

            <section className={`${workspaceMode === 'bank' ? 'block' : 'hidden'} workspace-collection-section`}>
              {loadError && <p role="alert" className="exercise-warning">{loadError}</p>}
              {message && <p role="status">{message}</p>}
              <div className="exercise-bank-search">
                <input value={searchKw} onChange={(e) => setSearchKw(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') load(); }} aria-label="搜索题目" placeholder="搜索题目、出处或考点" className="min-w-[260px] flex-1 app-field" />
                <button onClick={load} className="app-secondary-button">搜索</button>
              </div>

              <div className="exercise-bank-list">
                <ExerciseBankList key={`${activeName}|${targetSubject}|${filterChapter}|${filterExamSource}|${filterAuthoredFocus}|${practiceState}|${searchKw}`} records={records} visibleRecords={loading ? [] : recordList.visibleItems} textbookName={textbookSourceName} textbookLabel={textbookBook?.displayName || ''} disabled={loading || deletion.deleting} onOpen={setExpandedId} onDelete={deletion.request} />
                {recordList.hasMore && (
                  <div className="flex justify-center pt-1">
                    <button onClick={recordList.showMore} className="workspace-radius border border-border bg-bg-primary px-4 py-2 workspace-interface-text text-text-secondary hover:border-accent hover:text-text-primary">
                      加载更多习题（已显示 {recordList.visibleCount} / {recordList.totalCount}）
                    </button>
                  </div>
                )}
                {loading && <p role="status" className="exercise-feedback">正在读取题目…</p>}
                {!loading && records.length === 0 && <div className="py-12 text-center workspace-interface-text text-text-secondary">
                  <TexaExercises className="mx-auto mb-2 h-6 w-6" />{searchKw.trim() ? <><p>当前搜索条件下没有题目</p><button className="app-secondary-button mt-3" onClick={() => { setSearchKw(''); searchKwRef.current = ''; void load(); }}>清空搜索</button></> : <>暂无习题，请先导入 Word/PDF</>}</div>}
              </div>
            </section>
          </div>
        </main>
        {pdfOpen && sourcePdfPath && (
          <Dialog open title="教材 PDF 选页" onClose={() => setPdfOpen(false)} className="exercise-pdf-dialog">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
                <div>
                  <div className="workspace-interface-text font-semibold text-text-primary">{activeName} · PDF 选页</div>

                  <div className="workspace-support-text text-text-secondary">输入 PDF 页码后预览；点击“使用当前页”将起止页都设为当前页。</div>
                </div>
                <div className="flex items-center gap-2">
                  <input type="number" min="1" value={pdfPage} onChange={(e) => setPdfPage(e.target.value)} className="w-24 app-field" />
                  <button onClick={() => setPdfPage((value) => String(Math.max(1, Number(value || 1) - 1)))} className="workspace-radius border border-border px-2.5 py-1.5 workspace-support-text hover:border-accent">上一页</button>
                  <button onClick={() => setPdfPage((value) => String(Number(value || 1) + 1))} className="workspace-radius border border-border px-2.5 py-1.5 workspace-support-text hover:border-accent">下一页</button>
                  <button onClick={() => { const selectedPage = pdfPage || '1'; setTextbookPageStart(selectedPage); setTextbookPageEnd(selectedPage); setPdfOpen(false); }} className="workspace-radius bg-accent px-3 py-1.5 workspace-support-text text-white">使用当前页</button>
                  <button onClick={() => setPdfOpen(false)} aria-label="关闭 PDF" className="workspace-radius border border-border p-1.5 hover:border-accent">
                    <TexaClose className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {sourcePdfAsset.loading && <div className="flex min-h-0 flex-1 items-center justify-center gap-2 workspace-interface-text text-text-secondary">
                <Loader2 className="h-4 w-4 animate-spin" />正在安全加载教材 PDF...</div>}
              {!sourcePdfAsset.loading && sourcePdfAsset.error && <div className="m-4 workspace-radius border border-red-200 bg-red-50 px-4 py-3 workspace-interface-text text-red-700">PDF 加载失败：{sourcePdfAsset.error}</div>}
              {sourcePdfAsset.url && <iframe key={sourcePdfAsset.url + '#page=' + (pdfPage || '1')} title={"\u6559\u6750 PDF \u9884\u89c8"} src={sourcePdfAsset.url + '#page=' + Math.max(1, Number(pdfPage || 1))} className="min-h-0 flex-1 bg-white" />}
          </Dialog>
        )}
      </div>

    </div>
  );
};

export default ExercisesPage;
