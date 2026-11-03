import type { ExerciseRecord } from '../../../types';
import { useAuthenticatedBlobUrl } from '../../../hooks/useAuthenticatedBlobUrl';

function Attachment({ record, asset, bookName, showLabel }: { record: ExerciseRecord; showLabel: boolean; asset: NonNullable<ExerciseRecord['source_attachments']>[number]; bookName: string }) {
  const { url, loading, error } = useAuthenticatedBlobUrl(`/exercises/${encodeURIComponent(record.id)}/assets/${encodeURIComponent(asset.asset_id)}?book_name=${encodeURIComponent(bookName)}`);
  return <figure className="exercise-source-image">{url && <img src={url} alt={asset.label || '题目来源附图'} />}{showLabel && asset.label && <figcaption>{asset.label}</figcaption>}{loading && <p role="status">正在读取附图…</p>}{error && <p role="alert">附图暂不可读，请恢复附件后继续：{error}</p>}</figure>;
}

export function ExerciseAttachments({ record, bookName, roles, showLabels = true }: { showLabels?: boolean; record: ExerciseRecord; bookName: string; roles: string[] }) {
  return <>{record.source_attachments?.filter(asset => roles.includes(asset.role)).map(asset => <Attachment showLabel={showLabels} key={`${asset.asset_id}:${asset.role}`} record={record} asset={asset} bookName={bookName} />)}</>;
}
