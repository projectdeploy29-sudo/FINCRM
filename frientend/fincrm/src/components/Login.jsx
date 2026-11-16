import { useState } from 'react'
import { API_ROOT, readApiResponse } from '../api'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [page, setPage] = useState('work')
  const [registration, setRegistration] = useState({ organization_name: '', username: '', email: '', password: '', first_name: '', last_name: '', org_email: '', org_phone: '' })

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = await fetch(`${API_ROOT}/auth/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })
      const data = await readApiResponse(response)
      if (!response.ok) throw new Error(data.detail || 'Could not sign in. Check your credentials.')
      localStorage.setItem('fincrm_access', data.access)
      localStorage.setItem('fincrm_refresh', data.refresh)
      onLogin(data)
    } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }
  async function register(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = await fetch(`${API_ROOT}/organizations/register/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(registration) })
      const data = await readApiResponse(response)
      if (!response.ok) throw new Error(JSON.stringify(data))
      const session = { access: data.tokens.access, refresh: data.tokens.refresh, user: data.user, organization: data.organization, role: { code: 'org_admin', name: 'Organization Admin', hierarchy_level: 90 }, permissions: ['*'] }
      localStorage.setItem('fincrm_access', session.access); localStorage.setItem('fincrm_refresh', session.refresh); onLogin(session)
    } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }
  return <main>
    <header><h1>FinCRM</h1><nav aria-label="Public navigation"><button type="button" onClick={() => setPage('work')}>Work</button><button type="button" onClick={() => setPage('login')}>Login</button></nav></header>
    {page==='work' ? <section><h2>Finance CRM work platform</h2><p>Manage your organization, teams, leads, customers, applications, documents, tasks, follow-ups, and payments in one place.</p><p>Staff use their organization account. Leads can sign in to view their own lead record after the organization creates a lead portal login.</p><button type="button" onClick={() => setPage('login')}>Log in</button></section> : <><h2>Sign in to your account</h2>
    <p><button type="button" onClick={() => { setRegistering(false); setError('') }}>Sign in</button><button type="button" onClick={() => { setRegistering(true); setError('') }}>Register organization</button></p>
    {!registering ? <form onSubmit={submit}>
      <p><label>Username <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label></p>
      <p><label>Password <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label></p>
      <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form> : <form onSubmit={register}><h3>Create an organization and admin account</h3>
      {[['organization_name', 'Organization name'], ['username', 'Admin username'], ['email', 'Admin email'], ['password', 'Admin password'], ['first_name', 'First name'], ['last_name', 'Last name'], ['org_email', 'Organization email'], ['org_phone', 'Organization phone']].map(([key, label]) => <p key={key}><label>{label} <input type={key.includes('email') ? 'email' : key === 'password' ? 'password' : 'text'} value={registration[key]} onChange={(event) => setRegistration({ ...registration, [key]: event.target.value })} required={['organization_name', 'username', 'email', 'password'].includes(key)} /></label></p>)}
      <button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create organization'}</button>
    </form>}
    {error && <p role="alert">{error}</p>}
    </>}
  </main>
}
