import { EmptyState } from '../ui/AsyncState';
import type { ReactNode } from 'react';

export default function LearningEmptyWorkspace({
  isLoading,
  scopeSelector,
}: {
  isLoading: boolean;
  scopeSelector: ReactNode;
}) {
  return (
    <EmptyState variant="prompt" title="从一个问题开始" description={isLoading ? '正在准备当前学习范围' : undefined} action={scopeSelector} className="learning-empty-workspace" />
  );
}
