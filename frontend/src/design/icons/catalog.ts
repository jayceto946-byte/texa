import { Search, X, ArrowLeft, Settings, Trash2, Pencil, Copy, MessageSquare, BookOpen, ClipboardList, GraduationCap, NotebookPen, Target, BrainCircuit, Check, Shuffle, Send, ImagePlus } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
export type Sample = { id: string; label: string; tier: 1 | 2 | 3; existing?: LucideIcon; source: string };
export const samples: Sample[] = [
  { id: 'search', label: '搜索', tier: 1, existing: Search, source: 'MistakesPage / ExercisesPage · Search' },
  { id: 'close', label: '关闭', tier: 1, existing: X, source: 'ContextInspector · X' },
  { id: 'back', label: '返回', tier: 1, existing: ArrowLeft, source: 'BooksPage · ArrowLeft' },
  { id: 'settings', label: '设置', tier: 1, existing: Settings, source: 'AppRail · Settings' },
  { id: 'delete', label: '删除', tier: 1, existing: Trash2, source: 'LibraryWorkbench · Trash2' },
  { id: 'edit', label: '编辑', tier: 1, existing: Pencil, source: 'LibraryWorkbench · Pencil' },
  { id: 'copy', label: '复制', tier: 1, existing: Copy, source: 'UserGuidePage · Copy' },
  { id: 'learning', label: '学习', tier: 2, existing: MessageSquare, source: 'AppRail · MessageSquare' },
  { id: 'books', label: '教材', tier: 2, existing: BookOpen, source: 'AppRail · BookOpen' },
  { id: 'exercises', label: '练习与题库', tier: 2, existing: ClipboardList, source: 'AppRail · ClipboardList' },
  { id: 'mistakes', label: '错题', tier: 2, existing: GraduationCap, source: 'AppRail · GraduationCap' },
  { id: 'notes', label: '笔记', tier: 2, existing: NotebookPen, source: 'AppRail · NotebookPen' },
  { id: 'goals', label: '目标与任务', tier: 2, existing: Target, source: 'AppRail · Target' },
  { id: 'retrieve', label: '教材检索', tier: 3, existing: BookOpen, source: 'ExecutionTrace 来源 · BookOpen；并非独立检索标识' },
  { id: 'extract', label: '知识抽取', tier: 3, existing: BrainCircuit, source: 'LearningPage 完善知识关联 · BrainCircuit' },
  { id: 'verify', label: '数学验证', tier: 3, existing: Check, source: 'ExecutionTrace 完成状态 · Check；无独立数学验证图标' },
  { id: 'agent', label: '受控执行', tier: 3, source: '现有执行记录使用状态符号；无独立 Agent 图标' },
  { id: 'compose', label: '动态命题', tier: 3, existing: Shuffle, source: 'ChatPage · Shuffle；仅作探索，不增加产品入口' },
  { id: 'send', label: '发送', tier: 1, existing: Send, source: 'ChatPage · Send' },
  { id: 'image', label: '图片输入', tier: 1, existing: ImagePlus, source: 'ChatPage · ImagePlus' },
];
export const directions = [
  { id: 'A', title: 'Precision Geometry', name: '精密几何', rationale: '当前深化方向。以线框与预留负空间组织成熟隐喻；命题和验证保留内容并缩小框内动作；教材检索保留初版外置镜片。辨识直接，但产品身份仍较弱。' },
  { id: 'B', title: 'Editorial Minimalism', name: '编辑极简', rationale: '用实心书脊、标题带与不对称轮廓建立阅读节奏。单枚辨识快；实心与空心交替时重量偏差明显，删除和发送过重。' },
  { id: 'C', title: 'Texa Original', name: '页边索引', rationale: '以页边索引和段落操作连接教材、抽取与验证。学习资产同源；相似纸页轮廓会削弱无文字辨识，必须保留标签并精简通用操作。' },
] as const;
