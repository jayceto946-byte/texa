/** Isolated, read-only UI fixtures. Never connects to Texa storage or an LLM.
 * Run: node scripts/visual-preview-server.mjs
 * Then VITE_BACKEND_TARGET=http://127.0.0.1:8019 npm run dev -- --port 5189
 * Set TEXA_VISUAL_PORT to isolate concurrent preview sessions.
 */
import { createServer } from 'node:http';
const port = Number(process.env.TEXA_VISUAL_PORT || 8019);

const titles = ['高等数学 · 上册（第七版）', '高等数学 · 下册（第七版）', '线性代数（第六版）', '概率论与数理统计', '数学分析 · 第一册', '考研数学典型例题与方法', '微积分学习指导', '线性代数习题集'];
const books = titles.map((name, i) => ({
  name, book_id: `visual-book-${i}`, display_name: name, has_pdf: true,
  subject: `数学/${i === 2 || i === 7 ? '线代' : i === 3 ? '概率论' : '高数'}`,
  chapter_count: [7, 5, 6, 9, 8, 12, 7, 6][i],
  book_role: i < 4 ? 'core' : i === 6 ? 'standalone' : 'reference',
  resource_group: i < 2 || i === 4 || i === 5 ? '高等数学' : '',
  lifecycle_status: i === 7 ? 'archived' : 'active',
  readiness: {
    technical: { status: i === 4 ? 'degraded' : i === 6 ? 'missing' : 'ready', chunk_count: 846 + i * 127 },
    canonical: { status: i === 5 ? 'needs_review' : i === 6 ? 'unavailable' : 'ready', warning_count: i === 5 ? 3 : 0 },
    semantic: { status: i < 2 ? 'verified' : 'unverified', human_case_count: i < 2 ? 24 : 0 },
  },
}));
const answer = String.raw`求极限时，关键是判断：**被替换的量处在乘除结构中，还是加减结构中**。等价无穷小描述的是比值趋于 1；两项相减时，主要部分可能抵消，留下的恰好是被忽略的误差。

## 01　先看等价关系保留了什么

当 $x\to 0$ 时，$\sin x\sim x$ 的含义是：

$$\lim_{x\to 0}\frac{\sin x}{x}=1,\qquad \sin x=x+o(x).$$

这足以支持乘积或商中的替换，但不能说明 $\sin x-x$ 的具体阶数。若直接把 $\sin x$ 换成 $x$，差值会变成零，原本决定极限的高阶项也随之消失。[[cite:E1]]

## 02　一个需要保留三阶项的例子

计算 $\displaystyle\lim_{x\to0}\frac{x-\sin x}{x^3}$。分母已经提示我们：需要把分子展开到三阶。

$$
\begin{aligned}
\sin x&=x-\frac{x^3}{6}+o(x^3),\\
x-\sin x&=\frac{x^3}{6}+o(x^3),\\
\lim_{x\to0}\frac{x-\sin x}{x^3}&=\frac16.
\end{aligned}
$$

这里一次项相消，三次项成为主导项。泰勒展开的作用，是把抵消之后仍然有效的信息保留下来。[[cite:E2]]

> 判断展开到几阶：先观察分母的阶，再检查分子的低阶项是否抵消。不要只记“展开三项”，而应保留到第一个不为零的有效项。

## 03　什么时候可以直接替换？

| 表达式 | 处理方式 | 原因 |
| :--- | :--- | :--- |
| $\sin x/x$ | 可将 $\sin x$ 替换为 $x$ | 商的等价替换 |
| $(1-\cos x)/x^2$ | 整体替换为 $x^2/2$ | 保留二阶主项 |
| $(x-\sin x)/x^3$ | 展开到三阶 | 一阶项相消 |

需要注意，“加减式不能替换”只是便于记忆的提醒，并不是绝对规则。若能证明替换误差相对于最终保留项是更高阶的无穷小，替换仍然成立。判断依据始终是误差，而不是表达式的外观。[[cite:E3]]

## 04　把方法迁移到另一道题

考虑 $\displaystyle\lim_{x\to0}\frac{e^x-1-x}{x^2}$。由于常数项和一次项都被减掉，需要保留二次项：

$$e^x=1+x+\frac{x^2}{2}+o(x^2)\quad\Longrightarrow\quad\lim_{x\to0}\frac{e^x-1-x}{x^2}=\frac12.$$

两道题的共同结构是：先识别抵消，再保留主项，最后比较阶数。复习时可以将错因记录为“忽略相减后的有效阶”，并回到泰勒公式的余项含义检查推导。

*以上内容与来源定位为界面演示样例，不是对真实教材页码的核验。*`;
const sessions = ['等价无穷小：为什么相减时不能直接替换？', '泰勒公式中的余项如何理解', '用几何意义理解定积分', '矩阵的秩与线性相关', '连续与可导的区别', '分部积分：怎样选择 u 和 dv', '条件概率与独立性', '一元函数极值的判断'];
const conversations = sessions.map((title, i) => ({ id: `visual-session-${i}`, title, subject: '数学/高数', book_name: titles[0], updated_at: new Date(Date.now() - i * 86400000).toISOString(), message_count: 2 }));
const sources = [
  ['第一章 函数与极限', '无穷小的比较', 48],
  ['第三章 微分中值定理与导数的应用', '泰勒公式', 125],
  ['第一章 函数与极限', '极限运算法则', 36],
].map(([chapter, section, page], i) => ({ id: `E${i + 1}`, book_name: titles[0], chapter, section_path: [chapter, section], page_idx: page, chunk_id: `visual-source-${i}` }));

