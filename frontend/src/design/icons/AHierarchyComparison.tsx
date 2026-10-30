import { aPrevious } from './aPrevious';
import { CandidateIcon, IconGlyph } from './CandidateIcon';
const revisions = [
  { id: 'compose', label: '动态命题', reason: '保留原页框与题干短线，将加号缩小到原跨度的一半，完整收进页内。' },
  { id: 'verify', label: '数学验证', reason: '保留原括号与内容短线，缩小勾选，放在框内右下的留白处。' },
  { id: 'retrieve', label: '教材检索', reason: '恢复初版教材检索图形，保留外置放大镜与原有比例。' },
  { id: 'extract', label: '知识抽取', reason: '段落与箭头分行排布，移除额外方块；箭头不穿页边。' },
  { id: 'mistakes', label: '错题', reason: '三行细点模拟题目条目；叉号缩小 50%，放在最后一行末尾，底部留白。' },
];
export function AHierarchyComparison({ onSelect }: { onSelect: (name: string) => void }) {
  return <section id="a-refinement" className="ib-section">
    <div className="ib-section-title"><div><span className="ib-kicker">A / HIERARCHY REFINEMENT</span><h2>先分清主次，再组合图形</h2></div><span>A 为当前深化方向 · 16 / 24 / 32 px</span></div>
    <p className="ib-refinement-lead">保留已选中的图形结构，重点校正动作符号的大小与留白：检索用初版，抽取保留新版。</p>
    <div className="ib-revisions" role="table" aria-label="A 方案层级修改前后对比">
      <div className="ib-revision-grid ib-revision-head" role="row"><span role="columnheader">语义</span><span role="columnheader">初版参考</span><span role="columnheader">当前采用</span><span role="columnheader">处理方式</span></div>
      {revisions.map(row => <div className="ib-revision-grid ib-revision-row" role="row" key={row.id}>
        <div role="cell"><button onClick={() => onSelect(row.id)} aria-label={`查看 A ${row.label}修订`}><strong>{row.label}</strong><small>{row.id}</small></button></div>
        <div role="cell" className="ib-revision-icons ib-revision-before">{[16, 24, 32].map(size => <span key={size}><IconGlyph shape={aPrevious[row.id]} size={size} /><small>{size}</small></span>)}</div>
        <div role="cell" className="ib-revision-icons">{[16, 24, 32].map(size => <span key={size}><CandidateIcon name={row.id} direction="A" size={size} /><small>{size}</small></span>)}</div>
        <p role="cell">{row.reason}</p>
      </div>)}
    </div>
  </section>;
}
