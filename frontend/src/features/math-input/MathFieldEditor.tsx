import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import type { MathfieldElement } from 'mathlive';
import 'mathlive/fonts.css';

interface MathFieldEditorProps {
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  ariaLabel?: string;
}

export interface MathFieldEditorHandle {
  insert: (latex: string) => void;
}

const MathFieldEditor = forwardRef<MathFieldEditorHandle, MathFieldEditorProps>(({ value, onChange, autoFocus = false, ariaLabel = '公式编辑器' }, ref) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const mathfieldRef = useRef<MathfieldElement | null>(null);
  const valueRef = useRef(value);
  const onChangeRef = useRef(onChange);
  const [ready, setReady] = useState(false);

  const focusWithoutPageShift = (mathfield: MathfieldElement) => {
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    const focusableElement: HTMLElement = mathfield;
    focusableElement.focus({ preventScroll: true });
    requestAnimationFrame(() => {
      if (window.scrollX !== scrollX || window.scrollY !== scrollY) window.scrollTo(scrollX, scrollY);
    });
  };

  useImperativeHandle(ref, () => ({
    insert(latex: string) {
      const mathfield = mathfieldRef.current;
      if (!mathfield) return;
      const scrollX = window.scrollX;
      const scrollY = window.scrollY;
      mathfield.executeCommand(['typedText', latex, {
        focus: false,
        feedback: false,
        simulateKeystroke: true,
      }]);
      focusWithoutPageShift(mathfield);
      if (window.scrollX !== scrollX || window.scrollY !== scrollY) window.scrollTo(scrollX, scrollY);
    },
  }));

  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    let disposed = false;
    let mathfield: MathfieldElement | null = null;

    void import('mathlive').then(({ MathfieldElement }) => {
      if (disposed || !hostRef.current) return;
      MathfieldElement.fontsDirectory = null;
      MathfieldElement.soundsDirectory = null;

      const initialValue = valueRef.current;
      mathfield = new MathfieldElement();
      mathfield.value = initialValue;
      mathfield.position = 0;
      mathfield.smartFence = true;
      mathfield.smartSuperscript = true;
      mathfield.mathVirtualKeyboardPolicy = 'manual';
      // MathLive otherwise calls host.scrollIntoView() during typing and IME composition.
      mathfield.onScrollIntoView = () => {};
      mathfield.setAttribute('aria-label', ariaLabel);
      mathfield.className = 'visual-math-field';

      let pageScrollX = window.scrollX;
      let pageScrollY = window.scrollY;
      const rememberPagePosition = () => {
        pageScrollX = window.scrollX;
        pageScrollY = window.scrollY;
      };
      const restorePagePosition = () => requestAnimationFrame(() => {
        if (window.scrollX !== pageScrollX || window.scrollY !== pageScrollY) window.scrollTo(pageScrollX, pageScrollY);
      });

      const handleInput = () => onChangeRef.current(mathfield?.value ?? '');
      mathfield.addEventListener('input', handleInput);
      mathfield.addEventListener('pointerdown', rememberPagePosition, { capture: true });
      mathfield.addEventListener('focusin', restorePagePosition);
      hostRef.current.replaceChildren(mathfield);
      mathfieldRef.current = mathfield;
      setReady(true);

      if (autoFocus) requestAnimationFrame(() => {
        if (!mathfield) return;
        focusWithoutPageShift(mathfield);
        if (initialValue.includes('\\placeholder')) {
          mathfield.position = 0;
          mathfield.executeCommand('moveToNextPlaceholder');
        }
      });
    });

    return () => {
      disposed = true;
      if (mathfield) mathfield.remove();
      mathfieldRef.current = null;
    };
  }, [ariaLabel, autoFocus]);

  useEffect(() => {
    const mathfield = mathfieldRef.current;
    if (mathfield && mathfield.value !== value) mathfield.setValue(value, { silenceNotifications: true });
  }, [value]);

  return (
    <div className="relative min-h-16">
      {!ready && <div className="absolute inset-0 flex items-center px-3 type-caption text-text-secondary">正在加载可视化公式编辑器...</div>}
      <div ref={hostRef} className={ready ? '' : 'invisible'} />
    </div>
  );
});

MathFieldEditor.displayName = 'MathFieldEditor';

export default MathFieldEditor;
