export default function LoadingSkeleton({ metricCount = 4, panelCount = 2, label = 'Loading content', variant = 'dashboard' }) {
  return <div className="loading-skeleton" role="status" aria-live="polite" aria-label={label} aria-busy="true">
    <span className="visually-hidden">{label}…</span>
    {variant === 'table' ? <div className="skeleton-table" aria-hidden="true">
      <i className="skeleton-line skeleton-table-head" />
      {Array.from({ length: 5 }, (_, index) => <i className="skeleton-line skeleton-table-row" key={index} />)}
    </div> : <>
      <div className={`skeleton-metrics${variant === 'cards' ? ' is-card-layout' : ''}`} aria-hidden="true">
        {Array.from({ length: metricCount }, (_, index) => <div className="skeleton-metric" key={index}>
          <i className="skeleton-line skeleton-label" />
          <i className="skeleton-line skeleton-value" />
          <i className="skeleton-line skeleton-detail" />
        </div>)}
      </div>
      {panelCount > 0 && <div className="skeleton-panels" aria-hidden="true">
        {Array.from({ length: panelCount }, (_, index) => <div className="skeleton-panel" key={index}>
          <i className="skeleton-line skeleton-panel-title" />
          <i className="skeleton-line skeleton-panel-row" />
          <i className="skeleton-line skeleton-panel-row" />
          <i className="skeleton-line skeleton-panel-row" />
          <i className="skeleton-line skeleton-panel-row" />
        </div>)}
      </div>}
    </>}
  </div>
}
