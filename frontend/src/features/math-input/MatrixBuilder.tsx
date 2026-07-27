import React, { useMemo, useState } from 'react';
import { Minus, Plus } from 'lucide-react';

import { SimpleMarkdown } from '../../components/chat/MarkdownRenderer';
import {
  buildMatrixLatex,
  createMatrixCells,
  isMatrixComplete,
  resizeMatrixCells,
  type MatrixEnvironment,
} from './matrixUtils';

interface MatrixBuilderProps {
  initialRows?: number;
  initialColumns?: number;
  onCancel: () => void;
  onSave: (latex: string) => void;
}

const environments: Array<{ value: MatrixEnvironment; label: string }> = [
  { value: 'bmatrix', label: '方括号 [ ]' },
  { value: 'pmatrix', label: '圆括号 ( )' },
  { value: 'vmatrix', label: '行列式 | |' },
  { value: 'matrix', label: '无括号' },
];

const MatrixBuilder: React.FC<MatrixBuilderProps> = ({ initialRows = 2, initialColumns = 2, onCancel, onSave }) => {
  const [rows, setRows] = useState(initialRows);
  const [columns, setColumns] = useState(initialColumns);
  const [environment, setEnvironment] = useState<MatrixEnvironment>('bmatrix');
  const [cells, setCells] = useState(() => createMatrixCells(initialRows, initialColumns));

  const latex = useMemo(() => buildMatrixLatex(cells, environment), [cells, environment]);
  const previewLatex = useMemo(
    () => buildMatrixLatex(cells.map((row) => row.map((cell) => cell.trim() || '\\square')), environment),
    [cells, environment],
  );
  const complete = isMatrixComplete(cells);

  const changeSize = (nextRows: number, nextColumns: number) => {
    const safeRows = Math.max(1, Math.min(5, nextRows));
    const safeColumns = Math.max(1, Math.min(5, nextColumns));
    setRows(safeRows);
    setColumns(safeColumns);
    setCells((current) => resizeMatrixCells(current, safeRows, safeColumns));
  };

  const updateCell = (rowIndex: number, columnIndex: number, value: string) => {
    setCells((current) => current.map((row, currentRow) =>
      currentRow === rowIndex
        ? row.map((cell, currentColumn) => currentColumn === columnIndex ? value : cell)
        : row,
    ));
  };

  return (
    <div className="p-3">
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div>
          <div className="mb-1 type-caption font-medium text-text-secondary">行数</div>
          <div className="flex items-center rounded-lg border border-border bg-bg-card">
            <button type="button" aria-label="减少一行" disabled={rows <= 1} onClick={() => changeSize(rows - 1, columns)} className="matrix-size-button flex h-8 w-8 items-center justify-center text-text-secondary disabled:opacity-30"><Minus className="h-3.5 w-3.5" /></button>
            <span className="w-7 text-center type-control tabular-nums">{rows}</span>
            <button type="button" aria-label="增加一行" disabled={rows >= 5} onClick={() => changeSize(rows + 1, columns)} className="matrix-size-button flex h-8 w-8 items-center justify-center text-text-secondary disabled:opacity-30"><Plus className="h-3.5 w-3.5" /></button>
          </div>
        </div>
        <div>
          <div className="mb-1 type-caption font-medium text-text-secondary">列数</div>
          <div className="flex items-center rounded-lg border border-border bg-bg-card">
            <button type="button" aria-label="减少一列" disabled={columns <= 1} onClick={() => changeSize(rows, columns - 1)} className="matrix-size-button flex h-8 w-8 items-center justify-center text-text-secondary disabled:opacity-30"><Minus className="h-3.5 w-3.5" /></button>
            <span className="w-7 text-center type-control tabular-nums">{columns}</span>
            <button type="button" aria-label="增加一列" disabled={columns >= 5} onClick={() => changeSize(rows, columns + 1)} className="matrix-size-button flex h-8 w-8 items-center justify-center text-text-secondary disabled:opacity-30"><Plus className="h-3.5 w-3.5" /></button>
          </div>
        </div>
        <label className="min-w-36 flex-1">
          <span className="mb-1 block type-caption font-medium text-text-secondary">外框</span>
          <select value={environment} onChange={(event) => setEnvironment(event.target.value as MatrixEnvironment)} className="h-9 w-full rounded-lg border border-border bg-bg-card px-2 type-caption outline-none focus:border-accent">
            {environments.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-[var(--surface-subtle)] p-2.5">
        <div className="mx-auto grid min-w-max gap-1.5" style={{ gridTemplateColumns: `repeat(${columns}, minmax(64px, 92px))` }}>
          {cells.flatMap((row, rowIndex) => row.map((cell, columnIndex) => (
            <input
              key={`${rowIndex}-${columnIndex}`}
              value={cell}
              onChange={(event) => updateCell(rowIndex, columnIndex, event.target.value)}
              aria-label={`第 ${rowIndex + 1} 行第 ${columnIndex + 1} 列`}
              placeholder="0"
              className="h-10 rounded-lg border border-border bg-bg-card px-2 text-center font-[var(--font-math)] text-sm outline-none focus:border-accent"
            />
          )))}
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-border bg-bg-card px-3 py-2">
        <div className="mb-1 type-caption font-medium text-text-secondary">矩阵预览</div>
        <div className="max-h-32 overflow-auto text-center"><SimpleMarkdown content={`$$\n${previewLatex}\n$$`} /></div>
      </div>

      {!complete && <div className="mt-2 type-caption text-text-secondary">请填写每个单元格，数字、字母和简单 LaTeX 均可。</div>}

      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-lg border border-border px-3 py-2 type-control text-text-secondary hover:bg-[var(--surface-muted)]">返回</button>
        <button type="button" disabled={!complete} onClick={() => onSave(latex)} className="rounded-lg bg-accent px-4 py-2 type-control text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40">添加矩阵</button>
      </div>
    </div>
  );
};

export default MatrixBuilder;
