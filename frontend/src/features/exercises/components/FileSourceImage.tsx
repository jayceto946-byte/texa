import { useAuthenticatedBlobUrl } from '../../../hooks/useAuthenticatedBlobUrl';

export function FileSourceImage({ sourceId, assetId, bookName, label }: { sourceId: string; assetId: string; bookName: string; label: string }) {
  const { url, loading, error } = useAuthenticatedBlobUrl(`/exercises/file-sources/${encodeURIComponent(sourceId)}/assets/${encodeURIComponent(assetId)}?book_name=${encodeURIComponent(bookName)}`);
  return <figure className="exercise-source-image">{url && <img src={url} alt={label || '解析包中的来源图片'} />}{loading && <p role="status">正在读取来源图片…</p>}{error && <p role="status">来源图片暂不可读：{error}</p>}</figure>;
}
