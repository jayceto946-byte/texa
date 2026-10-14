import { lazy, Suspense } from 'react';
import RemoteConnectionGate from './components/RemoteConnectionGate';
import WorkspaceSkeleton from './components/ui/WorkspaceSkeleton';

// Authenticated workspace modules are not fetched until the gate opens.
const Workspace = lazy(() => import('./Workspace'));

export default function App() {
  return <RemoteConnectionGate>
    <Suspense fallback={<WorkspaceSkeleton label="正在准备学习工作区" />}>
      <Workspace />
    </Suspense>
  </RemoteConnectionGate>;
}
