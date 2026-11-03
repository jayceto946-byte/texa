import { Code2, Sigma } from 'lucide-react';
import { createContext, useContext, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import type { Root, Element, Text, RootContent } from 'hast';
import type { Root as MarkdownRoot, Nodes } from 'mdast';
import Dialog from '../../components/ui/Dialog';
import { MathFormulaToolbox } from './MathFormulaToolbox';
import { ReadingMarkdown } from './ReadingMarkdown';
import './rendered-math-editor.css';
import { replaceSourceText, replaceSourceFormula } from './sourceTextEdit';

/** Preserve original Markdown offsets, including delimiters and table structure. */
function markMathSources() {
  return (tree: MarkdownRoot) => {
    const visit = (node: Nodes) => {
      if (node.type === 'math' || node.type === 'inlineMath') {
        node.data = { ...node.data, hProperties: { ...(node.data?.hProperties as object),
          'data-math-start': node.position?.start.offset, 'data-math-end': node.position?.end.offset,
          'data-math-value': node.value, 'data-math-display': node.type === 'math' } };
      }
      if ('children' in node) node.children.forEach(visit);
    };
    visit(tree);
  };
}

function editableSources() {
  return (tree: Root) => {
    const visit = (parent: Root | Element) => {
      parent.children = parent.children.map(child => {
        if (child.type === 'element') {
          if (child.properties['data-math-start'] != null) {
            const properties = child.properties;
            return { type: 'element', tagName: 'span', properties: { className: ['rendered-edit-formula'],
              'data-start': properties['data-math-start'], 'data-end': properties['data-math-end'],
              'data-latex': properties['data-math-value'], 'data-display': properties['data-math-display'] }, children: [child] } as Element;
          }
          if (child.tagName !== 'code' && child.tagName !== 'pre') visit(child);
          // Flow math is generated inside a pre element; keep the surrounding document surface.
          if (child.tagName === 'pre' && child.children.some(n => n.type === 'element' && n.properties['data-math-start'] != null)) {
            visit(child); child.tagName = 'div'; child.properties.className = ['rendered-edit-equation'];
          }
          return child;
        }
        const text = child as Text;
        if (child.type === 'text' && text.value.trim() && text.position?.start.offset != null && text.position?.end.offset != null) {
          return { type: 'element', tagName: 'span', properties: { className: ['rendered-edit-text'],
            'data-start': text.position.start.offset, 'data-end': text.position.end.offset }, children: [text] } as Element;
        }
        return child;
      }) as RootContent[] & Element['children'];
    };
    visit(tree);
  };
}


type Formula = { start: number; end: number; latex: string; display: boolean };

type EditContext = { disabled: boolean; label: string; replace: (start: number, end: number, text: string) => void; openFormula: (item: Formula, anchor: HTMLElement) => void };
const EditorContext = createContext<EditContext | null>(null);

function EditableText({ text, onInput, label, disabled, placeholder, onFinish, sourceStart }: { sourceStart?: number; text: string; onInput: (text: string) => void; label: string; disabled: boolean; placeholder?: string; onFinish?: () => void }) {
  const [initial] = useState(text);
  const element = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (element.current && document.activeElement !== element.current && element.current.textContent !== text) element.current.textContent = text;
  }, [text]);
  return <span ref={element} data-start={sourceStart} className={placeholder ? 'rendered-editor-empty' : 'rendered-edit-text'} data-placeholder={placeholder} contentEditable={disabled ? false : 'plaintext-only'} suppressContentEditableWarning role="textbox" aria-label={label} onInput={event => onInput(event.currentTarget.innerText)} onBlur={onFinish}>{initial}</span>;
}

const EditorSpan: Components['span'] = ({ node, children, className, ...props }) => {
  const context = useContext(EditorContext)!;
  const start = Number(node?.properties['data-start']);
  const end = Number(node?.properties['data-end']);
  if (className?.includes('rendered-edit-formula')) {
    const item = { start, end, latex: String(node?.properties['data-latex'] || ''), display: node?.properties['data-display'] === true || node?.properties['data-display'] === 'true' };
    return <span className={className} data-start={start} data-end={end} role="button" tabIndex={context.disabled ? -1 : 0} aria-label="编辑公式" onClick={event => !context.disabled && context.openFormula(item, event.currentTarget)} onKeyDown={event => { if (!context.disabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); context.openFormula(item, event.currentTarget); } }}>{children}</span>;
  }
  if (className?.includes('rendered-edit-text')) return <EditableText sourceStart={start} text={node?.children.map(n => n.type === 'text' ? n.value : '').join('') || ''} label={context.label} disabled={context.disabled} onInput={text => context.replace(start, end, text)} />;
  return <span className={className} {...props}>{children}</span>;
};
const components: Components = { span: EditorSpan };

