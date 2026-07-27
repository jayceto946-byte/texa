export interface MathQuickKey {
  id: string;
  label: string;
  latex: string;
  description: string;
}

export const mathQuickKeys: MathQuickKey[] = [
  { id: 'square', label: 'x²', latex: '^2', description: '添加平方上标' },
  { id: 'cube', label: 'x³', latex: '^3', description: '添加立方上标' },
  ...'1234567890'.split('').map((value) => ({
    id: `digit-${value}`,
    label: value,
    latex: value,
    description: `输入数字 ${value}`,
  })),
  { id: 'variable-x', label: 'x', latex: 'x', description: '输入变量 x' },
  { id: 'variable-y', label: 'y', latex: 'y', description: '输入变量 y' },
  { id: 'variable-z', label: 'z', latex: 'z', description: '输入变量 z' },
  { id: 'plus', label: '+', latex: '+', description: '输入加号' },
  { id: 'minus', label: '−', latex: '-', description: '输入减号' },
  { id: 'equals', label: '=', latex: '=', description: '输入等号' },
  { id: 'left-parenthesis', label: '(', latex: '(', description: '输入左括号' },
  { id: 'right-parenthesis', label: ')', latex: ')', description: '输入右括号' },
];
