import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookMarked, CalendarDays, ImagePlus, Images, Send, Shuffle, Square, X } from 'lucide-react';
import { figureQuestionStream, get, interruptFigureTask, mistakeSolutionStream, post, resumeFigureTaskStream } from '../api/client';

import HighlightRepositoryDialog from '../components/HighlightRepositoryDialog';
import LearningEmptyWorkspace from '../components/chat/LearningEmptyWorkspace';
import ComposerOverflowMenu from '../components/chat/ComposerOverflowMenu';
import ChatMessage from '../components/ChatMessage';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useChatContext } from '../contexts/ChatContext';
import { composeMathQuestion } from '../features/math-input/composeMathQuestion';
import ProblemImageEditor from '../features/mistakes/components/ProblemImageEditor';
import { insertFormulaReference } from '../features/math-input/formulaReferences';
import MathExpressionList from '../features/math-input/MathExpressionList';
import type { MathEditRequest, MathExpression } from '../features/math-input/types';
import VisualMathInputPopover from '../features/math-input/VisualMathInputPopover';
import FigureCatalog from '../features/visual-learning/FigureCatalog';
import FigureContextAttachment from '../features/visual-learning/FigureContextAttachment';
import FigurePageInspector from '../features/visual-learning/FigurePageInspector';
import FigureRegionViewer from '../features/visual-learning/FigureRegionViewer';
import { useChat } from '../hooks/useChat';
import type { ExerciseRecord, FigureArtifact, LearningTaskState, MistakeRecord, VisualRegion } from '../types';
import { mapStoredConversationMessages } from '../utils/conversationMessages';
import { createExecutionLifecycle, executionMessageStage, mergeChatActivity, mergeExecutionLifecycle, settleChatActivity } from '../utils/chatActivities';
import { buildTextbookScopeOptions, findDefaultTextbookScope, formatLearningScopeLabel, scopeContainsBook, type TextbookRecord } from '../utils/textbookScopes';
import { useInspector } from '../contexts/InspectorContext';
type ReportMode = 'daily' | 'weekly';
type ActionMode = ReportMode | 'exercise';

function firstLine(value = '', maxLength = 48) {
  const line = value.replace(/\s+/g, ' ').trim();
  return line.length > maxLength ? `${line.slice(0, maxLength)}...` : line;
}

function conversationTitle(value = '') {
  const withoutAttachment = value.replace(/^📎[^\r\n]*\r?\n(?:\r?\n)+/, '').trim();
  return firstLine(withoutAttachment || value || '学习会话', 56);
}

