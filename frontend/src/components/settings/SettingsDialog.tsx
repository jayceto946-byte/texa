import { X } from 'lucide-react';
import Dialog from '../ui/Dialog';
import SettingsPage from '../SystemHealth';

type SettingsDialogProps = {
  open: boolean;
  onClose: () => void;
};

export default function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      keepMounted
      title="设置"
      description="配置 Texa 的外观、系统、模型与教材解析。"
      className="settings-dialog"
    >
      <header className="settings-dialog-header">
        <h2 className="app-page-title">设置</h2>
        <button type="button" onClick={onClose} className="app-icon-button" aria-label="关闭设置">
          <X className="h-[18px] w-[18px]" />
        </button>
      </header>
      <SettingsPage />
    </Dialog>
  );
}
