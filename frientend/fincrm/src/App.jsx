import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
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
import BrandFooter from './components/BrandFooter'
import { getPresetDateRange } from './dateRange'
import logoUrl from './assets/logo.jpg'

const baseModules = ['dashboard','today','customers','leads','payments','employees','team-leads','managers','departments','teams','organization','plans','subscription','billing','hierarchy']

function FollowUpsPage({ modules, api, user }) {
  const [kind, setKind] = useState('customer-followups')
  const module = modules.find((item) => item.id === kind)
  return <section className="page"><h2>Follow-ups</h2><p>Create and track customer and lead follow-ups.</p>
    <div className="tabs">{[['customer-followups','Customers'],['lead-followups','Leads']].map(([id,label]) => <button type="button" key={id} className={kind===id?'active':''} onClick={() => setKind(id)}>{label}</button>)}</div>
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  function navigate(id) { onNavigate(id); setMobileMenuOpen(false) }
  useEffect(() => {
    if (!mobileMenuOpen) return undefined
    const closeOnEscape = (event) => { if (event.key === 'Escape') setMobileMenuOpen(false) }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', closeOnEscape) }
  }, [mobileMenuOpen])
  return <main className={`app-layout${mobileMenuOpen ? ' mobile-menu-open' : ''}`}>
    <button type="button" className="mobile-menu-backdrop" aria-label="Close menu" tabIndex={mobileMenuOpen ? 0 : -1} onClick={() => setMobileMenuOpen(false)} />
    <aside id="mobile-primary-menu" className={`app-sidebar${mobileMenuOpen ? ' is-mobile-open' : ''}`}>
      <div className="mobile-drawer-heading"><span>Administration menu</span><button type="button" aria-label="Close menu" onClick={() => setMobileMenuOpen(false)}>×</button></div>
      <button type="button" className="brand-lockup" onClick={() => navigate('enterprise-management')} aria-label="Auron FIN CRM administration">
        <img src={logoUrl} alt="" />
        <span><strong>AURON</strong> FIN CRM</span>
      </button>
      <p className="org-name">Platform administration</p>
      <nav aria-label="Platform administration" className="main-nav">
        {[['enterprise-management', 'Enterprise enquiries'], ['edit-plans', 'Edit plans']].map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => navigate(id)}>{label}</button>)}
      </nav>
      <div className="sidebar-bottom">
        <button type="button" className="profile-settings-button" onClick={() => navigate('settings')} aria-label="Open settings"><span className="profile-avatar">{(user?.user?.username || user?.username || 'A').slice(0, 1).toUpperCase()}</span><span className="profile-copy"><strong>{user?.user?.username || user?.username || 'Administrator'}</strong><span>Platform administrator</span></span></button>
        <button type="button" className="signout-button" onClick={onSignOut} aria-label="Sign out" title="Sign out">↗</button>
      </div>
    </aside>
    <section className="app-content"><header className="mobile-topbar"><button type="button" className="mobile-menu-toggle" aria-label="Open menu" aria-expanded={mobileMenuOpen} aria-controls="mobile-primary-menu" onClick={() => setMobileMenuOpen(true)}><span /><span /><span /></button><div className="mobile-topbar-title"><span>AURON FIN CRM</span><strong>{activeModule === 'edit-plans' ? 'Edit plans' : activeModule === 'settings' ? 'Settings' : 'Enterprise enquiries'}</strong></div></header>{children}<BrandFooter className="app-brand-footer" /></section>
  </main>
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('fincrm_access') || '')
  const [profile, setProfile] = useState(null)
  const [activeRole, setActiveRole] = useState(localStorage.getItem('fincrm_active_role') || '')
  const [activeModule, setActiveModule] = useState('dashboard')
  const [dateRange, setDateRange] = useState(() => getPresetDateRange('today'))
  const [drillTarget, setDrillTarget] = useState(null)
  const roleLevel = profile?.role?.hierarchy_level ?? parseJwt(token).hierarchy_level ?? 0
  const api = useMemo(() => createApi(token, () => {
    setToken(''); setProfile(null); localStorage.removeItem('fincrm_access'); localStorage.removeItem('fincrm_refresh')
  }, activeRole, setToken), [token, activeRole])
  const roleCode = profile?.role?.code || parseJwt(token).role || ''
  const isSuperAdmin = roleCode === 'super_admin' || profile?.is_superuser || parseJwt(token).is_superuser
  useLayoutEffect(() => {
    if (window.matchMedia('(max-width: 780px)').matches) window.scrollTo(0, 0)
  }, [activeModule])
  const visibleModules = useMemo(() => allModules.filter((module) => {
    if (roleCode === 'lead_portal') return ['dashboard', 'settings'].includes(module.id)
    if (module.id === 'enterprise-management') return roleCode === 'super_admin'
    if (module.id === 'plans') return roleLevel >= 90
    if (!baseModules.includes(module.id) && !['tasks','customer-followups','lead-followups'].includes(module.id)) return false
    if (module.id === 'managers' || module.id === 'departments' || module.id === 'organization') return roleLevel >= 90
    if (module.id === 'team-leads' || module.id === 'teams') return roleLevel >= 70
    if (module.id === 'employees') return roleLevel >= 50
    if (module.id === 'tasks') return roleLevel >= 30
    if (['customer-followups','lead-followups'].includes(module.id)) return roleLevel >= 30
    return !module.minLevel || roleLevel >= module.minLevel
  }), [roleLevel, roleCode])
  useEffect(() => {
    if (!token) return undefined
    let active = true
    api.get('/auth/me/').then((data) => {
      if (!active) return
      setProfile(data)
      const selectedRoleExists=(data.available_roles || []).some((role)=>role.code===activeRole)
      if ((!activeRole || !selectedRoleExists) && data.role?.code) {
        setActiveRole(data.role.code)
        localStorage.setItem('fincrm_active_role', data.role.code)
      }
    }).catch(() => {
      if (!active) return
      const claims = parseJwt(token)
      if (!claims.username) { setToken(''); localStorage.removeItem('fincrm_access') }
    })
    return () => { active = false }
  }, [api, token, activeRole])

  if (new URLSearchParams(window.location.search).has('enterprise_checkout') || window.sessionStorage.getItem('fincrm_enterprise_checkout')) return <EnterpriseCheckoutPage />
  if (new URLSearchParams(window.location.search).has('reset_uid') && new URLSearchParams(window.location.search).has('reset_token')) return <Login onLogin={signIn} />

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
  if (isSuperAdmin) return <PlatformAdminShell user={profile} activeModule={activeModule} onNavigate={setActiveModule} onSignOut={signOut}>
    <div className="page-transition" key={activeModule}>{activeModule === 'settings' ? <SettingsPage api={api} user={profile} onProfileUpdated={setProfile} onNavigate={setActiveModule} /> : activeModule === 'edit-plans' ? <SubscriptionPlanManagementPage api={api} /> : <EnterpriseManagementPage api={api} />}</div>
  </PlatformAdminShell>
  function changeRole(code) { setActiveRole(code); localStorage.setItem('fincrm_active_role', code); setActiveModule('dashboard'); setDrillTarget(null) }
  return <AppShell user={profile} modules={visibleModules} activeModule={activeModule} dateRange={dateRange} onDateRangeChange={changeDateRange} onNavigate={setActiveModule} onRoleChange={changeRole} onSignOut={signOut}>
    <div className="page-transition" key={`${activeModule}-${activeRole}`}>{activeModule === 'settings' ? <SettingsPage api={api} user={profile} onProfileUpdated={setProfile} onNavigate={setActiveModule} /> : roleCode === 'lead_portal' ? <LeadPortalDashboard key={`lead-portal-${activeRole}`} api={api} /> : activeModule === 'enterprise-management' ? <EnterpriseManagementPage api={api} /> : activeModule === 'plans' ? <PlanCatalog api={api} user={profile?.user || profile} /> : activeModule === 'pipeline' ? <PipelinePage api={api} dateRange={dateRange} onDrillDown={setDrillTarget} /> : activeModule === 'reports' ? <ReportPage api={api} dateRange={dateRange} onDrillDown={setDrillTarget} /> : activeModule === 'followups' ? <FollowUpsPage modules={visibleModules} api={api} user={profile} /> : activeModule === 'payments' ? <PaymentsPage api={api} user={profile} /> : active?.type === 'dashboard' ? <Dashboard key={`${profile?.role?.code || 'loading'}-${activeRole}`} api={api} user={profile} dateRange={dateRange} onNavigate={setActiveModule} onDrillDown={setDrillTarget} /> : active?.type === 'today' ? <TodayPage key={`${activeRole}-today`} api={api} /> : active && <ResourcePage key={active.id} module={active} api={api} user={profile} />}</div>
    {drillTarget && <Drilldown api={api} target={{ ...drillTarget, dateRange }} onClose={() => setDrillTarget(null)} />}
    {roleCode !== 'lead_portal' && <AIAssistant key={activeRole} api={api} roleName={profile?.role?.name} />}
  </AppShell>
}
