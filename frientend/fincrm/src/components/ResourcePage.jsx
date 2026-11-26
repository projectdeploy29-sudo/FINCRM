import { useCallback, useEffect, useRef, useState } from 'react'
import { unwrapList } from '../api'
import RecordForm from './RecordForm'
import WhatsAppComposer from './WhatsAppComposer'
import OrganizationHierarchyView from './OrganizationHierarchyView'
import LoadingSkeleton from './LoadingSkeleton'
import useSidePanelEntrance from './useSidePanelEntrance'
import { onboardingFields } from '../config/modules'

function rowLabel(row) { return row.user_details?.full_name || row.full_name || row.contact_name || row.title || row.name || row.customer_code || row.lead_code || row.id }
function cellValue(value) {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(cellValue).filter(Boolean).join(', ')
  if (typeof value === 'object') return value.full_name || value.name || value.contact_name || value.title || value.code || value.username || ''
  return String(value)
}
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const followupModules = ['customer-followups', 'lead-followups']
const staffColumns = {
  employees: ['staff_name', 'employee_code', 'department_name', 'team_name', 'manager_name', 'staff_role', 'designation', 'employment_status'],
  managers: ['staff_name', 'code', 'managed_department_names', 'designation', 'work_email', 'employment_status'],
  'team-leads': ['staff_name', 'code', 'department_name', 'manager_name', 'team_names', 'designation', 'work_email', 'employment_status'],
}
const staffColumnLabels = { staff_name: 'Name', employee_code: 'Employee code', code: 'Staff code', managed_department_names: 'Departments', department_name: 'Department', team_name: 'Team', manager_name: 'Manager', staff_role: 'Role', team_names: 'Teams', work_email: 'Email', designation: 'Designation', employment_status: 'Status', approved_amount: 'Approved amount', disbursed_amount: 'Loan principal', net_disbursed_amount: 'Net paid out', opening_balance: 'Opening balance', principal_due: 'Principal due', interest_due: 'Interest due', interest_days: 'Interest days', expected_amount: 'Total due', closing_balance: 'Closing balance' }
const resourceColumnLabels = { paid_at: 'Paid at', plan_name: 'Plan', billing_cycle: 'Billing cycle', amount: 'Amount', currency: 'Currency', invoice_reference: 'Reference' }
const recordColumns = {
  billing: ['paid_at', 'plan_name', 'billing_cycle', 'amount', 'currency', 'status', 'invoice_reference'],
  customers: ['customer_code', 'customer_type', 'full_name', 'primary_phone', 'email', 'priority', 'tags', 'assigned_to_name', 'status'],
  leads: ['lead_code', 'contact_name', 'address', 'phone', 'email', 'assigned_to_name', 'status', 'expected_amount'],
  schedules: ['label', 'installment_number', 'due_date', 'interest_days', 'opening_balance', 'principal_due', 'interest_due', 'expected_amount', 'closing_balance', 'status'],
  departments: ['name', 'description', 'manager_details', 'is_active', 'teams_count', 'employees_count'],
  teams: ['name', 'department_name', 'description', 'team_lead_details', 'is_active', 'members_count'],
}
const humanize = (key) => key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const titleCase = (value) => String(value || '').replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
function detailValue(value) {
  if (Array.isArray(value)) return value.map(detailValue).filter(Boolean).join(', ')
  if (value && typeof value === 'object') {
    return Object.entries(value).filter(([key, nested]) => key !== 'id' && nested !== null && nested !== '' && !(typeof nested === 'string' && uuidPattern.test(nested))).map(([key, nested]) => `${humanize(key)}: ${detailValue(nested)}`).filter(Boolean).join(' · ')
  }
  if (typeof value === 'string' && uuidPattern.test(value)) return ''
  return value === null || value === undefined ? '' : String(value)
}
function recordDetailDisplay(record, key, value) {
  const relatedName = record[`${key}_name`] || record[`${key.replace(/_id$/, '')}_name`]
  const relatedDetails = record[`${key}_details`] || record[`${key.replace(/_id$/, '')}_details`]
  if (relatedName) return relatedName
  if (relatedDetails) return relatedDetails.name || relatedDetails.full_name || detailValue(relatedDetails)
  return detailValue(value)
}
function recordDetailValueForModal(record, key) {
  const value = record[key]
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string' && uuidPattern.test(value) || key === 'id' || key.endsWith('_id') || key === 'user_details') return ''
  if (typeof value === 'object') return recordDetailDisplay(record, key, value)
  if (key.endsWith('_at') || key.endsWith('_date') || key === 'created_at' || key === 'updated_at') return formatDateTime(value)
  return recordDetailDisplay(record, key, value)
}
const formatDateTime = (value) => value ? new Date(value).toLocaleString() : ''
const escapeIcs = (value) => String(value || '').replaceAll('\\', '\\\\').replaceAll(';', '\\;').replaceAll(',', '\\,').replaceAll('\n', '\\n')
const toIcsDate = (value) => new Date(value).toISOString().replaceAll('-', '').replaceAll(':', '').replace(/\.\d{3}Z$/, 'Z')

