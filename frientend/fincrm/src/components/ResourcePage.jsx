import { useCallback, useEffect, useState } from 'react'
import { unwrapList } from '../api'
import RecordForm from './RecordForm'
import WhatsAppComposer from './WhatsAppComposer'
import OrganizationHierarchyView from './OrganizationHierarchyView'
import { modules as moduleDefinitions, onboardingFields } from '../config/modules'

function rowLabel(row) { return row.user_details?.full_name || row.full_name || row.contact_name || row.title || row.name || row.application_code || row.customer_code || row.lead_code || row.id }
function cellValue(value) {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map(cellValue).filter(Boolean).join(', ')
  if (typeof value === 'object') return value.full_name || value.name || value.contact_name || value.title || value.code || value.username || ''
  return String(value)
}
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const followupModules = ['customer-followups', 'lead-followups', 'application-followups']
const staffColumns = {
  employees: ['staff_name', 'employee_code', 'department_name', 'team_name', 'manager_name', 'staff_role', 'designation', 'employment_status'],
  managers: ['staff_name', 'code', 'managed_department_names', 'designation', 'work_email', 'employment_status'],
  'team-leads': ['staff_name', 'code', 'department_name', 'manager_name', 'team_names', 'designation', 'work_email', 'employment_status'],
}
const staffColumnLabels = { staff_name: 'Name', employee_code: 'Employee code', code: 'Staff code', managed_department_names: 'Departments', department_name: 'Department', team_name: 'Team', manager_name: 'Manager', staff_role: 'Role', team_names: 'Teams', work_email: 'Email', designation: 'Designation', employment_status: 'Status', approved_amount: 'Approved amount', disbursed_amount: 'Loan principal', net_disbursed_amount: 'Net paid out', opening_balance: 'Opening balance', principal_due: 'Principal due', interest_due: 'Interest due', interest_days: 'Interest days', expected_amount: 'Total due', closing_balance: 'Closing balance' }
const recordColumns = {
  customers: ['customer_code', 'customer_type', 'full_name', 'primary_phone', 'email', 'priority', 'tags', 'assigned_to_name', 'status'],
  leads: ['lead_code', 'contact_name', 'address', 'phone', 'email', 'assigned_to_name', 'status', 'expected_amount'],
  applications: ['application_code', 'customer_name', 'application_type', 'assigned_employee_name', 'requested_amount', 'approved_amount', 'disbursed_amount', 'net_disbursed_amount', 'status', 'created_at'],
  schedules: ['label', 'installment_number', 'due_date', 'interest_days', 'opening_balance', 'principal_due', 'interest_due', 'expected_amount', 'closing_balance', 'status'],
  departments: ['name', 'description', 'manager_details', 'is_active', 'teams_count', 'employees_count'],
  teams: ['name', 'department_name', 'description', 'team_lead_details', 'is_active', 'members_count'],
}
const humanize = (key) => key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
function detailValue(value) {
  if (Array.isArray(value)) return value.map(detailValue).filter(Boolean).join(', ')
  if (value && typeof value === 'object') {
    return Object.entries(value).filter(([key, nested]) => key !== 'id' && nested !== null && nested !== '' && !(typeof nested === 'string' && uuidPattern.test(nested))).map(([key, nested]) => `${humanize(key)}: ${detailValue(nested)}`).filter(Boolean).join(' · ')
  }
  if (typeof value === 'string' && uuidPattern.test(value)) return ''
  return value === null || value === undefined ? '' : String(value)
}
const formatDateTime = (value) => value ? new Date(value).toLocaleString() : ''
const escapeIcs = (value) => String(value || '').replaceAll('\\', '\\\\').replaceAll(';', '\\;').replaceAll(',', '\\,').replaceAll('\n', '\\n')
const toIcsDate = (value) => new Date(value).toISOString().replaceAll('-', '').replaceAll(':', '').replace(/\.\d{3}Z$/, 'Z')

