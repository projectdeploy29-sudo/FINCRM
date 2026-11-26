import { useCallback, useEffect, useState } from 'react'
import { API_ROOT, readApiResponse } from '../api'
import LandingPage from './LandingPage'
import PrivacyPolicy from './PrivacyPolicy'
import WebsiteIntro from './WebsiteIntro'
import BrandFooter from './BrandFooter'
import logoUrl from '../assets/logo.jpg'
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

const registrationFieldLabels = {
  organization_name: 'Organization name',
  username: 'Username',
  email: 'Email',
  password: 'Password',
  confirm_password: 'Confirm password',
  first_name: 'First name',
  last_name: 'Last name',
  org_email: 'Organization email',
  org_phone: 'Organization phone',
  registration_token: 'Registration link',
  non_field_errors: '',
}

function firstRegistrationError(data) {
  if (typeof data?.detail === 'string') return data.detail
  const [field, value] = Object.entries(data || {}).find(([key]) => key !== 'detail') || []
  if (!field) return 'Could not complete registration. Please check your details and try again.'
  const message = Array.isArray(value) ? value[0] : typeof value === 'string' ? value : ''
  if (!message) return 'Could not complete registration. Please check your details and try again.'
  const label = registrationFieldLabels[field] ?? field.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
  return label ? `${label}: ${message}` : message
}

