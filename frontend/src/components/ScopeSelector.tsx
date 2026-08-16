import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, Check, ChevronDown, ChevronRight, GraduationCap } from 'lucide-react';
import { get } from '../api/client';
import { scopeContainsBook, type TextbookScopeOption } from '../utils/textbookScopes';

export type ScopeBookOption = TextbookScopeOption;

type SubjectNode = {
  name: string;
  children?: string[];
};

type Placement = 'top' | 'bottom';
type Width = 'compact' | 'normal' | 'wide';
type BookMode = 'optional' | 'hidden';

const DEFAULT_SUBJECT_TREE: SubjectNode[] = [
  { name: '数学', children: ['高数', '线代', '概率论'] },
  { name: '英语', children: ['阅读', '写作', '翻译', '词汇'] },
  { name: '政治', children: ['马原', '毛中特', '史纲', '思修'] },
  { name: '专业课', children: [] },
];

function clean(value = '') {
  return value.trim().replace(/^\/+|\/+$/g, '');
}

function unique(values: string[]) {
  return Array.from(new Set(values.map(clean).filter(Boolean)));
}

function splitSubject(value = '') {
  const raw = clean(value);
  if (!raw.includes('/')) return { parent: raw, child: '' };
  const [parent, ...rest] = raw.split('/');
  return { parent: clean(parent), child: clean(rest.join('/')) };
}

function subjectValue(parent: string, child = '') {
  const nextParent = clean(parent);
  const nextChild = clean(child);
  return nextChild ? `${nextParent}/${nextChild}` : nextParent;
}

function addNode(target: SubjectNode[], parent: string, child = '') {
  const nextParent = clean(parent);
  const nextChild = clean(child);
  if (!nextParent) return;
  let node = target.find((item) => item.name === nextParent);
  if (!node) {
    node = { name: nextParent, children: [] };
    target.push(node);
  }
  if (nextChild) {
    node.children = unique([...(node.children || []), nextChild]);
  }
}

function mergeSubjectTree(managed: SubjectNode[], suggestions: string[], books: ScopeBookOption[]) {
  const merged: SubjectNode[] = [];
  const ingest = (value: string) => {
    const { parent, child } = splitSubject(value);
    addNode(merged, parent, child);
  };

  DEFAULT_SUBJECT_TREE.forEach((node) => {
    addNode(merged, node.name);
    (node.children || []).forEach((child) => addNode(merged, node.name, child));
  });
  managed.forEach((node) => {
    addNode(merged, node.name);
    (node.children || []).forEach((child) => addNode(merged, node.name, child));
  });
  suggestions.forEach(ingest);
  books.forEach((book) => ingest(book.subject || ''));

  return merged.filter((node) => node.name);
}

function inferSubject(value: string, tree: SubjectNode[]) {
  const raw = clean(value);
  if (!raw) return { parent: '', child: '', value: '' };
  const direct = splitSubject(raw);
  if (direct.child) return { ...direct, value: subjectValue(direct.parent, direct.child) };

  const parentNode = tree.find((node) => node.name === raw);
  if (parentNode) return { parent: raw, child: '', value: raw };

  const matches = tree
    .filter((node) => (node.children || []).includes(raw))
    .map((node) => ({ parent: node.name, child: raw, value: subjectValue(node.name, raw) }));
  return matches[0] || { parent: raw, child: '', value: raw };
}

function matchesSubject(recordSubject = '', selectedSubject = '') {
  const selected = clean(selectedSubject);
  if (!selected) return true;
  const record = clean(recordSubject);
  if (!record) return false;
  if (record === selected) return true;

  const selectedParts = splitSubject(selected);
  const recordParts = splitSubject(record);
  if (selectedParts.child) {
    return record === selectedParts.child || (recordParts.parent === selectedParts.parent && recordParts.child === selectedParts.child);
  }
  return recordParts.parent === selectedParts.parent || record === selectedParts.parent;
}

function subjectLabel(value = '') {
  const { parent, child } = splitSubject(value);
  if (!parent) return '全部学科';
  return child ? `${parent} / ${child}` : parent;
}

function widthClass(width: Width) {
  if (width === 'compact') return 'w-[176px] sm:w-[190px]';
  if (width === 'wide') return 'w-[232px] sm:w-[260px]';
  return 'w-[204px] sm:w-[224px]';
}