function downloadMeetingInvite(row) {
  const start = new Date(row.scheduled_at)
  const end = new Date(start.getTime() + Number(row.meeting_duration_minutes || 30) * 60000)
  const emails = [row.contact_email, ...(row.invitee_emails || '').split(',')].map((email) => email.trim()).filter(Boolean)
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//FINCRM//Follow-up Calendar//EN', 'CALSCALE:GREGORIAN', 'METHOD:REQUEST',
    'BEGIN:VEVENT', `UID:${row.id}@fincrm`, `DTSTAMP:${toIcsDate(new Date())}`, `DTSTART:${toIcsDate(start)}`, `DTEND:${toIcsDate(end)}`,
    `SUMMARY:${escapeIcs(`Meeting with ${row.contact_name || 'contact'}`)}`,
    `DESCRIPTION:${escapeIcs([row.notes, row.meeting_url].filter(Boolean).join('\n'))}`,
    ...(row.meeting_location ? [`LOCATION:${escapeIcs(row.meeting_location)}`] : []),
    ...emails.map((email) => `ATTENDEE;RSVP=TRUE:mailto:${email}`),
    'END:VEVENT', 'END:VCALENDAR',
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob); const link = document.createElement('a')
  link.href = url; link.download = `fincrm-meeting-${row.id}.ics`; link.click(); URL.revokeObjectURL(url)
}

