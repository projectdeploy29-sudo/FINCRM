const navItems = [
  ['dashboard', 'Dashboard'], ['tasks', 'Send'], ['followups', 'Follow-ups'],
  ['today', 'Today'], ['pipeline', 'Pipeline'], ['reports', 'Report'], ['settings', 'Settings'],
  ['subscription', 'My subscription'], ['billing', 'Billing history'], ['plans', 'Plans'],
]
const recordItems = [
  ['managers', 'Manager'], ['team-leads', 'Team Lead'], ['departments', 'Department'], ['teams', 'Team'],
  ['employees', 'Employee'], ['customers', 'Customer'], ['leads', 'Lead'], ['applications', 'Application'],
  ['payments', 'Payments'],
  ['hierarchy', 'Organization hierarchy'],
]

export default function AppShell({ user, modules, activeModule, dateRange, onDateRangeChange, onNavigate, onRoleChange, onSignOut, children }) {
  const roleChoices = user?.available_roles || []
  const roleLevel = user?.role?.hierarchy_level || 0
  const isLeadPortal = user?.role?.code === 'lead_portal'
  const showDateFilter = !isLeadPortal && ['dashboard', 'pipeline', 'reports'].includes(activeModule)
  const available = new Set(modules.map((module) => module.id))
  const coreItems = navItems.filter(([id]) => {
    if (isLeadPortal) return id === 'dashboard'
    if (id === 'plans') return (user?.role?.hierarchy_level || 0) >= 90
    if (id === 'followups') return (user?.role?.hierarchy_level || 0) >= 30
    if (id === 'tasks') return roleLevel >= 30
    return id === 'pipeline' || id === 'reports' || id === 'settings' || available.has(id)
  })
  const records = isLeadPortal ? [] : recordItems.filter(([id]) => available.has(id))
  const items = [...coreItems.slice(0, 1), ...records, ...coreItems.slice(1)]
  return <main className="app-layout">
    <aside className="app-sidebar">
      <div className="brand">FIN<span>CRM</span></div>
      <p className="org-name">{user?.organization?.name || 'Finance CRM'}</p>
      {roleChoices.length > 1 && <label className="role-picker">Role<select value={user?.role?.code || ''} onChange={(event) => onRoleChange(event.target.value)}>
        {roleChoices.map((role) => <option key={role.code} value={role.code}>{role.name}</option>)}
      </select></label>}
      <nav aria-label="Main navigation" className="main-nav">
        {coreItems.slice(0, 1).map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => onNavigate(id)}>{label}</button>)}
        {records.length > 0 && <details className="records-nav" open>
          <summary>Records</summary>
          {records.map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => onNavigate(id)}>{label}</button>)}
        </details>}
        {coreItems.slice(1).map(([id, label]) => <button type="button" key={id} className={activeModule === id ? 'active' : ''} aria-current={activeModule === id ? 'page' : undefined} onClick={() => onNavigate(id)}>{label}</button>)}
      </nav>
      <div className="sidebar-bottom"><span>{user?.user?.username || user?.username || ''}</span><button type="button" onClick={onSignOut}>Sign out</button></div>
    </aside>
    <section className="app-content">
      {showDateFilter && <div className="global-date-filter"><label htmlFor="global-date-preset">Date range</label><select id="global-date-preset" value={dateRange?.preset || 'today'} onChange={(event) => onDateRangeChange(event.target.value)}>
        <option value="today">Today</option><option value="month">Month to date</option><option value="year">Year to date</option><option value="custom">Custom range</option>
      </select>
      {dateRange?.preset === 'custom' && <><label htmlFor="global-date-start">From</label><input id="global-date-start" type="date" value={dateRange.start_date} onChange={(event) => onDateRangeChange('custom', 'start_date', event.target.value)} /><label htmlFor="global-date-end">To</label><input id="global-date-end" type="date" value={dateRange.end_date} min={dateRange.start_date || undefined} onChange={(event) => onDateRangeChange('custom', 'end_date', event.target.value)} /></>}
      </div>}
      {children}
    </section>
  </main>
}
