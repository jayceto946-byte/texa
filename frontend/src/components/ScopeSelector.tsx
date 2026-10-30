import { TexaTextbook } from './icons';
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, ChevronRight, GraduationCap } from 'lucide-react';
import { get } from '../api/client';
import { formatLearningScopeLabel, scopeContainsBook, type TextbookScopeOption } from '../utils/textbookScopes';
import { scopePopoverLayout } from '../utils/scopePopover';
import './ScopeSelector.css';

export type ScopeBookOption = TextbookScopeOption;

export type ScopeSubjectNode = {
  name: string;
  children?: string[];
};

type Placement = 'top' | 'bottom';
type Width = 'compact' | 'normal' | 'wide';
type BookMode = 'optional' | 'hidden';

const DEFAULT_SUBJECT_TREE: ScopeSubjectNode[] = [
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

function addNode(target: ScopeSubjectNode[], parent: string, child = '') {
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

function mergeSubjectTree(managed: ScopeSubjectNode[], suggestions: string[], books: ScopeBookOption[]) {
  const merged: ScopeSubjectNode[] = [];
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

function inferSubject(value: string, tree: ScopeSubjectNode[]) {
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

export default function ScopeSelector({
  subject,
  bookName = '',
  books = [],
  onSubjectChange,
  onBookChange,
  suggestions = [],
  subjectTree,
  label = '选择科目',
  placeholder = '选择科目',
  allowAllSubjects = false,
  bookMode = 'optional',
  emptyBookLabel,
  placement = 'bottom',
  align = 'left',
  width = 'normal',
  disabled = false,
  fullWidth = false,
  className = '',
  size = 'normal',
  popupSize = 'normal',
  onOpenChange,
}: {
  subject: string;
  bookName?: string;
  books?: ScopeBookOption[];
  onSubjectChange: (value: string) => void;
  onBookChange?: (value: string) => void;
  suggestions?: string[];
  subjectTree?: ScopeSubjectNode[];
  label?: string;
  placeholder?: string;
  allowAllSubjects?: boolean;
  bookMode?: BookMode;
  emptyBookLabel?: string;
  placement?: Placement;
  align?: 'left' | 'right';
  width?: Width;
  disabled?: boolean;
  fullWidth?: boolean;
  className?: string;
  size?: 'compact' | 'normal' | 'form';
  popupSize?: 'compact' | 'normal';
  onOpenChange?: (open: boolean, id: string) => void;
}) {
  const id = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const keyboardOpen = useRef(false);
  const [open, setOpen] = useState(false);
  const [popupStyle, setPopupStyle] = useState<CSSProperties | null>(null);
  const [popupLayout, setPopupLayout] = useState('books');
  const [loadedSubjects, setLoadedSubjects] = useState<ScopeSubjectNode[]>([]);
  useEffect(() => { onOpenChange?.(open, id); return () => onOpenChange?.(false, id); }, [id, onOpenChange, open]);
  const close = useCallback(() => { setOpen(false); rootRef.current?.querySelector('button')?.focus({ preventScroll: true }); }, []);
  useEffect(() => {
    if (open && popupStyle && keyboardOpen.current) {
      keyboardOpen.current = false;
      popupRef.current?.querySelector<HTMLButtonElement>('.scope-option[data-selected="true"],.scope-option')?.focus({ preventScroll: true });
    }
  }, [open, popupStyle]);

  useEffect(() => {
    if (subjectTree) return;
    let cancelled = false;
    get('/system/settings/subjects', 15000)
      .then((res) => {
        if (cancelled || !res?.success) return;
        setLoadedSubjects(Array.isArray(res.data) ? res.data : []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [subjectTree]);

  const updatePopupPosition = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;
    const layout = scopePopoverLayout({ anchor: rect, viewport: { width: window.innerWidth, height: window.innerHeight }, subjectOnly: bookMode === 'hidden', compact: popupSize === 'compact', placement, align });
    setPopupLayout(layout.layout);
    setPopupStyle({
      position: 'fixed',
      width: layout.width,
      left: layout.left,
      maxHeight: layout.maxHeight,
      ...(layout.openAbove ? { bottom: layout.edge, top: 'auto' } : { top: layout.edge, bottom: 'auto' }),
    });
  }, [align, bookMode, placement, popupSize]);

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
      if (event.key === 'Escape') { event.preventDefault(); close(); }
    };
    const onFocus = (event: FocusEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !popupRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('focusin', onFocus);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('focusin', onFocus);
    };
  }, [close, open]);

  const scopeBooks = books;
  const managedSubjects = subjectTree || loadedSubjects;
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
  const valueText = bookMode === 'hidden'
    ? (activeSubject ? subjectLabel(activeSubject) : placeholder)
    : formatLearningScopeLabel(
        activeSubject || '全部学科',
        currentBook?.displayName || currentBook?.name || emptyBookLabel || (visibleBooks.length ? '选择教材' : '通用 QA'),
      );

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
    close();
  };

  return (
    <div ref={rootRef} data-scope-size={size} data-scope-width={width} data-full-width={fullWidth} className={`scope-selector ${className}`}>
      <button
        type="button"
        onClick={event => { if (!disabled) { keyboardOpen.current = event.detail === 0; setOpen(next => !next); } }}
        onKeyDown={event => { if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); keyboardOpen.current = true; setOpen(true); } }}
        disabled={disabled}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? id : undefined}
        className="app-interactive scope-trigger"
      >
        <GraduationCap className="h-4 w-4 flex-shrink-0 text-accent" />
        <span className="scope-trigger-value" title={valueText}>{valueText}</span>
        <ChevronDown className={`h-4 w-4 flex-shrink-0 text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && createPortal(
        <div
          ref={popupRef}
          id={id}
          role="dialog"
          aria-label={label}
          data-layout={popupLayout}
          data-density={popupSize}
          style={popupStyle || { visibility: 'hidden' }}
          className="scope-popover app-popover-enter"
          onKeyDown={event => {
            const target = event.target as HTMLElement;
            const column = target.closest('.scope-column');
            const columns = Array.from(popupRef.current?.querySelectorAll('.scope-column') || []);
            const items = Array.from(column?.querySelectorAll<HTMLButtonElement>('.scope-option') || []);
            const index = items.indexOf(target as HTMLButtonElement);
            let next: HTMLButtonElement | undefined;
            if (event.key === 'ArrowDown') next = items[(index + 1) % items.length];
            if (event.key === 'ArrowUp') next = items[(index - 1 + items.length) % items.length];
            if (event.key === 'Home') next = items[0];
            if (event.key === 'End') next = items.at(-1);
            if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') next = columns[columns.indexOf(column!) + (event.key === 'ArrowRight' ? 1 : -1)]?.querySelector<HTMLButtonElement>('.scope-option[data-selected="true"],.scope-option') || undefined;
            if (next) { event.preventDefault(); next.focus(); }
          }}
        >
          <div className="scope-grid">
            <Column title="学科">
              {allowAllSubjects && (
                <OptionButton active={!activeSubject} onClick={() => { selectSubject(''); if (bookMode === 'hidden') close(); }}>
                  全部学科
                </OptionButton>
              )}
              {tree.map((node) => (
                <OptionButton key={node.name} active={Boolean(activeSubject) && node.name === activeParent} onClick={() => selectSubject(node.name)}>
                  <span className="truncate">{node.name}</span>
                  <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-text-secondary" />
                </OptionButton>
              ))}
            </Column>

            <Column title="细分方向">
              {activeNode ? (
                <>
                  <OptionButton active={activeSubject === activeNode.name} onClick={() => { selectSubject(activeNode.name); if (bookMode === 'hidden') close(); }}>
                    全部{activeNode.name}
                  </OptionButton>
                  {(activeNode.children || []).map((child) => {
                    const value = subjectValue(activeNode.name, child);
                    return (
                      <OptionButton key={child} active={activeSubject === value} onClick={() => { selectSubject(value); if (bookMode === 'hidden') close(); }}>
                        {child}
                      </OptionButton>
                    );
                  })}
                  {!(activeNode.children || []).length && <EmptyLine text="暂无细分方向" />}
                </>
              ) : (
                <EmptyLine text="先选择学科" />
              )}
            </Column>

            {bookMode !== 'hidden' && (
              <Column title="教材范围">
                {!visibleBooks.length && (
                  <OptionButton active={!bookName} onClick={() => selectBook('')}>
                    <span className="flex min-w-0 items-center gap-2">
                      <TexaTextbook className="h-3.5 w-3.5 flex-shrink-0 text-accent" />
                      <span className="truncate">{emptyBookLabel || '通用 QA'}</span>
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
    <section className="scope-column" aria-label={title}>
      <h3 className="scope-column-title">{title}</h3>
      <div className="scope-options">{children}</div>
    </section>
  );
}

function OptionButton({ active, onClick, children }: { active?: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-selected={Boolean(active)}
      className="app-interactive scope-option"
    >
      <span className="scope-option-label">{children}</span>
      {active && <Check className="h-3.5 w-3.5 flex-shrink-0 text-accent" />}
    </button>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <p className="scope-empty">{text}</p>;
}
