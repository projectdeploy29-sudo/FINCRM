import { useEffect, useState } from 'react'
import { API_ROOT, readApiResponse } from '../api'
import './Login.css'

const number = (value) => value == null ? 'Negotiated' : Number(value).toLocaleString('en-IN')
const money = (value) => value == null ? 'Custom recurring contract' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Number(value))

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [page, setPage] = useState('plans')
  const [plans, setPlans] = useState([])
  const [plansLoading, setPlansLoading] = useState(true)
  const [plansError, setPlansError] = useState('')
  const [registration, setRegistration] = useState({ organization_name: '', username: '', email: '', password: '', first_name: '', last_name: '', org_email: '', org_phone: '' })

  useEffect(() => {
    let active = true
    fetch(`${API_ROOT}/subscriptions/plans/`)
      .then(async (response) => {
        const data = await readApiResponse(response)
        if (!response.ok) throw new Error(data.detail || `Could not load plans (${response.status}).`)
        return data
      })
      .then((data) => { if (active) setPlans(Array.isArray(data) ? data : data.results || []) })
      .catch((exception) => { if (active) setPlansError(exception.message) })
      .finally(() => { if (active) setPlansLoading(false) })
    return () => { active = false }
  }, [])

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

  function startRegistration() { setPage('login'); setRegistering(true); setError('') }

  return <main className="public-layout">
    <header className="public-header"><h1 className="brand">FIN<span>CRM</span></h1><nav aria-label="Public navigation"><button type="button" className={page === 'plans' ? 'active' : ''} onClick={() => { setPage('plans'); setRegistering(false); setError('') }}>Plans</button><button type="button" className={page === 'login' ? 'active' : ''} onClick={() => { setPage('login'); setRegistering(false); setError('') }}>Login</button></nav></header>

    {page === 'plans' ? <section className="public-plans">
      <p className="plans-intro">Choose a plan that fits your organization. Features and limits are managed for each organization.</p>
      {plansLoading && <p className="muted">Loading plans…</p>}
      {plansError && <p className="plans-error" role="alert">{plansError}</p>}
      {!plansLoading && !plansError && plans.length === 0 && <p className="muted">No active plans are available right now.</p>}
      {!plansLoading && !plansError && <div className="plan-grid">{plans.map((plan) => <article className={`plan-card ${plan.code === 'starter' ? 'popular' : ''}`} key={plan.id}>
        <div className="plan-title"><h2>{plan.name}</h2>{plan.code === 'starter' && <span>POPULAR</span>}</div>
        <p className="plan-description">{plan.description}</p>
        <div className="plan-price">{money(plan.monthly_price)}{plan.monthly_price != null && <small> / month</small>}</div>
        {plan.yearly_price != null && <p className="plan-billing">{money(plan.yearly_price)} billed yearly</p>}
        <ul>
          <li>{number(plan.max_employees)} Staff Accounts</li>
          <li>{number(plan.max_leads)} Leads</li>
          <li>{number(plan.daily_ai_tokens)} AI Tokens Per Day</li>
          {plan.features?.applications && <li>Applications</li>}
        </ul>
        <button type="button" className="plan-cta" onClick={startRegistration}>Get started <span aria-hidden="true">⟶</span></button>
      </article>)}</div>}
    </section> : <section className="public-auth">
      <h2>{registering ? 'Create your organization' : 'Sign in to your account'}</h2>
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
    </section>}
  </main>
}
