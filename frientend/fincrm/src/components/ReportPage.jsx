import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'

function Bars({ title, rows, color = 'blue', onSelect }) {
  const max = Math.max(1, ...rows.map((row) => Number(row.count)))
  return <article className="chart-card"><h3>{title}</h3>{rows.length ? rows.map((row) => <button type="button" className="bar-row drill-bar-row" key={row.status} onClick={() => onSelect(row)}><span>{row.status.replaceAll('_', ' ')}</span><div className="bar-track"><i className={`bar-${color}`} style={{ width: `${Math.max(4, Number(row.count) / max * 100)}%` }} /></div><b>{row.count}</b></button>) : <p>No data yet.</p>}</article>
}

export default function ReportPage({ api, dateRange, onDrillDown }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.get(withDateRange('/reports/summary/', dateRange)).then(setData).catch((exception) => setError(exception.message)) }, [api, dateRange])
  const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))
  const open = (title, kind, filter = {}) => onDrillDown({ title, kind, filter })
  const metric = (title, value, drill) => <button type="button" className="metric-card drill-metric" key={title} onClick={drill}><span>{title}</span><strong>{value}</strong></button>
  return <section className="page"><h2>Report</h2><p>Activity and revenue across the work you can access.</p>
    {error && <p role="alert">{error}</p>}
    {data && <>
      <div className="metric-grid">{metric('Active leads',data.active_leads,()=>open('Active leads','leads',{active:true}))}{metric('Won',data.won,()=>open('Won leads','leads',{won:true}))}{metric('Customers',data.customers,()=>open('Customers','customers'))}{metric('Follow-ups',data.followups,()=>open('Follow-ups','followups'))}{metric('Overdue tasks',data.tasks_overdue,()=>open('Overdue tasks','tasks',{overdue:true}))}{metric('Revenue in selected range',money(data.revenue_in_range ?? data.revenue_this_month),()=>open('Payments in selected range','payments'))}</div>
      <div className="chart-grid"><Bars title="Leads by stage" rows={data.leads_by_status} onSelect={(row)=>open(`${row.status.replaceAll('_',' ')} leads`,'leads',{status:row.status})} /><Bars title="Applications by status" rows={data.applications_by_status} color="green" onSelect={(row)=>open(`${row.status.replaceAll('_',' ')} applications`,'applications',{status:row.status})} /><Bars title="Tasks by status" rows={data.tasks_by_status} color="orange" onSelect={(row)=>open(`${row.status.replaceAll('_',' ')} tasks`,'tasks',{status:row.status})} /></div>
    </>}
  </section>
}