const ChatPage: React.FC = () => {
  const [input, setInput] = useState('');
  const [mathExpressions, setMathExpressions] = useState<MathExpression[]>([]);
  const [mathEditRequest, setMathEditRequest] = useState<MathEditRequest | null>(null);
  const [books, setBooks] = useState<TextbookRecord[]>([]);
  const [booksLoaded, setBooksLoaded] = useState(false);
  const [highlightDialogOpen, setHighlightDialogOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<ActionMode | null>(null);
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [rawAttachmentFile, setRawAttachmentFile] = useState<File | null>(null);
  const [attachmentPreview, setAttachmentPreview] = useState('');
  const [attachmentEditorOpen, setAttachmentEditorOpen] = useState(false);
  const [importAttachment, setImportAttachment] = useState(false);
  const [attachmentLoading, setAttachmentLoading] = useState(false);
  const [mistakePickerOpen, setMistakePickerOpen] = useState(false);
  const [cachedMistakes, setCachedMistakes] = useState<MistakeRecord[]>([]);
  const [selectedMistakeId, setSelectedMistakeId] = useState('');
  const [activeFigure, setActiveFigure] = useState<FigureArtifact | null>(null);
  const [visualRegion, setVisualRegion] = useState<VisualRegion | null>(null);
  const [figureWorkspaceExpanded, setFigureWorkspaceExpanded] = useState(false);
  const { messages, isLoading, sendMessage, stop, resumeTask } = useChat();
  const {
    bookName,
    setBookName,
    subject,
    setSubject,
    conversationId,
    addMessage,
    updateLastMessage,
    updateMessageByTaskId,
    historyPage,
    prependConversationMessages,
  } = useChatContext();
  const [historyLoading, setHistoryLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const preserveHistoryScrollRef = useRef<{ height: number; top: number } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const attachmentInputRef = useRef<HTMLInputElement>(null);
  const visualAbortRef = useRef<(() => void) | null>(null);
  const activeVisualTaskRef = useRef<LearningTaskState | null>(null);
  const activeFigureIdentityRef = useRef<{ taskId: string; runId: string } | null>(null);
  const visualPartialOutputRef = useRef('');
  const mathExpressionSequenceRef = useRef(0);
  const mathEditSequenceRef = useRef(0);
  const { openInspector, closeInspector } = useInspector();
  const scopeBooks = useMemo(() => buildTextbookScopeOptions(books), [books]);
  const currentScope = scopeBooks.find((scope) => scopeContainsBook(scope, bookName));
  const headerScopeLabel = formatLearningScopeLabel(
    subject,
    currentScope?.displayName || currentScope?.name || bookName || '通用问答',
  );

  useEffect(() => {
    const loadBooks = async () => {
      try {
        const res = await get('/books/list');
        if (res?.success) setBooks(res.data || []);
      } catch {
        setBooks([]);
      } finally {
        setBooksLoaded(true);
      }
    };
    const onChanged = () => loadBooks();
    window.addEventListener('books:changed', onChanged);
    loadBooks();
    return () => window.removeEventListener('books:changed', onChanged);
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const preserved = preserveHistoryScrollRef.current;
    if (preserved) {
      preserveHistoryScrollRef.current = null;
      container.scrollTop = preserved.top + (container.scrollHeight - preserved.height);
      return;
    }
    container.scrollTop = container.scrollHeight;
  }, [messages]);

  const loadEarlierMessages = async () => {
    const beforeSeq = historyPage?.next_before_seq;
    if (!historyPage?.has_more || beforeSeq == null || historyLoading) return;
    const container = scrollRef.current;
    if (container) {
      preserveHistoryScrollRef.current = {
        height: container.scrollHeight,
        top: container.scrollTop,
      };
    }
    setHistoryLoading(true);
    try {
      const params = new URLSearchParams({ limit: '40', before_seq: String(beforeSeq) });
      const res = await get(`/chat/conversations/${encodeURIComponent(conversationId)}/messages?${params.toString()}`, 20000);
      if (!res?.success || !res.data) throw new Error(res?.message || '加载历史消息失败');
      prependConversationMessages(
        mapStoredConversationMessages(res.data.messages || []),
        res.data.page,
      );
    } catch {
      preserveHistoryScrollRef.current = null;
    } finally {
      setHistoryLoading(false);
    }
  };

  const persistLocalExchange = async (
    userContent: string,
    assistantContent: string,
    options: { turnId?: string; learningTask?: LearningTaskState; deliveryStatus?: 'waiting' | 'complete' | 'error' } = {},
  ) => {
    try {
      await post('/chat/log', {
        conversation_id: conversationId,
        book_name: bookName,
        subject,
        turn_id: options.turnId,
        messages: [
          { role: 'user', content: userContent, turn_id: options.turnId },
          {
            role: 'assistant', content: assistantContent, turn_id: options.turnId,
            delivery_status: options.deliveryStatus || 'complete', learning_task: options.learningTask,
          },
        ],
      }, 15000);
    } catch {
      // Local workflow cards should stay usable even if the backend has not been restarted yet.
    }
  };

  const switchBook = useCallback(async (name: string) => {
    if (!name) {
      setBookName('');
      return;
    }
    try {
      const res = await get(`/books/switch/${encodeURIComponent(name)}`);
      if (res?.success) {
        setBookName(res.data.name);
        if (res.data.subject) setSubject(res.data.subject);
      }
    } catch {
      setBookName(name);
    }
  }, [setBookName, setSubject]);

  useEffect(() => {
    if (!booksLoaded) return;
    if (bookName) {
      if (!scopeBooks.some((scope) => scopeContainsBook(scope, bookName))) setBookName('');
      return;
    }
    const target = findDefaultTextbookScope(scopeBooks, subject);
    if (target) void switchBook(target.name);
  }, [bookName, booksLoaded, scopeBooks, setBookName, subject, switchBook]);

  const clearAttachment = () => {
    if (attachmentPreview) URL.revokeObjectURL(attachmentPreview);
    setAttachmentFile(null);
    setRawAttachmentFile(null);
    setAttachmentPreview('');
    setAttachmentEditorOpen(false);
    if (attachmentInputRef.current) attachmentInputRef.current.value = '';
  };

  const selectAttachment = (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) return;
    clearAttachment();
    setSelectedMistakeId('');
    setActiveFigure(null);
    setVisualRegion(null);
    setFigureWorkspaceExpanded(false);
    setRawAttachmentFile(file);
    setAttachmentEditorOpen(true);
  };

  useEffect(() => {
    setActiveFigure(null);
    setVisualRegion(null);
    setFigureWorkspaceExpanded(false);
  }, [bookName]);

  const applyAttachmentProcessing = (processed: { file: File; preview: string }) => {
    if (attachmentPreview) URL.revokeObjectURL(attachmentPreview);
    setAttachmentFile(processed.file);
    setAttachmentPreview(processed.preview);
    setAttachmentEditorOpen(false);
  };

  const loadCachedMistakes = async () => {
    setMistakePickerOpen((open) => !open);
    if (cachedMistakes.length) return;
    try {
      const query = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';
      const result = await post(`/mistakes/list${query}`, { subject, limit: 30 });
      setCachedMistakes(result?.data || []);
    } catch {
      setCachedMistakes([]);
    }
  };

  const openFigureCatalog = () => {
    if (!bookName) return;
    openInspector({
      kind: 'source',
      title: '教材图片',
      subtitle: currentScope?.displayName || currentScope?.name || bookName,
      content: (
        <FigureCatalog
          bookNames={currentScope?.sourceNames?.length ? currentScope.sourceNames : [bookName]}
          onSelect={(figure) => {
            clearAttachment();
            setSelectedMistakeId('');
            setMistakePickerOpen(false);
            setActiveFigure(figure);
            setVisualRegion(null);
            setFigureWorkspaceExpanded(true);
            closeInspector();
          }}
        />
      ),
    });
  };

  const openActiveFigureSource = () => {
    if (!activeFigure) return;
    openInspector({
      kind: 'source',
      title: 'Figure 来源',
      subtitle: `${activeFigure.book_name}${activeFigure.page ? ` · p.${activeFigure.page}` : ''}`,
      content: <FigurePageInspector figure={activeFigure} />,
    });
  };

  const submitFigureQuestion = (questionValue: string) => {
    if (!activeFigure || attachmentLoading) return;
    const question = questionValue || (visualRegion ? '请解释选中区域。' : '请解释这幅教材图片。');
    const turnId = `turn_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
    const label = `📎 教材图 · ${activeFigure.page ? `p.${activeFigure.page}` : '未标页'}\n\n${question}`;
    setAttachmentLoading(true);
    activeVisualTaskRef.current = null;
    activeFigureIdentityRef.current = null;
    visualPartialOutputRef.current = '';
    addMessage({ role: 'user', content: label, turnId });
    addMessage({ role: 'assistant', content: '', stage: 'thinking', activities: [], turnId, answerMode: 'visual_grounded' });
    setInput('');
    setMathExpressions([]);
    setMathEditRequest(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    let lifecycle = createExecutionLifecycle('');
    visualAbortRef.current = figureQuestionStream({
      book_name: activeFigure.book_name,
      figure_id: activeFigure.figure_id,
      question,
      bbox: visualRegion,
      subject,
      conversation_id: conversationId,
      turn_id: turnId,
    }, (event) => {
      const merged = mergeExecutionLifecycle(lifecycle, event.execution_event);
      if (merged === lifecycle) return;
      lifecycle = merged;
      visualPartialOutputRef.current = lifecycle.output;
      if (lifecycle.taskId) activeFigureIdentityRef.current = { taskId: lifecycle.taskId, runId: lifecycle.runId };
      const eventTask = event.learning_task || event.result?.learning_task;
      if (eventTask) activeVisualTaskRef.current = eventTask;
      updateLastMessage((last) => last.role === 'assistant' ? {
        ...last,
        id: event.result?.message_id || last.id,
        content: lifecycle.terminalType === 'error'
          ? (lifecycle.errorCode === 'figure_index_out_of_date'
            ? `教材图片索引已过期：${lifecycle.errorMessage || '请重新导入教材后再试'}`
            : `教材图片问答失败：${lifecycle.errorMessage || '未知错误'}`)
          : lifecycle.hasOutput ? lifecycle.output : last.content,
        stage: executionMessageStage(lifecycle, eventTask || last.learningTask),
        answerMode: 'visual_grounded',
        sources: event.result?.sources || last.sources,
        learningTask: eventTask || last.learningTask,
        citationProvenance: event.result?.citation_provenance || last.citationProvenance,
        activities: lifecycle.activities,
      } : last);
      if (lifecycle.terminal) {
        visualAbortRef.current = null;
        activeVisualTaskRef.current = null;
        activeFigureIdentityRef.current = null;
        visualPartialOutputRef.current = '';
        setAttachmentLoading(false);
        if (lifecycle.terminalType === 'final') {
          setVisualRegion(null);
          setFigureWorkspaceExpanded(false);
        }
      }
    }, (error) => {
      visualAbortRef.current = null;
      activeVisualTaskRef.current = null;
      activeFigureIdentityRef.current = null;
      visualPartialOutputRef.current = '';
      setAttachmentLoading(false);
      updateLastMessage((last) => last.role === 'assistant' ? {
        ...last,
        content: `教材图片问答失败：${error.message}`,
        stage: 'error',
        activities: mergeChatActivity(last.activities, {
          id: 'figure-request', kind: 'system', label: 'Figure 问答中断', status: 'failed', detail: error.message,
        }),
      } : last);
    });
  };

  const submitVisualQuestion = (question: string) => {
    if (attachmentLoading) return;
    setAttachmentLoading(true);
    activeVisualTaskRef.current = null;
    activeFigureIdentityRef.current = null;
    const label = attachmentFile
      ? `📎 ${attachmentFile.name}\n\n${question || '请完整讲解这道题'}`
      : `从历史错题讲解：${firstLine(cachedMistakes.find((item) => item.id === selectedMistakeId)?.question_text || '')}\n\n${question || '请重新讲解这道错题'}`;
    const turnId = `turn_${Date.now()}_${Math.random().toString(16).slice(2, 10)}`;
    addMessage({ role: 'user', content: label, turnId });
    addMessage({ role: 'assistant', content: '', stage: 'thinking', activities: [], turnId });
    let payload: FormData | Record<string, unknown>;
    let path: '/mistakes/solve-image-stream' | '/mistakes/solve-cached-stream';
    if (attachmentFile) {
      const form = new FormData();
      form.append('file', attachmentFile);
      form.append('question', question || '请完整讲解这道题');
      form.append('subject', subject);
      form.append('book_name', bookName || 'default');
      form.append('import_to_mistakes', String(importAttachment));
      form.append('conversation_id', conversationId);
      form.append('turn_id', turnId);
      path = '/mistakes/solve-image-stream';
      payload = form;
    } else {
      path = '/mistakes/solve-cached-stream';
      payload = { id: selectedMistakeId, question: question || '请重新讲解这道错题', book_name: bookName || 'default' };
    }
    setInput('');
    setMathExpressions([]);
    setMathEditRequest(null);
    setSelectedMistakeId('');
    setMistakePickerOpen(false);
    setImportAttachment(false);
    clearAttachment();
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    let lifecycle = createExecutionLifecycle('');
    visualAbortRef.current = mistakeSolutionStream(path, payload, (event) => {
      const merged = mergeExecutionLifecycle(lifecycle, event.execution_event);
      if (merged === lifecycle) return;
      lifecycle = merged;
      const eventTask = event.learning_task || event.result?.learning_task;
      updateLastMessage((last) => last.role === 'assistant' ? {
        ...last,
        content: lifecycle.terminalType === 'error'
          ? `图片处理失败：${lifecycle.errorMessage || '未知错误'}`
          : lifecycle.hasOutput ? lifecycle.output : last.content,
        stage: executionMessageStage(lifecycle, eventTask || last.learningTask),
        activities: lifecycle.activities,
        linkedConcepts: event.result?.linked_concepts || last.linkedConcepts,
        learningTask: eventTask || last.learningTask,
      } : last);
      if (eventTask?.input_action_required) {
        visualAbortRef.current = null;
        setAttachmentLoading(false);
        const waitingContent = '精确解答已暂停：缺失材料会影响最终结论。';
        updateLastMessage((last) => last.role === 'assistant' ? { ...last, content: waitingContent, stage: 'waiting_for_input', learningTask: eventTask } : last);
        void persistLocalExchange(label, waitingContent, { turnId, learningTask: eventTask, deliveryStatus: 'waiting' });
      } else if (lifecycle.terminalType === 'final') {
        visualAbortRef.current = null;
        setAttachmentLoading(false);
        void persistLocalExchange(label, lifecycle.output, { turnId, learningTask: eventTask, deliveryStatus: 'complete' });
      } else if (lifecycle.terminalType === 'error') {
        visualAbortRef.current = null;
        setAttachmentLoading(false);
      }
    }, (error) => {
      visualAbortRef.current = null;
      setAttachmentLoading(false);
      updateLastMessage((last) => last.role === 'assistant' ? {
        ...last, content: `图片处理失败：${error.message}`, stage: 'error',
        activities: mergeChatActivity(last.activities, { id: 'request', kind: 'system', label: '请求中断', status: 'failed', detail: error.message }),
      } : last);
    });
  };

  const resumeLearningTask = async (
    task: LearningTaskState,
    action: 'provide_input' | 'method_only',
    file?: File,
  ) => {
    if (attachmentLoading || !task.input_action_required) return;
    setAttachmentLoading(true);
    updateMessageByTaskId(task.id, (message) => ({
      ...message,
      stage: 'thinking',
      activities: mergeChatActivity(message.activities, {
        id: 'resume', kind: 'system', label: '恢复原任务', status: 'active', detail: '正在读取已保存的原题与任务状态',
      }),
    }));
    const form = new FormData();
    form.append('action', action);
    if (file) form.append('file', file);
    let lifecycle = createExecutionLifecycle('');
    await new Promise<void>((resolve, reject) => {
      visualAbortRef.current = mistakeSolutionStream(
        `/mistakes/visual-tasks/${task.id}/resume-stream`,
        form,
        (event) => {
          const merged = mergeExecutionLifecycle(lifecycle, event.execution_event);
          if (merged === lifecycle) return;
          lifecycle = merged;
          const eventTask = event.learning_task || event.result?.learning_task;
          updateMessageByTaskId(task.id, (message) => {
            return {
              ...message,
              content: lifecycle.terminalType === 'error'
                ? `图片处理失败：${lifecycle.errorMessage || '恢复失败'}`
                : lifecycle.hasOutput ? lifecycle.output : message.content,
              stage: executionMessageStage(lifecycle, eventTask || message.learningTask),
              activities: lifecycle.activities,
              linkedConcepts: event.result?.linked_concepts || message.linkedConcepts,
              learningTask: eventTask || message.learningTask,
            };
          });
          if (eventTask?.input_action_required) {
            visualAbortRef.current = null;
            setAttachmentLoading(false);
            resolve();
          } else if (lifecycle.terminalType === 'final') {
            visualAbortRef.current = null;
            setAttachmentLoading(false);
            void persistLocalExchange(
              task.goal,
              lifecycle.output,
              { turnId: task.turn_id, learningTask: eventTask, deliveryStatus: 'complete' },
            );
            resolve();
          } else if (lifecycle.terminalType === 'error') {
            visualAbortRef.current = null;
            setAttachmentLoading(false);
            reject(new Error(lifecycle.errorMessage || '恢复任务失败'));
          }
        },
        (error) => {
          visualAbortRef.current = null;
          setAttachmentLoading(false);
          updateMessageByTaskId(task.id, (message) => ({
            ...message,
            stage: 'waiting_for_input',
            activities: settleChatActivity(message.activities, 'resume', 'failed', error.message || '恢复失败'),
          }));
          reject(error);
        },
      );
    });
  };

  const resumeFigureLearningTask = (task: LearningTaskState) => {
    if (attachmentLoading || !task.resumable) return;
    setAttachmentLoading(true);
    activeVisualTaskRef.current = task;
    activeFigureIdentityRef.current = { taskId: task.id, runId: '' };
    visualPartialOutputRef.current = '';
    updateMessageByTaskId(task.id, (message) => ({
      ...message,
      content: '',
      stage: 'thinking',
      activities: mergeChatActivity(message.activities, {
        id: 'figure-resume', kind: 'system', label: '恢复 Figure 问答', status: 'active', detail: '正在重用已保存的 Figure、选区与教材上下文',
      }),
    }));
    let lifecycle = createExecutionLifecycle('');
    visualAbortRef.current = resumeFigureTaskStream(task.id, (event) => {
      const merged = mergeExecutionLifecycle(lifecycle, event.execution_event);
      if (merged === lifecycle) return;
      lifecycle = merged;
      visualPartialOutputRef.current = lifecycle.output;
      if (lifecycle.taskId) activeFigureIdentityRef.current = { taskId: lifecycle.taskId, runId: lifecycle.runId };
      const eventTask = event.learning_task || event.result?.learning_task;
      if (eventTask) activeVisualTaskRef.current = eventTask;
      updateMessageByTaskId(task.id, (message) => ({
        ...message,
        id: event.result?.message_id || message.id,
        content: lifecycle.terminalType === 'error'
          ? (lifecycle.errorCode === 'figure_index_out_of_date'
            ? `教材图片索引已过期：${lifecycle.errorMessage || '请重新导入教材后再试'}`
            : `教材图片问答失败：${lifecycle.errorMessage || '恢复失败'}`)
          : lifecycle.hasOutput ? lifecycle.output : message.content,
        stage: executionMessageStage(lifecycle, eventTask || message.learningTask),
        sources: event.result?.sources || message.sources,
        citationProvenance: event.result?.citation_provenance || message.citationProvenance,
        learningTask: eventTask || message.learningTask,
        activities: lifecycle.activities,
      }));
      if (lifecycle.terminal) {
        visualAbortRef.current = null;
        activeVisualTaskRef.current = null;
        activeFigureIdentityRef.current = null;
        visualPartialOutputRef.current = '';
        setAttachmentLoading(false);
        if (lifecycle.terminalType === 'final') {
          setVisualRegion(null);
          setFigureWorkspaceExpanded(false);
        }
      }
    }, (error) => {
      visualAbortRef.current = null;
      activeVisualTaskRef.current = null;
      activeFigureIdentityRef.current = null;
      visualPartialOutputRef.current = '';
      setAttachmentLoading(false);
      updateMessageByTaskId(task.id, (message) => ({
        ...message,
        stage: 'stopped',
        activities: settleChatActivity(message.activities, 'figure-resume', 'failed', error.message || '恢复失败'),
      }));
    });
  };

  const resumeInterruptedTask = (task: LearningTaskState) => {
    if (task.task_type === 'figure_qa') {
      resumeFigureLearningTask(task);
      return;
    }
    resumeTask(task);
  };

  const stopVisualQuestion = () => {
    const task = activeVisualTaskRef.current;
    const identity = activeFigureIdentityRef.current;
    const partialOutput = visualPartialOutputRef.current;
    visualAbortRef.current?.();
    visualAbortRef.current = null;
    activeVisualTaskRef.current = null;
    activeFigureIdentityRef.current = null;
    setAttachmentLoading(false);
    updateLastMessage((last) => {
      if (last.role !== 'assistant' || last.learningTask?.terminal || last.stage === 'done' || last.stage === 'error') return last;
      const activities = (last.activities || []).map((activity) => (
        activity.status === 'active'
          ? { ...activity, status: 'skipped' as const, detail: '用户已停止本次处理' }
          : activity
      ));
      return {
        ...last,
        content: last.content || '已停止图片讲解。',
        stage: 'stopped',
        learningTask: task || last.learningTask,
        activities,
      };
    });
    const figureTaskId = task?.task_type === 'figure_qa' ? task.id : identity?.taskId;
    if (figureTaskId && task?.interruptible !== false) {
      void interruptFigureTask(figureTaskId, partialOutput).then((response) => {
        activeVisualTaskRef.current = response.learning_task;
        updateMessageByTaskId(figureTaskId, (message) => ({
          ...message,
          stage: response.learning_task.resumable ? 'stopped' : response.learning_task.terminal ? 'done' : message.stage,
          learningTask: response.learning_task,
        }));
      }).catch((error) => {
        updateMessageByTaskId(figureTaskId, (message) => ({
          ...message,
          activities: mergeChatActivity(message.activities, {
            id: 'figure-interrupt', kind: 'system', label: '停止状态未保存', status: 'failed', detail: error instanceof Error ? error.message : String(error),
          }),
        }));
      });
    }
  };

  useEffect(() => () => {
    visualAbortRef.current?.();
    visualAbortRef.current = null;
  }, []);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const question = composeMathQuestion(input, mathExpressions);
    if ((!question && !attachmentFile && !selectedMistakeId && !activeFigure) || isLoading || attachmentLoading) return;
    if (activeFigure) {
      submitFigureQuestion(question);
      return;
    }
    if (attachmentFile || selectedMistakeId) {
      submitVisualQuestion(question);
      return;
    }
    sendMessage(question);
    setInput('');
    setMathExpressions([]);
    setMathEditRequest(null);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleAddMathExpression = (latex: string, displayMode: boolean) => {
    const id = `math-${Date.now()}-${++mathExpressionSequenceRef.current}`;
    setMathExpressions((current) => {
      const referenceNumber = current.reduce(
        (maximum, item, index) => Math.max(maximum, item.referenceNumber ?? index + 1),
        0,
      ) + 1;
      return [...current, { id, latex, displayMode, referenceNumber }];
    });
  };

  const handleUpdateMathExpression = (id: string, latex: string, displayMode: boolean) => {
    setMathExpressions((current) => current.map((item) => (
      item.id === id ? { ...item, latex, displayMode } : item
    )));
    setMathEditRequest(null);
  };

  const handleEditMathExpression = (expression: MathExpression) => {
    setMathEditRequest({
      nonce: ++mathEditSequenceRef.current,
      expression,
    });
  };

  const handleRemoveMathExpression = (id: string) => {
    setMathExpressions((current) => current.filter((item) => item.id !== id));
    setMathEditRequest((current) => current?.expression.id === id ? null : current);
  };

  const handleReferenceMathExpression = (referenceNumber: number) => {
    const field = textareaRef.current;
    const insertion = insertFormulaReference(
      input,
      referenceNumber,
      field?.selectionStart ?? input.length,
      field?.selectionEnd ?? input.length,
    );
    setInput(insertion.text);
    window.requestAnimationFrame(() => {
      field?.focus({ preventScroll: true });
      field?.setSelectionRange(insertion.cursor, insertion.cursor);
      if (field) field.style.height = Math.min(field.scrollHeight, 160) + 'px';
    });
  };

  const showReport = async (mode: ReportMode) => {
    if (actionLoading) return;
    const isDaily = mode === 'daily';
    const title = isDaily ? '学习日报' : '学习周报';
    const userContent = `展示我的${title}`;
    addMessage({ role: 'user', content: userContent });
    setActionLoading(mode);
    try {
      const params = new URLSearchParams({ book_name: bookName || 'default', subject, days: isDaily ? '1' : '7' });
      const res = await get(`/reports/weekly?${params.toString()}`);
      if (!res?.success) throw new Error(res?.message || `生成${title}失败`);
      addMessage({ role: 'assistant', content: '', stage: 'done', reportCard: { kind: mode, report: res.data } });
      void persistLocalExchange(userContent, `${title}已整理，可在当前对话中查看卡片。`);
    } catch (err) {
      addMessage({ role: 'assistant', content: `出错了：${err instanceof Error ? err.message : String(err)}`, stage: 'error' });
    } finally {
      setActionLoading(null);
    }
  };

  const pickRandomExercise = async () => {
    if (actionLoading) return;
    const userContent = '随机抽一道习题';
    addMessage({ role: 'user', content: userContent });
    setActionLoading('exercise');
    const bookQuery = bookName ? `?book_name=${encodeURIComponent(bookName)}` : '';
    try {
      const statuses = ['needs_review', 'practicing', 'new', ''];
      let pool: ExerciseRecord[] = [];
      for (const status of statuses) {
        const res = await post(`/exercises/list${bookQuery}`, { search_kw: '', subject, status, limit: 100 });
        if (res?.success && Array.isArray(res.data) && res.data.length) {
          const rows = res.data as ExerciseRecord[];
          pool = status ? rows : rows.filter((item) => item.status !== 'mastered');
          if (pool.length) break;
        }
      }
      if (!pool.length) {
        const content = '习题库里暂时没有可抽取的题目。可以先在“习题库”导入 Word/PDF，或从错题本转入习题。';
        addMessage({ role: 'assistant', content, stage: 'done' });
        void persistLocalExchange(userContent, content);
        return;
      }
      const record = pool[Math.floor(Math.random() * pool.length)];
      addMessage({ role: 'assistant', content: '', stage: 'done', exerciseCard: { record } });
      void persistLocalExchange(userContent, `已从题库抽取：${firstLine(record.question_text, 72)}`);
    } catch (err) {
      addMessage({ role: 'assistant', content: `出错了：${err instanceof Error ? err.message : String(err)}`, stage: 'error' });
    } finally {
      setActionLoading(null);
    }
  };


  const openMistakeQuickCapture = () => {
    const userContent = '打开错题速录';
    const assistantContent = '已打开错题速录卡片，可以上传图片、粘贴题干并校正识别结果。';
    addMessage({ role: 'user', content: userContent });
    addMessage({ role: 'assistant', content: '', stage: 'done', utilityCard: { kind: 'mistake_quick_capture' } });
    void persistLocalExchange(userContent, assistantContent);
  };

  const openHighlightDialog = () => {
    if (actionLoading) return;
    setHighlightDialogOpen(true);
  };

  return (
    <div className="relative flex h-full min-w-0 bg-bg-primary">
      <div
        data-empty={messages.length === 0 && !activeFigure ? 'true' : 'false'}
        className="learning-workspace-shell flex min-w-0 flex-1 flex-col"
      >
        <div className="learning-workspace-header">
          <div className="learning-workspace-title min-w-0">
            <h2>{messages.length ? conversationTitle(messages.find((message) => message.role === 'user')?.content) : '新学习会话'}</h2>
            <p>{headerScopeLabel}</p>
          </div>
          <div className="window-drag-region" aria-hidden="true" />
        </div>

        <div ref={scrollRef} className="learning-workspace-scroll">
          <div className="learning-document-column">
            {historyPage?.has_more && (
              <div className="flex justify-center pb-2">
                <button
                  type="button"
                  onClick={() => void loadEarlierMessages()}
                  disabled={historyLoading}
                  className="rounded-lg border border-border bg-bg-card px-3 py-1.5 type-caption text-text-secondary transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-wait disabled:opacity-60"
                >
                  {historyLoading ? '加载中…' : `加载更早消息（共 ${historyPage.total} 条）`}
                </button>
              </div>
            )}
            {messages.length === 0 && !activeFigure && (
              <LearningEmptyWorkspace
                isLoading={isLoading || Boolean(actionLoading)}
              />
            )}
            {messages.map((msg, i) => (
              <ErrorBoundary key={msg.id || `${msg.turnId || 'message'}-${i}`}>
                <ChatMessage messageId={msg.id} answerFeedback={msg.answerFeedback} role={msg.role} content={msg.content} stage={msg.stage} activities={msg.activities} turnId={msg.turnId} subjectSuggestion={msg.subjectSuggestion} answerMode={msg.answerMode} suggestedAnswerMode={msg.suggestedAnswerMode} scopeReason={msg.scopeReason} originalQuestion={msg.originalQuestion} onRequestGlobalAnswer={(question) => sendMessage(question, { answerMode: 'global_general' })} onRequestSuggestedAnswer={(question, answerMode) => sendMessage(question, { answerMode })} linkedConcepts={msg.linkedConcepts} sources={msg.sources} sourceChapters={msg.sourceChapters} reportCard={msg.reportCard} exerciseCard={msg.exerciseCard} chapterHighlightCard={msg.chapterHighlightCard} utilityCard={msg.utilityCard} learningTask={msg.learningTask} citationProvenance={msg.citationProvenance} onResumeLearningTask={resumeLearningTask} onResumeInterruptedTask={resumeInterruptedTask} />
              </ErrorBoundary>
            ))}
            {activeFigure && figureWorkspaceExpanded && (
              <FigureRegionViewer
                figure={activeFigure}
                region={visualRegion}
                onRegionChange={setVisualRegion}
                onOpenSource={openActiveFigureSource}
                onClose={() => setFigureWorkspaceExpanded(false)}
              />
            )}
          </div>
        </div>

        <div className="chat-composer">
          {mistakePickerOpen && (
            <div className="composer-popover max-h-52 overflow-y-auto p-2">
              {cachedMistakes.length ? cachedMistakes.map((mistake) => (
                <button key={mistake.id} type="button" onClick={() => { clearAttachment(); setActiveFigure(null); setVisualRegion(null); setSelectedMistakeId(mistake.id); setMistakePickerOpen(false); }} className="block w-full rounded-lg px-3 py-2 text-left hover:bg-bg-secondary">
                  <div className="truncate text-sm text-text-primary">{firstLine(mistake.question_text || mistake.ocr_text || '未命名错题', 80)}</div>
                  <div className="mt-0.5 text-xs text-text-secondary">{mistake.subject || '未分类'} · {(mistake.tags || []).join('、') || '无标签'}</div>
                </button>
              )) : <div className="px-3 py-5 text-center text-sm text-text-secondary">当前范围没有可用的历史错题</div>}
            </div>
          )}
          <form onSubmit={handleSubmit} className="composer-surface">
            <input ref={attachmentInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/bmp" className="hidden" onChange={(event) => selectAttachment(event.target.files?.[0])} />
            {activeFigure && !figureWorkspaceExpanded && (
              <FigureContextAttachment
                figure={activeFigure}
                onEditRegion={() => setFigureWorkspaceExpanded(true)}
                onOpenSource={openActiveFigureSource}
                onRemove={() => { setActiveFigure(null); setVisualRegion(null); }}
              />
            )}
            {(attachmentPreview || selectedMistakeId) && (
              <div className="composer-attachment">
                {attachmentPreview ? (
                  <img src={attachmentPreview} alt="待解析的题目附件" className="h-12 w-12 rounded-[var(--radius-small)] object-cover" />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-[var(--radius-small)] bg-[var(--accent-soft)] text-accent"><BookMarked className="h-5 w-5" /></div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-text-primary">
                    {attachmentFile?.name || firstLine(cachedMistakes.find((item) => item.id === selectedMistakeId)?.question_text || '历史错题')}
                  </div>
                  {attachmentFile && (
                    <label className="mt-1 inline-flex items-center gap-1.5 text-xs text-text-secondary">
                      <input type="checkbox" checked={importAttachment} onChange={(event) => setImportAttachment(event.target.checked)} className="accent-accent" />
                      解答后导入错题本
                    </label>
                  )}
                </div>
                <button type="button" aria-label="移除附件" onClick={() => { clearAttachment(); setSelectedMistakeId(''); }} className="app-icon-button"><X className="h-4 w-4" /></button>
              </div>
            )}
            <div className="min-w-0 overflow-hidden">
              <MathExpressionList
                expressions={mathExpressions}
                onEdit={handleEditMathExpression}
                onRemove={handleRemoveMathExpression}
                onReference={handleReferenceMathExpression}
              />
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                placeholder={activeFigure ? (visualRegion ? '询问选中区域…' : '询问这幅教材图片…') : mathExpressions.length ? '继续描述问题，点击公式编号可引用…' : '输入问题...'}
                disabled={isLoading || attachmentLoading}
                className="composer-textarea"
              />
            </div>
            <div className="composer-toolbar">
              <div className="composer-tools" role="toolbar" aria-label="问题输入工具">
                <button type="button" disabled={isLoading || attachmentLoading} aria-label="上传题目图片" title="上传题目图片" onClick={() => attachmentInputRef.current?.click()} className="composer-tool-button chat-image-upload-button"><ImagePlus className="h-4 w-4" /><span>图片</span></button>
                <button type="button" disabled={isLoading || attachmentLoading || !bookName} aria-label="选择教材图片" title={bookName ? '选择教材图片' : '请先选择教材'} onClick={openFigureCatalog} className={`composer-tool-button ${activeFigure ? 'is-active' : ''}`}><Images className="h-4 w-4" /><span>教材图</span></button>
                <button type="button" disabled={isLoading || attachmentLoading} aria-label="选择历史错题" title="选择历史错题" onClick={() => void loadCachedMistakes()} className="composer-tool-button"><BookMarked className="h-4 w-4" /><span>错题</span></button>
                <VisualMathInputPopover
                  disabled={isLoading || attachmentLoading}
                  editRequest={mathEditRequest}
                  onAddExpression={handleAddMathExpression}
                  onUpdateExpression={handleUpdateMathExpression}
                />
                <ComposerOverflowMenu>
                  {(close) => (
                    <>
                      <button role="menuitem" type="button" onClick={() => { close(); void showReport('daily'); }} disabled={Boolean(actionLoading)} className="composer-overflow-item"><CalendarDays className="h-3.5 w-3.5" />{actionLoading === 'daily' ? '整理日报' : '学习日报'}</button>
                      <button role="menuitem" type="button" onClick={() => { close(); void showReport('weekly'); }} disabled={Boolean(actionLoading)} className="composer-overflow-item"><CalendarDays className="h-3.5 w-3.5" />{actionLoading === 'weekly' ? '整理周报' : '学习周报'}</button>
                      <button role="menuitem" type="button" onClick={() => { close(); void pickRandomExercise(); }} disabled={Boolean(actionLoading)} className="composer-overflow-item"><Shuffle className="h-3.5 w-3.5" />{actionLoading === 'exercise' ? '抽题中' : '随机抽题'}</button>
                      <button role="menuitem" type="button" onClick={() => { close(); openHighlightDialog(); }} disabled={Boolean(actionLoading)} className="composer-overflow-item"><BookMarked className="h-3.5 w-3.5" />查看/生成重点</button>
                      <button role="menuitem" type="button" onClick={() => { close(); openMistakeQuickCapture(); }} className="composer-overflow-item"><ImagePlus className="h-3.5 w-3.5" />错题速录</button>
                    </>
                  )}
                </ComposerOverflowMenu>
              </div>
              {isLoading || attachmentLoading ? (
                <button type="button" onClick={attachmentLoading ? stopVisualQuestion : stop} className="composer-send is-stopping" aria-label="停止生成" title="停止生成">
                  <Square className="h-4 w-4 fill-current" />
                </button>
              ) : (
                <button type="submit" aria-label="发送问题" title="发送" disabled={attachmentLoading || (!input.trim() && mathExpressions.length === 0 && !attachmentFile && !selectedMistakeId && !activeFigure)} className="composer-send">
                  <Send className="h-4 w-4" />
                </button>
              )}
            </div>
          </form>
        </div>
      </div>
      <HighlightRepositoryDialog
        open={highlightDialogOpen}
        books={books}
        currentBookName={bookName}

        onClose={() => setHighlightDialogOpen(false)}
      />
      <ProblemImageEditor
        file={rawAttachmentFile}
        open={attachmentEditorOpen}
        title="裁剪并增强题目图片"
        onCancel={() => { setAttachmentEditorOpen(false); setRawAttachmentFile(null); if (attachmentInputRef.current) attachmentInputRef.current.value = ''; }}
        onApply={applyAttachmentProcessing}
      />
    </div>
  );
};

export default ChatPage;