/** Editable rendered text; formulas use the learning composer's visual editor. */
export function RenderedMathEditor({ value, onChange, label, disabled = false, heading, actions }: { value: string; onChange: (value: string) => void; label: string; disabled?: boolean; heading?: string; actions?: ReactNode }) {
  const [formula, setFormula] = useState<Formula | null>(null);
  const [latex, setLatex] = useState('');
  const [emptyInput, setEmptyInput] = useState(!value);
  const [sourceEditing, setSourceEditing] = useState(false);
  const [sourceDraft, setSourceDraft] = useState('');
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const insertion = useRef<number | null>(null);
  const editor = useRef<HTMLDivElement>(null);
  const openFormula = (item: Formula, target: HTMLElement) => { setAnchor(target); setFormula(item); setLatex(item.latex); };
  const rememberInsertion = () => {
    const selection = window.getSelection();
    const node = selection?.anchorNode;
    const element = node?.nodeType === Node.ELEMENT_NODE ? node as HTMLElement : node?.parentElement;
    const text = element?.closest<HTMLElement>('.rendered-edit-text[data-start]');
    if (text && editor.current?.contains(text) && selection?.rangeCount) {
      const range = selection.getRangeAt(0).cloneRange();
      range.selectNodeContents(text); range.setEnd(selection.anchorNode!, selection.anchorOffset);
      insertion.current = Number(text.dataset.start) + range.toString().length;
    }
  };
  const saveFormula = (remove = false) => {
    if (!formula) return;
    onChange(replaceSourceFormula(value, formula.start, formula.end, latex, formula.display, remove));
    setEmptyInput(false);
    insertion.current = null;
    setFormula(null);
  };
  return <EditorContext.Provider value={{ disabled, label, replace: (start, end, text) => onChange(replaceSourceText(value, start, end, text)), openFormula }}><div ref={editor} className="rendered-editor" aria-label={label} onMouseUp={rememberInsertion} onKeyUp={rememberInsertion}>
    <div className="rendered-editor-header">
      {heading && <h3>{heading}</h3>}
      <div className="rendered-editor-tools">
        {actions}
        <button type="button" className="app-icon-button" disabled={disabled} aria-label="编辑原文" title="编辑 Markdown 原文与预览" onClick={() => { setSourceDraft(value); setSourceEditing(true); }}><Code2 size={16} /></button>
        <button type="button" className="rendered-insert-formula app-icon-button" aria-label="数学符号工具箱" title="数学符号工具箱" aria-haspopup="dialog" aria-expanded={Boolean(formula)} disabled={disabled} onMouseDown={event => event.preventDefault()} onClick={event => { if (formula) setFormula(null); else { const position = insertion.current ?? value.length; openFormula({ start: position, end: position, latex: '', display: false }, event.currentTarget); } }}><Sigma size={16} /></button>
      </div>
    </div>
    <div className="rendered-editor-body">
      {emptyInput || !value ? <EditableText text={value} label={label} disabled={disabled} placeholder={`填写${label}`} onInput={onChange} onFinish={() => setEmptyInput(false)} /> : <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath, markMathSources]} rehypePlugins={[editableSources, [rehypeKatex, { strict: false, throwOnError: false }]]} components={components}>{value}</ReactMarkdown>}
    </div>
    {formula && anchor && <MathFormulaToolbox anchor={anchor} latex={latex} display={formula.display} editing={formula.start !== formula.end} onChange={setLatex} onDisplayChange={display => setFormula({ ...formula, display })} onSave={() => saveFormula()} onRemove={() => saveFormula(true)} onClose={() => setFormula(null)} />}
    <Dialog open={sourceEditing} title="编辑原文" onClose={() => setSourceEditing(false)} dismissOnBackdrop className="rendered-source-dialog">
      <h2>编辑原文</h2><div className="rendered-source-columns"><textarea className="rendered-editor-source" aria-label={`${label}原文`} value={sourceDraft} onChange={event => setSourceDraft(event.target.value)} rows={10} /><div className="rendered-source-preview" aria-label="公式与排版预览"><ReadingMarkdown content={sourceDraft} /></div></div>
      <footer><button type="button" className="app-secondary-button" onClick={() => setSourceEditing(false)}>取消</button><button type="button" className="app-primary-button" onClick={() => { onChange(sourceDraft); setEmptyInput(false); setSourceEditing(false); }}>应用修改</button></footer>
    </Dialog>
  </div></EditorContext.Provider>;
}

/** A labelled learning-content field shared by intake, correction and answer drafts. */
export function MathContentField(props: Parameters<typeof RenderedMathEditor>[0]) {
  return <section className="math-content-field"><RenderedMathEditor {...props} heading={props.label} /></section>;
}
