import { useEffect, useState } from 'react'
import { withDateRange } from '../dateRange'
import useSidePanelEntrance from './useSidePanelEntrance'

const money = (value, currency = 'INR') => new Intl.NumberFormat('en-IN', { style: 'currency', currency: currency || 'INR', maximumFractionDigits: 0 }).format(Number(value || 0))
const titleCase = (value) => String(value || '').toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
const rowsOf = (value) => Array.isArray(value) ? value : value?.results || []
const idOf = (value) => typeof value === 'object' && value ? String(value.id ?? value.pk ?? '') : String(value ?? '')
const displayName = (item) => {
  if (!item) return ''
  if (typeof item !== 'object') return String(item)
  const user = item.user || item
  return user.full_name || [user.first_name, user.last_name].filter(Boolean).join(' ') || item.full_name || item.contact_name || item.name || item.title || item.lead_code || item.customer_name || user.username || item.username || ''
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
  if (kind === 'tasks') return item.title || 'Task'
  if (kind === 'payments') return `${money(item.amount)} · ${item.transaction_reference || titleCase(item.verification_status)}`
  if (kind === 'customers') return item.full_name || item.legal_name || 'Customer'
  return `${titleCase(item.kind || item.followup_type || 'Follow-up')} · ${item.contact_name || item.customer_name || item.lead_name || ''}`
}

function getSubtitle(item, kind) {
  if (kind === 'leads') return `${item.lead_code || ''} · ${titleCase(item.status)} · ${money(item.expected_amount, item.currency)}`
  if (kind === 'tasks') return `${titleCase(item.status)} · Due ${item.due_date ? new Date(item.due_date).toLocaleString() : 'not set'}`
  if (kind === 'payments') return `${titleCase(item.verification_status)} · ${item.payment_date || ''}`
  if (kind === 'customers') return `${item.primary_phone || ''} · ${item.email || ''}`
  return `${titleCase(item.status || 'Pending')} · ${item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : ''}`
}

function detailGroups(record) {
  const entries = Object.entries(record || {}).filter(([key, value]) => {
    if (!value || key === 'id') return false
    if (isUuid(value)) return false
    if (typeof value === 'object') return false
    if (key.endsWith('_id') || key === 'user_details') return false
    return true
  })
  const identityKeys = ['title','name','full_name','contact_name','customer_name','lead_name','customer_code','lead_code','staff_name','staff_role','designation']
  const contactKeys = ['phone','primary_phone','work_phone','contact_phone','email','work_email','contact_email','address','address_line1','city','state','country','pin_code']
  const scheduleKeys = ['scheduled_at','due_date','payment_date','completed_at','created_at','updated_at','join_date','meeting_duration_minutes','meeting_location','meeting_url']
  const statusKeys = ['status','verification_status','priority','followup_type','payment_method','payment_recipient','active','is_active','purpose','outcome','notes','description','remarks','reason','transaction_reference']
  const financeKeys = ['amount','requested_amount','approved_amount','disbursed_amount','net_disbursed_amount','opening_balance','principal_due','interest_due','expected_amount','closing_balance','outstanding_amount','annual_interest_rate','tenure_months','loan_tenure_months','currency']
  const take = (keys) => entries.filter(([key]) => keys.includes(key))
  const used = new Set()
  const groups = []
  for (const [title, keys] of [['Identity', identityKeys],['Contact details', contactKeys],['Schedule and dates', scheduleKeys],['Status and activity', statusKeys],['Financial details', financeKeys]]) {
    const rows = take(keys)
    rows.forEach(([key]) => used.add(key))
    if (rows.length) groups.push([title, rows])
  }
  const other = entries.filter(([key]) => !used.has(key))
  if (other.length) groups.push(['Additional information', other])
  return groups
}

