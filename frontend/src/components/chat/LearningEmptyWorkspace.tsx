export default function LearningEmptyWorkspace({
  isLoading,
}: {
  isLoading: boolean;
}) {
  return (
    <section className="learning-empty-workspace" aria-label="开始学习会话">
      <h1>Ask Texa</h1>
      <p>{isLoading ? '正在准备当前学习范围' : '输入问题、公式或上传图片'}</p>
    </section>
  );
}