function downloadMeetingInvite(row) {
  const start = new Date(row.scheduled_at)
  const end = new Date(start.getTime() + Number(row.meeting_duration_minutes || 30) * 60000)
  const emails = [row.contact_email, ...(row.invitee_emails || '').split(',')].map((email) => email.trim()).filter(Boolean)
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Auron FIN CRM//Follow-up Calendar//EN', 'CALSCALE:GREGORIAN', 'METHOD:REQUEST',
    'BEGIN:VEVENT', `UID:${row.id}@auronfincrm`, `DTSTAMP:${toIcsDate(new Date())}`, `DTSTART:${toIcsDate(start)}`, `DTEND:${toIcsDate(end)}`,
    `SUMMARY:${escapeIcs(`Meeting with ${row.contact_name || 'contact'}`)}`,
    `DESCRIPTION:${escapeIcs([row.notes, row.meeting_url].filter(Boolean).join('\n'))}`,
    ...(row.meeting_location ? [`LOCATION:${escapeIcs(row.meeting_location)}`] : []),
    ...emails.map((email) => `ATTENDEE;RSVP=TRUE:mailto:${email}`),
    'END:VEVENT', 'END:VCALENDAR',
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob); const link = document.createElement('a')
  link.href = url; link.download = `auron-fin-crm-meeting-${row.id}.ics`; link.click(); URL.revokeObjectURL(url)
}