function emailMeetingInvite(row) {
  const recipients = [row.contact_email, ...(row.invitee_emails || '').split(',')].map((email) => email.trim()).filter(Boolean).join(',')
  const subject = `Meeting: ${row.contact_name || 'FINCRM follow-up'}`
  const body = [`When: ${formatDateTime(row.scheduled_at)}`, `Duration: ${row.meeting_duration_minutes || 30} minutes`, row.meeting_location && `Location: ${row.meeting_location}`, row.meeting_url && `Meeting link: ${row.meeting_url}`, row.notes && `Notes: ${row.notes}`, '', 'The calendar invite is attached separately from FINCRM.'].filter(Boolean).join('\n')
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
  const [whatsappFollowup, setWhatsappFollowup] = useState(null)
  const [search, setSearch] = useState('')

  const roleCode=user?.role?.code || ''
  const roleLevel=user?.role?.hierarchy_level || 0
  const canCreateByRole={
    org_admin:['customers','leads','applications','customer-followups','lead-followups','application-followups','payments'],
    super_admin:['customers','leads','applications','customer-followups','lead-followups','application-followups','payments'],
    manager:['employees','teams','customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','payments'],
    team_lead:['employees','customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','payments'],
    general_employee:['customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','payments'],
  }
  const staffTypeByModule = { managers: 'manager', 'team-leads': 'team_lead', employees: 'employee' }
  const staffTypeForPage = staffTypeByModule[module.id]
  const canAddStaff = staffTypeForPage === 'manager' ? roleLevel >= 90 : staffTypeForPage === 'team_lead' ? roleLevel >= 70 : staffTypeForPage === 'employee' ? roleLevel >= 50 : false
  const employeeRole = roleLevel >= 30 && roleLevel < 50
  const canCreateForRole = canCreateByRole[roleCode] || (employeeRole ? canCreateByRole.general_employee : [])
  const canCreate = !readOnlyPortal && !module.single && !module.creationDisabled && (staffTypeForPage ? canAddStaff : !module.readOnly && (roleLevel>=90 || canCreateForRole.includes(module.id)))
  const canEditRow=!readOnlyPortal && (module.editLevel != null ? roleLevel >= module.editLevel : roleLevel>=50 || (employeeRole && ['customers','leads','applications'].includes(module.id)))
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
    if (module.id === 'followups-today') path = `/followups/${row.kind === 'customer' ? 'customers' : row.kind === 'lead' ? 'leads' : 'applications'}/${row.id}/`
    let result
    if (action.endpoint) result = await api.post(action.endpoint, requestPayload)
    else if (action.path && method === 'GET') result = await api.get(path)
    else if (method === 'PATCH' || module.id === 'followups-today') result = await api.patch(path, module.id === 'followups-today' ? { ...requestPayload, status: 'COMPLETED' } : requestPayload)
    else result = await api.post(path, requestPayload)
    if (action.path === 'timeline' || action.path?.endsWith('history')) {
      setActionForm({ title: action.label, result: unwrapList(result) })
      return
    }
    setMessage(result?.detail || `${action.label} completed.`)
    await load()
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
        if (histories[0].status === 'fulfilled') assignmentHistory = unwrapList(histories[0].value)
        else assignmentHistoryError = histories[0].reason.message || 'Could not load assignment history.'
        if (histories[1].status === 'fulfilled') statusHistory = unwrapList(histories[1].value)
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
    if (column.endsWith('_name') && value) return value
    const relatedName = row[`${column}_name`] || row[`${column.replace(/_id$/, '')}_name`]
    if (relatedName) return relatedName
    const details = row[`${column}_details`] || row[`${column.replace(/_id$/, '')}_details`]
    if (details) return details.name || details.full_name || ''
    if (typeof value === 'string' && uuidPattern.test(value)) return ''
    if (column === 'contact_phone' && value) return <a href={`tel:${value}`}>{value}</a>
    if (column === 'contact_email' && value) return <a href={`mailto:${value}`}>{value}</a>
    if (column === 'scheduled_at' || column === 'created_at' || column === 'completed_at') return formatDateTime(value)
    if (column === 'followup_type' || column === 'status') return String(value || '').toLowerCase().replaceAll('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase())
    if (column === 'meeting_url' && value) return <a href={value} target="_blank" rel="noreferrer">Join meeting</a>
    return cellValue(value)
  }
  return <section>
    <h2>{module.label}</h2>
    <p>{module.description || `Manage ${module.label.toLowerCase()} in the active organization.`}</p>
    <button type="button" onClick={() => load()} disabled={loading}>Refresh</button>
    {canCreate && <button type="button" onClick={() => setForm({ title: staffTypeForPage ? `Add ${staffTypeForPage === 'team_lead' ? 'Team Lead' : staffTypeForPage === 'manager' ? 'Manager' : 'Employee'}` : `Add ${module.label.replace(/s$/, '')}`, initial: staffTypeForPage ? { staff_type: staffTypeForPage } : undefined })}>Add</button>}
    {(module.id === 'applications' || module.id === 'schedules') && roleLevel >= 30 && <button type="button" onClick={() => setActionForm({ title: 'Generate repayment schedule', endpoint: '/finance/schedules/generate/', fields: module.fieldsGenerate || moduleDefinitions.find((entry)=>entry.id==='schedules').fieldsGenerate })}>Generate repayment schedule</button>}
    {module.id === 'followups-today' && <button type="button" onClick={() => load()}>Load today’s follow-ups</button>}
    {module.id === 'employees' && module.history && <p>Staff records can be updated from the employee list. Use this form to onboard a manager, team lead, or employee.</p>}
    {!module.single && <label>Search records <input value={search} onChange={(event) => setSearch(event.target.value)} /></label>}
    {loading && <p>Loading…</p>}{error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {module.id === 'hierarchy' && <OrganizationHierarchyView data={single} />}
    {module.single && module.id !== 'hierarchy' && single && <><dl>{Object.entries(single).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{cellValue(value)}</dd></div>)}</dl>{!module.readOnly && <button type="button" onClick={() => setForm({ row: single, title: `Edit ${module.label}` })}>Edit settings</button>}</>}
    {module.id === 'subscription' && single?.has_active_subscription && <button type="button" onClick={() => { if (window.confirm('Cancel the current subscription?')) api.post('/subscriptions/cancel/', {}).then(() => load()).catch((exception) => setError(exception.message)) }}>Cancel subscription</button>}
    {visibleRows.length > 0 && !module.single && <table>
      <thead><tr>{columns.map((column) => <th key={column}>{staffColumnLabels[column] || humanize(column)}</th>)}<th>Actions</th></tr></thead>
      <tbody>{visibleRows.map((row) => <tr key={row.id || rowLabel(row)}>{columns.map((column, index) => <td key={column}>{index === 0 && row.id ? <button type="button" className="record-link" onClick={() => showRecord(row)}>{renderCell(row, column) || rowLabel(row)}</button> : renderCell(row, column)}</td>)}<td>
        {followupModules.includes(module.id) && row.contact_phone && <a className="action-link" href={`tel:${row.contact_phone}`}>Call</a>}
        {followupModules.includes(module.id) && row.contact_email && <a className="action-link" href={`mailto:${row.contact_email}`}>Email</a>}
        {followupModules.includes(module.id) && row.contact_phone && !readOnlyPortal && roleLevel >= 30 && <button type="button" onClick={() => setWhatsappFollowup({ row, kind: module.id === 'customer-followups' ? 'customer' : module.id === 'lead-followups' ? 'lead' : 'application' })}>WhatsApp</button>}
        {followupModules.includes(module.id) && row.followup_type === 'MEETING' && <><button type="button" onClick={() => downloadMeetingInvite(row)}>Add to calendar</button><button type="button" onClick={() => emailMeetingInvite(row)}>Prepare invite email</button></>}
        {module.fields?.length > 0 && !module.readOnly && !module.editDisabled && canEditRow && !(module.id === 'roles' && row.is_system_role) && <button type="button" onClick={() => setForm({ row, title: `Edit ${rowLabel(row)}` })}>Edit</button>}
        {module.actions?.filter((action) => canSeeAction(action) && (!action.onlyStatus || action.onlyStatus.includes(row[action.onlyField || 'status']))).map((action) => <button type="button" key={action.label} onClick={() => {
          if (!action.fields?.length) return runAction(row, action).catch((exception) => setError(exception.message))
          const fields=action.fields
            .filter((field)=>!field.applicationStatus || field.applicationStatus.includes(row.application_status))
            .map((field)=>field.name==='status' && action.path==='transition' && module.id==='applications' ? {...field,options:({draft:['submitted','withdrawn'],submitted:['under_review','withdrawn'],under_review:['qualified','unqualified','rejected','withdrawn'],qualified:['rejected','withdrawn'],approved:['withdrawn'],disbursed:['completed']})[row.status] || []} : field.name==='status' && action.path==='transition' && module.id==='leads' ? {
              ...field,
              options: ({new:['contacted'],contacted:['approved'],approved:['disbursed'],disbursed:['qualified']})[row.status] || [],
              helpText: row.status==='contacted' && !['qualified','approved'].includes(row.application_status)
                ? `The linked application must be Qualified before this lead can be Approved. Current status: ${row.application_status || 'not linked'}.`
                : '',
            } : field)
          setActionForm({ row, action, title: action.label, fields, initial: action.endpoint ? { plan_id: row.id } : {} })
        }}>{action.label}</button>)}
        {module.id === 'employees' && !readOnlyPortal && <button type="button" onClick={() => api.get(`${module.endpoint}${row.id}/history/`).then((result) => setActionForm({ title: 'Staff assignment history', result })).catch((exception) => setError(exception.message))}>History</button>}
        {module.id === 'leads' && !readOnlyPortal && row.can_create_portal_account && <button type="button" onClick={() => setActionForm({row,action:{label:'Create lead portal login',path:'portal-account',method:'POST'},title:'Create lead portal login',fields:[{name:'portal_login',label:'Username',required:true},{name:'portal_password',label:'Initial password',type:'password',required:true}]})}>Create lead login</button>}
        {!module.readOnly && !module.deleteDisabled && !module.single && (user?.role?.hierarchy_level || 0)>=(module.deleteLevel || 90) && !(module.id === 'roles' && row.is_system_role) && !(['managers', 'team-leads'].includes(module.id) && row.employment_status === 'terminated') && <button type="button" onClick={() => { const staffDelete = ['managers', 'team-leads'].includes(module.id); const prompt = staffDelete ? `Delete ${rowLabel(row)}? Their account will be disabled and existing records will be kept.` : `Delete ${rowLabel(row)}?`; if (window.confirm(prompt)) api.delete(`${module.endpoint}${row.id}/`).then(load).catch((exception) => setError(exception.message)) }}>Delete</button>}
      </td></tr>)}</tbody>
    </table>}
    {!loading && !error && rows.length === 0 && <p>No {module.label.toLowerCase()} found.</p>}
    {(next || previous) && <p>{previous && <button type="button" onClick={() => load(previous)}>Previous</button>} {next && <button type="button" onClick={() => load(next)}>Next</button>}</p>}
    {form && <RecordForm key={`${module.id}-${form.row?.id || 'new'}`} fields={staffTypeForPage ? (form.row ? module.fields : onboardingFields.filter((field)=>!(roleLevel<70 && field.name==='department_id') && !(roleLevel<50 && field.name==='team_id')).map((field) => field.name==='staff_type' ? {...field,options:[form.initial?.staff_type || staffTypeForPage]} : field)) : module.id==='leads' && roleLevel<50 ? module.fields.filter((field)=>!['assigned_to', 'assignment_reason'].includes(field.name)) : module.id==='applications' && form.row ? module.fields.map((field)=>field.name==='customer' ? {...field,optionsEndpoint:'/customers/?page_size=100'} : field) : module.fields} initial={form.row || form.initial || {}} api={api} timezone={user?.organization?.timezone || 'UTC'} title={form.title} submitLabel={form.row ? 'Update' : 'Create'} onCancel={() => setForm(null)} onSubmit={saveRecord} />}
    {actionForm?.fields?.length > 0 && <RecordForm fields={actionForm.fields} initial={actionForm.initial} api={api} timezone={user?.organization?.timezone || 'UTC'} title={actionForm.title} onCancel={() => setActionForm(null)} onSubmit={async (payload) => {
      if (actionForm.endpoint) { await api.post(actionForm.endpoint, payload); setMessage('Repayment schedule generated.'); setActionForm(null); await load(); return }
      await runAction(actionForm.row, actionForm.action, payload); setActionForm(null)
    }} />}
    {actionForm && !actionForm.fields?.length && <dialog open className="detail-dialog"><div className="record-modal-header"><h3>{actionForm.title}</h3><button type="button" className="modal-close" aria-label="Close history" onClick={() => setActionForm(null)}>×</button></div>
      {Array.isArray(actionForm.result) && actionForm.result.length > 0 ? actionForm.result.map((entry, index) => <article className="history-entry" key={entry.id || index}><dl>{Object.entries(entry).filter(([key, value]) => key !== 'id' && !key.endsWith('_id') && value !== null && value !== '').map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') ? formatDateTime(value) : cellValue(value)}</dd></div>)}</dl></article>) : <p>No history recorded yet.</p>}
      <button type="button" onClick={() => setActionForm(null)}>Close</button></dialog>}
    {detailRecord && <dialog open className="detail-dialog"><div className="record-modal-header"><h3>{detailRecord.title}</h3><button type="button" className="modal-close" aria-label="Close record details" onClick={() => setDetailRecord(null)}>×</button></div>
      {detailRecord.loading && <p>Loading record details…</p>}{detailRecord.error && <p role="alert">{detailRecord.error}</p>}
      {detailRecord.record && <dl className="record-detail-grid">{Object.entries(detailRecord.record).filter(([key, value]) => key !== 'id' && value !== null && value !== '' && !key.endsWith('_id') && !(typeof value === 'string' && uuidPattern.test(value))).map(([key, value]) => {
        const relatedName = detailRecord.record[`${key}_name`] || detailRecord.record[`${key.replace(/_id$/, '')}_name`]
        const relatedDetails = detailRecord.record[`${key}_details`] || detailRecord.record[`${key.replace(/_id$/, '')}_details`]
        const display = relatedName || relatedDetails?.name || detailValue(value)
        return display ? <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') || key.endsWith('_date') ? formatDateTime(value) : display}</dd></div> : null
      })}</dl>}
      {module.id === 'leads' && detailRecord.record && <>
        <h4>Assignment history</h4>
        {detailRecord.assignmentHistoryError ? <p role="alert">Could not load assignment history: {detailRecord.assignmentHistoryError}</p> : detailRecord.assignmentHistory?.length ? detailRecord.assignmentHistory.map((entry) => <article className="history-entry" key={entry.id}><dl>{Object.entries(entry).filter(([key, value]) => key !== 'id' && !key.endsWith('_id') && value !== null && value !== '').map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') ? formatDateTime(value) : detailValue(value)}</dd></div>)}</dl></article>) : <p>No assignment changes recorded.</p>}
        <h4>Status history</h4>
        {detailRecord.statusHistoryError ? <p role="alert">Could not load status history: {detailRecord.statusHistoryError}</p> : detailRecord.statusHistory?.length ? detailRecord.statusHistory.map((entry) => <article className="history-entry" key={entry.id}><dl>{Object.entries(entry).filter(([key, value]) => key !== 'id' && !key.endsWith('_id') && value !== null && value !== '').map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') ? formatDateTime(value) : detailValue(value)}</dd></div>)}</dl></article>) : <p>No status changes recorded.</p>}
      </>}
      <button type="button" onClick={() => setDetailRecord(null)}>Close</button></dialog>}
    {whatsappFollowup && <WhatsAppComposer api={api} followup={whatsappFollowup.row} followupKind={whatsappFollowup.kind} timezone={user?.organization?.timezone || 'UTC'} onClose={() => setWhatsappFollowup(null)} />}
  </section>
}
