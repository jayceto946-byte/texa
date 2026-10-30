/** Icon acceptance only: actual product components, synthetic in-memory responses. */
import '@fontsource/jetbrains-mono/latin-400.css';
import '../../index.css';
import { StrictMode, useEffect } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ChatProvider, useChatContext } from '../../contexts/ChatContext';
import { InspectorProvider } from '../../contexts/InspectorContext';
import FocusProvider from '../../features/focus/FocusProvider';
import MainLayout from '../../layouts/MainLayout';
import ChatPage from '../../pages/ChatPage';
import NotesPage from '../../pages/NotesPage';
import GoalsPage from '../../pages/GoalsPage';
import SystemHealth from '../../components/SystemHealth';
import { applyTexaTheme } from '../../theme';

applyTexaTheme('mineral');
const created = '2026-10-30T09:00:00+08:00';
const management = { state: 'active', pinned: false, revision: 1 };
const messages = [{ id: 'q', role: 'user', content: '偏导数是什么意思', turn_id: 'turn' }, { id: 'a', role: 'assistant', content: '偏导数表示函数沿一个坐标方向的变化率。', turn_id: 'turn' }];
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input : input.url, location.href);
  if (!url.pathname.startsWith('/api/')) return nativeFetch(input, init);
  if (init?.method && init.method !== 'GET') return new Response(JSON.stringify({success:false,message:'图标预览不提交业务操作'}), {status:405,headers:{'Content-Type':'application/json'}});
  const path = url.pathname.slice(4);
  let data: unknown = [];
  if (path === '/chat/conversations') {
    const rows = [{ id: 'icon-fixture', title: '偏导数是什么意思', subject: '数学', book_name: '', updated_at: created, message_count: 2, management }];
    data = url.searchParams.has('view') ? { items: rows, next_cursor: null, has_more: false } : rows;
  }
  if (path === '/chat/conversations/icon-fixture') data = { id:'icon-fixture', messages, subject:'数学', book_name:'', management, page:{has_more:false,total:2,limit:40} };
  if (path.endsWith('/management')) data = management;
  if (path === '/focus') data = {revision:0,runtime_id:'icon-preview',snapshot_sequence:1,tasks:[],next_offset:null,current_task:null,current_session:null,next_task:null,goal_stats:[],status:'idle',reason:'',checkpoint_at:null,active_ms:0,remaining_seconds:null,overtime_seconds:0,server_time:Date.now()/1000};
  if (path === '/system/settings') data = {subjects:[{name:'数学',children:['高数','线代','概率论']}],env:{}};
  if (path === '/notes' || path === '/notes/drafts') data = {items:path === '/notes' ? [{id:'icon-note',title:'偏导数的定义与计算',abstract:'固定其他变量，考察选定方向的变化率。',subject:'数学',tags:['偏导数'],status:'active',revision:1,updated_at:created,chapter_refs:[],origins:[{conversation_id:'icon-fixture',title_snapshot:'偏导数是什么意思',captured_at:created}]}] : [],next_cursor:null};
  if (path === '/notes/filters') data = {books:[],chapter_refs:[]};
  if (path === '/goals') data = [{id:'icon-goal',revision:1,status:'paused',title:'复习偏导数的定义与计算',objective:'理解偏导数并复习教材例题。',scope:{},contract:{success_criteria:[]},created_at:created,updated_at:created}];
  return new Response(JSON.stringify({success:true,data}), {headers:{'Content-Type':'application/json'}});
};
function Seed({ children }: {children:ReactNode}) {
  const { loadConversation } = useChatContext();
  useEffect(() => { loadConversation('icon-fixture', [{id:'q',role:'user',turnId:'turn',content:'偏导数是什么意思'}, {id:'a',role:'assistant',turnId:'turn',stage:'done',content:'## 定义\n\n偏导数表示函数沿一个坐标方向的变化率。\n\n$$f_x=2xy$$'}], {subject:'数学',bookName:''}); }, [loadConversation]);
  return children;
}
const scene = new URLSearchParams(location.search).get('scene') || 'chat';
const entry = ({chat:'/',notes:'/notes',books:'/books',goals:'/goals'} as Record<string,string>)[scene] || '/';
createRoot(document.getElementById('root')!).render(<StrictMode><ChatProvider><FocusProvider><InspectorProvider><MemoryRouter initialEntries={[entry]}><Seed><Routes><Route path="/" element={<MainLayout/>}><Route index element={<ChatPage/>}/><Route path="notes" element={<NotesPage/>}/><Route path="books" element={<SystemHealth standaloneTab="subjects"/>}/><Route path="goals" element={<GoalsPage/>}/></Route></Routes></Seed></MemoryRouter></InspectorProvider></FocusProvider></ChatProvider></StrictMode>);
