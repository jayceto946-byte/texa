import { Code2, Sigma, Eye } from 'lucide-react';
import { createContext, useContext, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import type { Root, Element, Text, RootContent } from 'hast';
import type { Root as MarkdownRoot, Nodes } from 'mdast';
import Dialog from '../../components/ui/Dialog';
import MathFieldEditor from '../math-input/MathFieldEditor';
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

type EditContext = { disabled: boolean; label: string; replace: (start: number, end: number, text: string) => void; openFormula: (item: Formula) => void };
const EditorContext = createContext<EditContext | null>(null);

function EditableText({ text, onInput, label, disabled, placeholder, onFinish }: { text: string; onInput: (text: string) => void; label: string; disabled: boolean; placeholder?: string; onFinish?: () => void }) {
  const [initial] = useState(text);
  const element = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (element.current && document.activeElement !== element.current && element.current.textContent !== text) element.current.textContent = text;
  }, [text]);
  return <span ref={element} className={placeholder ? 'rendered-editor-empty' : 'rendered-edit-text'} data-placeholder={placeholder} contentEditable={disabled ? false : 'plaintext-only'} suppressContentEditableWarning role="textbox" aria-label={label} onInput={event => onInput(event.currentTarget.innerText)} onBlur={onFinish}>{initial}</span>;
}

const EditorSpan: Components['span'] = ({ node, children, className, ...props }) => {
  const context = useContext(EditorContext)!;
  const start = Number(node?.properties['data-start']);
  const end = Number(node?.properties['data-end']);
  if (className?.includes('rendered-edit-formula')) {
    const item = { start, end, latex: String(node?.properties['data-latex'] || ''), display: node?.properties['data-display'] === true || node?.properties['data-display'] === 'true' };
    return <span className={className} data-start={start} data-end={end} role="button" tabIndex={context.disabled ? -1 : 0} aria-label="编辑公式" onClick={() => !context.disabled && context.openFormula(item)} onKeyDown={event => { if (!context.disabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); context.openFormula(item); } }}>{children}</span>;
  }
  if (className?.includes('rendered-edit-text')) return <EditableText text={node?.children.map(n => n.type === 'text' ? n.value : '').join('') || ''} label={context.label} disabled={context.disabled} onInput={text => context.replace(start, end, text)} />;
  return <span className={className} {...props}>{children}</span>;
};
const components: Components = { span: EditorSpan };

/** Editable rendered text; formulas use the learning composer's visual editor. */
export function RenderedMathEditor({ value, onChange, label, disabled = false, heading, actions }: { value: string; onChange: (value: string) => void; label: string; disabled?: boolean; heading?: string; actions?: ReactNode }) {
  const [formula, setFormula] = useState<Formula | null>(null);
  const [latex, setLatex] = useState('');
  const [emptyInput, setEmptyInput] = useState(!value);
  const [sourceEditing, setSourceEditing] = useState(false);
  const openFormula = (item: Formula) => { setFormula(item); setLatex(item.latex); };
  const saveFormula = (remove = false) => {
    if (!formula) return;
    onChange(replaceSourceFormula(value, formula.start, formula.end, latex, formula.display, remove));
    setEmptyInput(false);
    setFormula(null);
  };
  return <EditorContext.Provider value={{ disabled, label, replace: (start, end, text) => onChange(replaceSourceText(value, start, end, text)), openFormula }}><div className="rendered-editor" aria-label={label}>
    <div className="rendered-editor-header">
      {heading && <h3>{heading}</h3>}
      <div className="rendered-editor-tools">
        {actions}
        <button type="button" className="app-icon-button" disabled={disabled} aria-label={sourceEditing ? '可视化编辑' : '编辑原文'} title={sourceEditing ? '可视化编辑' : '编辑原文'} aria-pressed={sourceEditing} onClick={() => { setSourceEditing(!sourceEditing); setEmptyInput(false); }}>{sourceEditing ? <Eye size={16} /> : <Code2 size={16} />}</button>
        <button type="button" className="rendered-insert-formula app-icon-button" aria-label="插入公式" title="插入公式" disabled={disabled} onClick={() => openFormula({ start: value.length, end: value.length, latex: '', display: true })}><Sigma size={16} /></button>
      </div>
    </div>
    <div className="rendered-editor-body">
      {sourceEditing ? <textarea className="rendered-editor-source" aria-label={`${label}原文`} value={value} onChange={event => onChange(event.target.value)} disabled={disabled} rows={5} /> : emptyInput || !value ? <EditableText text={value} label={label} disabled={disabled} placeholder={`填写${label}`} onInput={onChange} onFinish={() => setEmptyInput(false)} /> : <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath, markMathSources]} rehypePlugins={[editableSources, [rehypeKatex, { strict: false, throwOnError: false }]]} components={components}>{value}</ReactMarkdown>}
    </div>
    <Dialog open={Boolean(formula)} title="编辑公式" onClose={() => setFormula(null)} dismissOnBackdrop className="rendered-formula-dialog">
      <h2>编辑公式</h2><MathFieldEditor value={latex} onChange={setLatex} ariaLabel="可视化编辑公式" autoFocus />
      <footer><button className="app-ghost-button" onClick={() => saveFormula(true)}>删除公式</button><div><button className="app-secondary-button" onClick={() => setFormula(null)}>取消</button><button className="app-primary-button" onClick={() => saveFormula()} disabled={!latex.trim()}>保存</button></div></footer>
    </Dialog>
  </div></EditorContext.Provider>;
}

/** A labelled learning-content field shared by intake, correction and answer drafts. */
export function MathContentField(props: Parameters<typeof RenderedMathEditor>[0]) {
  return <section className="math-content-field"><RenderedMathEditor {...props} heading={props.label} /></section>;
}
