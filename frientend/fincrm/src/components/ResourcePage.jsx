import { useEffect, useMemo, useRef, useState } from 'react'
import { unwrapList } from '../api'
import RecordForm from './RecordForm'
import { modules as moduleDefinitions, onboardingFields } from '../config/modules'

function rowLabel(row) { return row.full_name || row.contact_name || row.title || row.name || row.application_code || row.customer_code || row.lead_code || row.id }
function cellValue(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export default function ResourcePage({ module, api, user, createSignal = 0, createStaffType = 'employee', readOnlyPortal = false, initialPath }) {
  const [rows, setRows] = useState([])
  const [single, setSingle] = useState(null)
  const [next, setNext] = useState(null)
  const [previous, setPrevious] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [form, setForm] = useState(null)
  const [actionForm, setActionForm] = useState(null)
  const [search, setSearch] = useState('')
  const lastCreateSignal = useRef(0)

  const roleCode=user?.role?.code || ''
  const roleLevel=user?.role?.hierarchy_level || 0
  const canCreateByRole={
    org_admin:['managers','team-leads','departments','teams','employees','customers','leads','applications','documents','categories','tasks','customer-followups','lead-followups','application-followups','payments'],
    super_admin:['managers','team-leads','departments','teams','employees','customers','leads','applications','documents','categories','tasks','customer-followups','lead-followups','application-followups','payments'],
    manager:['employees','teams','customers','leads','applications','tasks'],
    team_lead:['employees','customers','leads','applications','tasks'],
    general_employee:['employees','customers','leads','applications','tasks','customer-followups','lead-followups','application-followups'],
    sales_analyst:['payments','tasks','customer-followups','lead-followups','application-followups'],
    doc_officer:['documents','categories','tasks','customer-followups','lead-followups','application-followups'],
    document_verification_officer:['documents','categories','tasks','customer-followups','lead-followups','application-followups'],
    finance_analyst:['payments','tasks'],
    financial_analyst:['payments','tasks'],
  }
  const canCreate = !readOnlyPortal && !module.readOnly && !module.single && (canCreateByRole[roleCode] || []).includes(module.id)
  const canEditRow=!readOnlyPortal && (roleLevel>=50 || (roleCode==='general_employee' && ['customers','leads','applications','tasks'].includes(module.id)) || (roleCode==='sales_analyst' && module.id==='payments'))
  const canSeeAction = (action) => !readOnlyPortal && roleLevel >= (action.minLevel || 0) && (!action.minRole || user?.role?.code === action.minRole || action.minRoles?.includes(roleCode) || roleLevel >= 70)
  useEffect(() => {
    if (!createSignal || createSignal===lastCreateSignal.current || !canCreate) return
    lastCreateSignal.current=createSignal
    setForm({title:`Create ${module.label.replace(/s$/, '')}`,initial:module.id==='employees'?{staff_type:createStaffType}:undefined})
  },[createSignal,canCreate,module.id,createStaffType])
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
    else if (module.id === 'employees') result = await api.post('/staff/onboard/', payload)
    else result = await api.post(module.endpoint, payload)
    setMessage(form?.row ? 'Record updated.' : module.id === 'employees' ? `Staff onboarded: ${JSON.stringify(result)}` : 'Record created.')
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

  const columns = visibleRows.length ? Object.keys(visibleRows[0]).filter((key) => !['id', 'file'].includes(key)).slice(0, 7) : []
  return <section>
    <h2>{module.label}</h2>
    <p>{module.description || `Manage ${module.label.toLowerCase()} in the active organization.`}</p>
    <button type="button" onClick={() => load()} disabled={loading}>Refresh</button>
    {canCreate && <button type="button" onClick={() => setForm({ title: `Create ${module.label.replace(/s$/, '')}`, initial:module.id==='employees'?{staff_type:'employee'}:undefined })}>{module.id === 'employees' ? 'Onboard staff' : `Create ${module.label.replace(/s$/, '')}`}</button>}
    {module.id === 'documents' && !readOnlyPortal && ((roleLevel >= 70) || ['doc_officer','document_verification_officer'].includes(roleCode)) && <button type="button" onClick={() => setForm({ category: true, title: 'Create document category' })}>Add document category</button>}
    {(module.id === 'applications' || module.id === 'schedules') && ((user?.role?.hierarchy_level || 0)>=70 || ['finance_analyst','financial_analyst'].includes(roleCode)) && <button type="button" onClick={() => setActionForm({ title: 'Generate repayment schedule', endpoint: '/finance/schedules/generate/', fields: module.fieldsGenerate || moduleDefinitions.find((entry)=>entry.id==='schedules').fieldsGenerate })}>Generate repayment schedule</button>}
    {module.id === 'followups-today' && <button type="button" onClick={() => load()}>Load today’s follow-ups</button>}
    {module.id === 'employees' && module.history && <p>Staff records can be updated from the employee list. Use this form to onboard a manager, team lead, or employee.</p>}
    {!module.single && <label>Search this page <input value={search} onChange={(event) => setSearch(event.target.value)} /></label>}
    {loading && <p>Loading…</p>}{error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {module.id === 'hierarchy' && <pre>{JSON.stringify(single, null, 2)}</pre>}
    {module.single && single && <><dl>{Object.entries(single).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{cellValue(value)}</dd></div>)}</dl>{!module.readOnly && <button type="button" onClick={() => setForm({ row: single, title: `Edit ${module.label}` })}>Edit settings</button>}</>}
    {module.id === 'subscription' && single?.has_active_subscription && <button type="button" onClick={() => { if (window.confirm('Cancel the current subscription?')) api.post('/subscriptions/cancel/', {}).then(() => load()).catch((exception) => setError(exception.message)) }}>Cancel subscription</button>}
    {visibleRows.length > 0 && !module.single && <table>
      <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}<th>Actions</th></tr></thead>
      <tbody>{visibleRows.map((row) => <tr key={row.id || rowLabel(row)}>{columns.map((column) => <td key={column}>{cellValue(row[column])}</td>)}<td>
        {module.fields?.length > 0 && !module.readOnly && canEditRow && !(module.id === 'roles' && row.is_system_role) && <button type="button" onClick={() => setForm({ row, title: `Edit ${rowLabel(row)}` })}>Edit</button>}
        {module.actions?.filter((action) => canSeeAction(action) && (!action.onlyStatus || action.onlyStatus.includes(row[action.onlyField || 'status']))).map((action) => <button type="button" key={action.label} onClick={() => {
          if (!action.fields) return runAction(row, action).catch((exception) => setError(exception.message))
          const fields=action.fields.map((field)=>field.name==='status' && action.path==='transition' && module.id==='applications' ? {...field,options:({draft:['submitted','withdrawn'],submitted:['under_review','withdrawn'],under_review:['approved','rejected','withdrawn'],approved:['disbursed','withdrawn'],disbursed:['completed']})[row.status] || []} : field.name==='status' && action.path==='transition' && module.id==='leads' ? {...field,options:({new:['contacted','unqualified'],contacted:['qualified','unqualified']})[row.status] || []} : field)
          setActionForm({ row, action, title: action.label, fields, initial: action.endpoint ? { plan_id: row.id } : {} })
        }}>{action.label}</button>)}
        {row.file_available && module.id === 'documents' && <button type="button" onClick={() => api.download(`/documents/documents/${row.id}/download/`, row.file_name || row.id).catch((exception) => setError(exception.message))}>Download</button>}
        {row.payment_proof_available && module.id === 'payments' && <button type="button" onClick={() => api.download(`/finance/payments/${row.id}/proof/`, `payment-proof-${row.id}`).catch((exception) => setError(exception.message))}>Payment proof</button>}
        {module.id === 'employees' && !readOnlyPortal && <button type="button" onClick={() => api.get(`${module.endpoint}${row.id}/history/`).then((result) => setActionForm({ title: 'Staff assignment history', result })).catch((exception) => setError(exception.message))}>History</button>}
        {module.id === 'leads' && !readOnlyPortal && !row.has_portal_account && <button type="button" onClick={() => setActionForm({row,action:{label:'Create lead portal login',path:'portal-account',method:'POST'},title:'Create lead portal login',fields:[{name:'portal_login',label:'Username',required:true},{name:'portal_password',label:'Initial password',type:'password',required:true}]})}>Create lead login</button>}
        {!module.readOnly && !module.single && (user?.role?.hierarchy_level || 0)>=(module.deleteLevel || 90) && !(module.id === 'roles' && row.is_system_role) && <button type="button" onClick={() => { if (window.confirm(`Delete ${rowLabel(row)}?`)) api.delete(`${module.endpoint}${row.id}/`).then(load).catch((exception) => setError(exception.message)) }}>Delete</button>}
      </td></tr>)}</tbody>
    </table>}
    {!loading && !error && rows.length === 0 && <p>No {module.label.toLowerCase()} found.</p>}
    {(next || previous) && <p>{previous && <button type="button" onClick={() => load(previous)}>Previous</button>} {next && <button type="button" onClick={() => load(next)}>Next</button>}</p>}
    {form && <RecordForm key={`${module.id}-${form.row?.id || 'new'}-${form.category ? 'category' : 'main'}`} fields={form.category ? [{ name: 'name', required: true }, { name: 'description', type: 'textarea' }] : module.id === 'employees' ? (form.row ? module.fields : onboardingFields.filter((field)=>!(roleLevel<70 && field.name==='department_id') && !(roleLevel<50 && field.name==='team_id')).map((field) => field.name==='staff_type' ? {...field,options:roleLevel>=90?['manager','team_lead','employee']:roleLevel>=70?['team_lead','employee']:['employee']} : field.name==='role_ids' && roleLevel<70 ? {...field,allowedCodes:['general_employee']} : field)) : module.id==='leads' && form.row ? module.fields.filter((field)=>!['assigned_to','assigned_doc_officer','assigned_sales_analyst','create_portal_account','portal_login','portal_password'].includes(field.name)) : module.fields} initial={form.row || form.initial || {}} api={api} title={form.title} submitLabel={form.row ? 'Update' : 'Create'} onCancel={() => setForm(null)} onSubmit={saveRecord} />}
    {actionForm?.fields && <RecordForm fields={actionForm.fields} initial={actionForm.initial} api={api} title={actionForm.title} onCancel={() => setActionForm(null)} onSubmit={async (payload) => {
      if (actionForm.endpoint) { await api.post(actionForm.endpoint, payload); setMessage('Repayment schedule generated.'); await load(); return }
      await runAction(actionForm.row, actionForm.action, payload); setActionForm(null)
    }} />}
    {actionForm && !actionForm.fields && <dialog open><h3>{actionForm.title}</h3><pre>{JSON.stringify(actionForm.result, null, 2)}</pre><button type="button" onClick={() => setActionForm(null)}>Close</button></dialog>}
  </section>
}
