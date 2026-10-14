import type { ReactNode } from 'react';

/** A normal-layout action region; domain owners retain all save/state behavior. */
export function WorkspaceActionBar({ status, children }: { status: ReactNode; children: ReactNode }) {
  return <footer className="workspace-action-bar">
    <div className="workspace-action-status" role="status">{status}</div>
    <div className="workspace-action-controls">{children}</div>
  </footer>;
}