async function downloadBillingDocument(api, row, kind) {
  const path = kind === 'receipt' ? row.receipt_url : row.invoice_url
  if (!path) return
  const blob = await api.download(path)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `auron-fin-crm-${kind}-${row.id}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function emailMeetingInvite(row) {
  const recipients = [row.contact_email, ...(row.invitee_emails || '').split(',')].map((email) => email.trim()).filter(Boolean).join(',')
  const subject = `Meeting: ${row.contact_name || 'Auron FIN CRM follow-up'}`
  const body = [`When: ${formatDateTime(row.scheduled_at)}`, `Duration: ${row.meeting_duration_minutes || 30} minutes`, row.meeting_location && `Location: ${row.meeting_location}`, row.meeting_url && `Meeting link: ${row.meeting_url}`, row.notes && `Notes: ${row.notes}`, '', 'The calendar invite is attached separately from Auron FIN CRM.'].filter(Boolean).join('\n')
  window.location.href = `mailto:${encodeURIComponent(recipients)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

function withSearch(path, term) {
  const [base, query = ''] = path.split('?')
  const parameters = new URLSearchParams(query)
  if (term.trim()) parameters.set('search', term.trim())
  else parameters.delete('search')
  const serialized = parameters.toString()
  return serialized ? `${base}?${serialized}` : base
}

async function resolveHistoryEntries(api, entries) {
  const rows = unwrapList(entries)
  const [recipients, employees, managers, teamLeads, me] = await Promise.all([
    api.get('/tasks/recipients/').then(unwrapList).catch(() => []),
    api.getAll('/staff/employees/').catch(() => []),
    api.getAll('/staff/managers/').catch(() => []),
    api.getAll('/staff/team-leads/').catch(() => []),
    api.get('/auth/me/').catch(() => null),
  ])
  const people = [me, ...recipients, ...employees, ...managers, ...teamLeads].filter(Boolean)
  const personName = (value) => {
    const id = typeof value === 'object' ? value.id || value.pk : value
    const person = people.find((item) => String(item.id || item.pk) === String(id) ||
      String(item.user?.id || item.user?.pk) === String(id))
    if (person) return person.full_name || person.name ||
      [person.first_name, person.last_name].filter(Boolean).join(' ') ||
      person.user_details?.full_name || person.user_details?.username ||
      person.username || person.user?.username || person.email || ''
    return ''
  }
  return rows.map((entry) => {
    const resolved = { ...entry }
    for (const key of ['changed_by','changed_by_user','created_by','assigned_by_user','assigned_to_user','user']) {
      if (resolved[key] !== undefined) {
        resolved[`${key}_name`] = personName(resolved[key]) || resolved[`${key}_name`] || ''
      }
    }
    if (resolved.customer || resolved.customer_id) {
      resolved.customer_name = resolved.customer_name || resolved.customer_details?.name || ''
    }
    return resolved
  })
}

function SubscriptionSummary({ subscription, organizationName }) {
  const active = Boolean(subscription.has_active_subscription)
  const plan = subscription.plan_details || {}
  const formatDate = (value) => {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString()
  }
  const usageValue = (current, maximum) => `${current ?? 0} / ${maximum ?? 'Negotiated'}`
  const details = active ? [
    ['Organization', subscription.organization_name || organizationName || '—'],
    ['Subscription reference', subscription.Subscriptioncode || '—'],
    ['Billing cycle', titleCase(subscription.billing_cycle || '—')],
    ['Start date', formatDate(subscription.start_date)],
    ['End date', formatDate(subscription.end_date)],
    ['Next billing date', formatDate(subscription.next_billing_date)],
    ['Days remaining', subscription.days_remaining ?? '—'],
    ['Staff usage', usageValue(subscription.usage?.staff_count, subscription.usage?.max_staff_allowed)],
    ['Lead usage', usageValue(subscription.usage?.leads_count, subscription.usage?.max_leads_allowed)],
    ...(subscription.ai_tokens ? [[
      'AI tokens used today',
      `${Number(subscription.ai_tokens.used || 0).toLocaleString()} / ${subscription.ai_tokens.total == null ? 'Unlimited' : Number(subscription.ai_tokens.total).toLocaleString()}`,
    ]] : []),
  ] : [
    ['Organization', subscription.organization_name || organizationName || '—'],
    ['Subscription status', 'Inactive'],
  ]

  return <section className={`subscription-summary-card ${active ? 'is-active' : 'is-inactive'}`}>
    <header className="subscription-summary-header">
      <div className="subscription-summary-mark" aria-hidden="true">{active ? '✓' : '—'}</div>
      <div className="subscription-summary-title">
        <span className="subscription-summary-eyebrow">Subscription details</span>
        <h3>{active ? plan.name || 'Active plan' : 'No active subscription'}</h3>
        <p>{active
          ? `${titleCase(subscription.status || 'active')} subscription${subscription.billing_cycle ? ` · ${subscription.billing_cycle.toLowerCase()} billing` : ''}`
          : subscription.detail || 'This organization does not currently have an active plan.'}</p>
      </div>
      <span className="subscription-summary-status">{active ? titleCase(subscription.status || 'active') : 'Inactive'}</span>
    </header>
    <dl className="subscription-summary-details">
      {details.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
    </dl>
  </section>
}

export default function ResourcePage({ module, api, user, readOnlyPortal = false, initialPath }) {
  const [rows, setRows] = useState([])
  const [single, setSingle] = useState(null)
  const [next, setNext] = useState(null)
  const [previous, setPrevious] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [form, setForm] = useState(null)
  const [actionForm, setActionForm] = useState(null)
  const [detailRecord, setDetailRecord] = useState(null)
  const detailDialogRef = useRef(null)
  const historyDialogRef = useRef(null)
  const [whatsappFollowup, setWhatsappFollowup] = useState(null)
  const [search, setSearch] = useState('')
  const hasDetailRecord = Boolean(detailRecord)
  const detailEntered = useSidePanelEntrance(detailDialogRef, hasDetailRecord)
  const hasActivityPanel = Boolean(actionForm && !actionForm.fields?.length)
  const activityEntered = useSidePanelEntrance(historyDialogRef, hasActivityPanel)

  const roleCode=user?.role?.code || ''
  const roleLevel=user?.role?.hierarchy_level || 0
  const canCreateByRole={
    org_admin:['customers','leads','customer-followups','lead-followups','payments'],
    super_admin:['customers','leads','customer-followups','lead-followups','payments'],
    manager:['employees','teams','customers','leads','tasks','customer-followups','lead-followups','payments'],
    team_lead:['employees','customers','leads','tasks','customer-followups','lead-followups','payments'],
    general_employee:['customers','leads','tasks','customer-followups','lead-followups','payments'],
  }
  const staffTypeByModule = { managers: 'manager', 'team-leads': 'team_lead', employees: 'employee' }
  const staffTypeForPage = staffTypeByModule[module.id]
  const canAddStaff = staffTypeForPage === 'manager' ? roleLevel >= 90 : staffTypeForPage === 'team_lead' ? roleLevel >= 70 : staffTypeForPage === 'employee' ? roleLevel >= 50 : false
  const employeeRole = roleLevel >= 30 && roleLevel < 50
  const canCreateForRole = canCreateByRole[roleCode] || (employeeRole ? canCreateByRole.general_employee : [])
  const canCreate = !readOnlyPortal && !module.single && !module.creationDisabled && (staffTypeForPage ? canAddStaff : !module.readOnly && (roleLevel>=90 || canCreateForRole.includes(module.id)))
  const canEditRow=!readOnlyPortal && (module.editLevel != null ? roleLevel >= module.editLevel : roleLevel>=50 || (employeeRole && ['customers','leads'].includes(module.id)))
  const canSeeAction = (action) => {
    if (readOnlyPortal || roleLevel < (action.minLevel || 0)) return false
    if (action.minRole && roleCode !== action.minRole) return false
    if (action.minRoles?.length && !action.minRoles.includes(roleCode)) return false
    return true
  }
  const load = useCallback(async (path = module.endpoint, searchTerm = search) => {
    setLoading(true); setError(''); setMessage('')
    try {
      const result = await api.get(withSearch(path, searchTerm))
      if (module.single) { setSingle(result); setRows([result]); setNext(null); setPrevious(null) }
      else { setSingle(null); setRows(unwrapList(result)); setNext(result?.next || null); setPrevious(result?.previous || null) }
    } catch (exception) { setError(exception.message); setRows([]); setSingle(null) } finally { setLoading(false) }
  }, [api, module.endpoint, module.single, search])
  useEffect(() => {
    const timer = setTimeout(() => load(initialPath || module.endpoint, search), search.trim() ? 250 : 0)
    return () => clearTimeout(timer)
  }, [initialPath, load, module.endpoint, search])

  const visibleRows = rows

  async function saveRecord(values) {
    let payload = values
    let result
    if (form?.row && module.single) result = await api.patch(module.endpoint, payload)
    else if (form?.row) result = await api.patch(`${module.endpoint}${form.row.id}/`, payload)
    else if (['employees', 'managers', 'team-leads'].includes(module.id)) result = await api.post('/staff/onboard/', payload)
    else result = await api.post(module.endpoint, payload)
    setMessage(form?.row ? 'Record updated.' : ['employees', 'managers', 'team-leads'].includes(module.id) ? `Staff onboarded: ${JSON.stringify(result)}` : 'Record created.')
    await load()
  }

  async function runAction(row, action, payload = {}) {
    const confirmText = action.confirm ? `Confirm ${action.label.toLowerCase()} for ${rowLabel(row)}?` : null
    if (confirmText && !window.confirm(confirmText)) return
    const requestPayload = { ...payload, ...(action.staticBody || {}) }
    const method = action.method || 'POST'
    let path = action.path ? `${module.endpoint}${row.id}/${action.path}/` : `${module.endpoint}${row.id}/`
    if (module.id === 'followups-today') path = `/followups/${row.kind === 'customer' ? 'customers' : 'leads'}/${row.id}/`
    let result
    if (action.endpoint) result = await api.post(action.endpoint, requestPayload)
    else if (action.path && method === 'GET') result = await api.get(path)
    else if (method === 'PATCH' || module.id === 'followups-today') result = await api.patch(path, module.id === 'followups-today' ? { ...requestPayload, status: 'COMPLETED' } : requestPayload)
    else result = await api.post(path, requestPayload)
    if (action.path === 'timeline' || action.path?.endsWith('history')) {
      const resolved = await resolveHistoryEntries(api, result)
      setActionForm({ title: action.label, result: resolved })
      return
    }
    setMessage(result?.detail || `${action.label} completed.`)
    await load()
  }

  function openRowAction(row, action) {
    if (!action.fields?.length) {
      runAction(row, action).catch((exception) => setError(exception.message))
      return
    }
    const fields = action.fields
      .map((field) => field.name === 'status' && action.path === 'transition' && module.id === 'customers'
        ? { ...field, options: ({ new: ['contacted'], contacted: ['under_review'] })[row.status] || [] }
        : field.name === 'status' && action.path === 'transition' && module.id === 'leads'
          ? {
              ...field,
              options: ({ new: ['contacted'], contacted: ['approved'], approved: ['disbursed'], disbursed: ['completed'] })[row.status] || [],
            }
          : field)
    setActionForm({ row, action, title: action.label, fields, initial: action.endpoint ? { plan_id: row.id } : {} })
  }

  async function showRecord(row) {
    setDetailRecord({ title: rowLabel(row), record: null, loading: true, error: '' })
    try {
      const record = await api.get(`${module.endpoint}${row.id}/`)
      let assignmentHistory = []
      let statusHistory = []
      let assignmentHistoryError = ''
      let statusHistoryError = ''
      if (module.id === 'leads') {
        const histories = await Promise.allSettled([
          api.get(`${module.endpoint}${row.id}/history/`),
          api.get(`${module.endpoint}${row.id}/status-history/`),
        ])
        if (histories[0].status === 'fulfilled') assignmentHistory = await resolveHistoryEntries(api, histories[0].value)
        else assignmentHistoryError = histories[0].reason.message || 'Could not load assignment history.'
        if (histories[1].status === 'fulfilled') statusHistory = await resolveHistoryEntries(api, histories[1].value)
        else statusHistoryError = histories[1].reason.message || 'Could not load status history.'
      }
      setDetailRecord({ title: rowLabel(record) || rowLabel(row), record, assignmentHistory, statusHistory, assignmentHistoryError, statusHistoryError, loading: false, error: '' })
    } catch (exception) {
      setDetailRecord({ title: rowLabel(row), record: row, loading: false, error: exception.message })
    }
  }

  const columns = visibleRows.length ? staffColumns[module.id] || recordColumns[module.id] || (followupModules.includes(module.id)
    ? ['title', 'followup_type', 'contact_name', 'contact_record_code', 'contact_phone', 'contact_email', 'assigned_to_name', 'scheduled_at', 'status', 'purpose', 'outcome', 'notes', ...(visibleRows.some((row) => row.followup_type === 'MEETING') ? ['meeting_location', 'meeting_url'] : [])].filter((key) => key in visibleRows[0] || visibleRows.some((row) => key in row))
    : Object.keys(visibleRows[0]).filter((key) => !['id', 'file'].includes(key)).slice(0, 7)) : []
  function renderCell(row, column) {
    if (column === 'staff_name') return row.user_details?.full_name || row.user_details?.username || ''
    if (column === 'staff_role') return (row.roles || (row.role_details ? [row.role_details] : [])).map((role) => role.name).filter(Boolean).join(', ')
    if (column === 'managed_department_names') return (row.managed_departments || []).map((department) => department.name).filter(Boolean).join(', ')
    if (column === 'team_names') return (row.led_teams || []).map((team) => team.name).filter(Boolean).join(', ')
    if (column === 'address') return [row.city, row.state].filter(Boolean).join(', ')
    if (column === 'tags') return (row.tags || []).map((tag) => typeof tag === 'object' ? tag.tag : tag).filter(Boolean).join(', ')
    if (column === 'priority' && row[column]) return String(row[column]).toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase())
    if (column === 'manager_details' || column === 'team_lead_details') return row[column]?.name || ''
    const value = row[column]
    if (['status', 'employment_status', 'verification_status'].includes(column) && value) {
      const normalizedStatus = String(value).toLowerCase().replaceAll('_', '-')
      const positiveStatuses = ['approved', 'disbursed', 'completed', 'verified', 'active', 'paid', 'converted']
      const warningStatuses = ['contacted', 'pending', 'submitted', 'under-review', 'in-progress', 'on-leave', 'partial']
      const negativeStatuses = ['rejected', 'overdue', 'cancelled', 'withdrawn', 'terminated']
      const tone = positiveStatuses.includes(normalizedStatus) ? 'positive' : warningStatuses.includes(normalizedStatus) ? 'warning' : negativeStatuses.includes(normalizedStatus) ? 'negative' : 'neutral'
      return <span className={`resource-status-badge is-${tone}`}>{titleCase(value)}</span>
    }
    if (column.endsWith('_name') && value) return value
    const relatedName = row[`${column}_name`] || row[`${column.replace(/_id$/, '')}_name`]
    if (relatedName) return relatedName
    const details = row[`${column}_details`] || row[`${column.replace(/_id$/, '')}_details`]
    if (details) return details.name || details.full_name || ''
    if (typeof value === 'string' && uuidPattern.test(value)) return ''
    if (column === 'contact_phone' && value) return <a href={`tel:${value}`}>{value}</a>
    if (column === 'contact_email' && value) return <a href={`mailto:${value}`}>{value}</a>
    if (column === 'scheduled_at' || column === 'created_at' || column === 'completed_at' || column === 'paid_at') return formatDateTime(value)
    if (column === 'followup_type' || column === 'status' || column === 'billing_cycle') return String(value || '').toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
    if (column === 'meeting_url' && value) return <a href={value} target="_blank" rel="noreferrer">Join meeting</a>
    return cellValue(value)
  }
  const createTitle = staffTypeForPage
    ? `Add ${staffTypeForPage === 'team_lead' ? 'Team Lead' : staffTypeForPage === 'manager' ? 'Manager' : 'Employee'}`
    : `Add ${module.label.replace(/s$/, '')}`
  return <section className="resource-page">
    <header className="resource-page-header">
      <div className="resource-page-heading">
        <h2>{module.label}</h2>
        <p>{module.description || `Manage ${module.label.toLowerCase()} in the active organization.`}</p>
      </div>
      <div className="resource-page-toolbar">
        <button className="resource-toolbar-button" type="button" onClick={() => load()} disabled={loading}>Refresh</button>
        {canCreate && <button className="resource-toolbar-button resource-create-button" type="button" onClick={() => setForm({ title: createTitle, initial: staffTypeForPage ? { staff_type: staffTypeForPage } : undefined })}>+ {createTitle.replace(/^Add /, 'Create ')}</button>}
        {module.id === 'schedules' && roleLevel >= 30 && <button className="resource-toolbar-button resource-create-button" type="button" onClick={() => setActionForm({ title: 'Generate repayment schedule', endpoint: '/finance/schedules/generate/', fields: module.fieldsGenerate })}>+ Generate repayment schedule</button>}
        {module.id === 'followups-today' && <button className="resource-toolbar-button" type="button" onClick={() => load()}>Load today’s follow-ups</button>}
        {module.single && module.id !== 'hierarchy' && single && !module.readOnly && <button className="resource-toolbar-button" type="button" onClick={() => setForm({ row: single, title: `Edit ${module.label}` })}>Edit settings</button>}
        {module.id === 'subscription' && single?.has_active_subscription && <button className="resource-toolbar-button is-danger" type="button" onClick={() => { if (window.confirm('Cancel the current subscription?')) api.post('/subscriptions/cancel/', {}).then(() => load()).catch((exception) => setError(exception.message)) }}>Cancel subscription</button>}
      </div>
    </header>
    {module.id === 'employees' && module.history && <p>Staff records can be updated from the employee list. Use this form to onboard a manager, team lead, or employee.</p>}
    {!module.single && module.id !== 'hierarchy' && <div className="resource-list-toolbar">
      <label className="resource-search"><span>Search records</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${module.label.toLowerCase()}...`} /></label>
      <span className="resource-loaded-count">{rows.length} {rows.length === 1 ? 'record' : 'records'} loaded</span>
    </div>}
    {loading && <LoadingSkeleton variant="table" label={`Loading ${module.label.toLowerCase()}`} />}{error && <p className="resource-feedback" role="alert">{error}</p>}{message && <p className="resource-feedback" role="status">{message}</p>}
    {module.id === 'hierarchy' && <OrganizationHierarchyView data={single} />}
    {module.id === 'subscription' && single && <SubscriptionSummary subscription={single} organizationName={user?.organization?.name} />}
    {module.single && !['hierarchy', 'subscription'].includes(module.id) && single && <dl className="resource-single-data">{Object.entries(single).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{cellValue(value)}</dd></div>)}</dl>}
    {!module.single && module.id !== 'hierarchy' && <div className="resource-table-card">
    {visibleRows.length > 0 && <div className="resource-table-scroll"><table className="resource-table">
      <thead><tr>{columns.map((column) => <th key={column}>{staffColumnLabels[column] || resourceColumnLabels[column] || humanize(column)}</th>)}<th>{module.id === 'billing' ? 'Documents' : 'Actions'}</th></tr></thead>
      <tbody>{visibleRows.map((row, rowIndex) => {
        const availableActions = module.actions?.filter((action) => canSeeAction(action) && (!action.onlyStatus || action.onlyStatus.includes(row[action.onlyField || 'status']))) || []
        const primaryAction = availableActions.find((action) => action.label.toLowerCase().includes('assign')) || availableActions[0]
        const secondaryActions = availableActions.filter((action) => action !== primaryAction)
        const canEdit = module.fields?.length > 0 && !module.readOnly && !module.editDisabled && canEditRow && !(module.id === 'roles' && row.is_system_role)
        const canDelete = !module.readOnly && !module.deleteDisabled && !module.single &&
          (user?.role?.hierarchy_level || 0) >= (module.deleteLevel || 90) &&
          !(module.id === 'roles' && row.is_system_role) &&
          !(['managers', 'team-leads'].includes(module.id) && row.employment_status === 'terminated')
        const isFollowup = followupModules.includes(module.id)
        const canWhatsApp = !readOnlyPortal && roleLevel >= 30 && (isFollowup ? row.contact_phone : module.id === 'leads' && row.phone)
        const hasFollowupActions = isFollowup && (row.contact_phone || row.contact_email || canWhatsApp || row.followup_type === 'MEETING')
        const hasMoreActions = secondaryActions.length > 0 || hasFollowupActions || canWhatsApp || canDelete
        const menuId = `record-actions-${module.id}-${String(row.id || rowLabel(row)).replace(/[^a-zA-Z0-9_-]/g, '-')}`
        const deleteRow = () => {
          const staffDelete = ['managers', 'team-leads'].includes(module.id)
          const prompt = staffDelete ? `Delete ${rowLabel(row)}? Their account will be disabled and existing records will be kept.` : `Delete ${rowLabel(row)}?`
          if (window.confirm(prompt)) api.delete(`${module.endpoint}${row.id}/`).then(load).catch((exception) => setError(exception.message))
        }
        return <tr key={row.id || rowLabel(row)} style={{ '--row-delay': `${Math.min(rowIndex, 10) * 72}ms` }}>
          {columns.map((column, index) => <td key={column}>{module.id !== 'billing' && index === 0 && row.id ? <button type="button" className="record-link" onClick={() => showRecord(row)}>{renderCell(row, column) || rowLabel(row)}</button> : renderCell(row, column)}</td>)}
          {module.id === 'billing' ? <td><div className="resource-row-actions billing-document-actions">
            <button type="button" className="resource-row-action is-primary" disabled={!row.receipt_url} onClick={() => downloadBillingDocument(api, row, 'receipt').catch((exception) => setError(exception.message))}>Download receipt</button>
            <button type="button" className="resource-row-action" disabled={!row.invoice_url} onClick={() => downloadBillingDocument(api, row, 'invoice').catch((exception) => setError(exception.message))}>GST test draft</button>
          </div></td> : <td><div className="resource-row-actions">
            {canEdit && <button type="button" className="resource-row-action is-edit" aria-label={`Edit ${rowLabel(row)}`} onClick={() => setForm({ row, title: `Edit ${rowLabel(row)}` })}>
              <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.8 4.2 15.8 7.2M4 16l3.6-.8 8.8-8.8a1.8 1.8 0 0 0-2.6-2.6L5 12.6 4 16Z" /></svg><span>Edit</span>
            </button>}
            {primaryAction && <button type="button" className="resource-row-action is-primary" onClick={() => openRowAction(row, primaryAction)}>
              {primaryAction.label.toLowerCase().includes('assign')
                ? <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="7" cy="6" r="3" /><path d="M1.8 16a5.2 5.2 0 0 1 10.4 0M15 7v6M12 10h6" /></svg>
                : <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10h13M11 5l5 5-5 5" /></svg>}
              <span>{primaryAction.label === 'Assign lead' ? 'Assign' : primaryAction.label}</span>
            </button>}
            {hasMoreActions && <>
              <button type="button" className="resource-row-action resource-action-more" popoverTarget={menuId} popoverTargetAction="toggle" aria-label={`More actions for ${rowLabel(row)}`} title="More actions" onClick={(event) => {
                const menu = event.currentTarget.nextElementSibling
                if (!menu) return
                const rect = event.currentTarget.getBoundingClientRect()
                const viewport = event.currentTarget.ownerDocument.defaultView
                const menuHeight = Math.min(menu.scrollHeight || 240, viewport.innerHeight - 24)
                const top = rect.bottom + menuHeight + 8 > viewport.innerHeight ? Math.max(12, rect.top - menuHeight - 6) : rect.bottom + 6
                menu.style.setProperty('--resource-menu-top', `${top}px`)
                menu.style.setProperty('--resource-menu-right', `${viewport.innerWidth - rect.right}px`)
              }}>
                <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="4" r="1.25" /><circle cx="10" cy="10" r="1.25" /><circle cx="10" cy="16" r="1.25" /></svg>
              </button>
              <div id={menuId} popover="auto" role="menu" aria-label={`Actions for ${rowLabel(row)}`} className="resource-action-menu">
                {secondaryActions.map((action) => <button type="button" role="menuitem" className="resource-action-menu-item" key={action.label} popoverTarget={menuId} popoverTargetAction="hide" onClick={() => openRowAction(row, action)}>{action.label}</button>)}
                {isFollowup && row.contact_phone && <a role="menuitem" className="resource-action-menu-item" href={`tel:${row.contact_phone}`}>Call</a>}
                {isFollowup && row.contact_email && <a role="menuitem" className="resource-action-menu-item" href={`mailto:${row.contact_email}`}>Email</a>}
                {canWhatsApp && <button type="button" role="menuitem" className="resource-action-menu-item" popoverTarget={menuId} popoverTargetAction="hide" onClick={() => setWhatsappFollowup({ row, directLead: module.id === 'leads', kind: module.id === 'customer-followups' ? 'customer' : 'lead' })}>WhatsApp</button>}
                {isFollowup && row.followup_type === 'MEETING' && <>
                  <button type="button" role="menuitem" className="resource-action-menu-item" popoverTarget={menuId} popoverTargetAction="hide" onClick={() => downloadMeetingInvite(row)}>Add to calendar</button>
                  <button type="button" role="menuitem" className="resource-action-menu-item" popoverTarget={menuId} popoverTargetAction="hide" onClick={() => emailMeetingInvite(row)}>Prepare invite email</button>
                </>}
                {canDelete && <button type="button" role="menuitem" className="resource-action-menu-item is-danger" popoverTarget={menuId} popoverTargetAction="hide" onClick={deleteRow}>Delete</button>}
              </div>
            </>}
            {!canEdit && !primaryAction && !hasMoreActions && <span className="resource-no-actions">—</span>}
          </div></td>}
        </tr>
      })}</tbody>
    </table></div>}
    {!loading && !error && rows.length === 0 && <div className="resource-empty-state"><span aria-hidden="true">—</span><h3>No {module.label.toLowerCase()} found</h3><p>No records match this view. Try another search term or refresh the list.</p></div>}
    <footer className="resource-table-footer">
      <span>Showing {rows.length} {rows.length === 1 ? 'record' : 'records'} on this page</span>
      {(next || previous) && <nav aria-label="Record pages" className="resource-pagination">
        {previous && <button className="resource-pagination-button" type="button" onClick={() => load(previous)}>Previous</button>}
        {next && <button className="resource-pagination-button is-next" type="button" onClick={() => load(next)}>Next</button>}
      </nav>}
    </footer>
    </div>}
    {form && <RecordForm key={`${module.id}-${form.row?.id || 'new'}`} fields={staffTypeForPage ? (form.row ? module.fields : onboardingFields.filter((field)=>!(roleLevel<70 && field.name==='department_id') && !(roleLevel<50 && field.name==='team_id')).map((field) => field.name==='staff_type' ? {...field,options:[form.initial?.staff_type || staffTypeForPage]} : field)) : module.id==='leads' && roleLevel<50 ? module.fields.filter((field)=>!['assigned_to', 'assignment_reason'].includes(field.name)) : module.fields} initial={form.row || form.initial || {}} api={api} timezone={user?.organization?.timezone || 'UTC'} title={form.title} submitLabel={form.row ? 'Update' : 'Create'} onCancel={() => setForm(null)} onSubmit={saveRecord} />}
    {actionForm?.fields?.length > 0 && <RecordForm fields={actionForm.fields} initial={actionForm.initial} api={api} timezone={user?.organization?.timezone || 'UTC'} title={actionForm.title} onCancel={() => setActionForm(null)} onSubmit={async (payload) => {
      if (actionForm.endpoint) { await api.post(actionForm.endpoint, payload); setMessage('Repayment schedule generated.'); setActionForm(null); await load(); return }
      await runAction(actionForm.row, actionForm.action, payload); setActionForm(null)
    }} />}
    {hasActivityPanel && <dialog ref={historyDialogRef} className={`detail-dialog side-panel-dialog history-side-panel${activityEntered ? ' is-entered' : ''}`} aria-labelledby="activity-panel-title" onCancel={(event) => { event.preventDefault(); setActionForm(null) }}>
      <div className="record-modal-header history-panel-header"><div><p>Activity timeline</p><h3 id="activity-panel-title">{actionForm.title}</h3></div><button type="button" className="modal-close" aria-label="Close history" onClick={() => setActionForm(null)}>×</button></div>
      <div className="history-panel-body">
        {Array.isArray(actionForm.result) && actionForm.result.length > 0 ? actionForm.result.map((entry, index) => {
          const oldStatus = entry.old_status || entry.previous_status || entry.from_status
          const newStatus = entry.new_status || entry.to_status || entry.status
          const changedBy = entry.changed_by_name || entry.changed_by_user_name || entry.created_by_name || entry.assigned_by_user_name || entry.user_name || (entry.changed_by && !uuidPattern.test(String(entry.changed_by)) ? entry.changed_by : '') || 'System'
          const changedAt = entry.changed_at || entry.created_at || entry.updated_at
          return <article className="history-timeline-card" key={entry.id || index}>
            {(oldStatus || newStatus) && <div className="history-status-transition"><div><span>Old status</span><strong>{titleCase(oldStatus || 'Not set')}</strong></div><span className="history-transition-arrow">→</span><div><span>New status</span><strong>{titleCase(newStatus || 'Not set')}</strong></div></div>}
            <div className="history-timeline-meta">
              {changedAt && <div><span>Changed at</span><strong>{formatDateTime(changedAt)}</strong></div>}
              <div><span>Changed by</span><strong>{changedBy}</strong></div>
              {entry.reason && <div><span>Reason</span><strong>{detailValue(entry.reason)}</strong></div>}
            </div>
            {Object.entries(entry).filter(([key, value]) => !['id','old_status','previous_status','from_status','new_status','to_status','status','changed_at','created_at','updated_at','changed_by','changed_by_user','created_by','assigned_by_user','reason'].includes(key) && !key.endsWith('_id') && value !== null && value !== '').length > 0 && <details className="history-extra-details"><summary>Additional details</summary><dl>{Object.entries(entry).filter(([key, value]) => !['id','old_status','previous_status','from_status','new_status','to_status','status','changed_at','created_at','updated_at','changed_by','changed_by_user','created_by','assigned_by_user','reason'].includes(key) && !key.endsWith('_id') && value !== null && value !== '').map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') ? formatDateTime(value) : detailValue(value)}</dd></div>)}</dl></details>}
          </article>
        }) : <div className="history-empty"><span>↻</span><h3>No history recorded</h3><p>Changes will appear here after the record is updated.</p></div>}
      </div>
      <footer className="history-panel-footer"><button type="button" onClick={() => setActionForm(null)}>Close history</button></footer>
    </dialog>}
    {detailRecord && <dialog ref={detailDialogRef} className={`detail-dialog record-detail-modal${detailEntered ? ' is-entered' : ''}`} aria-labelledby="record-detail-title" onCancel={(event) => { event.preventDefault(); setDetailRecord(null) }}>
      <div className="record-modal-header record-detail-header">
        <div><p className="record-detail-eyebrow">{module.label}</p><h3 id="record-detail-title">{detailRecord.title}</h3></div>
        <button type="button" className="modal-close" aria-label="Close record details" onClick={() => setDetailRecord(null)}>×</button>
      </div>
      {detailRecord.loading && <div className="record-detail-loading">Loading record details…</div>}
      {detailRecord.error && <p role="alert">{detailRecord.error}</p>}
      {detailRecord.record && (() => {
        const record = detailRecord.record
        const userDetails = record.user_details && typeof record.user_details === 'object' ? record.user_details : null
        const status = record.status || record.employment_status || record.verification_status || 'Record'
        const initial = String(detailRecord.title || 'R').slice(0, 1).toUpperCase()
        const entries = Object.entries(record).filter(([key]) => key !== 'id' && key !== 'user_details' && recordDetailValueForModal(record, key))
        const identityKeys = ['name','full_name','staff_name','contact_name','customer_code','lead_code','employee_code','code','title','legal_name','designation']
        const contactKeys = ['primary_phone','phone','work_phone','email','work_email','contact_email','city','state','country','address','address_line1','pin_code']
        const organizationKeys = ['department_name','department','team_name','team','managed_department_names','team_names','organization','staff_role','role','roles','manager_name','team_lead_details','assigned_to_name','assigned_employee_name']
        const dateKeys = ['created_at','updated_at','join_date','scheduled_at','completed_at','due_date','payment_date','followup_at','start_date','end_date','next_billing_date']
        const statusKeys = ['status','employment_status','verification_status','priority','active','is_active','customer_type','preferred_channel','followup_type','payment_method','payment_recipient','currency']
        const used = new Set()
        const take = (keys) => entries.filter(([key]) => { const match = keys.includes(key); if (match) used.add(key); return match }).map(([key]) => [key, recordDetailValueForModal(record, key)])
        const identity = take(identityKeys)
        const contact = take(contactKeys)
        const organization = take(organizationKeys)
        const dates = take(dateKeys)
        const statusFields = take(statusKeys)
        const other = entries.filter(([key]) => !used.has(key)).map(([key]) => [key, recordDetailValueForModal(record, key)])
        const section = (title, rows, extraClass = '') => rows.length ? <section className={`record-detail-section ${extraClass}`}><h4>{title}</h4><dl>{rows.map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{value}</dd></div>)}</dl></section> : null
        return <>
          <div className="record-detail-summary">
            <div className="record-detail-avatar">{initial}</div>
            <div><p>{module.label}</p><h3>{detailRecord.title}</h3></div>
            <span className={`record-detail-status status-${String(status).toLowerCase().replaceAll('_','-')}`}>{String(status).replaceAll('_',' ')}</span>
          </div>
          <div className="record-detail-content">
            {userDetails && <section className="record-detail-section user-detail-section"><h4>User account</h4><dl>
              {['username','email','first_name','last_name','full_name'].map((key) => userDetails[key] ? <div key={key}><dt>{humanize(key)}</dt><dd>{key === 'full_name' ? detailValue(userDetails[key]) : userDetails[key]}</dd></div> : null)}
            </dl></section>}
            {section('Identity', identity)}
            {section('Contact information', contact)}
            {section('Organization and assignment', organization)}
            {section('Status and priority', statusFields)}
            {section('Important dates', dates)}
            {section('Additional details', other)}
          </div>
        </>
      })()}
      {module.id === 'leads' && detailRecord.record && <div className="record-detail-history">
        <section><h4>Assignment history</h4>
          {detailRecord.assignmentHistoryError ? <p role="alert">{detailRecord.assignmentHistoryError}</p> : detailRecord.assignmentHistory?.length ? detailRecord.assignmentHistory.map((entry) => <article className="history-entry" key={entry.id}>{detailValue(entry)}</article>) : <p className="muted">No assignment changes recorded.</p>}
        </section>
        <section><h4>Status history</h4>
          {detailRecord.statusHistoryError ? <p role="alert">{detailRecord.statusHistoryError}</p> : detailRecord.statusHistory?.length ? detailRecord.statusHistory.map((entry) => <article className="history-entry" key={entry.id}>{detailValue(entry)}</article>) : <p className="muted">No status changes recorded.</p>}
        </section>
      </div>}
      <footer className="record-detail-footer"><button type="button" onClick={() => setDetailRecord(null)}>Close details</button></footer>
    </dialog>}
    {whatsappFollowup && <WhatsAppComposer api={api} lead={whatsappFollowup.directLead ? whatsappFollowup.row : undefined} followup={whatsappFollowup.directLead ? undefined : whatsappFollowup.row} followupKind={whatsappFollowup.kind} timezone={user?.organization?.timezone || 'UTC'} onClose={() => setWhatsappFollowup(null)} />}
  </section>
}
