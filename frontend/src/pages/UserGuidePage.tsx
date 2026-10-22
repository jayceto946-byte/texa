import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Copy, Maximize2, X } from 'lucide-react';
import Dialog from '../components/ui/Dialog';
import { SegmentedControl } from '../components/ui/SelectionControls';
import { guideScenes } from '../features/guide/content';
import '../features/guide/guide.css';

function GuideCommand({ label, text }: { label: string; text: string }) {
  const [feedback, setFeedback] = useState('');
  return <div className="guide-command"><div className="guide-command-header"><span>{label}</span><button type="button" className="app-ghost-button" aria-label={`复制：${label}`} onClick={async () => {
    try { await navigator.clipboard.writeText(text); setFeedback('已复制'); }
    catch { setFeedback('复制失败，请选中命令复制'); }
  }}><Copy size={14} />复制</button></div><pre tabIndex={0} aria-label={label}><code>{text}</code></pre><span className="guide-copy-feedback" role="status">{feedback}</span></div>;
}

export default function UserGuidePage() {
  const [params, setParams] = useSearchParams();
  const scene = guideScenes.find(item => item.id === params.get('scene')) || guideScenes[0];
  const index = Math.max(0, scene.steps.findIndex(item => item.id === params.get('step')));
  const step = scene.steps[index];
  const [enlarged, setEnlarged] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const shouldFocus = useRef(false);
  const navigate = useNavigate();
  const select = (sceneId: string, stepId: string, focusHeading = true) => {
    shouldFocus.current = focusHeading;
    setParams({ scene: sceneId, step: stepId });
  };
  useEffect(() => {
    scroll.current?.scrollTo(0, 0);
    if (shouldFocus.current) { heading.current?.focus(); shouldFocus.current = false; }
  }, [scene.id, step.id]);
  const nextScene = guideScenes[guideScenes.indexOf(scene) + 1];

  return <div className="management-workspace user-guide">
    <header className="app-page-header guide-header window-drag-region"><h1 className="app-page-title">用户指南</h1><Link className="app-ghost-button" to="/">返回学习</Link></header>
    <div className="guide-scenarios"><SegmentedControl label="指南场景" value={scene.id} options={guideScenes.map(item => ({ value: item.id, label: item.title }))} onChange={id => select(id, guideScenes.find(item => item.id === id)!.steps[0].id, false)} /></div>
    <div className="guide-body">
      <nav className="guide-index" aria-label={`${scene.title}步骤`}><p>{scene.title}</p><ol>{scene.steps.map((item, i) => <li key={item.id}><button type="button" aria-current={item.id === step.id ? 'step' : undefined} onClick={() => select(scene.id, item.id)}><span>{i + 1}</span>{item.title}</button></li>)}</ol></nav>
      <div className="guide-scroll" ref={scroll}>
        <article className="guide-article" aria-labelledby="guide-step-heading">
          <p className="guide-description">{scene.description}</p>
          <p className="guide-progress">第 {index + 1} 步 / 共 {scene.steps.length} 步</p>
          <h2 id="guide-step-heading" ref={heading} tabIndex={-1}>{step.title}</h2>
          <ol className="guide-instructions">{step.instructions.map(text => <li key={text}>{text}</li>)}</ol>
          <figure className="guide-figure"><button type="button" onClick={() => setEnlarged(true)} aria-label={`放大截图：${step.title}`}><img src={`/guide/${step.image}.png`} alt={step.alt} loading="lazy" width={1280} height={820} /><span><Maximize2 size={14} />放大查看</span></button><figcaption>当前桌面界面 · 示例资料</figcaption></figure>
          {step.warning && <p className="guide-warning" role="note"><strong>请留意</strong>{step.warning}</p>}
          {step.sections?.map(section => <section className="guide-section" key={section.title}><h3>{section.title}</h3>{section.paragraphs.map(text => <p key={text}>{text}</p>)}{section.commands?.map(command => <GuideCommand key={command.label} {...command} />)}</section>)}
          <p className="guide-result"><strong>完成后</strong>{step.result}</p>
          {step.more && <details className="guide-more" key={step.id}><summary>{step.more.title}</summary><p>{step.more.text}</p></details>}
          {step.resources && <div className="guide-resources"><p>官方参考 · 核对于 2026-10-19</p>{step.resources.map(resource => <a key={resource.url} href={resource.url} target="_blank" rel="noreferrer">{resource.label}</a>)}</div>}
          <div className="guide-actions">{step.actions.map(action => 'to' in action ? <Link key={action.label} className="app-secondary-button" to={action.to}>{action.label}<ArrowRight size={14} /></Link> : <button key={action.label} type="button" className="app-secondary-button" onClick={() => navigate({ pathname: '/guide', search: params.toString() }, { state: { openSettings: true, settingsTab: action.settings } })}>{action.label}<ArrowRight size={14} /></button>)}</div>
          <footer className="guide-pagination"><button type="button" className="app-ghost-button" disabled={index === 0} onClick={() => select(scene.id, scene.steps[index - 1].id)}><ArrowLeft size={15} />上一步</button>{index < scene.steps.length - 1 ? <button type="button" className="app-primary-button" onClick={() => select(scene.id, scene.steps[index + 1].id)}>下一步<ArrowRight size={15} /></button> : nextScene ? <button type="button" className="app-primary-button" onClick={() => select(nextScene.id, nextScene.steps[0].id)}>{nextScene.title}<ArrowRight size={15} /></button> : <Link className="app-primary-button" to="/">回到学习<ArrowRight size={15} /></Link>}</footer>
        </article>
      </div>
    </div>
    <Dialog open={enlarged} onClose={() => setEnlarged(false)} title={step.title} className="guide-image-dialog"><header><h2>{step.title}</h2><button type="button" className="app-icon-button" aria-label="关闭截图" onClick={() => setEnlarged(false)}><X size={18} /></button></header><div className="guide-image-scroll"><img src={`/guide/${step.image}.png`} alt={step.alt} /></div></Dialog>
  </div>;
}
