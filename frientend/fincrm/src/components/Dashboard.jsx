import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'
import CountUp from './CountUp'
import LoadingSkeleton from './LoadingSkeleton'

const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))

export default function Dashboard({ api, user, dateRange, onNavigate, onDrillDown }) {
  const [pipeline, setPipeline] = useState(null)
  const [report, setReport] = useState(null)
  const [today, setToday] = useState({ tasks: [], followups: [] })
  const [subscription, setSubscription] = useState(null)
  const [error, setError] = useState('')
  const [requestKey, setRequestKey] = useState(0)
  useEffect(() => {
    let active = true
    Promise.all([api.get(withDateRange('/pipeline/', dateRange)), api.get(withDateRange('/reports/summary/', dateRange)), api.get(withDateRange('/tasks/my-tasks/', dateRange)), api.get(withDateRange('/followups/today/', dateRange))]).then(([pipe, summary, tasks, followups]) => {
      if (!active) return
      setPipeline(pipe); setReport(summary)
      const now=new Date(); const date=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10)
      const start=dateRange?.start_date || date; const end=dateRange?.end_date || date
      setToday({ tasks:(Array.isArray(tasks)?tasks:tasks.results||[]).filter((task)=>!['COMPLETED','CANCELLED'].includes(task.status)&&String(task.due_date).slice(0,10)>=start&&String(task.due_date).slice(0,10)<=end).slice(0,4), followups:(Array.isArray(followups)?followups:followups.results||[]).slice(0,4) })
    }).catch((exception) => { if (active) setError(exception.message) })
    return () => { active = false }
  }, [api, dateRange, requestKey])
  const isOrganizationAdmin = (user?.role?.hierarchy_level || 0) >= 90
  useEffect(() => {
    if (!isOrganizationAdmin) { setSubscription(null); return undefined }
    let active = true
    api.get('/subscriptions/current/')
      .then((result) => { if (active) setSubscription(result) })
      .catch(() => { if (active) setSubscription(null) })
    return () => { active = false }
  }, [api, isOrganizationAdmin])
  const open = (title, kind, filter = {}) => onDrillDown({ title, kind, filter })
  const metric = (title, value, drill) => <button type="button" className="metric-card drill-metric" key={title} onClick={drill}><span>{title}</span><strong><CountUp value={value} /></strong></button>
  const displayName = user?.first_name || user?.user?.first_name || user?.user?.username || user?.username || 'Team member'
  return <section className="page dashboard-page">
    <div className="dashboard-hero">
      <div>
        <div className="hero-status-row"><p className="dashboard-eyebrow">WORKSPACE OVERVIEW</p><span><i /> Live workstream active</span></div>
        <h2>Welcome back, {displayName}</h2>
        <p>{user?.organization?.name || 'Organization'} · Direct sign-off work requires your attention today.</p>
      </div>
      <div className="hero-actions">
        <button type="button" className="primary-action" onClick={() => onNavigate('today')}><span className="action-icon">!</span> View Today's priorities</button>
        <button type="button" className="secondary-action" onClick={() => onNavigate('pipeline')}><span className="action-icon">▤</span> Open Pipeline</button>
        <button type="button" className="secondary-action" onClick={() => onNavigate('reports')}><span className="action-icon">▥</span> Open Report</button>
      </div>
    </div>
    <div className="workspace-strip">
      <div><span>Reporting scope</span><strong>{dateRange?.preset === 'custom' ? `${dateRange.start_date} — ${dateRange.end_date}` : dateRange?.preset === 'month' ? 'Month to date' : dateRange?.preset === 'year' ? 'Year to date' : 'Today'}</strong></div>
      <div><span>Entity</span><strong>{user?.organization?.name || 'Organization'}</strong></div>
      <div><span>Workspace</span><strong>Operational Desk</strong></div>
    </div>
    {isOrganizationAdmin && subscription?.has_active_subscription && subscription.ai_tokens && <section className="dashboard-ai-usage">
      <div className="dashboard-ai-usage-heading"><span className="dashboard-ai-usage-icon" aria-hidden="true">✦</span><div><p>Organization AI usage</p><small>Daily plan allowance · usage across all organization users</small></div></div>
      <div className="dashboard-ai-usage-total"><strong>{Number(subscription.ai_tokens.used || 0).toLocaleString()}</strong><span>used</span><i>/</i><strong>{subscription.ai_tokens.total == null ? 'Unlimited' : Number(subscription.ai_tokens.total).toLocaleString()}</strong><span>total today</span></div>
      {subscription.ai_tokens.total != null && <div className="dashboard-ai-usage-track" aria-label={`${subscription.ai_tokens.used} of ${subscription.ai_tokens.total} AI tokens used today`}><i style={{ width: `${Math.min(100, (Number(subscription.ai_tokens.used || 0) / Math.max(1, Number(subscription.ai_tokens.total))) * 100)}%` }} /></div>}
      <small className="dashboard-ai-usage-foot">Input and output tokens reported by the AI provider are counted for today.</small>
    </section>}
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(''); setRequestKey((current) => current + 1) }}>Try again</button></p>}
    {!error && (!pipeline || !report) && <LoadingSkeleton label="Loading dashboard" />}
    {pipeline && report && <>
      <div className="section-heading"><h3>Activity overview</h3><button type="button" onClick={() => onNavigate('today')}>Open tasks and follow-ups</button></div>
      <div className="metric-grid">{metric('Active leads',report.active_leads,()=>open('Active leads','leads',{active:true}))}{metric('Follow-ups',report.followups,()=>open('Follow-ups','followups'))}{metric('Overdue tasks',report.tasks_overdue,()=>open('Overdue tasks','tasks',{overdue:true}))}{metric('Customers under review',report.customers_under_review,()=>open('Customers under review','customers',{status:'under_review'}))}</div>
      <div className="today-preview"><article><h4>Tasks in selected range</h4>{today.tasks.length?today.tasks.map((task)=><button className="preview-row" type="button" key={task.id} onClick={()=>onDrillDown({kind:'record-detail',resource:'tasks',id:task.id,title:task.title})}>{task.title}<small>{task.priority} · {new Date(task.due_date).toLocaleString()}</small></button>):<p className="muted">No tasks in this range.</p>}</article><article><h4>Follow-ups in selected range</h4>{today.followups.length?today.followups.map((item)=><div className="preview-item" key={item.id}><button className="preview-row" type="button" onClick={()=>onDrillDown({kind:'record-detail',resource:'followups',followupKind:`${item.kind}s`,id:item.id,title:`${item.contact_name || item.kind} follow-up`})}>{item.contact_name || `${item.kind} follow-up`}<small>{item.followup_type} · {new Date(item.scheduled_at).toLocaleString()}</small></button><div>{item.contact_phone && <a href={`tel:${item.contact_phone}`}>Call {item.contact_phone}</a>}{item.contact_email && <a href={`mailto:${item.contact_email}`}>{item.contact_email}</a>}</div></div>):<p className="muted">No follow-ups in this range.</p>}</article></div>
      <div className="section-heading"><h3>Pipeline</h3><button type="button" onClick={() => onNavigate('pipeline')}>Open pipeline</button></div>
      <div className="metric-grid">{metric('Lead value',money(pipeline.total_value),()=>open('Pipeline leads','pipeline-leads'))}{metric('Payments in selected range',money(pipeline.payments_in_range ?? pipeline.payments_this_month),()=>open('Payments in selected range','payments'))}{metric('Paid leads',pipeline.paid,()=>open('Paid leads','pipeline-leads',{payment_status:'paid'}))}{metric('Overdue payments',pipeline.overdue,()=>open('Overdue payments','pipeline-leads',{payment_status:'overdue'}))}</div>
      <div className="section-heading"><h3>Reports</h3><button type="button" onClick={() => onNavigate('reports')}>Open report</button></div>
      <div className="dashboard-stages">{report.leads_by_status.map((row) => <button type="button" key={row.status} onClick={()=>open(`${row.status.replaceAll('_',' ')} leads`,'leads',{status:row.status})}><span>{row.status.replaceAll('_',' ')}</span><b><CountUp value={row.count} /></b></button>)}</div>
    </>}
  </section>
}