const fixtureMistakes = [
  {
    id: 'visual-mistake-1', question_text: String.raw`求 $\lim_{x\to0}\frac{x-\sin x}{x^3}$，说明为什么不能直接使用 $\sin x\sim x$。`,
    user_answer: '直接替换得到 0。', correct_answer: String.raw`由 $\sin x=x-\frac{x^3}{6}+o(x^3)$，极限为 $\frac16$。`,
    explanation: '一次项相消，需要保留到三阶；直接等价替换会丢掉决定结果的误差项。',
    source: '高等数学 · 上册 / 第三章', subject: '数学/高数', chapter: '泰勒公式', tags: ['极限', '泰勒展开'],
    mistake_type: ['公式记错'], difficulty: 3, created_at: '2026-09-20T08:00:00Z', next_review: '2026-09-25', interval: 2,
    review_history: [], linked_concepts: [{ name: '泰勒公式' }],
  },
  {
    id: 'visual-mistake-2', question_text: String.raw`已知矩阵 $A$ 的两行线性相关，判断 $\operatorname{rank}(A)$。`,
    user_answer: '秩等于行数。', correct_answer: '秩小于行数。', explanation: '行向量线性相关，无法组成满秩行组。',
    source: '线性代数 / 第二章', subject: '数学/线代', chapter: '矩阵的秩', tags: ['矩阵'],
    mistake_type: ['概念不清'], difficulty: 2, created_at: '2026-09-19T08:00:00Z', next_review: '2026-09-27', interval: 4,
    review_history: [], linked_concepts: [{ name: '矩阵的秩' }],
  },
];
const fixtureExercises = [
  {
    id: 'visual-exercise-1', question_text: fixtureMistakes[0].question_text, answer: fixtureMistakes[0].correct_answer,
    explanation: fixtureMistakes[0].explanation, source: '高等数学 · 上册 / 例题', subject: '数学/高数', chapter: '泰勒公式',
    tags: ['极限', '泰勒展开'], question_type: '计算题', difficulty: 3, linked_concepts: [{ name: '泰勒公式' }],
    origin_type: 'manual', origin_id: '', status: 'practicing', notes: '', practice_count: 2,
    created_at: '2026-09-18T08:00:00Z', updated_at: '2026-09-24T08:00:00Z',
  },
  {
    id: 'visual-exercise-2', question_text: fixtureMistakes[1].question_text, answer: fixtureMistakes[1].correct_answer,
    explanation: fixtureMistakes[1].explanation, source: '线性代数 / 课后题', subject: '数学/线代', chapter: '矩阵的秩',
    tags: ['矩阵'], question_type: '证明题', difficulty: 2, linked_concepts: [{ name: '矩阵的秩' }],
    origin_type: 'textbook', origin_id: 'visual-source-2', status: 'needs_review', notes: '等待人工校对', practice_count: 0,
    created_at: '2026-09-19T08:00:00Z', updated_at: '2026-09-19T08:00:00Z',
  },
];
const fixtureLearningSummary = {
  stats: { total_concepts: 12, total_exposures: 38, weak_count: 2, forgotten_count: 1 },
  top_concepts: [{ name: '泰勒公式', count: 8 }, { name: '矩阵的秩', count: 5 }],
  weak_concepts: [{ name: '泰勒公式', exposure_count: 4, weak_reason: '近期错题' }],
  review_queue: [{ name: '无穷小比较', reason: 'forgotten' }],
  concept_review_plan: [{ name: '泰勒公式', priority: 1, reasons: ['近期错题中多次遗漏高阶项'], exposure_count: 4, weak: true,
    recent_questions: [], related_mistakes: [fixtureMistakes[0]], textbook_snippets: [{ type: 'example', chapter: '第三章 · 泰勒公式', text: '保留有效阶' }] }],
  daily: Array.from({ length: 7 }, (_, i) => ({ date: `2026-09-${String(19 + i).padStart(2, '0')}`, qa: i % 3, mistake: i % 2, total: i % 3 + i % 2 })),
  mistake_stats: { total: 2, due_today: 1 }, mistake_weak_points: [{ name: '泰勒公式', type: '公式记错', count: 1 }],
  due_mistakes: [fixtureMistakes[0]], recent_questions: [{ question: '等价无穷小为什么相减时不能直接替换？', source: 'qa', timestamp: '2026-09-24T08:00:00Z', concepts: [{ name: '泰勒公式' }] }],
  subjects: ['数学/高数', '数学/线代'], selected_subject: '数学/高数',
};

