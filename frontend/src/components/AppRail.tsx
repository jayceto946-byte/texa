import { BarChart3, BookOpen, ClipboardList, GraduationCap, MessageSquare, Settings } from 'lucide-react';
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

export default function AppRail() {
  return (
    <aside className="app-rail" aria-label="产品导航">
      <NavLink to="/" className="app-rail-mark" aria-label="Texa 学习工作区" title="Texa">
        <span className="app-rail-logo-icon"><BookOpen className="h-5 w-5" /></span>
      </NavLink>

      <nav className="app-rail-primary" aria-label="主要功能">
        {primaryItems.map((item) => <RailLink key={item.to} {...item} />)}
      </nav>

      <nav className="app-rail-footer" aria-label="应用设置">
        <RailLink to="/settings" icon={Settings} label="设置" />
      </nav>
    </aside>
  );
}
