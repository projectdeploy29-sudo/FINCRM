import { useEffect, useState } from 'react'
import CountUp from './CountUp'
import LoadingSkeleton from './LoadingSkeleton'

const money = (value, currency = 'INR') => value == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value))
const dateTime = (value) => value ? new Date(value).toLocaleString() : '—'

export default function LeadPortalDashboard({ api }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [requestKey, setRequestKey] = useState(0)
  useEffect(() => {
    let active = true
    api.get('/leads/portal-dashboard/').then((result) => { if (active) setData(result) }).catch((exception) => { if (active) setError(exception.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [api, requestKey])
  const currency = data?.lead?.currency || 'INR'
  return <section className="page">
    <div className="dashboard-hero lead-portal-hero">
      <div>
        <p className="dashboard-eyebrow">BORROWER PORTAL</p>
        <h2>My loan dashboard</h2>
        <p>{data?.lead?.contact_name || 'Your loan and follow-up information.'}</p>
      </div>
      {data?.loan?.next_payment_due_date && <button type="button" className="primary-action" onClick={() => document.querySelector('.lead-portal-payments')?.scrollIntoView({ behavior: 'smooth' })}>Next payment <span>→</span></button>}
    </div>
    {loading && !data && <LoadingSkeleton label="Loading your account" />}
    {error && <p role="alert">{error} <button type="button" onClick={() => { setError(''); setLoading(true); setRequestKey((current) => current + 1) }}>Try again</button></p>}
    {data && <>
      <div className="metric-grid">
        <article><span>Approved loan</span><strong><CountUp value={money(data.loan.approved_amount, currency)} /></strong></article>
        <article><span>Loan principal</span><strong><CountUp value={money(data.loan.disbursed_amount, currency)} /></strong></article>
        <article><span>Cash paid to you</span><strong><CountUp value={money(data.loan.net_disbursed_amount, currency)} /></strong></article>
        <article><span>Upfront deductions</span><strong><CountUp value={money(data.loan.upfront_deductions_amount, currency)} /></strong></article>
        <article><span>Monthly repayment</span><strong><CountUp value={money(data.loan.monthly_repayment_amount, currency)} /></strong></article>
        <article><span>Rate / method / tenure</span><strong>{data.loan.annual_interest_rate == null ? '—' : `${data.loan.annual_interest_rate}% · ${data.loan.interest_calculation_method?.replaceAll('_', ' ')} · ${data.loan.tenure_months || '—'} months`}</strong></article>
        <article><span>Total scheduled interest</span><strong>{money(data.loan.total_scheduled_interest, currency)}</strong></article>
        <article><span>Total scheduled repayment</span><strong>{money(data.loan.total_scheduled_repayment, currency)}</strong></article>
        <article><span>Disbursed on</span><strong>{data.loan.disbursed_at ? dateTime(data.loan.disbursed_at) : '—'}</strong></article>
        <article><span>Next payment due</span><strong>{data.loan.next_payment_due_date ? new Date(`${data.loan.next_payment_due_date}T00:00:00`).toLocaleDateString() : '—'}</strong></article>
        <article><span>Total paid</span><strong>{money(data.loan.total_paid, currency)}</strong></article>
        <article><span>Remaining balance</span><strong>{money(data.loan.remaining_balance, currency)}</strong></article>
      </div>
      <h3 className="lead-portal-payments">Upcoming payments</h3>
      {data.upcoming_payments.length ? <div className="table-wrap"><table><thead><tr><th>Installment</th><th>Due date</th><th>Principal</th><th>Interest</th><th>Amount remaining</th><th>Status</th></tr></thead><tbody>{data.upcoming_payments.map((item) => <tr key={item.id}><td>{item.installment_number}</td><td>{new Date(`${item.due_date}T00:00:00`).toLocaleDateString()}</td><td>{money(item.principal_due, currency)}</td><td>{money(item.interest_due, currency)}</td><td>{money(item.amount, currency)}</td><td>{item.status}</td></tr>)}</tbody></table></div> : <p className="muted">No upcoming payments.</p>}
      {data.overdue_payments.length > 0 && <><h3>Overdue payments</h3><div className="table-wrap"><table><thead><tr><th>Installment</th><th>Due date</th><th>Principal</th><th>Interest</th><th>Amount remaining</th><th>Status</th></tr></thead><tbody>{data.overdue_payments.map((item) => <tr key={item.id}><td>{item.installment_number}</td><td>{new Date(`${item.due_date}T00:00:00`).toLocaleDateString()}</td><td>{money(item.principal_due, currency)}</td><td>{money(item.interest_due, currency)}</td><td>{money(item.amount, currency)}</td><td>{item.status}</td></tr>)}</tbody></table></div></>}
      <h3>Payment history</h3>
      {data.payment_history.length ? <div className="table-wrap"><table><thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Status</th><th>Reference</th></tr></thead><tbody>{data.payment_history.map((item) => <tr key={item.id}><td>{new Date(`${item.payment_date}T00:00:00`).toLocaleDateString()}</td><td>{money(item.amount, currency)}</td><td>{item.payment_method}</td><td>{item.status}</td><td>{item.transaction_reference || '—'}</td></tr>)}</tbody></table></div> : <p className="muted">No payments recorded.</p>}
      <h3>Completed payments</h3>
      {data.completed_payments.length ? <div className="table-wrap"><table><thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Reference</th></tr></thead><tbody>{data.completed_payments.map((item) => <tr key={item.id}><td>{new Date(`${item.payment_date}T00:00:00`).toLocaleDateString()}</td><td>{money(item.amount, currency)}</td><td>{item.payment_method}</td><td>{item.transaction_reference || '—'}</td></tr>)}</tbody></table></div> : <p className="muted">No completed payments yet.</p>}
      <h3>Follow-ups</h3>
      {[['Upcoming follow-ups', data.upcoming_followups], ['Completed follow-ups', data.completed_followups]].map(([title, rows]) => <section key={title}><h4>{title}</h4>{rows.length ? <div className="today-preview">{rows.map((item) => <article key={item.id}><strong>{item.title}</strong><p>{item.type} · {dateTime(item.scheduled_at)}</p>{item.purpose && <p>Purpose: {item.purpose}</p>}{item.description && <p>{item.description}</p>}{item.remarks && <p>Remarks: {item.remarks}</p>}{item.outcome && <p>Outcome: {item.outcome}</p>}</article>)}</div> : <p className="muted">None.</p>}</section>)}
    </>}
  </section>
}
