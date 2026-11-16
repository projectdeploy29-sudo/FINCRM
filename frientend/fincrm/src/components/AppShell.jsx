const FOLLOWUP_IDS = new Set(['customer-followups', 'lead-followups', 'application-followups'])
const TODAY_IDS = new Set(['today'])
const WORK_EXCLUDE = new Set(['dashboard', 'tasks', 'followups-today', ...FOLLOWUP_IDS, ...TODAY_IDS])

export default function AppShell({ user, modules, addActions = [], activeModule, onNavigate, onCreateModule, onRoleChange, onSignOut, children }) {
  const roleChoices = user?.available_roles || []
  const grouped = {
    Work: modules.filter((module) => !WORK_EXCLUDE.has(module.id)),
    Add: addActions,
    Dashboard: modules.filter((module) => module.id === 'dashboard'),
    Send: modules.filter((module) => module.id === 'tasks'),
    'Follow-up': modules.filter((module) => FOLLOWUP_IDS.has(module.id)),
    Today: modules.filter((module) => TODAY_IDS.has(module.id)),
  }
  return <main>
    <header>
      <h1>FinCRM</h1>
      <p>{user?.organization?.name || 'Finance CRM'} · {user?.role?.name || 'User'}</p>
      <p>{user?.username || user?.user?.username || ''}</p>
      {roleChoices.length > 1 && <label>Use role <select value={user?.role?.code || ''} onChange={(event) => onRoleChange(event.target.value)}>
        {roleChoices.map((role) => <option key={role.code} value={role.code}>{role.name}</option>)}
      </select></label>}
      <button type="button" onClick={onSignOut}>Sign out</button>
    </header>
    <nav aria-label="Main navigation">
      {Object.entries(grouped).filter(([, items]) => items.length).map(([label, items]) => <details key={label} open={label === 'Work' || label === 'Dashboard'}>
        <summary>{label}</summary>
        {label === 'Add' ? items.map(([id, title, staffType]) => <button type="button" key={`create-${id}-${staffType || ''}`} onClick={() => onCreateModule(id, staffType)}>{`Add ${title}`}</button>) : items.map((module) => <button type="button" key={module.id} aria-current={activeModule === module.id ? 'page' : undefined} onClick={() => onNavigate(module.id)}>{module.label}</button>)}
        {label === 'Send' && items.map((module) => <button type="button" key={`create-${module.id}`} onClick={() => onCreateModule(module.id)}>Create and assign task</button>)}
      </details>)}
    </nav>
    <section>{children}</section>
  </main>
}
