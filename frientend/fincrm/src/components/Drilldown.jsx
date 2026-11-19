import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'

const money = (value, currency = 'INR') => new Intl.NumberFormat('en-IN', { style: 'currency', currency: currency || 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))
const titleCase = (value) => String(value || '').toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
const rowsOf = (value) => Array.isArray(value) ? value : value?.results || []
const idOf = (value) => typeof value === 'object' && value ? String(value.id ?? value.pk ?? '') : String(value ?? '')
const displayName = (item) => {
  if (!item) return ''
  if (typeof item !== 'object') return String(item)
  const user = item.user || item
  return user.full_name || [user.first_name, user.last_name].filter(Boolean).join(' ') || item.full_name || item.contact_name || item.name || item.title || item.application_code || item.lead_code || item.customer_name || user.username || item.username || ''
}
const isUuid = (value) => typeof value === 'string' && /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(value)
const formatValue = (key, value) => {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string' && /^\d{4}-\d\d-\d\d(?:T.*)?$/.test(value)) {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) return value.includes('T') ? date.toLocaleString() : date.toLocaleDateString()
  }
  if (typeof value === 'string' && isUuid(value)) return ''
  if (typeof value === 'string' && ['status', 'priority', 'role', 'employment_status', 'followup_type'].includes(key)) return titleCase(value)
  return String(value)
}
function localDay(value) {
  if (!value) return ''
  if (/^\d{4}-\d\d-\d\d$/.test(String(value))) return String(value)
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function getLabel(item, kind) {
  if (kind === 'leads') return item.contact_name || item.lead_code || 'Lead'
  if (kind === 'applications') return item.application_code || item.customer_name || `Application ${item.id}`
  if (kind === 'tasks') return item.title || 'Task'
  if (kind === 'payments') return `${money(item.amount)} · ${item.transaction_reference || titleCase(item.verification_status)}`
  if (kind === 'customers') return item.full_name || item.legal_name || 'Customer'
  return `${titleCase(item.kind || item.followup_type || 'Follow-up')} · ${item.contact_name || item.customer_name || item.lead_name || item.application_code || ''}`
}

function getSubtitle(item, kind) {
  if (kind === 'leads') return `${item.lead_code || ''} · ${titleCase(item.status)} · ${money(item.expected_amount, item.currency)}`
  if (kind === 'applications') return `${titleCase(item.status)} · ${money(item.requested_amount || item.approved_amount)}`
  if (kind === 'tasks') return `${titleCase(item.status)} · Due ${item.due_date ? new Date(item.due_date).toLocaleString() : 'not set'}`
  if (kind === 'payments') return `${titleCase(item.verification_status)} · ${item.payment_date || ''}`
  if (kind === 'customers') return `${item.primary_phone || ''} · ${item.email || ''}`
  return `${titleCase(item.status || 'Pending')} · ${item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : ''}`
}

export default function Drilldown({ api, target, onClose }) {
  const [stack, setStack] = useState([target])
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const current = stack[stack.length - 1]

  useEffect(() => {
    let cancelled = false
    setData(null); setError('')
    async function load() {
      try {
        if (current.kind === 'lead-detail') {
          const lead = await api.get(`/leads/${current.id}/`)
          const [statusHistory, assignmentHistory, applications, customers, schedules] = await Promise.all([
            api.get(`/leads/${current.id}/status-history/`).catch(() => []),
            api.get(`/leads/${current.id}/history/`).catch(() => []),
            api.getAll('/applications/').catch(() => []), api.getAll('/customers/').catch(() => []), api.getAll('/finance/schedules/').catch(() => []),
          ])
          const appRows = rowsOf(applications).filter((item) => idOf(item.lead) === String(current.id))
          const customerId = idOf(lead.converted_customer) || idOf(appRows[0]?.customer)
          const customer = rowsOf(customers).find((item) => String(item.id) === customerId) || null
          const scheduleRows = rowsOf(schedules).filter((item) => idOf(item.lead) === String(current.id) || appRows.some((app) => idOf(app.id) === idOf(item.application)))
          const paymentRows = (await api.getAll('/finance/payments/').catch(() => [])).filter((item) => scheduleRows.some((schedule) => idOf(schedule.id) === idOf(item.repayment_schedule)))
          const overdue = scheduleRows.some((item) => item.is_overdue || (item.due_date < new Date().toISOString().slice(0, 10) && ['PENDING', 'PARTIAL'].includes(String(item.status).toUpperCase())))
          const paid = scheduleRows.length > 0 && scheduleRows.every((item) => String(item.status).toUpperCase() === 'PAID')
          const detail = { lead, paymentStatus: overdue ? 'Overdue' : paid ? 'Paid' : 'Not paid', statusHistory: rowsOf(statusHistory), assignmentHistory: rowsOf(assignmentHistory), applications: appRows, customer, schedules: scheduleRows, payments: paymentRows }
          if (!cancelled) setData(detail)
          return
        }
        if (current.kind === 'record-detail') {
          const resourcePaths = { payments: '/finance/payments/', schedules: '/finance/schedules/' }
          const collection = current.resource === 'followups' ? `/followups/${current.followupKind}/` : (resourcePaths[current.resource] || `/${current.resource}/`)
          const path = `${collection}${current.id}/`
          const record = await api.get(path)
          let history = []
          if (current.resource === 'tasks' || current.resource === 'applications') history = await api.get(`${path}history/`).catch(() => [])
          const relationRoutes = {
            customer: '/customers/', related_customer: '/customers/', lead: '/leads/', related_lead: '/leads/',
            application: '/applications/', related_application: '/applications/', department: '/organizations/departments/',
            team: '/organizations/teams/', assigned_to: '/staff/employees/', created_by: '/staff/employees/',
            assigned_by_manager: '/staff/managers/', assigned_by_teamlead: '/staff/team-leads/',
          }
          const references = {}
          await Promise.all(Object.entries(record).map(async ([key, value]) => {
            if (relationRoutes[key] && value && isUuid(idOf(value))) {
              references[key] = await api.get(`${relationRoutes[key]}${idOf(value)}/`).catch(() => null)
            }
          }))
          if ('organization' in record) references.organization = await api.get('/organizations/current/').catch(() => null)
          const userIds = ['assigned_by_user', 'assigned_to_user'].map((key) => idOf(record[key])).filter(isUuid)
          if (userIds.length) {
            const [recipients, me, employees, managers, teamLeads] = await Promise.all([
              api.get('/tasks/recipients/').then(rowsOf).catch(() => []), api.get('/auth/me/').catch(() => null),
              api.getAll('/staff/employees/').catch(() => []), api.getAll('/staff/managers/').catch(() => []), api.getAll('/staff/team-leads/').catch(() => []),
            ])
            const directory = [...recipients, ...rowsOf(employees), ...rowsOf(managers), ...rowsOf(teamLeads), me].filter(Boolean)
            for (const key of ['assigned_by_user', 'assigned_to_user']) {
              const id = idOf(record[key]); const person = directory.find((item) => idOf(item) === id || idOf(item.user) === id || idOf(item.user?.id) === id)
              if (person) references[key] = person
            }
          }
          if (!cancelled) setData({ record, history: rowsOf(history), references })
          return
        }
        let result
        if (current.kind === 'pipeline-leads') result = (await api.get(withDateRange('/pipeline/', current.dateRange))).leads || []
        else if (current.kind === 'leads') result = await api.getAll('/leads/')
        else if (current.kind === 'applications') result = await api.getAll('/applications/')
        else if (current.kind === 'tasks') result = await api.getAll('/tasks/')
        else if (current.kind === 'customers') result = await api.getAll('/customers/')
        else if (current.kind === 'payments') result = await api.getAll('/finance/payments/')
        else if (current.kind === 'followups') {
          const [customers, leads, applications] = await Promise.all(['/followups/customers/', '/followups/leads/', '/followups/applications/'].map((path) => api.getAll(path).catch(() => [])))
          result = [...customers.map((row) => ({ ...row, kind: 'Customer' })), ...leads.map((row) => ({ ...row, kind: 'Lead' })), ...applications.map((row) => ({ ...row, kind: 'Application' }))]
        } else result = []
        result = rowsOf(result)
        const { filter = {} } = current
        result = result.filter((item) => {
          if (current.kind !== 'pipeline-leads' && current.dateRange?.start_date && current.dateRange?.end_date) {
            const dateField = current.kind === 'payments' ? item.payment_date : current.kind === 'tasks' ? item.due_date : current.kind === 'followups' ? item.scheduled_at : current.kind === 'documents' ? item.uploaded_at : item.created_at
            const day = localDay(dateField)
            if (!day || day < current.dateRange.start_date || day > current.dateRange.end_date) return false
          }
          if (filter.status && String(item.status).toLowerCase() !== String(filter.status).toLowerCase()) return false
          if (filter.payment_status && String(item.payment_status).toLowerCase() !== filter.payment_status) return false
          if (filter.active && ['unqualified', 'completed', 'cancelled', 'withdrawn'].includes(String(item.status).toLowerCase())) return false
          if (filter.won && !item.converted_customer) return false
          if (filter.overdue) {
            const due = new Date(item.due_date || item.due_date_display || item.scheduled_at || 0)
            if (!item.due_date && !item.scheduled_at) return false
            if (!(due < new Date()) || ['COMPLETED', 'CANCELLED', 'PAID', 'VERIFIED'].includes(String(item.status || item.verification_status).toUpperCase())) return false
          }
          return true
        })
        if (!cancelled) setData(result)
      } catch (exception) { if (!cancelled) setError(exception.message) }
    }
    load()
    return () => { cancelled = true }
  }, [api, current])

  const back = () => stack.length > 1 ? setStack((items) => items.slice(0, -1)) : onClose()
  const pushLead = (item) => setStack((items) => [...items, { kind: 'lead-detail', id: item.id, title: item.contact_name || 'Lead details', dateRange: current.dateRange }])
  const section = (title, items, label) => <div className="drill-section" key={title}><h4>{title}</h4>{items?.length ? items.map((item) => <div className="drill-history" key={item.id || `${title}-${label(item)}`}><b>{label(item)}</b><span>{item.status ? titleCase(item.status) : ''} {item.due_date || item.payment_date || item.scheduled_at || ''}</span></div>) : <p className="muted">No {title.toLowerCase()} found.</p>}</div>

  return <div className="drill-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="drill-panel" role="dialog" aria-modal="true" aria-label={current.title || 'Details'}>
      <header className="drill-header"><button type="button" onClick={back}>{stack.length > 1 ? '← Back' : 'Close'}</button><div><h2>{current.title || 'Details'}</h2><p>Records in your organization and reporting scope</p></div><button type="button" aria-label="Close details" onClick={onClose}>×</button></header>
      <div className="drill-content">{error && <p role="alert" className="drill-error">{error}</p>}{data === null && !error && <p className="muted">Loading details…</p>}
        {Array.isArray(data) && (data.length ? data.map((item) => <button type="button" className="drill-row" key={item.id} onClick={() => current.kind === 'leads' || current.kind === 'pipeline-leads' ? pushLead(item) : setStack((items) => [...items, { kind: 'record-detail', resource: current.kind === 'pipeline-leads' ? 'leads' : current.kind, id: item.id, followupKind: item.kind === 'Customer' ? 'customers' : item.kind === 'Lead' ? 'leads' : 'applications', title: getLabel(item, current.kind), dateRange: current.dateRange }])}><b>{getLabel(item, current.kind)}</b><span>{getSubtitle(item, current.kind)}</span><small>Open details</small></button>) : <p className="muted">No matching records.</p>)}
        {data?.lead && <><div className="drill-lead-summary"><h3>{data.lead.contact_name}</h3><p>{data.lead.lead_code} · {titleCase(data.lead.status)} · Assigned to {data.lead.assigned_to_name || data.lead.assigned_to?.name || '—'}</p><strong>{money(data.lead.expected_amount, data.lead.currency)}</strong><p className={`status status-${data.paymentStatus.toLowerCase().replace(' ','_')}`}>{data.paymentStatus} payment status</p><p>{data.lead.phone || ''} · {data.lead.email || ''} · {data.lead.city || ''}</p></div>
          {data.customer && section('Customer', [data.customer], (item) => item.full_name || item.legal_name || 'Customer')}
          {section('Applications', data.applications, (item) => `${item.application_code || 'Application'} · ${titleCase(item.status)} · ${money(item.requested_amount || item.approved_amount)}`)}
          {section('Repayment schedule', data.schedules, (item) => { const paid = data.payments.filter((payment) => idOf(payment.repayment_schedule) === idOf(item.id) && String(payment.verification_status).toUpperCase() === 'VERIFIED').reduce((sum, payment) => sum + Number(payment.amount || 0), 0); return `Installment ${item.installment_number || ''} · Expected ${money(item.expected_amount)} · Paid ${money(paid)} · Outstanding ${money(item.outstanding_amount)} · Due ${item.due_date || ''} · ${titleCase(item.status)}` })}
          {section('Payments', data.payments, (item) => `${money(item.amount)} · ${item.payment_date || ''} · ${titleCase(item.verification_status)}`)}
          {section('Status history', data.statusHistory, (item) => `${titleCase(item.previous_status || item.from_status || '')} → ${titleCase(item.new_status || item.to_status || item.status || '')}`)}
          {section('Assignment history', data.assignmentHistory, (item) => `${item.reason || 'Assignment'} · ${item.created_at ? new Date(item.created_at).toLocaleString() : ''}`)}
        </>}
        {data?.record && <><div className="drill-lead-summary"><h3>{getLabel(data.record, current.resource)}</h3><p>{getSubtitle(data.record, current.resource)}</p></div><div className="drill-field-grid">{Object.entries(data.record).filter(([, value]) => value !== null && value !== '').map(([key, value]) => { const reference = data.references?.[key]; const shown = reference ? displayName(reference) : (typeof value === 'object' ? displayName(value) : formatValue(key, value)); return shown ? <div key={key}><span>{titleCase(key)}</span><b>{shown}</b></div> : null })}</div>{section('History', data.history, (item) => `${item.description || item.action || item.status || item.title || 'Updated'} ${item.created_at ? `· ${new Date(item.created_at).toLocaleString()}` : ''}`)}</>}
      </div>
    </section>
  </div>
}
