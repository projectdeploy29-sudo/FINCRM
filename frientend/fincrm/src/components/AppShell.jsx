import { useEffect, useRef, useState } from 'react'
import logoUrl from '../assets/logo.jpg'
import BrandFooter from './BrandFooter'

const navItems = [
  ['dashboard', 'Dashboard'], ['tasks', 'Send'], ['followups', 'Follow-ups'],
  ['today', 'Today'], ['pipeline', 'Pipeline'], ['reports', 'Report'], ['settings', 'Settings'],
  ['subscription', 'My subscription'], ['billing', 'Billing history'], ['plans', 'Plans'],
]
const recordItems = [
  ['managers', 'Manager'], ['team-leads', 'Team Lead'], ['departments', 'Department'], ['teams', 'Team'],
  ['employees', 'Employee'], ['customers', 'Customer'], ['leads', 'Lead'],
  ['payments', 'Payments'],
  ['hierarchy', 'Organization hierarchy'],
]

const coreIcons = {
  dashboard: 'dashboard',
  today: 'clock',
  pipeline: 'columns',
  reports: 'chart',
  settings: 'settings',
  subscription: 'gem',
  billing: 'receipt',
  plans: 'sparkles',
  followups: 'check',
  tasks: 'checklist',
}

const recordIcons = {
  managers: 'briefcase',
  'team-leads': 'users',
  departments: 'building',
  teams: 'grid',
  employees: 'contact',
  customers: 'user',
  leads: 'target',
  payments: 'wallet',
  hierarchy: 'tree',
}

const iconShapes = {
  dashboard: <><rect x="3" y="3" width="8" height="8" rx="1.5" /><rect x="13" y="3" width="8" height="5" rx="1.5" /><rect x="13" y="10" width="8" height="11" rx="1.5" /><rect x="3" y="13" width="8" height="8" rx="1.5" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  columns: <><rect x="3" y="4" width="5" height="16" rx="1.5" /><rect x="9.5" y="4" width="5" height="11" rx="1.5" /><rect x="16" y="4" width="5" height="14" rx="1.5" /></>,
  chart: <><path d="M4 19.5h16" /><path d="M6.5 16v-4M12 16V6M17.5 16v-7" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.2h-2.6v-.2a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H6.3v-2.6h.2a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5v-.2H15v.2a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.2V14h-.2a1.7 1.7 0 0 0-1.5 1Z" /></>,
  gem: <><path d="m12 3 8.5 5-8.5 13L3.5 8 12 3Z" /><path d="m3.5 8 17 0M8.5 8 12 21M15.5 8 12 21M8 3l-4.5 5M16 3l4.5 5" /></>,
  receipt: <><path d="M6 3.5h12v17l-2.2-1.4-1.8 1.4-2-1.4-2 1.4-1.8-1.4L6 20.5v-17Z" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  sparkles: <><path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z" /><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15Z" /></>,
  check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16.5 9" /></>,
  checklist: <><path d="m4 6 1.5 1.5L8 5M11 6h9M4 12l1.5 1.5L8 11M11 12h9M4 18l1.5 1.5L8 17M11 18h9" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
  briefcase: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0M16 5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 4 5" /></>,
  building: <><rect x="4" y="3" width="16" height="18" rx="1.5" /><path d="M8 7h2M14 7h2M8 11h2M14 11h2M8 15h2M14 15h2M10 21v-3h4v3" /></>,
  contact: <><rect x="4" y="3" width="16" height="18" rx="2" /><circle cx="12" cy="9" r="2.5" /><path d="M8 17a4 4 0 0 1 8 0" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></>,
  wallet: <><rect x="3" y="5" width="18" height="15" rx="2" /><path d="M3 9h18M16 14h2" /><path d="M7 5V3h10v2" /></>,
  tree: <><path d="M12 4v4M6 12V9h12v3M6 12v3M12 12v3M18 12v3M3 19h6M9 19h6M15 19h6" /><circle cx="12" cy="4" r="1.5" /><circle cx="6" cy="17" r="1.5" /><circle cx="12" cy="17" r="1.5" /><circle cx="18" cy="17" r="1.5" /></>,
}

function NavIcon({ name }) {
  return <svg className="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconShapes[name] || iconShapes.grid}</svg>
}

