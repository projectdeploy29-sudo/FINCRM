import { useEffect, useState } from 'react'
import { API_ROOT, readApiResponse } from '../api'
import PlanCatalog from './PlanCatalog'
import './Login.css'

const emptyRegistration = {
  registration_token: '',
  organization_name: '',
  username: '',
  email: '',
  password: '',
  confirm_password: '',
  first_name: '',
  last_name: '',
  org_email: '',
  org_phone: '',
}

export default function Login({ onLogin }) {
  const [registrationToken] = useState(() => new URLSearchParams(window.location.search).get('registration_token') || '')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [registering, setRegistering] = useState(Boolean(registrationToken))
  const [page, setPage] = useState(registrationToken ? 'login' : 'plans')
  const [registration, setRegistration] = useState(() => ({ ...emptyRegistration, registration_token: registrationToken }))
  const [invitationDetails, setInvitationDetails] = useState(null)

  useEffect(() => {
    if (!registrationToken) return
    fetch(`${API_ROOT}/subscriptions/registration-details/?token=${encodeURIComponent(registrationToken)}`)
      .then(async (response) => {
        const data = await readApiResponse(response)
        if (!response.ok) throw new Error(data.detail || 'This registration link is invalid or expired.')
        return data
      })
      .then((data) => {
        setInvitationDetails(data)
        setRegistration((current) => ({
          ...current,
          email: data.email || current.email,
          organization_name: data.organization_name || current.organization_name,
          first_name: data.first_name || current.first_name,
          last_name: data.last_name || current.last_name,
        }))
      })
      .catch((exception) => setError(exception.message))
  }, [registrationToken])

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
      if (registration.password !== registration.confirm_password) throw new Error('Passwords do not match.')
      const response = await fetch(`${API_ROOT}/organizations/register/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(registration) })
      const data = await readApiResponse(response)
      if (!response.ok) throw new Error(JSON.stringify(data))
      const session = { access: data.tokens.access, refresh: data.tokens.refresh, user: data.user, organization: data.organization, role: { code: 'org_admin', name: 'Organization Admin', hierarchy_level: 90 }, permissions: ['*'] }
      localStorage.setItem('fincrm_access', session.access)
      localStorage.setItem('fincrm_refresh', session.refresh)
      window.history.replaceState({}, '', window.location.pathname)
      onLogin(session)
    } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }

  function changeRegistration(key, value) {
    setRegistration((current) => ({ ...current, [key]: value }))
  }

  return <main className="public-layout">
    <header className="public-header"><h1 className="brand">FIN<span>CRM</span></h1>
      {registrationToken ? <p className="registration-link-label">Complete your registration</p> : <nav aria-label="Public navigation">
        <button type="button" className={page === 'plans' ? 'active' : ''} onClick={() => { setPage('plans'); setRegistering(false); setError('') }}>Plans</button>
        <button type="button" className={page === 'login' ? 'active' : ''} onClick={() => { setPage('login'); setRegistering(false); setError('') }}>Login</button>
      </nav>}
    </header>

    {page === 'plans' ? <PlanCatalog /> : <section className="public-auth">
      <h2>{registering ? 'Complete your organization registration' : 'Sign in to your account'}</h2>
      {!registering ? <form onSubmit={submit}>
        <p><label>Username <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label></p>
        <p><label>Password <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label></p>
        <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form> : <form onSubmit={register}><h3>Enter your organization and admin account details</h3>
        {[['organization_name', 'Organization name'], ['username', 'Admin username'], ['email', 'Payment email'], ['password', 'Admin password'], ['confirm_password', 'Confirm password'], ['first_name', 'First name'], ['last_name', 'Last name'], ['org_email', 'Organization email'], ['org_phone', 'Organization phone']].map(([key, label]) => <p key={key}><label>{label} <input autoComplete={key === 'email' ? 'email' : undefined} type={key.includes('email') ? 'email' : key.includes('password') ? 'password' : 'text'} value={registration[key]} onChange={(event) => changeRegistration(key, event.target.value)} readOnly={key === 'email' || (key === 'organization_name' && invitationDetails?.enterprise)} required={['organization_name', 'username', 'email', 'password', 'confirm_password'].includes(key)} /></label></p>)}
        <button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create organization'}</button>
      </form>}
      {error && <p role="alert">{error}</p>}
    </section>}
  </main>
}
