import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'
import CountUp from './CountUp'
import LoadingSkeleton from './LoadingSkeleton'

const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))
const INITIAL_PIPELINE_LEADS = 4
const PIPELINE_LEADS_PER_EXPANSION = 4

export default function PipelinePage({ api, dateRange, onDrillDown }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [requestKey, setRequestKey] = useState(0)
  const [visibleCounts, setVisibleCounts] = useState({})
  useEffect(() => {
    let active = true
    api.get(withDateRange('/pipeline/', dateRange)).then((result) => { if (active) setData(result) }).catch((exception) => { if (active) setError(exception.message) })
    return () => { active = false }
  }, [api, dateRange, requestKey])
  const open = (title, filter = {}) => onDrillDown({ title, kind: 'pipeline-leads', filter })
  return <section className="page">
    <h2>Pipeline</h2><p>Lead value and payment status in your reporting scope.</p>
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(''); setRequestKey((current) => current + 1) }}>Try again</button></p>}
    {!error && !data && <LoadingSkeleton label="Loading pipeline" />}
    {data && <>
      <div className="metric-grid">
        <button type="button" className="metric-card drill-metric" onClick={() => open('All pipeline leads')}><span>Total leads</span><strong><CountUp value={data.total_leads} /></strong></button>
        <button type="button" className="metric-card drill-metric" onClick={() => open('Leads by expected value')}><span>Total expected value</span><strong><CountUp value={money(data.total_value)} /></strong></button>
        <button type="button" className="metric-card drill-metric" onClick={() => onDrillDown({ title: 'Payments in selected range', kind: 'payments' })}><span>Payments in selected range</span><strong><CountUp value={money(data.payments_in_range ?? data.payments_this_month)} /></strong></button>
        <button type="button" className="metric-card drill-metric" onClick={() => open('Overdue payments', { payment_status: 'overdue' })}><span>Overdue</span><strong><CountUp value={data.overdue} /></strong></button>
      </div>
      <h3>Leads by stage</h3><input className="board-search" aria-label="Search leads" placeholder="Find a lead…" value={search} onChange={(event) => { setSearch(event.target.value); setVisibleCounts({}) }} />
      <p className="pipeline-mobile-hint">Swipe horizontally to explore stages <span aria-hidden="true">→</span></p>
      <div className="pipeline-board">{[['new','New'],['contacted','Contacted'],['approved','Approved'],['disbursed','Disbursed'],['completed','Completed']].map(([stage,label]) => {
        const leads=data.leads.filter((lead)=>lead.status===stage && (!search || `${lead.contact_name} ${lead.lead_code}`.toLowerCase().includes(search.toLowerCase())))
        const visibleCount = visibleCounts[stage] ?? INITIAL_PIPELINE_LEADS
        const visibleLeads = leads.slice(0, visibleCount)
        const isExpanded = visibleCount >= leads.length
        return <section className={`pipeline-column stage-${stage}`} key={stage}>
          <button type="button" className="pipeline-column-heading" onClick={() => open(`${label} leads`, { status: stage })}><b>{label}</b><span>{leads.length}</span></button>
          <strong>{money(leads.reduce((sum,lead)=>sum+Number(lead.expected_amount||0),0))}</strong>
          {visibleLeads.map((lead, index)=><button type="button" className="lead-card drill-lead-card pipeline-lead-enter" style={{ '--pipeline-row-delay': `${Math.min(index % PIPELINE_LEADS_PER_EXPANSION, PIPELINE_LEADS_PER_EXPANSION - 1) * 65}ms` }} key={lead.id} onClick={() => onDrillDown({ title: lead.contact_name, kind: 'lead-detail', id: lead.id })}><b>{lead.contact_name}</b><small>{lead.lead_code} · {lead.assigned_to || 'Unassigned'}</small><strong>{money(lead.expected_amount)}</strong><span className={`status status-${lead.payment_status}`}>{lead.payment_status.replace('_',' ')}</span></button>)}
          {leads.length === 0 && <p className="empty-column">No leads</p>}
          {leads.length > INITIAL_PIPELINE_LEADS && <button type="button" className="pipeline-show-more" aria-expanded={isExpanded} onClick={() => setVisibleCounts((current) => ({ ...current, [stage]: isExpanded ? INITIAL_PIPELINE_LEADS : Math.min(visibleCount + PIPELINE_LEADS_PER_EXPANSION, leads.length) }))}>{isExpanded ? 'Show less' : `Show ${Math.min(PIPELINE_LEADS_PER_EXPANSION, leads.length - visibleCount)} more`}</button>}
        </section>
      })}</div>
    </>}
  </section>
}
