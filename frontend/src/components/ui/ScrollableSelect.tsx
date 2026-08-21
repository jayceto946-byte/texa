import { Check, ChevronDown } from 'lucide-react';
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export type ScrollableSelectOption = {
  value: string;
  label: string;
  description?: string;
  group?: string;
};

type Props = {
  ariaLabel: string;
  value: string;
  options: ScrollableSelectOption[];
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
};

type Placement = {
  bottom?: number;
  left: number;
  maxHeight: number;
  top?: number;
  width: number;
};

export default function ScrollableSelect({ ariaLabel, value, options, onChange, className = '', placeholder = '请选择' }: Props) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = options[selectedIndex];

  const close = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) requestAnimationFrame(() => triggerRef.current?.focus());
  };

  const choose = (index: number) => {
    const option = options[index];
    if (!option) return;
    if (option.value !== value) onChange(option.value);
    close(true);
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !listRef.current?.contains(target)) close();
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const updatePlacement = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const edge = 8;
      const gap = 4;
      const preferredWidth = Math.max(rect.width, 280);
      const width = Math.min(preferredWidth, window.innerWidth - edge * 2);
      const left = Math.min(Math.max(rect.left, edge), window.innerWidth - width - edge);
      const below = window.innerHeight - rect.bottom - edge - gap;
      const above = rect.top - edge - gap;
      const openAbove = below < 180 && above > below;
      const maxHeight = Math.max(120, Math.min(256, openAbove ? above : below));
      setPlacement(openAbove
        ? { bottom: window.innerHeight - rect.top + gap, left, maxHeight, width }
        : { top: rect.bottom + gap, left, maxHeight, width });
    };
    updatePlacement();
    window.addEventListener('resize', updatePlacement);
    window.addEventListener('scroll', updatePlacement, true);
    return () => {
      window.removeEventListener('resize', updatePlacement);
      window.removeEventListener('scroll', updatePlacement, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const nextIndex = selectedIndex >= 0 ? selectedIndex : 0;
    setActiveIndex(nextIndex);
    requestAnimationFrame(() => {
      listRef.current?.focus();
      document.getElementById(`${listId}-option-${nextIndex}`)?.scrollIntoView({ block: 'nearest' });
    });
  }, [listId, open, selectedIndex]);

  const onListKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!options.length) return;
    let nextIndex: number;
    if (event.key === 'ArrowDown') nextIndex = Math.min(options.length - 1, activeIndex + 1);
    else if (event.key === 'ArrowUp') nextIndex = Math.max(0, activeIndex - 1);
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = options.length - 1;
    else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      choose(activeIndex);
      return;
    } else if (event.key === 'Escape') {
      event.preventDefault();
      close(true);
      return;
    } else if (event.key === 'Tab') {
      close();
      return;
    } else return;
    event.preventDefault();
    setActiveIndex(nextIndex);
    document.getElementById(`${listId}-option-${nextIndex}`)?.scrollIntoView({ block: 'nearest' });
  };

  return (
    <div ref={rootRef} className={`relative min-w-0 ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
          event.preventDefault();
          setOpen(true);
        }}
        className="flex min-h-10 w-full items-center gap-2 rounded-md border border-border bg-bg-card px-3 text-left type-control text-text-primary outline-none hover:border-accent/45 focus:border-accent focus:ring-2 focus:ring-[var(--accent-soft)]"
      >
        <span className="min-w-0 flex-1 truncate">
          <span>{selected?.label || value || placeholder}</span>
          {selected?.description && <span className="ml-2 text-text-secondary">{selected.description}</span>}
        </span>
        <ChevronDown className={`h-4 w-4 flex-none text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>

      {open && placement && createPortal(
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          aria-activedescendant={`${listId}-option-${activeIndex}`}
          tabIndex={0}
          onKeyDown={onListKeyDown}
          className="app-scrollable-select-popover app-popover-enter fixed z-[1400] outline-none"
          style={{ bottom: placement.bottom, left: placement.left, top: placement.top, width: placement.width }}
        >
          <div className="app-scrollable-select-list p-1.5" style={{ maxHeight: placement.maxHeight }}>
            {options.map((option, index) => {
              const showGroup = option.group && option.group !== options[index - 1]?.group;
              const isSelected = option.value === value;
              const isActive = index === activeIndex;
              return (
                <div key={option.value}>
                  {showGroup && <div className="px-2 pb-1 pt-2 type-caption font-medium text-text-tertiary first:pt-1">{option.group}</div>}
                  <div
                    id={`${listId}-option-${index}`}
                    role="option"
                    aria-selected={isSelected}
                    onPointerMove={() => setActiveIndex(index)}
                    onPointerDown={(event) => event.preventDefault()}
                    onClick={() => choose(index)}
                    className={`app-scrollable-select-option ${isSelected ? 'is-selected' : ''} ${isActive ? 'is-active' : ''}`}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      <span>{option.label}</span>
                      {option.description && <span className="ml-2 text-text-secondary">{option.description}</span>}
                    </span>
                    {isSelected && <Check className="h-4 w-4 flex-none text-accent" aria-hidden="true" />}
                  </div>
                </div>
              );
            })}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
