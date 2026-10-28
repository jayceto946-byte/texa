export const MistakeRange = ({
  label,
  value,
  min,
  max,
  suffix = '%',
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  suffix?: string;
  onChange: (value: number) => void;
}) => (
  <label className="block space-y-1 text-sm text-text-primary">
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <span className="text-xs text-text-secondary">{value}{suffix}</span>
    </div>
    <input
      type="range"
      min={min}
      max={max}
      value={value}
      onChange={(event) => onChange(Number(event.target.value))}
      className="w-full accent-accent"
    />
  </label>
);
