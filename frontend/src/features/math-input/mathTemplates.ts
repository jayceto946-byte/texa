export type MathTemplateCategory = 'common' | 'calculus' | 'linear-algebra' | 'greek';

export interface MathTemplate {
  id: string;
  label: string;
  description: string;
  category: MathTemplateCategory;
  value: string;
}

export const mathTemplateCategories: Array<{ id: MathTemplateCategory; label: string }> = [
  { id: 'common', label: '常用' },
  { id: 'calculus', label: '微积分' },
  { id: 'linear-algebra', label: '线性代数' },
  { id: 'greek', label: '希腊字母' },
];

export const mathTemplates: MathTemplate[] = [
  { id: 'fraction', label: 'a/b', description: '分数', category: 'common', value: '$\\frac{[[selection|分子]]}{[[cursor|分母]]}$' },
  { id: 'superscript', label: 'xⁿ', description: '上标', category: 'common', value: '$[[selection|x]]^{[[cursor|n]]}$' },
  { id: 'subscript', label: 'xᵢ', description: '下标', category: 'common', value: '$[[selection|x]]_{[[cursor|i]]}$' },
  { id: 'square-root', label: '√x', description: '平方根', category: 'common', value: '$\\sqrt{[[selection|表达式]]}$' },
  { id: 'nth-root', label: 'ⁿ√x', description: 'n 次根', category: 'common', value: '$\\sqrt[[cursor|n]]{[[selection|表达式]]}$' },
  { id: 'absolute', label: '|x|', description: '绝对值', category: 'common', value: '$\\lvert [[selection|x]] \\rvert$' },
  { id: 'less-equal', label: '≤', description: '小于等于', category: 'common', value: '$\\le$' },
  { id: 'greater-equal', label: '≥', description: '大于等于', category: 'common', value: '$\\ge$' },
  { id: 'not-equal', label: '≠', description: '不等于', category: 'common', value: '$\\ne$' },
  { id: 'approximately', label: '≈', description: '约等于', category: 'common', value: '$\\approx$' },
  { id: 'infinity', label: '∞', description: '无穷', category: 'common', value: '$\\infty$' },
  { id: 'arrow', label: '→', description: '趋于或映射到', category: 'common', value: '$\\to$' },

  { id: 'sine', label: 'sin', description: '正弦', category: 'calculus', value: '$\\sin([[selection|x]])$' },
  { id: 'cosine', label: 'cos', description: '余弦', category: 'calculus', value: '$\\cos([[selection|x]])$' },
  { id: 'tangent', label: 'tan', description: '正切', category: 'calculus', value: '$\\tan([[selection|x]])$' },
  { id: 'logarithm', label: 'ln', description: '自然对数', category: 'calculus', value: '$\\ln([[selection|x]])$' },
  { id: 'limit', label: 'lim', description: '极限', category: 'calculus', value: '$\\lim_{[[cursor|x\\to 0]]} [[selection|f(x)]]$' },
  { id: 'derivative', label: "f′(x)", description: '导数', category: 'calculus', value: "$[[selection|f]]'([[cursor|x]])$" },
  { id: 'leibniz-derivative', label: 'dy/dx', description: '莱布尼茨导数', category: 'calculus', value: '$\\frac{d[[selection|y]]}{d[[cursor|x]]}$' },
  { id: 'partial-derivative', label: '∂f/∂x', description: '偏导数', category: 'calculus', value: '$\\frac{\\partial [[selection|f]]}{\\partial [[cursor|x]]}$' },
  { id: 'indefinite-integral', label: '∫', description: '不定积分', category: 'calculus', value: '$\\int [[selection|f(x)]]\\,d[[cursor|x]]$' },
  { id: 'definite-integral', label: '∫ₐᵇ', description: '定积分', category: 'calculus', value: '$\\int_{[[cursor|a]]}^{b} [[selection|f(x)]]\\,dx$' },
  { id: 'double-integral', label: '∬', description: '二重积分', category: 'calculus', value: '$\\iint_{[[cursor|D]]} [[selection|f(x,y)]]\\,dx\\,dy$' },
  { id: 'summation', label: 'Σ', description: '求和', category: 'calculus', value: '$\\sum_{[[cursor|i=1]]}^{n} [[selection|a_i]]$' },
  { id: 'product', label: 'Π', description: '连乘', category: 'calculus', value: '$\\prod_{[[cursor|i=1]]}^{n} [[selection|a_i]]$' },

  { id: 'vector', label: 'a⃗', description: '向量', category: 'linear-algebra', value: '$\\vec{[[selection|a]]}$' },
  { id: 'bold-vector', label: '𝐯', description: '粗体向量', category: 'linear-algebra', value: '$\\mathbf{[[selection|v]]}$' },
  { id: 'norm', label: '‖v‖', description: '向量范数', category: 'linear-algebra', value: '$\\lVert [[selection|\\mathbf{v}]] \\rVert$' },
  { id: 'dot-product', label: 'a·b', description: '点积', category: 'linear-algebra', value: '$[[selection|\\mathbf{a}]]\\cdot [[cursor|\\mathbf{b}]]$' },
  { id: 'cross-product', label: 'a×b', description: '叉积', category: 'linear-algebra', value: '$[[selection|\\mathbf{a}]]\\times [[cursor|\\mathbf{b}]]$' },
  { id: 'transpose', label: 'Aᵀ', description: '矩阵转置', category: 'linear-algebra', value: '$[[selection|A]]^T$' },
  { id: 'inverse', label: 'A⁻¹', description: '逆矩阵', category: 'linear-algebra', value: '$[[selection|A]]^{-1}$' },
  { id: 'determinant', label: 'det(A)', description: '行列式', category: 'linear-algebra', value: '$\\det([[selection|A]])$' },
  { id: 'rank', label: 'rank(A)', description: '矩阵的秩', category: 'linear-algebra', value: '$\\operatorname{rank}([[selection|A]])$' },
  { id: 'matrix-2', label: '2×2', description: '二阶矩阵', category: 'linear-algebra', value: '$$\n\\begin{bmatrix}\n[[selection|a]] & b \\\\\n c & d\n\\end{bmatrix}\n$$' },
  { id: 'matrix-3', label: '3×3', description: '三阶矩阵', category: 'linear-algebra', value: '$$\n\\begin{bmatrix}\n[[selection|a]] & b & c \\\\\n d & e & f \\\\\n g & h & i\n\\end{bmatrix}\n$$' },

  { id: 'alpha', label: 'α', description: 'alpha', category: 'greek', value: '$\\alpha$' },
  { id: 'beta', label: 'β', description: 'beta', category: 'greek', value: '$\\beta$' },
  { id: 'gamma', label: 'γ', description: 'gamma', category: 'greek', value: '$\\gamma$' },
  { id: 'delta', label: 'δ', description: 'delta', category: 'greek', value: '$\\delta$' },
  { id: 'theta', label: 'θ', description: 'theta', category: 'greek', value: '$\\theta$' },
  { id: 'lambda', label: 'λ', description: 'lambda', category: 'greek', value: '$\\lambda$' },
  { id: 'mu', label: 'μ', description: 'mu', category: 'greek', value: '$\\mu$' },
  { id: 'pi', label: 'π', description: 'pi', category: 'greek', value: '$\\pi$' },
  { id: 'rho', label: 'ρ', description: 'rho', category: 'greek', value: '$\\rho$' },
  { id: 'sigma', label: 'σ', description: 'sigma', category: 'greek', value: '$\\sigma$' },
  { id: 'phi', label: 'φ', description: 'varphi', category: 'greek', value: '$\\varphi$' },
  { id: 'omega', label: 'ω', description: 'omega', category: 'greek', value: '$\\omega$' },
];
