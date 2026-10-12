import './WorkspaceSkeleton.css';

export default function WorkspaceSkeleton({ label = '正在读取页面', header = true, reading = false }: {
  label?: string;
  header?: boolean;
  reading?: boolean;
}) {
  return <div className={`workspace-skeleton ${reading ? 'is-reading' : ''}`} role="status" aria-label={label} aria-busy="true">
    <div aria-hidden="true">
      {header && <div className="workspace-skeleton-header"><span className="skeleton-shape skeleton-title" /><span className="skeleton-shape skeleton-action" /></div>}
      <div className="workspace-skeleton-content">
        <div className="skeleton-shape skeleton-subtitle" />
        {Array.from({ length: reading ? 3 : 5 }, (_, index) => <div className="workspace-skeleton-row" key={index}>
          <span className="skeleton-shape skeleton-line" />
          <span className="skeleton-shape skeleton-line is-short" />
          {reading && <span className="skeleton-shape skeleton-line" />}
        </div>)}
      </div>
    </div>
  </div>;
}