export default function Drilldown({ api, target, onClose }) {
  const [stack, setStack] = useState([target])
  const [result, setResult] = useState(null)
  const entered = useSidePanelEntrance()
  const current = stack[stack.length - 1]
  const data = result?.target === current ? result.data : null
  const error = result?.target === current ? result.error : ''

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        if (current.kind === 'lead-detail') {
          const lead = await api.get(`/leads/${current.id}/`)
          const [statusHistory, assignmentHistory, schedules] = await Promise.all([
            api.get(`/leads/${current.id}/status-history/`).catch(() => []),
            api.get(`/leads/${current.id}/history/`).catch(() => []),
            api.getAll('/finance/schedules/').catch(() => []),
          ])
          const customerId = idOf(lead.customer)
          const customer = customerId ? await api.get(`/customers/${customerId}/`).catch(() => null) : null
          const scheduleRows = rowsOf(schedules).filter((item) => idOf(item.lead) === String(current.id))
          const paymentRows = (await api.getAll('/finance/payments/').catch(() => [])).filter((item) => scheduleRows.some((schedule) => idOf(schedule.id) === idOf(item.repayment_schedule)))
          const overdue = scheduleRows.some((item) => item.is_overdue || (item.due_date < new Date().toISOString().slice(0, 10) && ['PENDING', 'PARTIAL'].includes(String(item.status).toUpperCase())))
          const paid = scheduleRows.length > 0 && scheduleRows.every((item) => String(item.status).toUpperCase() === 'PAID')
          const detail = { lead, paymentStatus: overdue ? 'Overdue' : paid ? 'Paid' : 'Not paid', statusHistory: rowsOf(statusHistory), assignmentHistory: rowsOf(assignmentHistory), customer, schedules: scheduleRows, payments: paymentRows }
          if (!cancelled) setResult({ target: current, data: detail, error: '' })
          return
        }
        if (current.kind === 'record-detail') {
          const resourcePaths = { payments: '/finance/payments/', schedules: '/finance/schedules/' }
          const collection = current.resource === 'followups' ? `/followups/${current.followupKind}/` : (resourcePaths[current.resource] || `/${current.resource}/`)
          const path = `${collection}${current.id}/`
          const record = await api.get(path)
          let history = []
          if (current.resource === 'tasks') history = await api.get(`${path}history/`).catch(() => [])
          const relationRoutes = {
            customer: '/customers/', related_customer: '/customers/', lead: '/leads/', related_lead: '/leads/',
            department: '/organizations/departments/',
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
          if (!cancelled) setResult({ target: current, data: { record, history: rowsOf(history), references }, error: '' })
          return
        }
        let result
        if (current.kind === 'pipeline-leads') result = (await api.get(withDateRange('/pipeline/', current.dateRange))).leads || []
        else if (current.kind === 'leads') result = await api.getAll('/leads/')
        else if (current.kind === 'tasks') result = await api.getAll('/tasks/')
        else if (current.kind === 'customers') result = await api.getAll('/customers/')
        else if (current.kind === 'payments') result = await api.getAll('/finance/payments/')
        else if (current.kind === 'followups') {
          const [customers, leads] = await Promise.all(['/followups/customers/', '/followups/leads/'].map((path) => api.getAll(path).catch(() => [])))
          result = [...customers.map((row) => ({ ...row, kind: 'Customer' })), ...leads.map((row) => ({ ...row, kind: 'Lead' }))]
        } else result = []
        result = rowsOf(result)
        const { filter = {} } = current
        result = result.filter((item) => {
          if (current.kind !== 'pipeline-leads' && current.dateRange?.start_date && current.dateRange?.end_date) {
            const dateField = current.kind === 'payments' ? item.payment_date : current.kind === 'tasks' ? item.due_date : current.kind === 'followups' ? item.scheduled_at : item.created_at
            const day = localDay(dateField)
            if (!day || day < current.dateRange.start_date || day > current.dateRange.end_date) return false
          }
          if (filter.status && String(item.status).toLowerCase() !== String(filter.status).toLowerCase()) return false
          if (filter.payment_status && String(item.payment_status).toLowerCase() !== filter.payment_status) return false
          if (filter.active && ['completed', 'cancelled', 'inactive'].includes(String(item.status).toLowerCase())) return false
          if (filter.won && String(item.status).toLowerCase() !== 'completed') return false
          if (filter.overdue) {
            const due = new Date(item.due_date || item.due_date_display || item.scheduled_at || 0)
            if (!item.due_date && !item.scheduled_at) return false
            if (!(due < new Date()) || ['COMPLETED', 'CANCELLED', 'PAID', 'VERIFIED'].includes(String(item.status || item.verification_status).toUpperCase())) return false
          }
          return true
        })
        if (!cancelled) setResult({ target: current, data: result, error: '' })
      } catch (exception) { if (!cancelled) setResult({ target: current, data: null, error: exception.message }) }
    }
    load()
    return () => { cancelled = true }
  }, [api, current])

  const back = () => stack.length > 1 ? setStack((items) => items.slice(0, -1)) : onClose()
  const pushLead = (item) => setStack((items) => [...items, { kind: 'lead-detail', id: item.id, title: item.contact_name || 'Lead details', dateRange: current.dateRange }])
  const section = (title, items, label) => <div className="drill-section" key={title}><h4>{title}</h4>{items?.length ? items.map((item) => <div className="drill-history" key={item.id || `${title}-${label(item)}`}><b>{label(item)}</b><span>{item.status ? titleCase(item.status) : ''} {item.due_date || item.payment_date || item.scheduled_at || ''}</span></div>) : <p className="muted">No {title.toLowerCase()} found.</p>}</div>

  return <div className={`drill-backdrop${entered ? ' is-entered' : ''}`} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="drill-panel" role="dialog" aria-modal="true" aria-label={current.title || 'Details'}>
      <header className="drill-header">
        <button type="button" className="drill-back-button" onClick={back}>{stack.length > 1 ? '← Back' : 'Close'}</button>
        <div><p className="drill-eyebrow">Record workspace</p><h2>{current.title || 'Details'}</h2><p>{Array.isArray(data) ? `${data.length} matching ${data.length === 1 ? 'record' : 'records'} · ` : ''}Organization and reporting scope</p></div>
        <button type="button" className="drill-close-button" aria-label="Close details" onClick={onClose}>×</button>
      </header>
      <div className="drill-content">{error && <p role="alert" className="drill-error">{error}</p>}{data === null && !error && <div className="drill-loading"><span /><p>Loading details…</p></div>}
        {Array.isArray(data) && (data.length ? <div className="drill-record-list">{data.map((item) => {
          const status = item.status || item.verification_status || item.payment_status
          const title = getLabel(item, current.kind)
          const subtitle = getSubtitle(item, current.kind)
          const kind = current.kind === 'followups'
            ? String(item.kind || '').toLowerCase()
            : String(current.kind || '').toLowerCase()
          const rowIcon = kind.includes('customer') ? 'C'
            : kind.includes('lead') ? 'L'
            : kind.includes('task') ? '✓'
            : kind.includes('payment') ? '₹'
            : kind.includes('follow') ? '↗'
            : String(title).slice(0, 1).toUpperCase()
          return <button type="button" className="drill-row" key={`${current.kind}-${item.id}`} onClick={() => current.kind === 'leads' || current.kind === 'pipeline-leads' ? pushLead(item) : setStack((items) => [...items, { kind: 'record-detail', resource: current.kind === 'pipeline-leads' ? 'leads' : current.kind, id: item.id, followupKind: item.kind === 'Customer' ? 'customers' : 'leads', title, dateRange: current.dateRange }])}>
            <span className={`drill-row-marker drill-row-marker-${kind}`} aria-hidden="true">{rowIcon}</span>
            <span className="drill-row-copy"><b>{title}</b><small>{subtitle}</small></span>
            {status && <span className={`drill-status status-${String(status).toLowerCase().replaceAll('_','-')}`}>{titleCase(status)}</span>}
            <span className="drill-open-action">Open details <b>→</b></span>
          </button>
        })}</div> : <div className="drill-empty"><span>0</span><h3>No matching records</h3><p>Try changing the selected date range or filters.</p></div>)}
        {data?.lead && <><div className="drill-lead-summary"><h3>{data.lead.contact_name}</h3><p>{data.lead.lead_code} · {titleCase(data.lead.status)} · Assigned to {data.lead.assigned_to_name || data.lead.assigned_to?.name || '—'}</p><strong>{money(data.lead.expected_amount, data.lead.currency)}</strong><p className={`status status-${data.paymentStatus.toLowerCase().replace(' ','_')}`}>{data.paymentStatus} payment status</p><p>{data.lead.phone || ''} · {data.lead.email || ''} · {data.lead.city || ''}</p></div>
          {data.customer && section('Customer', [data.customer], (item) => item.full_name || item.legal_name || 'Customer')}
          {section('Repayment schedule', data.schedules, (item) => { const paid = data.payments.filter((payment) => idOf(payment.repayment_schedule) === idOf(item.id) && String(payment.verification_status).toUpperCase() === 'VERIFIED').reduce((sum, payment) => sum + Number(payment.amount || 0), 0); return `Installment ${item.installment_number || ''} · Principal ${money(item.principal_due)} · Interest ${money(item.interest_due)} · Expected ${money(item.expected_amount)} · Paid ${money(paid)} · Outstanding ${money(item.outstanding_amount)} · Due ${item.due_date || ''} · ${titleCase(item.status)}` })}
          {section('Payments', data.payments, (item) => `${money(item.amount)} · ${item.payment_date || ''} · ${titleCase(item.verification_status)}`)}
          {section('Status history', data.statusHistory, (item) => `${titleCase(item.previous_status || item.from_status || '')} → ${titleCase(item.new_status || item.to_status || item.status || '')}`)}
          {section('Assignment history', data.assignmentHistory, (item) => `${item.reason || 'Assignment'} · ${item.created_at ? new Date(item.created_at).toLocaleString() : ''}`)}
        </>}
        {data?.record && <div className="drill-record-detail">
          <div className="drill-record-hero">
            <span className="drill-record-avatar">{String(getLabel(data.record, current.resource)).slice(0, 1).toUpperCase()}</span>
            <div><p>{titleCase(current.resource)}</p><h3>{getLabel(data.record, current.resource)}</h3><small>{getSubtitle(data.record, current.resource)}</small></div>
            {(data.record.status || data.record.verification_status) && <span className={`record-detail-status status-${String(data.record.status || data.record.verification_status).toLowerCase().replaceAll('_','-')}`}>{titleCase(data.record.status || data.record.verification_status)}</span>}
          </div>
          <div className="drill-detail-groups">
            {detailGroups(data.record).map(([title, rows]) => <section className="drill-detail-section" key={title}>
              <h4>{title}</h4>
              <dl>{rows.map(([key, value]) => {
                const reference = data.references?.[key]
                const shown = reference ? displayName(reference) : formatValue(key, value)
                return shown ? <div key={key}><dt>{titleCase(key)}</dt><dd>{shown}</dd></div> : null
              })}</dl>
            </section>)}
          </div>
          {data.history?.length > 0 && <section className="drill-detail-section drill-detail-history">
            <h4>History</h4>
            {data.history.map((item, index) => <article key={item.id || index}><div><strong>{item.description || item.action || item.status || item.title || 'Updated'}</strong><span>{item.created_at ? new Date(item.created_at).toLocaleString() : ''}</span></div></article>)}
          </section>}
        </div>}
      </div>
    </section>
  </div>
}
