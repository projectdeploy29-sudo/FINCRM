import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'

const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))

export default function PipelinePage({ api, dateRange, onDrillDown }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  useEffect(() => { api.get(withDateRange('/pipeline/', dateRange)).then(setData).catch((exception) => setError(exception.message)) }, [api, dateRange])
  const open = (title, filter = {}) => onDrillDown({ title, kind: 'pipeline-leads', filter })
  return <section className="page">
    <h2>Pipeline</h2><p>Lead value and payment status in your reporting scope.</p>
    {error && <p role="alert">{error}</p>}
    {data && <>
      <div className="metric-grid">
        <button type="button" className="metric-card drill-metric" onClick={() => open('All pipeline leads')}><span>Total leads</span><strong>{data.total_leads}</strong></button>
        <button type="button" className="metric-card drill-metric" onClick={() => open('Leads by expected value')}><span>Total expected value</span><strong>{money(data.total_value)}</strong></button>
        <button type="button" className="metric-card drill-metric" onClick={() => onDrillDown({ title: 'Payments in selected range', kind: 'payments' })}><span>Payments in selected range</span><strong>{money(data.payments_in_range ?? data.payments_this_month)}</strong></button>
        <button type="button" className="metric-card drill-metric" onClick={() => open('Overdue payments', { payment_status: 'overdue' })}><span>Overdue</span><strong>{data.overdue}</strong></button>
      </div>
      <h3>Leads by stage</h3><input className="board-search" aria-label="Search leads" placeholder="Find a lead…" value={search} onChange={(event) => setSearch(event.target.value)} />
      <div className="pipeline-board">{[['new','New enquiry'],['contacted','Contacted'],['qualified','Qualified'],['unqualified','Unqualified']].map(([stage,label]) => {
        const leads=data.leads.filter((lead)=>lead.status===stage && (!search || `${lead.contact_name} ${lead.lead_code}`.toLowerCase().includes(search.toLowerCase())))
        return <section className={`pipeline-column stage-${stage}`} key={stage}><button type="button" className="pipeline-column-heading" onClick={() => open(`${label} leads`, { status: stage })}><b>{label}</b><span>{leads.length}</span></button><strong>{money(leads.reduce((sum,lead)=>sum+Number(lead.expected_amount||0),0))}</strong>{leads.map((lead)=><button type="button" className="lead-card drill-lead-card" key={lead.id} onClick={() => onDrillDown({ title: lead.contact_name, kind: 'lead-detail', id: lead.id })}><b>{lead.contact_name}</b><small>{lead.lead_code} · {lead.assigned_to || 'Unassigned'}</small><strong>{money(lead.expected_amount)}</strong><span className={`status status-${lead.payment_status}`}>{lead.payment_status.replace('_',' ')}</span></button>)}{leads.length===0&&<p className="empty-column">No leads</p>}</section>
      })}</div>
    </>}
  </section>
}
