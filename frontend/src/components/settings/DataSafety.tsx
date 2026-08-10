import { useCallback, useEffect, useState } from 'react';
import { Archive, Database, Loader2, RefreshCw, RotateCcw } from 'lucide-react';
import { get, post } from '../../api/client';

type BackupItem = {
  name: string;
  created_at?: string;
  app_version?: string;
  size: number;
  file_count?: number;
  included?: string[];
  sha256?: string;
  valid: boolean;
  error?: string;
};

function formatBytes(value = 0) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function DataSafety() {
  const [items, setItems] = useState<BackupItem[]>([]);
  const [includeDerived, setIncludeDerived] = useState(false);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [backupPath, setBackupPath] = useState('');
  const [lastRestore, setLastRestore] = useState<any>(null);

  const load = useCallback(async () => {
    const res = await get('/system/backups', 120000);
    if (!res?.success) throw new Error(res?.message || '读取备份失败');
    setItems(res.data?.items || []);
    setBackupPath(res.data?.backup_path || '');
    setLastRestore(res.data?.last || null);
  }, []);

  useEffect(() => {
    load().catch((error) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [load]);

  const create = async () => {
    setBusy('create');
    setMessage('正在创建一致性备份，请勿关闭应用...');
    try {
      const res = await post('/system/backups', { include_derived: includeDerived }, 30 * 60_000);
      setMessage(res?.message || (res?.success ? '备份已创建' : '备份失败'));
      if (res?.success) await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy('');
    }
  };

  const restore = async (item: BackupItem) => {
    if (!item.valid) return;
    if (!window.confirm(`确定从备份 ${item.name} 合并恢复吗？\n\n备份中包含的数据会被替换；备份中未包含的其他教材和记录会保留。系统会先创建当前数据的安全备份，实际恢复在重启时执行。`)) return;
    setBusy(item.name);
    setMessage('正在校验备份并创建恢复前快照...');
    try {
      const res = await post(`/system/backups/${encodeURIComponent(item.name)}/restore`, {}, 30 * 60_000);
      setMessage(res?.message || (res?.success ? '恢复已登记' : '恢复登记失败'));
      if (res?.success && window.kaoyanDesktop?.restart) {
        await window.kaoyanDesktop.restart();
      } else if (res?.success) {
        setMessage(`${res.message} 请手动重启后端服务。`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy('');
    }
  };

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-border bg-bg-card p-4">
        <div className="flex items-start gap-3">
          <Archive className="mt-0.5 h-5 w-5 text-accent" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-text-primary">学习数据备份</div>
            <div className="mt-1 text-xs leading-5 text-text-secondary">默认备份教材、章节、错题、习题和学习记录，不包含 API Key。备份完成后会自动校验压缩包。</div>
            {backupPath && <div className="mt-2 break-all text-[11px] text-text-secondary">保存位置：{backupPath}</div>}
          </div>
        </div>
        <label className="mt-4 flex items-start gap-2 text-xs text-text-secondary">
          <input type="checkbox" checked={includeDerived} onChange={(event) => setIncludeDerived(event.target.checked)} className="mt-0.5" />
          <span>同时备份向量库和 MinerU 产物（体积可能很大，但恢复后无需重新索引）</span>
        </label>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={create} disabled={Boolean(busy)} className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60">
            {busy === 'create' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}立即备份
          </button>
          <button type="button" onClick={() => load()} disabled={Boolean(busy)} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:border-accent disabled:opacity-60">
            <RefreshCw className="h-4 w-4" />刷新列表
          </button>
        </div>
      </div>

      {message && <div className="rounded-lg border border-border bg-bg-card px-3 py-2 text-sm text-text-secondary">{message}</div>}
      {lastRestore?.status && (
        <div className={`rounded-lg border p-3 text-xs ${lastRestore.status === 'completed' ? 'border-[#bfd4c6] bg-[#edf6f0] text-[var(--success)]' : 'border-red-200 bg-red-50 text-[var(--danger)]'}`}>
          最近合并恢复：{lastRestore.status === 'completed' ? '已完成' : '失败并已回滚'} · {lastRestore.archive}
          {lastRestore.status === 'completed' && lastRestore.reindex_required && ' · 已移除不匹配的向量索引，请在教材管理中重新索引'}
          {lastRestore.status === 'completed' && lastRestore.preserved_unlisted?.length > 0 && ` · 已保留 ${lastRestore.preserved_unlisted.length} 个备份未包含的数据目录`}
        </div>
      )}

      <div className="space-y-2">
        {items.length === 0 && <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-text-secondary">还没有备份</div>}
        {items.map((item) => (
          <article key={item.name} className="rounded-xl border border-border bg-bg-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="break-all text-sm font-medium text-text-primary">{item.name}</div>
                <div className="mt-1 text-xs text-text-secondary">
                  {item.created_at ? new Date(item.created_at).toLocaleString() : '时间未知'} · {formatBytes(item.size)} · {item.file_count || 0} 个文件 · v{item.app_version || '未知'}
                </div>
                <div className="mt-1 text-[11px] text-text-secondary">{item.valid ? `SHA-256 ${item.sha256?.slice(0, 16)}…` : `校验失败：${item.error || '未知错误'}`}</div>
              </div>
              <button type="button" onClick={() => restore(item)} disabled={!item.valid || Boolean(busy)} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm hover:border-accent disabled:opacity-50">
                {busy === item.name ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}合并恢复
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
