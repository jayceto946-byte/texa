const checkLabels: Record<string, string> = {
  formula: '公式或推导关系未通过检查', numeric: '数值未通过检查', unit: '单位未通过检查', required_outputs: '必要结论或步骤缺失', citations: '引用未通过检查',
};
/** Compatibility is restricted to the old deterministic notice, never formulas. */
export function readableVerificationNotice(content: string): string {
  return content.replace(/(^|\n)> 回答验收未通过：([a-z_, ]+)。本轮结果未标记为完整答案。(?=\n|$)/g, (whole, prefix: string, ids: string) => {
    const labels = ids.split(',').map(id => checkLabels[id.trim()]);
    return labels.every(Boolean) ? `${prefix}> 回答验收未通过：${labels.join('，')}。这些结论仍需核对。` : whole;
  }).replace(/(^|\n)> 回答核对：部分公式或数值尚无确定性核验依据，本轮结果未标记为完整答案。(?=\n|$)/g, '$1> 回答核对：部分公式或数值尚无确定性核验依据，请核对后使用。');
}

/** Separate only the exact system-appended, trailing unverified notice.
 * Keep user quotes, fenced examples and unknown/failing diagnostics intact.
 * The caller must still expose the unverified state outside the reading body.
 */
export function separateVerificationNotice(content: string): { body: string; notice: string } {
  const readable = readableVerificationNotice(content);
  const match = readable.match(/\n\n> 回答核对：部分公式或数值尚无确定性核验依据，请核对后使用。\s*$/);
  if (!match || match.index === undefined) return { body: readable, notice: '' };
  const body = readable.slice(0, match.index);
  // A matching line inside a code sample is content, not a system notice.
  let fence = '';
  for (const line of body.split('\n')) {
    const marker = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (!marker) continue;
    if (!fence) fence = marker[1];
    else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = '';
  }
  if (fence) return { body: readable, notice: '' };
  return { body: body.trimEnd(), notice: '部分公式或数值尚无确定性核验依据，请核对后使用。' };
}
