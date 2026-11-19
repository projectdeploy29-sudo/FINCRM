import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'

const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))

export default function Dashboard({ api, user, dateRange, onNavigate, onDrillDown }) {
  const [pipeline, setPipeline] = useState(null)
  const [report, setReport] = useState(null)
  const [today, setToday] = useState({ tasks: [], followups: [] })
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([api.get(withDateRange('/pipeline/', dateRange)), api.get(withDateRange('/reports/summary/', dateRange)), api.get(withDateRange('/tasks/my-tasks/', dateRange)), api.get(withDateRange('/followups/today/', dateRange))]).then(([pipe, summary, tasks, followups]) => {
      setPipeline(pipe); setReport(summary)
      const now=new Date(); const date=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10)
      const start=dateRange?.start_date || date; const end=dateRange?.end_date || date
      setToday({ tasks:(Array.isArray(tasks)?tasks:tasks.results||[]).filter((task)=>!['COMPLETED','CANCELLED'].includes(task.status)&&String(task.due_date).slice(0,10)>=start&&String(task.due_date).slice(0,10)<=end).slice(0,4), followups:(Array.isArray(followups)?followups:followups.results||[]).slice(0,4) })
    }).catch((exception) => setError(exception.message))
  }, [api, dateRange])
  const open = (title, kind, filter = {}) => onDrillDown({ title, kind, filter })
  const metric = (title, value, drill) => <button type="button" className="metric-card drill-metric" key={title} onClick={drill}><span>{title}</span><strong>{value}</strong></button>
  return <section className="page">
    <h2>Dashboard</h2><p>{user?.organization?.name || 'Organization'} · Your work at a glance.</p>
    {error && <p role="alert">{error}</p>}
    {pipeline && report && <>
      <div className="section-heading"><h3>Activity overview</h3><button type="button" onClick={() => onNavigate('today')}>Open tasks and follow-ups</button></div>
      <div className="metric-grid">{metric('Active leads',report.active_leads,()=>open('Active leads','leads',{active:true}))}{metric('Follow-ups',report.followups,()=>open('Follow-ups','followups'))}{metric('Overdue tasks',report.tasks_overdue,()=>open('Overdue tasks','tasks',{overdue:true}))}{metric('Applications',report.applications_by_status.reduce((sum, row) => sum + row.count, 0),()=>open('Applications','applications'))}</div>
      <div className="today-preview"><article><h4>Tasks in selected range</h4>{today.tasks.length?today.tasks.map((task)=><button className="preview-row" type="button" key={task.id} onClick={()=>onDrillDown({kind:'record-detail',resource:'tasks',id:task.id,title:task.title})}>{task.title}<small>{task.priority} · {new Date(task.due_date).toLocaleString()}</small></button>):<p className="muted">No tasks in this range.</p>}</article><article><h4>Follow-ups in selected range</h4>{today.followups.length?today.followups.map((item)=><div className="preview-item" key={item.id}><button className="preview-row" type="button" onClick={()=>onDrillDown({kind:'record-detail',resource:'followups',followupKind:`${item.kind}s`,id:item.id,title:`${item.contact_name || item.kind} follow-up`})}>{item.contact_name || `${item.kind} follow-up`}<small>{item.followup_type} · {new Date(item.scheduled_at).toLocaleString()}</small></button><div>{item.contact_phone && <a href={`tel:${item.contact_phone}`}>Call {item.contact_phone}</a>}{item.contact_email && <a href={`mailto:${item.contact_email}`}>{item.contact_email}</a>}</div></div>):<p className="muted">No follow-ups in this range.</p>}</article></div>
      <div className="section-heading"><h3>Pipeline</h3><button type="button" onClick={() => onNavigate('pipeline')}>Open pipeline</button></div>
      <div className="metric-grid">{metric('Lead value',money(pipeline.total_value),()=>open('Pipeline leads','pipeline-leads'))}{metric('Payments in selected range',money(pipeline.payments_in_range ?? pipeline.payments_this_month),()=>open('Payments in selected range','payments'))}{metric('Paid leads',pipeline.paid,()=>open('Paid leads','pipeline-leads',{payment_status:'paid'}))}{metric('Overdue payments',pipeline.overdue,()=>open('Overdue payments','pipeline-leads',{payment_status:'overdue'}))}</div>
      <div className="section-heading"><h3>Reports</h3><button type="button" onClick={() => onNavigate('reports')}>Open report</button></div>
      <div className="dashboard-stages">{report.leads_by_status.map((row) => <button type="button" key={row.status} onClick={()=>open(`${row.status.replaceAll('_',' ')} leads`,'leads',{status:row.status})}><span>{row.status.replaceAll('_',' ')}</span><b>{row.count}</b></button>)}</div>
    </>}
  </section>
}
