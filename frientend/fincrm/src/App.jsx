import { useEffect, useMemo, useState } from 'react'
import { createApi } from './api'
import { modules as allModules } from './config/modules'
import Login from './components/Login'
import AppShell from './components/AppShell'
import Dashboard from './components/Dashboard'
import ResourcePage from './components/ResourcePage'
import TodayPage from './components/TodayPage'

function parseJwt(token) {
  try { return JSON.parse(atob(token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/'))) } catch { return {} }
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('fincrm_access') || '')
  const [profile, setProfile] = useState(null)
  const [activeRole, setActiveRole] = useState(localStorage.getItem('fincrm_active_role') || '')
  const [activeModule, setActiveModule] = useState('dashboard')
  const [createSignal, setCreateSignal] = useState(0)
  const [createStaffType, setCreateStaffType] = useState('employee')
  const [modulePaths, setModulePaths] = useState({})
  const roleLevel = profile?.role?.hierarchy_level ?? parseJwt(token).hierarchy_level ?? 0
  const api = useMemo(() => createApi(token, () => {
    setToken(''); setProfile(null); localStorage.removeItem('fincrm_access'); localStorage.removeItem('fincrm_refresh')
  }, activeRole), [token, activeRole])
  const roleCode = profile?.role?.code || parseJwt(token).role || ''
  const allowedByRole = {
    lead_portal: ['leads'],
    manager: ['dashboard','customers','leads','applications','application-checklist','documents','tasks','customer-followups','lead-followups','application-followups','today','teams','employees','team-leads','managers','schedules','payments','interactions','drafts','attendees','hierarchy'],
    team_lead: ['dashboard','customers','leads','applications','application-checklist','documents','tasks','customer-followups','lead-followups','application-followups','today','teams','employees','team-leads','schedules','payments','interactions','drafts','attendees','hierarchy'],
    general_employee: ['dashboard','customers','leads','applications','documents','tasks','customer-followups','lead-followups','application-followups','today','employees','schedules','payments','interactions','drafts','attendees'],
    sales_analyst: ['dashboard','customers','leads','applications','tasks','customer-followups','lead-followups','application-followups','today','payments','schedules','interactions'],
    finance_analyst: ['dashboard','customers','leads','applications','application-checklist','documents','tasks','today','payments','schedules'],
    financial_analyst: ['dashboard','customers','leads','applications','application-checklist','documents','tasks','today','payments','schedules'],
    doc_officer: ['dashboard','customers','leads','applications','application-checklist','documents','categories','tasks','customer-followups','lead-followups','application-followups','today','interactions'],
    document_verification_officer: ['dashboard','customers','leads','applications','application-checklist','documents','categories','tasks','customer-followups','lead-followups','application-followups','today','interactions'],
  }
  const visibleModules = useMemo(() => allModules.filter((module) => (allowedByRole[roleCode] ? allowedByRole[roleCode].includes(module.id) : true) && (!module.minLevel || roleLevel >= module.minLevel || roleCode === 'lead_portal') && (!module.roles || module.roles.includes(roleCode))), [roleLevel, roleCode])
  const addActionsByRole = {
    org_admin: [['managers','Manager','manager'],['team-leads','Team lead','team_lead'],['departments','Department'],['teams','Team'],['employees','Employee','employee'],['customers','Customer'],['leads','Lead'],['applications','Application'],['documents','Document'],['categories','Document category'],['tasks','Task'],['customer-followups','Customer follow-up'],['lead-followups','Lead follow-up'],['application-followups','Application follow-up'],['payments','Payment']],
    super_admin: [['managers','Manager','manager'],['team-leads','Team lead','team_lead'],['departments','Department'],['teams','Team'],['employees','Employee','employee'],['customers','Customer'],['leads','Lead'],['applications','Application'],['documents','Document'],['categories','Document category'],['tasks','Task'],['customer-followups','Customer follow-up'],['lead-followups','Lead follow-up'],['application-followups','Application follow-up'],['payments','Payment']],
    manager: [['team-leads','Team lead','team_lead'],['teams','Team'],['employees','Employee','employee'],['customers','Customer'],['leads','Lead'],['applications','Application'],['tasks','Task']],
    team_lead: [['employees','Employee','employee'],['customers','Customer'],['leads','Lead'],['applications','Application'],['tasks','Task']],
    general_employee: [['employees','Employee','employee'],['customers','Customer'],['leads','Lead'],['applications','Application'],['tasks','Task'],['customer-followups','Customer follow-up'],['lead-followups','Lead follow-up'],['application-followups','Application follow-up']],
    sales_analyst: [['payments','Payment'],['tasks','Task'],['customer-followups','Customer follow-up'],['lead-followups','Lead follow-up'],['application-followups','Application follow-up']],
    doc_officer: [['documents','Document'],['categories','Document category'],['tasks','Task'],['customer-followups','Customer follow-up'],['lead-followups','Lead follow-up'],['application-followups','Application follow-up']],
    document_verification_officer: [['documents','Document'],['categories','Document category'],['tasks','Task'],['customer-followups','Customer follow-up'],['lead-followups','Lead follow-up'],['application-followups','Application follow-up']],
  }
  const addActions=(addActionsByRole[roleCode] || []).filter(([id]) => visibleModules.some((module) => module.id === id))

  useEffect(() => {
    if (!token) { setProfile(null); return }
    api.get('/auth/me/').then((data) => {
      setProfile(data)
      const selectedRoleExists=(data.available_roles || []).some((role)=>role.code===activeRole)
      if ((!activeRole || !selectedRoleExists) && data.role?.code) {
        setActiveRole(data.role.code)
        localStorage.setItem('fincrm_active_role', data.role.code)
      }
    }).catch(() => {
      const claims = parseJwt(token)
      if (!claims.username) { setToken(''); localStorage.removeItem('fincrm_access') }
    })
  }, [token, activeRole])

  function signIn(data) { setToken(data.access); setProfile(data); setActiveModule('dashboard'); const role=data.role?.code || ''; setActiveRole(role); if(role) localStorage.setItem('fincrm_active_role',role) }
  function signOut() {
    localStorage.removeItem('fincrm_access'); localStorage.removeItem('fincrm_refresh')
    localStorage.removeItem('fincrm_active_role')
    setToken(''); setProfile(null); setActiveModule('dashboard')
  }
  if (!token) return <Login onLogin={signIn} />
  const active = visibleModules.find((module) => module.id === activeModule) || visibleModules[0]
  function createModule(id, staffType) { setActiveModule(['managers','team-leads'].includes(id) ? 'employees' : id); setCreateStaffType(staffType || 'employee'); setCreateSignal((current) => current + 1) }
  function changeRole(code) { setActiveRole(code); localStorage.setItem('fincrm_active_role', code); setActiveModule('dashboard') }
  function drillDown(path) {
    const target=visibleModules.filter((module)=>module.endpoint && path.startsWith(module.endpoint)).sort((a,b)=>b.endpoint.length-a.endpoint.length)[0]
    if (!target) return
    setModulePaths((current)=>({...current,[target.id]:path})); setActiveModule(target.id)
  }
  return <AppShell user={profile} modules={visibleModules} addActions={addActions} activeModule={active?.id} onNavigate={setActiveModule} onCreateModule={createModule} onRoleChange={changeRole} onSignOut={signOut}>
    {roleCode === 'lead_portal' ? <ResourcePage key={`lead-portal-${activeRole}`} module={active} api={api} user={profile} readOnlyPortal /> : active?.type === 'dashboard' ? <Dashboard key={`${profile?.role?.code || 'loading'}-${activeRole}`} api={api} user={profile} onNavigate={setActiveModule} onDrillDown={drillDown} /> : active?.type === 'today' ? <TodayPage key={`${activeRole}-today`} api={api} /> : active && <ResourcePage key={active.id} module={active} api={api} user={profile} createSignal={createSignal} createStaffType={createStaffType} initialPath={modulePaths[active.id]} />}
  </AppShell>
}
