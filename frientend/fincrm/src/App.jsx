import { useEffect, useMemo, useState } from 'react'
import { createApi } from './api'
import { modules as allModules } from './config/modules'
import Login from './components/Login'
import AppShell from './components/AppShell'
import Dashboard from './components/Dashboard'
import ResourcePage from './components/ResourcePage'
import TodayPage from './components/TodayPage'
import PipelinePage from './components/PipelinePage'
import ReportPage from './components/ReportPage'
import SettingsPage from './components/SettingsPage'
import Drilldown from './components/Drilldown'
import LeadPortalDashboard from './components/LeadPortalDashboard'
import AIAssistant from './components/AIAssistant'
import { getPresetDateRange } from './dateRange'

function FollowUpsPage({ modules, api, user }) {
  const [kind, setKind] = useState('customer-followups')
  const module = modules.find((item) => item.id === kind)
  return <section className="page"><h2>Follow-ups</h2><p>Create and track customer, lead, and application follow-ups.</p>
    <div className="tabs">{[['customer-followups','Customers'],['lead-followups','Leads'],['application-followups','Applications']].map(([id,label]) => <button type="button" key={id} className={kind===id?'active':''} onClick={() => setKind(id)}>{label}</button>)}</div>
    {module && <ResourcePage key={kind} module={module} api={api} user={user} />}
  </section>
}

function ApplicationsPage({ api, user }) {
  const [section, setSection] = useState('applications')
  const sections = [['applications','Applications'],['schedules','Repayment schedules'],['payments','Payments']]
  const selected = allModules.find((item) => item.id === section)
  return <section className="page"><h2>Applications</h2><p>Manage assigned applications, repayment schedules, and payments.</p>
    <div className="tabs">{sections.map(([id,label]) => <button type="button" key={id} className={section===id?'active':''} onClick={() => setSection(id)}>{label}</button>)}</div>
    {selected && <ResourcePage key={section} module={selected} api={api} user={user} />}
  </section>
}

function parseJwt(token) {
  try { return JSON.parse(atob(token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/'))) } catch { return {} }
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('fincrm_access') || '')
  const [profile, setProfile] = useState(null)
  const [activeRole, setActiveRole] = useState(localStorage.getItem('fincrm_active_role') || '')
  const [activeModule, setActiveModule] = useState('dashboard')
  const [dateRange, setDateRange] = useState(() => getPresetDateRange('today'))
  const [modulePaths, setModulePaths] = useState({})
  const [drillTarget, setDrillTarget] = useState(null)
  const roleLevel = profile?.role?.hierarchy_level ?? parseJwt(token).hierarchy_level ?? 0
  const api = useMemo(() => createApi(token, () => {
    setToken(''); setProfile(null); localStorage.removeItem('fincrm_access'); localStorage.removeItem('fincrm_refresh')
  }, activeRole), [token, activeRole])
  const roleCode = profile?.role?.code || parseJwt(token).role || ''
  const baseModules = ['dashboard','today','customers','leads','applications','employees','team-leads','managers','departments','teams','organization','plans']
  const visibleModules = useMemo(() => allModules.filter((module) => {
    if (roleCode === 'lead_portal') return module.id === 'dashboard'
    if (module.id === 'plans') return roleLevel >= 90
    if (!baseModules.includes(module.id) && !['tasks','customer-followups','lead-followups','application-followups'].includes(module.id)) return false
    if (module.id === 'managers' || module.id === 'departments' || module.id === 'organization') return roleLevel >= 90
    if (module.id === 'team-leads' || module.id === 'teams') return roleLevel >= 70
    if (module.id === 'employees') return roleLevel >= 50
    if (module.id === 'tasks') return roleLevel >= 30
    if (['customer-followups','lead-followups','application-followups'].includes(module.id)) return roleLevel >= 30
    return !module.minLevel || roleLevel >= module.minLevel
  }), [roleLevel, roleCode])
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
  function changeDateRange(preset, field, value) {
    if (preset !== 'custom') { setDateRange(getPresetDateRange(preset)); return }
    if (!field) { setDateRange((current) => ({ ...current, preset: 'custom' })); return }
    setDateRange((current) => {
      const next = { ...current, preset: 'custom', [field]: value }
      if (field === 'start_date' && next.end_date && value > next.end_date) next.end_date = value
      return next
    })
  }
  if (!token) return <Login onLogin={signIn} />
  const active = visibleModules.find((module) => module.id === activeModule) || visibleModules[0]
  function changeRole(code) { setActiveRole(code); localStorage.setItem('fincrm_active_role', code); setActiveModule('dashboard'); setDrillTarget(null) }
  return <AppShell user={profile} modules={visibleModules} activeModule={activeModule} dateRange={dateRange} onDateRangeChange={changeDateRange} onNavigate={setActiveModule} onRoleChange={changeRole} onSignOut={signOut}>
    {roleCode === 'lead_portal' ? <LeadPortalDashboard key={`lead-portal-${activeRole}`} api={api} /> : activeModule === 'pipeline' ? <PipelinePage api={api} dateRange={dateRange} onDrillDown={setDrillTarget} /> : activeModule === 'reports' ? <ReportPage api={api} dateRange={dateRange} onDrillDown={setDrillTarget} /> : activeModule === 'settings' ? <SettingsPage api={api} user={profile} onProfileUpdated={setProfile} onNavigate={setActiveModule} /> : activeModule === 'followups' ? <FollowUpsPage modules={visibleModules} api={api} user={profile} /> : activeModule === 'applications' ? <ApplicationsPage api={api} user={profile} /> : active?.type === 'dashboard' ? <Dashboard key={`${profile?.role?.code || 'loading'}-${activeRole}`} api={api} user={profile} dateRange={dateRange} onNavigate={setActiveModule} onDrillDown={setDrillTarget} /> : active?.type === 'today' ? <TodayPage key={`${activeRole}-today`} api={api} /> : active && <ResourcePage key={active.id} module={active} api={api} user={profile} initialPath={modulePaths[active.id]} />}
    {drillTarget && <Drilldown api={api} target={{ ...drillTarget, dateRange }} onClose={() => setDrillTarget(null)} />}
    <AIAssistant key={activeRole} api={api} roleName={profile?.role?.name} />
  </AppShell>
}
