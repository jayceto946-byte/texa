/** Present legacy frozen OCR text without exposing its structured asset arrays. */
export function readableVisualQuestion(content: string): string {
  return content.replace(/^(实体|关系|标注|用户标记|公式|选项|手写作答|识别不确定项|所需材料)：\s*\n([^\n]+)(?:\n|$)/gm, (block, label: string, value: string) => {
    try {
      const parsed: unknown = JSON.parse(value);
      if (!Array.isArray(parsed)) return block;
      if (label === '实体') return '';
      if (label === '关系' || label === '所需材料') {
        const descriptions = parsed.filter(item => item && typeof item === 'object')
          .map(item => item.description || item.reason || item.name)
          .filter((item): item is string => typeof item === 'string' && Boolean(item));
        return descriptions.length ? `${label === '关系' ? '图形条件' : '待补充材料'}：\n${descriptions.join('\n')}\n` : '';
      }
      const lines = parsed.filter((item): item is string => typeof item === 'string');
      return lines.length ? `${label}：\n${lines.join('\n')}\n` : '';
    } catch { return block; }
  }).replace(/\n{3,}/g, '\n\n').trim();
}
