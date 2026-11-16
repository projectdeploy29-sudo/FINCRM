import { useEffect, useMemo, useState } from 'react'

const DASHBOARDS = {
  org_admin: [['admin','Organization'],['manager','Managers'],['teamlead','Team leads'],['employee','Employees'],['departments','Departments'],['tasks','Tasks']],
  super_admin: [['admin','Organization'],['manager','Managers'],['teamlead','Team leads'],['employee','Employees'],['departments','Departments'],['tasks','Tasks']],
  manager: [['manager','Manager'],['teamlead','Teams'],['employee','Employees'],['departments','Departments'],['tasks','Tasks']],
  team_lead: [['teamlead','Team'],['employee','Employees'],['tasks','Tasks']],
  general_employee: [['employee','My workspace'],['tasks','My tasks']],
  sales_analyst: [['sales_analyst','Sales revenue'],['tasks','My tasks']],
  finance_analyst: [['employee','Finance pipeline'],['tasks','My tasks']],
  financial_analyst: [['employee','Finance pipeline'],['tasks','My tasks']],
  doc_officer: [['document_officer','Document review'],['tasks','My tasks']],
  document_verification_officer: [['document_officer','Document review'],['tasks','My tasks']],
}
const DRILL = {
  customers:'/customers/', leads:'/leads/', applications:'/applications/',
  applications_approved:'/applications/?status=approved', applications_rejected:'/applications/?status=rejected',
  applications_pending:'/applications/?status=pending', tasks_open:'/tasks/?status=open', tasks_overdue:'/tasks/?overdue=true',
  tasks_completed:'/tasks/?status=COMPLETED', documents_received:'/documents/documents/',
  documents_pending:'/documents/documents/?status=uploaded', documents_verified:'/documents/documents/?status=accepted',
  documents_rejected:'/documents/documents/?status=rejected', payments_recorded:'/finance/payments/',
  verified_revenue:'/finance/payments/?verification_status=VERIFIED', pending_payments:'/finance/payments/?verification_status=PENDING',
  overdue_installments:'/finance/schedules/?overdue=true',
  disbursed_amount:'/applications/?status=disbursed', overdue_expected_amount:'/finance/schedules/?overdue=true',
}

export default function Dashboard({ api, user, onNavigate, onDrillDown }) {
  const roleCode=user?.role?.code || ''
  const options=useMemo(() => DASHBOARDS[roleCode] || [['employee','My workspace'],['tasks','My tasks']], [roleCode])
  const [dashboard, setDashboard] = useState(options[0][0])
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { setDashboard(options[0][0]) }, [options])
  async function load() {
    setBusy(true); setError('')
    try { setMetrics(await api.get(`/dashboards/${dashboard}/`)) } catch (exception) { setError(exception.message); setMetrics(null) } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [dashboard])
  function drill(key) {
    const path=DRILL[key]
    if (path && onDrillDown) onDrillDown(path)
    else if (key==='team_performance') onNavigate('teams')
    else if (key==='department_performance') onNavigate('departments')
    else if (key==='application_status') onNavigate('applications')
    else if (key.includes('task')) onNavigate('tasks')
  }
  return <section>
    <h2>Dashboard</h2>
    <label>View <select value={dashboard} onChange={(event) => setDashboard(event.target.value)}>{options.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <button type="button" onClick={load} disabled={busy}>Refresh dashboard</button>
    {error && <p role="alert">{error}</p>}
    {metrics && <>
      <h3>{options.find(([value]) => value===dashboard)?.[1] || 'Dashboard'} summary</h3>
      <dl>{Object.entries(metrics).filter(([key,value]) => !['role','application_status','team_performance','department_performance'].includes(key) && typeof value!=='object').map(([key,value]) => <div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd><button type="button" onClick={() => drill(key)} disabled={!DRILL[key]}>{String(value)}</button></dd></div>)}</dl>
      {metrics.application_status?.length>0 && <><h3>Application status</h3><ul>{metrics.application_status.map((row) => <li key={row.status}><button type="button" onClick={() => onDrillDown(`/applications/?status=${row.status}`)}>{row.status}: {row.count}</button></li>)}</ul></>}
      {metrics.team_performance?.length>0 && <><h3>Team performance</h3><ul>{metrics.team_performance.map((row) => <li key={row.assigned_to__team__id || row.assigned_to__team__name}>{row.assigned_to__team__name || 'Unassigned'}: {row.completed_tasks} of {row.total_tasks} tasks complete <button type="button" onClick={() => onDrillDown(`/tasks/?team=${row.assigned_to__team__id}`)}>View team tasks</button></li>)}</ul></>}
      {metrics.department_performance?.length>0 && <><h3>Department performance</h3><table><thead><tr><th>Department</th><th>Teams</th><th>Employees</th><th>Applications</th><th>Tasks</th><th>Drill through</th></tr></thead><tbody>{metrics.department_performance.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.teams}</td><td>{row.employees}</td><td>{row.applications}</td><td>{row.tasks}</td><td><button type="button" onClick={() => onDrillDown(`/organizations/teams/?department=${row.id}`)}>Teams</button> <button type="button" onClick={() => onDrillDown(`/applications/?department=${row.id}`)}>Applications</button> <button type="button" onClick={() => onDrillDown(`/tasks/?department=${row.id}`)}>Tasks</button></td></tr>)}</tbody></table></>}
    </>}
  </section>
}
