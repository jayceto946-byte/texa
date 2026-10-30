import { TexaTextbook, TexaExercises, TexaMistakes, TexaLearning, TexaSettings, TexaGoals, TexaNotes } from './icons';
import { BarChart3, PanelLeftClose, CircleHelp } from 'lucide-react';
import type { RefObject } from 'react';
import { NavLink } from 'react-router-dom';

const primaryItems = [
  { to: '/', icon: TexaLearning, label: '学习' },
  { to: '/goals', icon: TexaGoals, label: '目标与任务' },
  { to: '/learning', icon: BarChart3, label: '复习' },
  { to: '/notes', icon: TexaNotes, label: '笔记' },
  { to: '/mistakes', icon: TexaMistakes, label: '错题' },
  { to: '/exercises', icon: TexaExercises, label: '练习' },
  { to: '/books', icon: TexaTextbook, label: '教材' },
];

function RailLink({ to, icon: Icon, label }: (typeof primaryItems)[number]) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) => `app-rail-link ${isActive ? 'is-active' : ''}`}
      aria-label={label}
      title={label}
      draggable={false}
    >
      <Icon className="h-[18px] w-[18px]" />
      <span>{label}</span>
    </NavLink>
  );
}

type AppRailProps = {
  mobile: boolean;
  collapsed: boolean;
  onOpenSettings: () => void;
  onCollapse: () => void;
  onHome: () => void;
  settingsButtonRef: RefObject<HTMLButtonElement | null>;
};

export default function AppRail({ collapsed, mobile, onOpenSettings, settingsButtonRef, onCollapse, onHome }: AppRailProps) {
  return (
    <aside className="app-rail" aria-label="产品导航" inert={collapsed}>
      <button className="navigation-collapse app-icon-button" onClick={onCollapse} aria-label="收起侧栏" title="收起侧栏"><PanelLeftClose size={18} /></button>
      <NavLink to="/" onClick={(event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        onHome();
      }} className="app-rail-mark window-no-drag" aria-label="Texa 学习工作区" title="返回学习主页" draggable={false}>
        <span className="app-rail-logo-icon" aria-hidden="true">
          <img src="/brand/texa-mark.svg" alt="" draggable={false} />
        </span>
        <span className="study-brand-name">Texa<span>学习工作区</span></span>
      </NavLink>

      {mobile ? <details className="navigation-domains"><summary>功能与设置</summary>      <nav className="app-rail-primary" aria-label="主要功能">
        {primaryItems.map((item) => <RailLink key={item.to} {...item} />)}
      </nav>

      <nav className="app-rail-footer" aria-label="应用设置">
        <RailLink to="/guide" icon={CircleHelp} label="用户指南" />
        <button ref={settingsButtonRef} type="button" onClick={onOpenSettings} className="app-rail-link" aria-label="设置" title="设置" aria-haspopup="dialog">
          <TexaSettings className="h-[18px] w-[18px]" />
          <span>设置</span>
        </button>
      </nav>
</details> : <>      <nav className="app-rail-primary" aria-label="主要功能">
        {primaryItems.map((item) => <RailLink key={item.to} {...item} />)}
      </nav>

      <nav className="app-rail-footer" aria-label="应用设置">
        <RailLink to="/guide" icon={CircleHelp} label="用户指南" />
        <button ref={settingsButtonRef} type="button" onClick={onOpenSettings} className="app-rail-link" aria-label="设置" title="设置" aria-haspopup="dialog">
          <TexaSettings className="h-[18px] w-[18px]" />
          <span>设置</span>
        </button>
      </nav>
</>}
    </aside>
  );
}