export default function AppShell({ user, modules, activeModule, dateRange, onDateRangeChange, onNavigate, onRoleChange, onSignOut, children }) {
  const recordsMenuRef = useRef(null)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const roleChoices = user?.available_roles || []
  const roleLevel = user?.role?.hierarchy_level || 0
  const isLeadPortal = user?.role?.code === 'lead_portal'
  const showDateFilter = !isLeadPortal && ['dashboard', 'pipeline', 'reports'].includes(activeModule)
  const available = new Set(modules.map((module) => module.id))
  const coreItems = navItems.filter(([id]) => {
    if (isLeadPortal) return id === 'dashboard' || id === 'settings'
    if (id === 'plans') return (user?.role?.hierarchy_level || 0) >= 90
    if (id === 'followups') return (user?.role?.hierarchy_level || 0) >= 30
    if (id === 'tasks') return roleLevel >= 30
    return id === 'pipeline' || id === 'reports' || id === 'settings' || available.has(id)
  })
  const records = isLeadPortal ? [] : recordItems.filter(([id]) => available.has(id))
  const roleLabel = user?.role?.name || (isLeadPortal ? 'Lead portal' : 'Workspace member')
  const activeLabel = [...navItems, ...recordItems].find(([id]) => id === activeModule)?.[1] || 'Workspace'
  const quickItems = [['dashboard', 'Dashboard'], ['today', 'Today'], ['reports', 'Report'], ['settings', 'Profile']]
  function navigate(id) {
    if (window.matchMedia('(max-width: 780px)').matches) window.scrollTo(0, 0)
    onNavigate(id)
    setMobileMenuOpen(false)
    if (recordsMenuRef.current) recordsMenuRef.current.open = false
  }
  useEffect(() => {
    const closeRecordsMenu = (event) => {
      if (recordsMenuRef.current && !recordsMenuRef.current.contains(event.target)) recordsMenuRef.current.open = false
    }
    document.addEventListener('pointerdown', closeRecordsMenu)
    return () => document.removeEventListener('pointerdown', closeRecordsMenu)
  }, [])
  useEffect(() => {
    if (!mobileMenuOpen) return undefined
    const closeOnEscape = (event) => { if (event.key === 'Escape') setMobileMenuOpen(false) }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [mobileMenuOpen])
  return <main className={`app-layout${mobileMenuOpen ? ' mobile-menu-open' : ''}`}>
    <button type="button" className="mobile-menu-backdrop" aria-label="Close menu" tabIndex={mobileMenuOpen ? 0 : -1} onClick={() => setMobileMenuOpen(false)} />
    <aside id="mobile-primary-menu" className={`app-sidebar${mobileMenuOpen ? ' is-mobile-open' : ''}`}>
      <div className="mobile-drawer-heading"><span>Workspace menu</span><button type="button" aria-label="Close menu" onClick={() => setMobileMenuOpen(false)}>×</button></div>
      <button type="button" className="brand-lockup" onClick={() => navigate('dashboard')} aria-label="Go to dashboard">
        <img src={logoUrl} alt="" />
        <span><strong>AURON</strong> FIN CRM</span>
      </button>
      <p className="org-name">{user?.organization?.name || 'Finance CRM'}</p>
      <div className="sidebar-role"><span>{roleLabel}</span><b>{roleLevel >= 90 ? 'Admin' : roleLevel >= 70 ? 'Team' : roleLevel >= 30 ? 'Staff' : 'Lead'}</b></div>
      {roleChoices.length > 1 && <label className="role-picker">Role<select value={user?.role?.code || ''} onChange={(event) => onRoleChange(event.target.value)}>
        {roleChoices.map((role) => <option key={role.code} value={role.code}>{role.name}</option>)}
      </select></label>}
      <nav aria-label="Main navigation" className="main-nav">
        {coreItems.slice(0, 1).map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => navigate(id)}><span className="nav-icon" aria-hidden="true"><NavIcon name={coreIcons[id]} /></span><span>{label}</span></button>)}
        {records.length > 0 && <details ref={recordsMenuRef} className={`records-nav${records.some(([id]) => id === activeModule) ? ' has-active' : ''}`}>
          <summary><span className="nav-icon" aria-hidden="true"><NavIcon name="grid" /></span><span>Records</span></summary>
          <div className="records-nav-menu">{records.map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => navigate(id)}><span className="record-nav-icon" aria-hidden="true"><NavIcon name={recordIcons[id]} /></span><span>{label}</span></button>)}</div>
        </details>}
        {coreItems.slice(1).map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => navigate(id)}><span className="nav-icon" aria-hidden="true"><NavIcon name={coreIcons[id]} /></span><span>{label}</span></button>)}
      </nav>
      <div className="sidebar-bottom">
        <button type="button" className="profile-settings-button" onClick={() => navigate('settings')} aria-label="Open settings">
          <span className="profile-avatar">{(user?.user?.username || user?.username || 'U').slice(0, 1).toUpperCase()}</span>
          <span className="profile-copy"><strong>{user?.user?.username || user?.username || 'User'}</strong><span>{user?.role?.name || 'Member'}</span></span>
        </button>
        <button type="button" className="signout-button" onClick={onSignOut} aria-label="Sign out" title="Sign out">↗</button>
      </div>
    </aside>
    <section className="app-content">
      <header className="mobile-topbar">
        <button type="button" className="mobile-menu-toggle" aria-label="Open menu" aria-expanded={mobileMenuOpen} aria-controls="mobile-primary-menu" onClick={() => setMobileMenuOpen(true)}><span /><span /><span /></button>
        <div className="mobile-topbar-title"><span>AURON FIN CRM</span><strong>{activeLabel}</strong></div>
      </header>
      {showDateFilter && <div className="global-date-filter"><label htmlFor="global-date-preset">Date range</label><select id="global-date-preset" value={dateRange?.preset || 'today'} onChange={(event) => onDateRangeChange(event.target.value)}>
        <option value="today">Today</option><option value="month">Month to date</option><option value="year">Year to date</option><option value="custom">Custom range</option>
      </select>
      {dateRange?.preset === 'custom' && <><label htmlFor="global-date-start">From</label><input id="global-date-start" type="date" value={dateRange.start_date} onChange={(event) => onDateRangeChange('custom', 'start_date', event.target.value)} /><label htmlFor="global-date-end">To</label><input id="global-date-end" type="date" value={dateRange.end_date} min={dateRange.start_date || undefined} onChange={(event) => onDateRangeChange('custom', 'end_date', event.target.value)} /></>}
      </div>}
      {children}
      <BrandFooter className="app-brand-footer" />
    </section>
    <nav className="mobile-bottom-nav" aria-label="Quick navigation">
      {quickItems.map(([id, label]) => {
        const enabled = id === 'dashboard' || id === 'settings' || coreItems.some(([itemId]) => itemId === id)
        const active = id === 'settings' ? activeModule === 'settings' : activeModule === id
        return <button type="button" key={id} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} disabled={!enabled} onClick={() => navigate(id)}><NavIcon name={id === 'settings' ? 'user' : coreIcons[id]} /><span>{label}</span></button>
      })}
    </nav>
  </main>
}
