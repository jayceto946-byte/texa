import { lazy, Suspense } from 'react';
import RemoteConnectionGate from './components/RemoteConnectionGate';

// Authenticated workspace modules are not fetched until the gate opens.
const Workspace = lazy(() => import('./Workspace'));

export default function App() {
  return <RemoteConnectionGate>
    <Suspense fallback={<div role="status" style={{ padding: 24 }}>正在加载学习工作区…</div>}>
      <Workspace />
    </Suspense>
  </RemoteConnectionGate>;
}
