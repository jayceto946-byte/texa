import { useRef, type KeyboardEvent, type ReactNode } from 'react';

export type Choice<T extends string> = { value: T; label: string; icon?: ReactNode };

type ChoiceProps<T extends string> = {
  label: string;
  value: T;
  options: readonly Choice<T>[];
  onChange: (value: T) => void;
  className?: string;
};

function useChoiceKeys<T extends string>(options: readonly Choice<T>[], onChange: (value: T) => void) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0
      : event.key === 'End' ? options.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + options.length) % options.length;
    onChange(options[next].value);
    buttons.current[next]?.focus();
  };
  return { buttons, onKeyDown };
}

export function SegmentedControl<T extends string>({ label, value, options, onChange, className = '' }: ChoiceProps<T>) {
  const { buttons, onKeyDown } = useChoiceKeys(options, onChange);
  return (
    <div role="radiogroup" aria-label={label} className={`app-segmented-control ${className}`.trim()}>
      {options.map((option, index) => (
        <button
          key={option.value}
          ref={(node) => { buttons.current[index] = node; }}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          tabIndex={value === option.value ? 0 : -1}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => onKeyDown(event, index)}
          className="app-segmented-option"
        >
          {option.icon}{option.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({ label, value, options, onChange, className = '', panelId }: ChoiceProps<T> & { panelId: string }) {
  const { buttons, onKeyDown } = useChoiceKeys(options, onChange);
  return (
    <div role="tablist" aria-label={label} className={`app-tabs ${className}`.trim()}>
      {options.map((option, index) => (
        <button
          key={option.value}
          ref={(node) => { buttons.current[index] = node; }}
          id={`${panelId}-tab-${index}`}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          aria-controls={panelId}
          tabIndex={value === option.value ? 0 : -1}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => onKeyDown(event, index)}
          className="app-tab"
        >
          {option.icon}{option.label}
        </button>
      ))}
    </div>
  );
}
