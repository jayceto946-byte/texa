const checkLabels: Record<string, string> = {
  formula: '公式或推导关系未通过检查', numeric: '数值未通过检查', unit: '单位未通过检查', required_outputs: '必要结论或步骤缺失', citations: '引用未通过检查',
};
/** Compatibility is restricted to the old deterministic notice, never formulas. */
export function readableVerificationNotice(content: string): string {
  return content.replace(/(^|\n)> 回答验收未通过：([a-z_, ]+)。本轮结果未标记为完整答案。(?=\n|$)/g, (whole, prefix: string, ids: string) => {
    const labels = ids.split(',').map(id => checkLabels[id.trim()]);
    return labels.every(Boolean) ? `${prefix}> 回答验收未通过：${labels.join('，')}。本轮结果未标记为完整答案。` : whole;
  });
}