export default function ScopeSelector({
  subject,
  bookName = '',
  books = [],
  onSubjectChange,
  onBookChange,
  suggestions = [],
  label = '选择科目',
  placeholder = '选择科目',
  allowAllSubjects = false,
  bookMode = 'optional',
  placement = 'bottom',
  align = 'left',
  width = 'normal',
  disabled = false,
  fullWidth = false,
  className = '',
}: {
  subject: string;
  bookName?: string;
  books?: ScopeBookOption[];
  onSubjectChange: (value: string) => void;
  onBookChange?: (value: string) => void;
  suggestions?: string[];
  label?: string;
  placeholder?: string;
  allowAllSubjects?: boolean;
  bookMode?: BookMode;
  placement?: Placement;
  align?: 'left' | 'right';
  width?: Width;
  disabled?: boolean;
  fullWidth?: boolean;
  className?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [popupStyle, setPopupStyle] = useState<CSSProperties | null>(null);
  const [managedSubjects, setManagedSubjects] = useState<SubjectNode[]>([]);

  useEffect(() => {
    let cancelled = false;
    get('/system/settings/subjects', 15000)
      .then((res) => {
        if (cancelled || !res?.success) return;
        setManagedSubjects(Array.isArray(res.data) ? res.data : []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const updatePopupPosition = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;
    const margin = 12;
    const gap = 8;
    const popupWidth = fullWidth ? rect.width : Math.min(720, window.innerWidth - margin * 2);
    const preferredLeft = align === 'right' ? rect.right - popupWidth : rect.left;
    const left = Math.max(margin, Math.min(preferredLeft, window.innerWidth - popupWidth - margin));
    const above = Math.max(0, rect.top - margin);
    const below = Math.max(0, window.innerHeight - rect.bottom - margin);
    const openAbove = placement === 'top' ? above >= 180 || above >= below : below < 180 && above > below;
    const availableHeight = Math.max(120, (openAbove ? above : below) - gap);
    setPopupStyle({
      position: 'fixed',
      width: popupWidth,
      left,
      maxHeight: Math.min(560, availableHeight),
      ...(openAbove
        ? { bottom: window.innerHeight - rect.top + gap, top: 'auto' }
        : { top: rect.bottom + gap, bottom: 'auto' }),
    });
  }, [align, fullWidth, placement]);

  useLayoutEffect(() => {
    if (!open) {
      setPopupStyle(null);
      return;
    }
    updatePopupPosition();
    const reposition = () => updatePopupPosition();
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [open, updatePopupPosition]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !popupRef.current?.contains(target)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const scopeBooks = books;
  const tree = useMemo(() => mergeSubjectTree(managedSubjects, suggestions, scopeBooks), [managedSubjects, suggestions, scopeBooks]);
  const active = useMemo(() => inferSubject(subject, tree), [subject, tree]);
  const activeParent = active.parent || (allowAllSubjects ? '' : tree[0]?.name || '');
  const activeNode = activeParent ? tree.find((node) => node.name === activeParent) : undefined;
  const activeSubject = active.value;
  const visibleBooks = useMemo(
    () => scopeBooks.filter((book) => {
      const normalized = inferSubject(book.subject || '', tree).value || book.subject || '';
      return matchesSubject(normalized, activeSubject) || matchesSubject(book.subject || '', activeSubject);
    }),
    [scopeBooks, activeSubject, tree]
  );

  const currentBook = scopeBooks.find((book) => scopeContainsBook(book, bookName));
  const popupGridClass = fullWidth
    ? 'grid-cols-1 divide-y divide-border'
    : bookMode === 'hidden'
      ? 'grid-cols-1 divide-y divide-border sm:grid-cols-[170px_minmax(0,1fr)] sm:divide-x sm:divide-y-0'
      : 'grid-cols-1 divide-y divide-border sm:grid-cols-[160px_190px_minmax(0,1fr)] sm:divide-x sm:divide-y-0';
  const valueText = bookMode === 'hidden'
    ? (activeSubject ? subjectLabel(activeSubject) : placeholder)
    : `${activeSubject ? subjectLabel(activeSubject) : '全部学科'} · ${currentBook?.displayName || currentBook?.name || (visibleBooks.length ? '选择教材' : '通用 QA')}`;

  const selectSubject = (nextSubject: string) => {
    onSubjectChange(nextSubject);
    if (onBookChange && bookName) {
      const book = scopeBooks.find((item) => scopeContainsBook(item, bookName));
      const normalized = inferSubject(book?.subject || '', tree).value || book?.subject || '';
      if (!book || (!matchesSubject(normalized, nextSubject) && !matchesSubject(book.subject || '', nextSubject))) onBookChange('');
    }
  };

  const selectBook = (name: string) => {
    if (!onBookChange) return;
    const book = scopeBooks.find((item) => item.name === name);
    if (book?.subject) onSubjectChange(inferSubject(book.subject, tree).value || book.subject);
    onBookChange(name);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className={`relative min-w-0 ${fullWidth ? 'w-full' : 'max-w-full shrink'} ${className}`}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((next) => !next)}
        disabled={disabled}
        aria-label={label}
        className={`app-interactive flex h-9 ${fullWidth ? 'w-full min-w-0' : widthClass(width)} max-w-full items-center gap-2 rounded-[var(--radius-medium)] border border-border bg-bg-card px-3 text-left text-sm text-text-primary outline-none hover:border-accent/50 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-55`}
      >
        <GraduationCap className="h-4 w-4 flex-shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium leading-5">{valueText}</span>
        <ChevronDown className={`h-4 w-4 flex-shrink-0 text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && createPortal(
        <div
          ref={popupRef}
          style={popupStyle || { visibility: 'hidden' }}
          className="app-popover-enter z-[1100] overflow-y-auto rounded-[var(--radius-large)] border border-border bg-bg-card shadow-lg"
        >
          <div className={`grid ${popupGridClass}`}>
            <Column title="一级科目">
              {allowAllSubjects && (
                <OptionButton active={!activeSubject} onClick={() => selectSubject('')}>
                  全部学科
                </OptionButton>
              )}
              {tree.map((node) => (
                <OptionButton key={node.name} active={node.name === activeParent} onClick={() => selectSubject(node.name)}>
                  <span className="truncate">{node.name}</span>
                  <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-text-secondary" />
                </OptionButton>
              ))}
            </Column>

            <Column title="二级科目">
              {activeNode ? (
                <>
                  <OptionButton active={activeSubject === activeNode.name} onClick={() => selectSubject(activeNode.name)}>
                    全部{activeNode.name}
                  </OptionButton>
                  {(activeNode.children || []).map((child) => {
                    const value = subjectValue(activeNode.name, child);
                    return (
                      <OptionButton key={child} active={activeSubject === value} onClick={() => selectSubject(value)}>
                        {child}
                      </OptionButton>
                    );
                  })}
                  {!(activeNode.children || []).length && <EmptyLine text="该一级科目暂无二级科目" />}
                </>
              ) : (
                <EmptyLine text="先选择一级科目" />
              )}
            </Column>

            {bookMode !== 'hidden' && (
              <Column title="教材范围">
                {!visibleBooks.length && (
                  <OptionButton active={!bookName} onClick={() => selectBook('')}>
                    <span className="flex min-w-0 items-center gap-2">
                      <BookOpen className="h-3.5 w-3.5 flex-shrink-0 text-accent" />
                      <span className="truncate">通用 QA</span>
                    </span>
                  </OptionButton>
                )}
                {visibleBooks.map((book) => (
                  <OptionButton key={book.name} active={scopeContainsBook(book, bookName)} onClick={() => selectBook(book.name)}>
                    <span className="min-w-0">
                      <span className="block truncate">{book.displayName || book.name}</span>
                      {book.subject && <span className="block truncate text-[11px] font-normal text-text-secondary">{subjectLabel(book.subject)}</span>}
                    </span>
                  </OptionButton>
                ))}
              </Column>
            )}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-0 min-w-0 bg-bg-card sm:min-h-[220px]">
      <div className="border-b border-border px-3 py-2 text-[11px] font-medium text-text-secondary">{title}</div>
      <div className="max-h-[160px] space-y-1 overflow-y-auto p-2 sm:max-h-[330px]">{children}</div>
    </div>
  );
}

function OptionButton({ active, onClick, children }: { active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`app-interactive flex min-h-9 w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] outline-none focus-visible:ring-2 focus-visible:ring-accent/15 ${
        active ? 'bg-[var(--accent-soft)] font-semibold text-accent-hover' : 'text-text-primary hover:bg-bg-secondary'
      }`}
    >
      <span className="flex min-w-0 flex-1 items-center justify-between gap-2 truncate">{children}</span>
      {active && <Check className="h-3.5 w-3.5 flex-shrink-0 text-accent" />}
    </button>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs leading-5 text-text-secondary">{text}</div>;
}
