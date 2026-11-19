import { useEffect, useMemo, useState } from 'react'
import { unwrapList } from '../api'
import RecordForm from './RecordForm'
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
const staffColumnLabels = { staff_name: 'Name', employee_code: 'Employee code', code: 'Staff code', managed_department_names: 'Departments', department_name: 'Department', team_name: 'Team', manager_name: 'Manager', staff_role: 'Role', team_names: 'Teams', work_email: 'Email', designation: 'Designation', employment_status: 'Status' }
const recordColumns = {
  customers: ['customer_code', 'customer_type', 'full_name', 'primary_phone', 'email', 'priority', 'tags', 'assigned_to_name', 'status'],
  leads: ['lead_code', 'contact_name', 'address', 'phone', 'email', 'assigned_to_name', 'status', 'expected_amount'],
  applications: ['application_code', 'customer_name', 'application_type', 'assigned_employee_name', 'requested_amount', 'follow_up_at', 'status', 'created_at'],
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
  const [search, setSearch] = useState('')

  const roleCode=user?.role?.code || ''
  const roleLevel=user?.role?.hierarchy_level || 0
  const canCreateByRole={
    org_admin:['customers','leads','applications','customer-followups','lead-followups','application-followups','application-checklist','documents','payments'],
    super_admin:['customers','leads','applications','customer-followups','lead-followups','application-followups','application-checklist','documents','payments'],
    manager:['employees','teams','customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','interactions','application-checklist','documents','payments'],
    team_lead:['employees','customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','interactions','application-checklist','documents','payments'],
    general_employee:['customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','interactions','application-checklist','documents','payments'],
  }
  const staffTypeByModule = { managers: 'manager', 'team-leads': 'team_lead', employees: 'employee' }
  const staffTypeForPage = staffTypeByModule[module.id]
  const canAddStaff = staffTypeForPage === 'manager' ? roleLevel >= 90 : staffTypeForPage === 'team_lead' ? roleLevel >= 70 : staffTypeForPage === 'employee' ? roleLevel >= 50 : false
  const canCreate = !readOnlyPortal && !module.single && !module.creationDisabled && (staffTypeForPage ? canAddStaff : !module.readOnly && (roleLevel>=90 || (canCreateByRole[roleCode] || []).includes(module.id)))
  const canEditRow=!readOnlyPortal && (roleLevel>=50 || (roleCode==='general_employee' && ['customers','leads','applications'].includes(module.id)))
  const canSeeAction = (action) => {
    if (readOnlyPortal || roleLevel < (action.minLevel || 0)) return false
    if (action.minRole && roleCode !== action.minRole) return false
    if (action.minRoles?.length && !action.minRoles.includes(roleCode)) return false
    return true
  }
  async function load(path = module.endpoint) {
    setLoading(true); setError(''); setMessage('')
    try {
      const result = await api.get(path)
      if (module.single) { setSingle(result); setRows([result]); setNext(null); setPrevious(null) }
      else { setSingle(null); setRows(unwrapList(result)); setNext(result?.next || null); setPrevious(result?.previous || null) }
    } catch (exception) { setError(exception.message); setRows([]); setSingle(null) } finally { setLoading(false) }
  }
  useEffect(() => { load(initialPath || module.endpoint) }, [module.endpoint, initialPath])

  const visibleRows = useMemo(() => {
    if (!search.trim()) return rows
    const term = search.trim().toLowerCase()
    return rows.filter((row) => JSON.stringify(row).toLowerCase().includes(term))
  }, [rows, search])

  async function saveRecord(values) {
    let payload = values
    if (module.fields?.some((field) => field.type === 'file')) {
      const multipart = new FormData()
      Object.entries(values).forEach(([key, value]) => multipart.append(key, value))
      payload = multipart
    }
    let result
    if (form?.category) result = await api.post('/documents/document-categories/', payload)
    else if (form?.row && module.single) result = await api.patch(module.endpoint, payload)
    else if (form?.row) result = await api.patch(`${module.endpoint}${form.row.id}/`, payload)
    else if (['employees', 'managers', 'team-leads'].includes(module.id)) result = await api.post('/staff/onboard/', payload)
    else result = await api.post(module.endpoint, payload)
    setMessage(form?.row ? 'Record updated.' : ['employees', 'managers', 'team-leads'].includes(module.id) ? `Staff onboarded: ${JSON.stringify(result)}` : 'Record created.')
    await load()
  }

  async function runAction(row, action, payload = action.staticBody || {}) {
    const confirmText = action.confirm ? `Confirm ${action.label.toLowerCase()} for ${rowLabel(row)}?` : null
    if (confirmText && !window.confirm(confirmText)) return
    const method = action.method || 'POST'
    let path = action.path ? `${module.endpoint}${row.id}/${action.path}/` : `${module.endpoint}${row.id}/`
    if (module.id === 'followups-today') path = `/followups/${row.kind === 'customer' ? 'customers' : row.kind === 'lead' ? 'leads' : 'applications'}/${row.id}/`
    let result
    if (action.download) { await api.download(path, `${row.file_name || row.id}`); setMessage('Download started.'); return }
    else if (action.endpoint) result = await api.post(action.endpoint, payload)
    else if (action.path && method === 'GET') result = await api.get(path)
    else if (method === 'PATCH' || module.id === 'followups-today') result = await api.patch(path, module.id === 'followups-today' ? { status: 'COMPLETED' } : payload)
    else result = await api.post(path, payload)
    if (action.path === 'timeline' || action.path?.endsWith('history')) {
      setActionForm({ title: action.label, result })
      return
    }
    setMessage(result?.detail || `${action.label} completed.`)
    await load()
  }

  async function showRecord(row) {
    setDetailRecord({ title: rowLabel(row), record: null, loading: true, error: '' })
    try {
      const record = await api.get(`${module.endpoint}${row.id}/`)
      const histories = module.id === 'leads'
        ? await Promise.all([
            api.get(`${module.endpoint}${row.id}/history/`).catch(() => []),
            api.get(`${module.endpoint}${row.id}/status-history/`).catch(() => []),
          ])
        : [[], []]
      setDetailRecord({ title: rowLabel(record) || rowLabel(row), record, assignmentHistory: histories[0], statusHistory: histories[1], loading: false, error: '' })
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
    {module.id === 'documents' && !readOnlyPortal && roleLevel >= 70 && <button type="button" onClick={() => setForm({ category: true, title: 'Create document category' })}>Add document category</button>}
    {(module.id === 'applications' || module.id === 'schedules') && roleLevel >= 30 && <button type="button" onClick={() => setActionForm({ title: 'Generate repayment schedule', endpoint: '/finance/schedules/generate/', fields: module.fieldsGenerate || moduleDefinitions.find((entry)=>entry.id==='schedules').fieldsGenerate })}>Generate repayment schedule</button>}
    {module.id === 'followups-today' && <button type="button" onClick={() => load()}>Load today’s follow-ups</button>}
    {module.id === 'employees' && module.history && <p>Staff records can be updated from the employee list. Use this form to onboard a manager, team lead, or employee.</p>}
    {!module.single && <label>Search this page <input value={search} onChange={(event) => setSearch(event.target.value)} /></label>}
    {loading && <p>Loading…</p>}{error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {module.id === 'hierarchy' && <pre>{JSON.stringify(single, null, 2)}</pre>}
    {module.single && single && <><dl>{Object.entries(single).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{cellValue(value)}</dd></div>)}</dl>{!module.readOnly && <button type="button" onClick={() => setForm({ row: single, title: `Edit ${module.label}` })}>Edit settings</button>}</>}
    {module.id === 'subscription' && single?.has_active_subscription && <button type="button" onClick={() => { if (window.confirm('Cancel the current subscription?')) api.post('/subscriptions/cancel/', {}).then(() => load()).catch((exception) => setError(exception.message)) }}>Cancel subscription</button>}
    {visibleRows.length > 0 && !module.single && <table>
      <thead><tr>{columns.map((column) => <th key={column}>{staffColumnLabels[column] || humanize(column)}</th>)}<th>Actions</th></tr></thead>
      <tbody>{visibleRows.map((row) => <tr key={row.id || rowLabel(row)}>{columns.map((column, index) => <td key={column}>{index === 0 && row.id ? <button type="button" className="record-link" onClick={() => showRecord(row)}>{renderCell(row, column) || rowLabel(row)}</button> : renderCell(row, column)}</td>)}<td>
        {followupModules.includes(module.id) && row.contact_phone && <a className="action-link" href={`tel:${row.contact_phone}`}>Call</a>}
        {followupModules.includes(module.id) && row.contact_email && <a className="action-link" href={`mailto:${row.contact_email}`}>Email</a>}
        {followupModules.includes(module.id) && row.followup_type === 'MEETING' && <><button type="button" onClick={() => downloadMeetingInvite(row)}>Add to calendar</button><button type="button" onClick={() => emailMeetingInvite(row)}>Prepare invite email</button></>}
        {module.fields?.length > 0 && !module.readOnly && canEditRow && !(module.id === 'roles' && row.is_system_role) && <button type="button" onClick={() => setForm({ row, title: `Edit ${rowLabel(row)}` })}>Edit</button>}
        {module.actions?.filter((action) => canSeeAction(action) && (!action.onlyStatus || action.onlyStatus.includes(row[action.onlyField || 'status']))).map((action) => <button type="button" key={action.label} onClick={() => {
          if (!action.fields) return runAction(row, action).catch((exception) => setError(exception.message))
          const fields=action.fields.map((field)=>field.name==='status' && action.path==='transition' && module.id==='applications' ? {...field,options:({draft:['submitted','withdrawn'],submitted:['under_review','withdrawn'],under_review:['qualified','unqualified','rejected','withdrawn'],qualified:['approved','rejected','withdrawn'],approved:['disbursed','withdrawn'],disbursed:['completed']})[row.status] || []} : field.name==='status' && action.path==='transition' && module.id==='leads' ? {...field,options:({new:['contacted'],contacted:['qualified']})[row.status] || []} : field)
          setActionForm({ row, action, title: action.label, fields, initial: action.endpoint ? { plan_id: row.id } : {} })
        }}>{action.label}</button>)}
        {row.file_available && module.id === 'documents' && <button type="button" onClick={() => api.download(`/documents/documents/${row.id}/download/`, row.file_name || row.id).catch((exception) => setError(exception.message))}>Download</button>}
        {row.payment_proof_available && module.id === 'payments' && <button type="button" onClick={() => api.download(`/finance/payments/${row.id}/proof/`, `payment-proof-${row.id}`).catch((exception) => setError(exception.message))}>Payment proof</button>}
        {module.id === 'employees' && !readOnlyPortal && <button type="button" onClick={() => api.get(`${module.endpoint}${row.id}/history/`).then((result) => setActionForm({ title: 'Staff assignment history', result })).catch((exception) => setError(exception.message))}>History</button>}
        {module.id === 'leads' && !readOnlyPortal && row.can_create_portal_account && <button type="button" onClick={() => setActionForm({row,action:{label:'Create lead portal login',path:'portal-account',method:'POST'},title:'Create lead portal login',fields:[{name:'portal_login',label:'Username',required:true},{name:'portal_password',label:'Initial password',type:'password',required:true}]})}>Create lead login</button>}
        {!module.readOnly && !module.single && (user?.role?.hierarchy_level || 0)>=(module.deleteLevel || 90) && !(module.id === 'roles' && row.is_system_role) && <button type="button" onClick={() => { if (window.confirm(`Delete ${rowLabel(row)}?`)) api.delete(`${module.endpoint}${row.id}/`).then(load).catch((exception) => setError(exception.message)) }}>Delete</button>}
      </td></tr>)}</tbody>
    </table>}
    {!loading && !error && rows.length === 0 && <p>No {module.label.toLowerCase()} found.</p>}
    {(next || previous) && <p>{previous && <button type="button" onClick={() => load(previous)}>Previous</button>} {next && <button type="button" onClick={() => load(next)}>Next</button>}</p>}
    {form && <RecordForm key={`${module.id}-${form.row?.id || 'new'}-${form.category ? 'category' : 'main'}`} fields={form.category ? [{ name: 'name', required: true }, { name: 'description', type: 'textarea' }] : staffTypeForPage ? (module.id === 'employees' && form.row ? module.fields : onboardingFields.filter((field)=>!(roleLevel<70 && field.name==='department_id') && !(roleLevel<50 && field.name==='team_id')).map((field) => field.name==='staff_type' ? {...field,options:[form.initial?.staff_type || staffTypeForPage]} : field.name==='role_ids' && roleLevel<70 ? {...field,allowedCodes:['general_employee']} : field)) : module.id==='leads' ? module.fields.filter((field)=>!['assigned_doc_officer','assigned_sales_analyst', ...(form.row ? ['assigned_to'] : [])].includes(field.name)) : module.fields} initial={form.row || form.initial || {}} api={api} title={form.title} submitLabel={form.row ? 'Update' : 'Create'} onCancel={() => setForm(null)} onSubmit={saveRecord} />}
    {actionForm?.fields && <RecordForm fields={actionForm.fields} initial={actionForm.initial} api={api} title={actionForm.title} onCancel={() => setActionForm(null)} onSubmit={async (payload) => {
      if (actionForm.endpoint) { await api.post(actionForm.endpoint, payload); setMessage('Repayment schedule generated.'); setActionForm(null); await load(); return }
      await runAction(actionForm.row, actionForm.action, payload); setActionForm(null)
    }} />}
    {actionForm && !actionForm.fields && <dialog open className="detail-dialog"><div className="record-modal-header"><h3>{actionForm.title}</h3><button type="button" className="modal-close" aria-label="Close history" onClick={() => setActionForm(null)}>×</button></div>
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
        {detailRecord.assignmentHistory?.length ? detailRecord.assignmentHistory.map((entry) => <article className="history-entry" key={entry.id}><dl>{Object.entries(entry).filter(([key, value]) => key !== 'id' && !key.endsWith('_id') && value !== null && value !== '').map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') ? formatDateTime(value) : detailValue(value)}</dd></div>)}</dl></article>) : <p>No assignment changes recorded.</p>}
        <h4>Status history</h4>
        {detailRecord.statusHistory?.length ? detailRecord.statusHistory.map((entry) => <article className="history-entry" key={entry.id}><dl>{Object.entries(entry).filter(([key, value]) => key !== 'id' && !key.endsWith('_id') && value !== null && value !== '').map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{key.endsWith('_at') ? formatDateTime(value) : detailValue(value)}</dd></div>)}</dl></article>) : <p>No status changes recorded.</p>}
      </>}
      <button type="button" onClick={() => setDetailRecord(null)}>Close</button></dialog>}
  </section>
}
