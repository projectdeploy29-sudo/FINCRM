import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'
import CountUp from './CountUp'
import LoadingSkeleton from './LoadingSkeleton'

const chartColors = ['#ec303b', '#263555', '#647899', '#15916f', '#a9b3c3']
const money = (value) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))
const label = (value) => String(value || '').replaceAll('_', ' ')

function DonutChart({ title, rows, onSelect }) {
  const total = rows.reduce((sum, row) => sum + Number(row.count || 0), 0)
  const radius = 48
  const circumference = 2 * Math.PI * radius
  const segments = rows.reduce((result, row, index) => {
    const amount = total ? Number(row.count || 0) / total * circumference : 0
    const offset = result.length ? result[result.length - 1].offset + result[result.length - 1].amount : 0
    const segment = { ...row, amount, offset, color: chartColors[index % chartColors.length] }
    return [...result, segment]
  }, [])
  return <article className="report-chart-card">
    <header><h3>{title}</h3><span>{total.toLocaleString('en-IN')} records</span></header>
    {total ? <div className="report-donut-layout">
      <div className="report-donut-wrap"><svg className="report-donut" viewBox="0 0 120 120" role="img" aria-label={`${title}, ${total} records`}>
        <circle className="report-donut-track" cx="60" cy="60" r={radius} />
        {segments.map((row) => <circle key={row.status} cx="60" cy="60" r={radius} fill="none" stroke={row.color} strokeWidth="15" strokeDasharray={`${row.amount} ${circumference - row.amount}`} strokeDashoffset={-row.offset} />)}
      </svg><div className="report-donut-center"><strong><CountUp value={total} /></strong><span>Total</span></div></div>
      <div className="report-legend">{segments.map((row) => <button type="button" key={row.status} onClick={() => onSelect(row)}><i style={{ backgroundColor: row.color }} /><span>{label(row.status)}</span><b>{row.count}</b><small>{Math.round(Number(row.count || 0) / total * 100)}%</small></button>)}</div>
    </div> : <p className="report-empty">No records in this date range.</p>}
  </article>
}

function StageBars({ title, rows, order, onSelect }) {
  const ordered = order.map((status) => rows.find((row) => row.status === status) || { status, count: 0 })
  const max = Math.max(1, ...ordered.map((row) => Number(row.count || 0)))
  return <article className="report-chart-card report-stage-card"><header><h3>{title}</h3><span>By current stage</span></header>
    {ordered.map((row, index) => <button type="button" className="report-stage-row" key={row.status} onClick={() => onSelect(row)}>
      <span className="report-stage-name"><i style={{ backgroundColor: chartColors[index % chartColors.length] }} />{label(row.status)}</span>
      <span className="report-stage-track"><i style={{ width: `${Number(row.count || 0) / max * 100}%`, backgroundColor: chartColors[index % chartColors.length] }} /></span>
      <b>{row.count}</b>
    </button>)}
  </article>
}

function RevenueChart({ selected, lifetime, onSelect }) {
  const max = Math.max(1, Number(selected || 0), Number(lifetime || 0))
  const rows = [
    { title: 'Selected period', amount: Number(selected || 0), filter: true },
    { title: 'Lifetime revenue', amount: Number(lifetime || 0), filter: false },
  ]
  return <article className="report-chart-card report-revenue-card"><header><h3>Verified revenue</h3><span>Received payments</span></header>
    <div className="report-revenue-summary"><strong>{money(lifetime)}</strong><span>total collected</span></div>
    <div className="report-revenue-bars">{rows.map((row) => <button type="button" key={row.title} onClick={() => onSelect(row)}>
      <span>{row.title}</span><b>{money(row.amount)}</b><i><em style={{ width: `${row.amount / max * 100}%` }} /></i>
    </button>)}</div>
  </article>
}

export default function ReportPage({ api, dateRange, onDrillDown }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [requestKey, setRequestKey] = useState(0)
  useEffect(() => {
    let active = true
    api.get(withDateRange('/reports/summary/', dateRange)).then((result) => { if (active) setData(result) }).catch((exception) => { if (active) setError(exception.message) })
    return () => { active = false }
  }, [api, dateRange, requestKey])
  const open = (title, kind, filter = {}) => onDrillDown({ title, kind, filter })
  const metric = (title, value, drill) => <button type="button" className="metric-card drill-metric" key={title} onClick={drill}><span>{title}</span><strong><CountUp value={value} /></strong></button>
  return <section className="page"><h2>Report</h2><p>Activity and revenue across the work you can access.</p>
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(''); setRequestKey((current) => current + 1) }}>Try again</button></p>}
    {!data && !error && <LoadingSkeleton label="Loading report" />}
    {data && <>
      <div className="metric-grid">{metric('Active leads',data.active_leads,()=>open('Active leads','leads',{active:true}))}{metric('Won',data.won,()=>open('Won leads','leads',{won:true}))}{metric('Customers',data.customers,()=>open('Customers','customers'))}{metric('Follow-ups',data.followups,()=>open('Follow-ups','followups'))}{metric('Overdue tasks',data.tasks_overdue,()=>open('Overdue tasks','tasks',{overdue:true}))}{metric('Revenue in selected range',money(data.revenue_in_range ?? data.revenue_this_month),()=>open('Payments in selected range','payments'))}</div>
      <div className="report-insights-grid">
        <DonutChart title="Lead stage mix" rows={data.leads_by_status || []} onSelect={(row)=>open(`${label(row.status)} leads`,'leads',{status:row.status})} />
        <StageBars title="Customer journey" rows={data.customers_by_status || []} order={['new','contacted','under_review','converted']} onSelect={(row)=>open(`${label(row.status)} customers`,'customers',{status:row.status})} />
        <DonutChart title="Task completion" rows={data.tasks_by_status || []} onSelect={(row)=>open(`${label(row.status)} tasks`,'tasks',{status:row.status})} />
        <RevenueChart selected={data.revenue_in_range ?? data.revenue_this_month} lifetime={data.revenue_total} onSelect={(row)=>open(row.title,'payments',row.filter ? {} : {verification_status:'VERIFIED'})} />
      </div>
    </>}
  </section>
}