export default function Login({ onLogin }) {
  const [registrationToken] = useState(() => new URLSearchParams(window.location.search).get('registration_token') || '')
  const resetParams = new URLSearchParams(window.location.search)
  const resetUid = resetParams.get('reset_uid') || ''
  const resetToken = resetParams.get('reset_token') || ''
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [registering, setRegistering] = useState(Boolean(registrationToken))
  const [page, setPage] = useState(registrationToken || (resetUid && resetToken) ? 'login' : 'home')
  const [websiteIntroVisible, setWebsiteIntroVisible] = useState(() => {
    if (registrationToken || (resetUid && resetToken)) return false
    try { return window.sessionStorage.getItem('auron_website_intro_seen') !== 'true' } catch { return false }
  })
  const [darkTheme, setDarkTheme] = useState(() => localStorage.getItem('auron_public_theme') === 'dark')
  const [pendingPublicScroll, setPendingPublicScroll] = useState('')
  const [registration, setRegistration] = useState(() => ({ ...emptyRegistration, registration_token: registrationToken }))
  const [invitationDetails, setInvitationDetails] = useState(null)
  const [forgotOpen, setForgotOpen] = useState(false)
  const [resetEmail, setResetEmail] = useState('')
  const [resetUsername, setResetUsername] = useState('')
  const [resetPassword, setResetPassword] = useState('')
  const [resetMessage, setResetMessage] = useState('')
  const [resetWait, setResetWait] = useState('')

  useEffect(() => {
    localStorage.setItem('auron_public_theme', darkTheme ? 'dark' : 'light')
  }, [darkTheme])

  const finishWebsiteIntro = useCallback(() => {
    try { window.sessionStorage.setItem('auron_website_intro_seen', 'true') } catch { /* Intro still completes if storage is unavailable. */ }
    setWebsiteIntroVisible(false)
  }, [])

  useEffect(() => {
    if (!pendingPublicScroll) return undefined
    const frame = window.requestAnimationFrame(() => {
      if (pendingPublicScroll === 'plans') document.getElementById('plans')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      else window.scrollTo({ top: 0, behavior: 'smooth' })
      setPendingPublicScroll('')
    })
    return () => window.cancelAnimationFrame(frame)
  }, [page, pendingPublicScroll])

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
      if (!response.ok) throw new Error(firstRegistrationError(data))
      const session = { access: data.tokens.access, refresh: data.tokens.refresh, user: data.user, organization: data.organization, role: { code: 'org_admin', name: 'Organization Admin', hierarchy_level: 90 }, permissions: ['*'] }
      localStorage.setItem('fincrm_access', session.access)
      localStorage.setItem('fincrm_refresh', session.refresh)
      window.history.replaceState({}, '', window.location.pathname)
      onLogin(session)
    } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }

  async function requestReset(event) {
    event.preventDefault(); setBusy(true); setResetWait(''); setResetMessage('')
    try {
      const response = await fetch(`${API_ROOT}/auth/forgot-password/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: resetUsername.trim(), email: resetEmail.trim() }) })
      const data = await readApiResponse(response)
      if (response.status === 429) {
        const hours = Math.floor(data.retry_after_seconds / 3600)
        const minutes = Math.ceil((data.retry_after_seconds % 3600) / 60)
        setResetWait(`You can request another link in ${hours}h ${minutes}m.`)
      } else if (!response.ok) throw new Error(data.detail || 'Could not request a reset link.')
      else setResetMessage(data.detail)
    } catch (exception) { setResetWait(exception.message) } finally { setBusy(false) }
  }

  async function submitReset(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = await fetch(`${API_ROOT}/auth/reset-password/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uid: resetUid, token: resetToken, password: resetPassword }) })
      const data = await readApiResponse(response)
      if (!response.ok) throw new Error(data.detail || data.password?.[0] || 'This reset link is invalid or expired.')
      setError(''); setResetMessage('Password reset successfully. Redirecting to login…')
      window.history.replaceState({}, '', window.location.pathname)
      setTimeout(() => { window.location.reload() }, 1200)
    } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }

  function changeRegistration(key, value) {
    setError('')
    setRegistration((current) => ({ ...current, [key]: value }))
  }
  function navigatePublicPage(nextPage) {
    setPage(nextPage)
    setRegistering(false)
    setError('')
    setPendingPublicScroll(nextPage === 'plans' ? 'plans' : 'top')
  }

  return <main className={`public-layout${darkTheme ? ' theme-dark' : ''}`}>
    <header className="public-header"><button type="button" className="public-brand" onClick={() => { if (registrationToken) { setPage('login'); setError(''); return } navigatePublicPage('home') }} aria-label="Auron FIN CRM home">
      <img src={logoUrl} alt="" /><span><strong>AURON</strong> FIN CRM</span>
    </button>
      {registrationToken ? <p className="registration-link-label">Complete your registration</p> : <nav aria-label="Public navigation">
        <button type="button" className={`public-nav-home${page === 'home' ? ' active' : ''}`} aria-current={page === 'home' ? 'page' : undefined} onClick={() => navigatePublicPage('home')}>Home</button>
        <button type="button" className={`public-nav-plans${page === 'plans' ? ' active' : ''}`} aria-current={page === 'plans' ? 'page' : undefined} onClick={() => navigatePublicPage('plans')}>Plans</button>
        <button type="button" className={`public-login-link${page === 'login' ? ' active' : ''}`} aria-label="Sign in" title="Sign in" onClick={() => navigatePublicPage('login')}><span className="public-avatar-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3.5" /><path d="M4.5 20a7.5 7.5 0 0 1 15 0" /></svg></span></button>
        <button type="button" className="public-theme-toggle" aria-label={darkTheme ? 'Switch to light theme' : 'Switch to dark theme'} aria-pressed={darkTheme} title={darkTheme ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => setDarkTheme((current) => !current)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none">{darkTheme ? <><circle cx="12" cy="12" r="3.5" /><path d="M12 2.5v2M12 19.5v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2.5 12h2m15 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></> : <path d="M20.2 15.4A8.5 8.5 0 0 1 8.6 3.8 8.7 8.7 0 1 0 20.2 15.4Z" />}</svg></button>
      </nav>}
    </header>

    {resetUid && resetToken ? <section className="public-auth"><h2>Reset password</h2><form onSubmit={submitReset}><p><label>New password<input type="password" autoComplete="new-password" minLength="8" required value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} /></label></p><button type="submit" disabled={busy}>{busy ? 'Resetting…' : 'Set new password'}</button></form>{error && <p role="alert">{error}</p>}{resetMessage && <p role="status">{resetMessage}</p>}</section> : page === 'home' || page === 'plans' ? <LandingPage onNavigate={navigatePublicPage} /> : page === 'privacy-policy' ? <PrivacyPolicy onNavigate={navigatePublicPage} /> : <section className="public-auth">
      <h2>{registering ? 'Complete your organization registration' : 'Sign in to your account'}</h2>
      {!registering ? <form onSubmit={submit}>
        <p><label>Username <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label></p>
        <p><label>Password <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label></p>
        <button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <button type="button" className="forgot-password-link" onClick={() => { setForgotOpen(true); setResetMessage(''); setResetWait('') }}>Forgot Password?</button>
      </form> : <form onSubmit={register}><h3>Enter your organization and admin account details</h3>
        {[['organization_name', 'Organization name'], ['username', 'Admin username'], ['email', 'Payment email'], ['password', 'Admin password'], ['confirm_password', 'Confirm password'], ['first_name', 'First name'], ['last_name', 'Last name'], ['org_email', 'Organization email'], ['org_phone', 'Organization phone']].map(([key, label]) => <p key={key}><label>{label} <input autoComplete={key === 'email' ? 'email' : undefined} type={key.includes('email') ? 'email' : key.includes('password') ? 'password' : 'text'} value={registration[key]} onChange={(event) => changeRegistration(key, event.target.value)} readOnly={key === 'email' || (key === 'organization_name' && invitationDetails?.enterprise)} required={['organization_name', 'username', 'email', 'password', 'confirm_password'].includes(key)} /></label></p>)}
        <button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create organization'}</button>
      </form>}
      {error && <p role="alert">{error}</p>}
      {forgotOpen && <div className="reset-confirm-backdrop"><section className="reset-confirm" role="dialog" aria-modal="true" aria-labelledby="reset-confirm-title"><h3 id="reset-confirm-title">Request a password reset?</h3><p>Enter the username and email on the same active account. We’ll send a secure link only when both match. Each link is valid for 12 hours, and you can request another after the 12-hour wait.</p><form onSubmit={requestReset}><label>Username<input autoComplete="username" required value={resetUsername} onChange={(event) => setResetUsername(event.target.value)} /></label><label>Registered email<input type="email" autoComplete="email" required value={resetEmail} onChange={(event) => setResetEmail(event.target.value)} /></label><div className="reset-confirm-actions"><button type="button" onClick={() => setForgotOpen(false)}>Cancel</button><button type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button></div></form>{resetMessage && <p role="status">{resetMessage}</p>}{resetWait && <p role="alert">{resetWait}</p>}</section></div>}
    </section>}
    {(page === 'login' || page === 'privacy-policy' || (resetUid && resetToken)) && <BrandFooter className="public-brand-footer" />}
    {websiteIntroVisible && page === 'home' && <WebsiteIntro onComplete={finishWebsiteIntro} />}
  </main>
}
