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
import PlanCatalog from './components/PlanCatalog'
import EnterpriseCheckoutPage from './components/EnterpriseCheckoutPage'
import EnterpriseManagementPage from './components/EnterpriseManagementPage'
import SubscriptionPlanManagementPage from './components/SubscriptionPlanManagementPage'
import { getPresetDateRange } from './dateRange'

function FollowUpsPage({ modules, api, user }) {
  const [kind, setKind] = useState('customer-followups')
  const module = modules.find((item) => item.id === kind)
  return <section className="page"><h2>Follow-ups</h2><p>Create and track customer, lead, and application follow-ups.</p>
    <div className="tabs">{[['customer-followups','Customers'],['lead-followups','Leads'],['application-followups','Applications']].map(([id,label]) => <button type="button" key={id} className={kind===id?'active':''} onClick={() => setKind(id)}>{label}</button>)}</div>
    {module && <ResourcePage key={kind} module={module} api={api} user={user} />}
  </section>
}

function PaymentsPage({ api, user }) {
  const [section, setSection] = useState('schedules')
  const sections = [['schedules','Repayment schedules'],['payments','Payments']]
  const selected = allModules.find((item) => item.id === section)
  return <section className="page"><h2>Payments</h2><p>Review repayment schedules and track verified payments.</p>
    <div className="tabs">{sections.map(([id,label]) => <button type="button" key={id} className={section===id?'active':''} onClick={() => setSection(id)}>{label}</button>)}</div>
    {selected && <ResourcePage key={section} module={selected} api={api} user={user} />}
  </section>
}

function parseJwt(token) {
  try { return JSON.parse(atob(token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/'))) } catch { return {} }
}

function PlatformAdminShell({ user, activeModule, onNavigate, onSignOut, children }) {
  return <main className="app-layout">
    <aside className="app-sidebar">
      <div className="brand">FIN<span>CRM</span></div>
      <p className="org-name">Platform administration</p>
      <nav aria-label="Platform administration" className="main-nav">
        {[['enterprise-management', 'Enterprise enquiries'], ['edit-plans', 'Edit plans']].map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => onNavigate(id)}>{label}</button>)}
      </nav>
      <div className="sidebar-bottom"><span>{user?.user?.username || user?.username || 'Administrator'}</span><button type="button" onClick={onSignOut}>Sign out</button></div>
    </aside>
    <section className="app-content">{children}</section>
  </main>
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
  }, activeRole, setToken), [token, activeRole])
  const roleCode = profile?.role?.code || parseJwt(token).role || ''
  const isSuperAdmin = roleCode === 'super_admin' || profile?.is_superuser || parseJwt(token).is_superuser
  const baseModules = ['dashboard','today','customers','leads','applications','payments','employees','team-leads','managers','departments','teams','organization','plans','subscription','billing','hierarchy']
  const visibleModules = useMemo(() => allModules.filter((module) => {
    if (roleCode === 'lead_portal') return module.id === 'dashboard'
    if (module.id === 'enterprise-management') return roleCode === 'super_admin'
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

  if (new URLSearchParams(window.location.search).has('enterprise_checkout') || window.sessionStorage.getItem('fincrm_enterprise_checkout')) return <EnterpriseCheckoutPage />

  function signIn(data) {
    setToken(data.access)
    setProfile(data)
    const role = data.role?.code || ''
    const superAdmin = role === 'super_admin' || data.user?.is_superuser || data.is_superuser || parseJwt(data.access).is_superuser
    setActiveModule(superAdmin ? 'enterprise-management' : 'dashboard')
    setActiveRole(role)
    if (role) localStorage.setItem('fincrm_active_role', role)
  }
  async function signOut() {
    const refresh = localStorage.getItem('fincrm_refresh')
    if (refresh) await api.logout(refresh).catch(() => {})
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
  if (isSuperAdmin) return <PlatformAdminShell user={profile} activeModule={activeModule === 'edit-plans' ? 'edit-plans' : 'enterprise-management'} onNavigate={setActiveModule} onSignOut={signOut}>
    {activeModule === 'edit-plans' ? <SubscriptionPlanManagementPage api={api} /> : <EnterpriseManagementPage api={api} />}
  </PlatformAdminShell>
  function changeRole(code) { setActiveRole(code); localStorage.setItem('fincrm_active_role', code); setActiveModule('dashboard'); setDrillTarget(null) }
  return <AppShell user={profile} modules={visibleModules} activeModule={activeModule} dateRange={dateRange} onDateRangeChange={changeDateRange} onNavigate={setActiveModule} onRoleChange={changeRole} onSignOut={signOut}>
    {roleCode === 'lead_portal' ? <LeadPortalDashboard key={`lead-portal-${activeRole}`} api={api} /> : activeModule === 'enterprise-management' ? <EnterpriseManagementPage api={api} /> : activeModule === 'plans' ? <PlanCatalog api={api} user={profile?.user || profile} /> : activeModule === 'pipeline' ? <PipelinePage api={api} dateRange={dateRange} onDrillDown={setDrillTarget} /> : activeModule === 'reports' ? <ReportPage api={api} dateRange={dateRange} onDrillDown={setDrillTarget} /> : activeModule === 'settings' ? <SettingsPage api={api} user={profile} onProfileUpdated={setProfile} onNavigate={setActiveModule} /> : activeModule === 'followups' ? <FollowUpsPage modules={visibleModules} api={api} user={profile} /> : activeModule === 'payments' ? <PaymentsPage api={api} user={profile} /> : active?.type === 'dashboard' ? <Dashboard key={`${profile?.role?.code || 'loading'}-${activeRole}`} api={api} user={profile} dateRange={dateRange} onNavigate={setActiveModule} onDrillDown={setDrillTarget} /> : active?.type === 'today' ? <TodayPage key={`${activeRole}-today`} api={api} /> : active && <ResourcePage key={active.id} module={active} api={api} user={profile} initialPath={modulePaths[active.id]} />}
    {drillTarget && <Drilldown api={api} target={{ ...drillTarget, dateRange }} onClose={() => setDrillTarget(null)} />}
    <AIAssistant key={activeRole} api={api} roleName={profile?.role?.name} />
  </AppShell>
}
