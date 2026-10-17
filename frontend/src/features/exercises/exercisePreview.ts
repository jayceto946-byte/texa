/** A bounded list preview. Never cuts a math token or changes the stored question. */
export function exercisePreview(raw: string, limit = 80): string {
  const normalized = raw.replace(/\$\$([\s\S]*?)\$\$|\$((?:\\.|[^$\\\n])+)\$/g, (_match, display: string | undefined, inline: string | undefined) => {
    const math = (display ?? inline ?? '').trim();
    return math.length <= 32 && !/\n|\\begin|\\end/.test(math) ? `$${math}$` : '〔公式〕';
  });
  const line = normalized.split('\n').map(value => value.trim()).find(Boolean) || '题干待补全';
  const tokens = line.match(/\$(?:\\.|[^$\\])*\$|〔公式〕|./gu) || [];
  let result = '';
  for (const token of tokens) {
    if (result.length + token.length > limit) return `${result.trimEnd()}…`;
    result += token;
  }
  return result;
}
