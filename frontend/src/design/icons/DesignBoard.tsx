import { BarChart3 } from 'lucide-react';
import '@fontsource/jetbrains-mono/latin-400.css';
import { StrictMode, useState } from 'react';
import type { CSSProperties } from 'react';
import { createRoot } from 'react-dom/client';
import { TEXA_THEMES } from '../../theme';
import '../../index.css';
import '../../layouts/ApprovedWorkspace.css';
import { CandidateIcon, svgAsset } from './CandidateIcon';
import { AHierarchyComparison } from './AHierarchyComparison';
import { samples, directions } from './catalog';
import type { Direction } from './geometry';
import './board.css';
const sizes = [16, 20, 24, 32];
function DesignBoard() {
  const [themeId, setTheme] = useState('mineral');
  const [size, setSize] = useState(24);
  const [tier, setTier] = useState(0);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState('retrieve');
  const [direction, setDirection] = useState<Direction>('A');
  const [activeNav, setActiveNav] = useState('books');
  const [status, setStatus] = useState('选择图标可查看尺寸与 SVG。');
  const [draft, setDraft] = useState('');
  const theme = TEXA_THEMES.find(t => t.id === themeId)!;
  const sample = samples.find(s => s.id === selected)!;
  const filtered = samples.filter(s => (!tier || s.tier === tier) && `${s.label} ${s.id}`.toLowerCase().includes(query.toLowerCase()));
  const icon = (name: string, px = 20) => <CandidateIcon name={name} direction={direction} size={px} />;
  function download() {
    const url = URL.createObjectURL(new Blob([svgAsset(selected, direction, size)], { type: 'image/svg+xml' }));
    const a = document.createElement('a'); a.href = url; a.download = `texa-${direction}-${selected}-${size}.svg`; a.click(); URL.revokeObjectURL(url);
    setStatus(`已导出 ${direction} / ${selected} / ${size}px`);
  }
  return <div className="icon-board" style={theme.tokens as CSSProperties}>
    <header className="ib-masthead"><a href="#comparison" className="ib-wordmark">Texa<span>DESIGN STUDIES / 01</span></a><span className="ib-edition">图标系统探索 · 2026.10</span><label>主题<select value={themeId} onChange={e => setTheme(e.target.value)}>{TEXA_THEMES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</select></label></header>
    <main className="ib-main">
      <section className="ib-intro"><div><p className="ib-kicker">TECHNICAL MINIMALISM × EDITORIAL DESIGN</p><h1>让功能拥有清晰的形状。</h1><p className="ib-lead">20 个语义，3 套造型语言。从单枚轮廓到学习工作区，检视一套图标如何共同成立。</p></div><div className="ib-scope"><span>当前阶段</span><strong>审计 / 探索 / 原型</strong><span>60 枚原创 SVG · 保留现有产品图标</span></div></section>
      <nav className="ib-jump" aria-label="设计板章节"><a href="#a-refinement">A 本轮调整</a><a href="#comparison">01 并排比较</a><a href="#sizes">02 尺寸检查</a><a href="#context">03 产品语境</a><a href="#review">04 设计评审</a></nav>
      <AHierarchyComparison onSelect={name => { setSelected(name); setDirection('A'); setStatus('已选择 A 的层级修订，可在尺寸区检查或导出。'); }} />
      <section id="comparison" className="ib-section"><div className="ib-section-title"><div><span className="ib-kicker">01 / COMPARISON</span><h2>同一语义，四种表达</h2></div><span>点击任一候选，检查局部细节</span></div>
        <div className="ib-controls"><label className="ib-search">搜索语义<input value={query} onChange={e => setQuery(e.target.value)} placeholder="教材 / retrieve" /></label><label>层级<select value={tier} onChange={e => setTier(Number(e.target.value))}><option value={0}>全部 · 20</option><option value={1}>T1 通用操作</option><option value={2}>T2 产品导航</option><option value={3}>T3 Texa 专属</option></select></label><fieldset><legend>显示尺寸</legend>{sizes.map(n => <button key={n} aria-pressed={size === n} onClick={() => setSize(n)}>{n}<small>px</small></button>)}</fieldset></div>
        <div className="ib-comparison" role="table" aria-label="现有与三套候选比较"><div className="ib-grid ib-table-head" role="row"><span role="columnheader">语义 / SEMANTIC</span><span role="columnheader">现有 <small>Lucide / 状态</small></span>{directions.map(d => <span role="columnheader" key={d.id}><b>{d.id}</b> {d.name}<small>{d.title}</small></span>)}</div>
        {filtered.map((s, index) => <div className={`ib-grid ib-icon-row ${selected === s.id ? 'is-selected' : ''}`} role="row" key={s.id}><div role="cell" className="ib-semantic"><small>{String(index + 1).padStart(2, '0')} / T{s.tier}</small><strong>{s.label}</strong><span>{s.id}</span></div><div role="cell" className="ib-existing" title={s.source}>{s.existing ? <s.existing size={size} strokeWidth={2} aria-hidden="true" /> : <span className="ib-no-icon">无独立图标</span>}</div>{directions.map(d => <div role="cell" key={d.id}><button className="ib-candidate" aria-label={`${d.id} ${s.label}`} aria-pressed={selected === s.id && direction === d.id} onClick={() => { setSelected(s.id); setDirection(d.id); }}><CandidateIcon name={s.id} direction={d.id} size={size} /></button></div>)}</div>)}
        {!filtered.length && <p className="ib-empty">没有匹配的语义。试试“教材”或清空搜索。</p>}</div><p className="ib-note">现有栏显示源码中对应符号；教材检索和数学验证目前复用来源与状态图标。悬停现有图标可看来源。T3 是候选语义，不新增功能入口。预览侧栏保持实际导航次序；复习图标保留现有 BarChart3，不计入 20 个样本。</p>
      </section>
      <section id="sizes" className="ib-section"><div className="ib-section-title"><div><span className="ib-kicker">02 / OPTICAL CHECK</span><h2>{sample.label} <em>/ {selected}</em></h2></div><button className="app-secondary-button" onClick={download}>导出 {direction} · {size}px SVG</button></div><div className="ib-size-panel">{directions.map(d => <div className="ib-size-row" key={d.id}><strong>{d.id} <span>{d.name}</span></strong>{sizes.map(n => <div key={n}><div className="ib-specimen"><CandidateIcon direction={d.id} name={selected} size={n} /></div><small>{n} px</small></div>)}</div>)}</div><p className="ib-note">A 的抽取与 C 的五个复杂图标在 16px 使用减笔版本。画布按 1:1 CSS 像素显示，禁止容器覆写描边。</p></section>
      <section id="context" className="ib-section"><div className="ib-section-title"><div><span className="ib-kicker">03 / IN CONTEXT</span><h2>放回学习工作区</h2></div><fieldset><legend>预览方案</legend>{directions.map(d => <button key={d.id} aria-pressed={direction === d.id} onClick={() => setDirection(d.id)}>{d.id} · {d.name}</button>)}</fieldset></div>
        <div className="ib-workspace"><aside className="ib-sidebar"><div className="ib-product-name">Texa <small>学习工作区</small></div><nav aria-label="候选导航预览">{['learning', 'goals', 'review', 'notes', 'mistakes', 'exercises', 'books'].map(id => id === 'review' ? { id, label: '复习' } : samples.find(s => s.id === id)!).map(s => <button key={s.id} className={`ib-nav-link ${activeNav === s.id ? 'is-active' : ''}`} aria-pressed={activeNav === s.id} onClick={() => setActiveNav(s.id)}>{s.id === 'review' ? <BarChart3 size={18} aria-hidden="true" /> : icon(s.id, 18)}<span>{s.label}</span></button>)}</nav><button className="ib-nav-link" onClick={() => setStatus('设置按钮预览；主题可在设计板顶部切换。')}>{icon('settings', 18)}设置</button></aside>
        <div className="ib-canvas"><header className="ib-toolbar"><strong>{samples.find(s => s.id === activeNav)?.label || '复习'}</strong><div><button className="app-icon-button" title="搜索" aria-label="预览搜索" onClick={() => setStatus('搜索按钮预览。')}>{icon('search', 16)}</button><button className="app-icon-button" title="编辑" aria-label="预览编辑" onClick={() => setStatus('编辑按钮预览。')}>{icon('edit', 16)}</button><button className="app-icon-button" disabled aria-label="删除不可用">{icon('delete', 16)}</button></div></header>
          <article className="ib-document"><p className="ib-kicker">教材片段 / 第三章</p><h3>在内容与操作之间，保留阅读空间。</h3><p>一枚图标应当提示下一步动作。与教材、笔记和练习同时出现时，清楚的功能差异比单独的造型更重要。</p><div className="ib-context-actions"><button className="app-secondary-button" onClick={() => setStatus('教材检索 · 候选操作已选中。')}>{icon('retrieve', 16)}检索教材</button><button className="app-ghost-button" onClick={() => setStatus('已选择整理笔记预览。')}>{icon('notes', 16)}整理为笔记</button></div><div className="ib-feature-cards">{['extract', 'verify', 'agent'].map(id => <button key={id} onClick={() => { setSelected(id); setStatus(`已选择 ${samples.find(s => s.id === id)?.label}。`); }}>{icon(id, 24)}<strong>{samples.find(s => s.id === id)?.label}</strong><span>{id === 'extract' ? '从段落到知识条目' : id === 'verify' ? '检查可验证的运算' : '有边界的步骤执行'}</span></button>)}</div></article>
          <div className="ib-composer"><label htmlFor="ib-draft">输入操作预览</label><textarea id="ib-draft" placeholder="围绕当前教材，写下一个问题……" value={draft} onChange={e => setDraft(e.target.value)} /><div><button className="app-icon-button" aria-label="预览图片输入" onClick={() => setStatus('图片输入按钮预览。')}>{icon('image', 20)}</button><button className="app-primary-button" disabled={!draft.trim()} onClick={() => { setStatus('已预览发送状态。此设计板不调用模型。'); setDraft(''); }}>{icon('send', 16)}发送</button></div></div>
        </div></div>
        <div className="ib-states" aria-label="交互状态比较">{['默认', '悬停', '选中', '禁用'].map((state, i) => <div key={state}><button className={`ib-state-button state-${i}`} disabled={i === 3} aria-label={`${state}状态样本`} aria-pressed={i === 2} onClick={() => setStatus(`${state}状态样本`)}>{icon(selected, 20)}</button><span>{state}</span></div>)}<span className="ib-note">悬停为固定样本；其余按钮支持真实 hover 与键盘焦点。</span></div><p role="status" className="ib-live">{status}</p>
      </section>
      <section id="review" className="ib-section"><div className="ib-section-title"><div><span className="ib-kicker">04 / DESIGN REVIEW</span><h2>取舍，而非风格投票</h2></div><span>初步设计判断 · 非用户识别测试</span></div><div className="ib-rationales">{directions.map(d => <article key={d.id}><span className="ib-direction-letter">{d.id}</span><h3>{d.title}</h3><p>{d.rationale}</p></article>)}</div><div className="ib-recommendation"><span>当前深化方向 · 根据本轮反馈</span><h3>A 精密几何，先理清图形层级</h3><p>保持 A 的清晰线框与内容结构。命题和验证以较小的框内动作符号表达；检索恢复初版，抽取保留新版，错题用三行细点表现记录，末行末尾放置缩小一半的叉号，底部留白。B、C 保留作探索对照，生产迁移仍未启动。</p></div></section>
      <footer className="ib-footer"><span>Texa / Icon System Studies</span><span>独立开发入口 · 不连接 API · 主题选择不写入产品偏好</span></footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><DesignBoard /></StrictMode>);