const visualModels = {
  providers: [{id:'openai_compatible',label:'本地界面演示（不调用模型）',capabilities:['text','reasoning','vision'],default_endpoint:'http://127.0.0.1:8029',default_models:{reasoning:'visual-demo',vision:'visual-demo'},requires_api_key:false}],
  models: [], roles: {reasoning:{provider:'openai_compatible',model:'visual-demo',credential_id:'demo',endpoint_id:'demo'},vision:{provider:'openai_compatible',model:'visual-demo',credential_id:'demo',endpoint_id:'demo'}},
  credentials: {reasoning:{configured:false,required:false},vision:{configured:false,required:false}},
  endpoints: {reasoning:{base_url:'http://127.0.0.1:8029',is_default:true},vision:{base_url:'http://127.0.0.1:8029',is_default:true}},
  multimodal_mode:'native',profiles:[],active_profile_id:'',editing_profile_id:'demo',profile_name:'界面演示',credential_status:{}
};

createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Kaoyan-Token');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (req.method === 'OPTIONS') { res.end(); return; }
  if (req.method === 'POST' && url.pathname === '/api/system/settings/model-profiles') { res.end(JSON.stringify({success:true,data:visualModels,message:'仅界面演示，未保存真实配置'})); return; }
  const readOnlyPost = ['/api/mistakes/list', '/api/mistakes/overview', '/api/exercises/overview'].includes(url.pathname);
  if (req.method !== 'GET' && !(req.method === 'POST' && readOnlyPost)) { res.writeHead(405); res.end(JSON.stringify({ message: '只读视觉样例：不保存数据或调用模型' })); return; }
  let data = {};
  if (url.pathname === '/health') { res.end(JSON.stringify({ status: 'ok', warmup: { status: 'ready' } })); return; }
  if (url.pathname === '/api/system/health') { res.end(JSON.stringify({ status: 'healthy', book_name: titles[0], components: { backend: { status: 'healthy', message: '本地服务运行正常' }, vector_store: { status: 'healthy', message: '教材检索可用' }, database: { status: 'healthy', message: '学习记录可用' } } })); return; }
  if (url.pathname === '/api/books/list') data = url.searchParams.has('include_archived') ? books : books.filter(b => b.lifecycle_status === 'active');
  else if (url.pathname === '/api/system/version') data = { current_version: 'visual-fixture', latest_version: 'visual-fixture', update_available: false };
  else if (url.pathname === '/api/system/settings') data = { models:visualModels, subjects: [{ name: '数学', children: ['高数', '线代', '概率论'] }, { name: '专业课', children: ['数据结构', '计算机组成'] }], env: {} };
  else if (url.pathname === '/api/system/assets/status') data = { needs_setup: false, assets: {} };
  else if (url.pathname === '/api/chat/conversations') data = conversations;
  else if (url.pathname === '/api/jobs') data = [];
  else if (/^\/api\/goals\/[^/]+\/evidence$/.test(url.pathname)) data = [{id:'event-visual-1',label:'习题作答',timestamp:'2026-09-26T10:00:00'}];
  else if (/^\/api\/goals\/[^/]+\/runtime$/.test(url.pathname)) data = null;
  else if (url.pathname === '/api/goals') data = [
    { id: 'goal-visual-1', title: '复习极限中的等价替换与泰勒展开', objective: '能说明相减结构中替换误差的阶数，并用作答记录核验。', status: 'active', revision: 3, scope: { book_name: titles[0], subject: '数学/高数' }, success_criteria: [{ id: 'c1', description: '完成两道极限题并说明有效阶数' }], progress: { unknowns: ['c1'], evidence_refs: [] } },
    { id: 'goal-visual-2', title: '复习矩阵的秩', objective: '理解线性相关', status: 'paused', revision: 2, scope: {}, success_criteria: [], progress: { unknowns: [], evidence_refs: [] } },
  ];
  else if (url.pathname === '/api/kg/learning-summary') data = fixtureLearningSummary;
  else if (url.pathname === '/api/mistakes/list') data = fixtureMistakes;
  else if (url.pathname === '/api/mistakes/overview') data = { records: fixtureMistakes, due_records: [fixtureMistakes[0]] };
  else if (url.pathname === '/api/mistakes/due') data = [fixtureMistakes[0]];
  else if (url.pathname === '/api/mistakes/stats') { res.end(JSON.stringify({ total: 2, due_today: 1, by_type: { 公式记错: 1, 概念不清: 1 }, by_tag: { 极限: 1, 矩阵: 1 }, by_difficulty: { 2: 1, 3: 1 } })); return; }
  else if (url.pathname === '/api/mistakes/weak-points') data = [{ name: '泰勒公式', type: '公式记错', count: 1 }];
  else if (url.pathname === '/api/exercises/overview') data = { records: fixtureExercises, stats: { total: 2, by_type: { 计算题: 1, 证明题: 1 }, by_tag: { 极限: 1, 矩阵: 1 }, by_status: { practicing: 1, needs_review: 1 } }, practice_session: null };
  else if (url.pathname.startsWith('/api/chat/conversations/')) {
    const id = url.pathname.split('/')[4];
    data = { id, subject: '数学/高数', book_name: titles[0], messages: [{ role: 'user', content: sessions[Number(id.split('-').at(-1))] || sessions[0] }, { role: 'assistant', content: answer.replace(/\$\$([\s\S]*?)\$\$/g, (_, body) => '$$\n' + body.trim() + '\n$$'), sources, answer_mode: 'textbook_grounded' }], page: { has_more: false, total: 2, limit: 40 } };
  } else if (url.pathname.startsWith('/api/books/switch/')) data = { name: decodeURIComponent(url.pathname.split('/').at(-1)), subject: '数学/高数' };
  else { res.writeHead(404); res.end(JSON.stringify({ detail: '此接口不在只读视觉样例范围内' })); return; }
  res.end(JSON.stringify({ success: true, data }));
}).listen(port, '127.0.0.1', () => console.log(`Read-only visual fixtures: http://127.0.0.1:${port}`));
