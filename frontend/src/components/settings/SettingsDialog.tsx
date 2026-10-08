import { X } from 'lucide-react';
import { lazy, Suspense, useCallback, useRef } from 'react';
import Dialog from '../ui/Dialog';
const SettingsPage = lazy(() => import('../SystemHealth'));

type SettingsDialogProps = {
  open: boolean;
  onClose: () => void;
};

export default function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  const modelDirty = useRef(false);
  const setModelDirty = useCallback((dirty: boolean) => { modelDirty.current = dirty; }, []);
  const close = useCallback(() => {
    if (modelDirty.current && !window.confirm('模型配置有未保存更改。放弃更改并关闭设置吗？')) return;
    onClose();
  }, [onClose]);
  return (
    <Dialog
      open={open}
      onClose={close}
      keepMounted
      title="设置"
      description="配置 Texa 的偏好、模型连接和学习数据。"
      className="settings-dialog"
    >
      <header className="settings-dialog-header">
        <h2 className="app-page-title">设置</h2>
        <button type="button" onClick={close} className="app-icon-button" aria-label="关闭设置">
          <X className="h-[18px] w-[18px]" />
        </button>
      </header>
      <Suspense fallback={<div role="status">正在加载设置…</div>}>
        <SettingsPage open={open} onModelDirtyChange={setModelDirty} />
      </Suspense>
    </Dialog>
  );
}
