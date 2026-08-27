import { BarChart3, BookOpen, ClipboardList, GraduationCap, MessageSquare, Settings } from 'lucide-react';
import type { RefObject } from 'react';
import { NavLink } from 'react-router-dom';

const primaryItems = [
  { to: '/', icon: MessageSquare, label: '学习' },
  { to: '/learning', icon: BarChart3, label: '复习' },
  { to: '/mistakes', icon: GraduationCap, label: '错题' },
  { to: '/exercises', icon: ClipboardList, label: '练习' },
  { to: '/books', icon: BookOpen, label: '教材' },
];

function RailLink({ to, icon: Icon, label }: (typeof primaryItems)[number]) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) => `app-rail-link ${isActive ? 'is-active' : ''}`}
      aria-label={label}
      title={label}
    >
      <Icon className="h-[18px] w-[18px]" />
      <span>{label}</span>
    </NavLink>
  );
}

type AppRailProps = {
  onOpenSettings: () => void;
  settingsButtonRef: RefObject<HTMLButtonElement | null>;
};

export default function AppRail({ onOpenSettings, settingsButtonRef }: AppRailProps) {
  return (
    <aside className="app-rail" aria-label="产品导航">
      <NavLink to="/" className="app-rail-mark" aria-label="Texa 学习工作区" title="Texa">
        <span className="app-rail-logo-icon" aria-hidden="true">
          <img src="/brand/texa-mark.svg" alt="" />
        </span>
      </NavLink>

      <nav className="app-rail-primary" aria-label="主要功能">
        {primaryItems.map((item) => <RailLink key={item.to} {...item} />)}
      </nav>

      <nav className="app-rail-footer" aria-label="应用设置">
        <button ref={settingsButtonRef} type="button" onClick={onOpenSettings} className="app-rail-link" aria-label="设置" title="设置" aria-haspopup="dialog">
          <Settings className="h-[18px] w-[18px]" />
          <span>设置</span>
        </button>
      </nav>
    </aside>
  );
}
