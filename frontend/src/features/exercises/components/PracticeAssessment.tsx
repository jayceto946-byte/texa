import { useState } from 'react';

export function PracticeAssessment({ disabled, continuous, onSubmit }: { disabled: boolean; continuous: boolean; onSubmit: (quality: number) => void }) {
  const [quality, setQuality] = useState<number | null>(null);
  return <>
    <span>本次自评</span>
    <div className="exercise-assessment">
      <div role="group" aria-label="本次掌握程度">{[1, 3, 5].map((value, index) => <button key={value} type="button" className="app-secondary-button" aria-pressed={quality === value} disabled={disabled} onClick={() => setQuality(value)}>{['没掌握', '基本理解', '已掌握'][index]}</button>)}</div>
      <button type="button" className="app-primary-button" disabled={disabled || quality === null} onClick={() => { if (quality !== null) onSubmit(quality); }}>{continuous ? '提交并下一题' : '记录本次作答'}</button>
    </div>
  </>;
}
