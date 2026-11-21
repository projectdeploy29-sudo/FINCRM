import { useEffect, useState } from 'react'

export default function SettingsPage({ api, user, onProfileUpdated, onNavigate }) {
  const [profile, setProfile] = useState({ first_name: user?.first_name || '', last_name: user?.last_name || '', email: user?.email || '' })
  const [password, setPassword] = useState({ old_password: '', new_password: '' })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [subscription, setSubscription] = useState(null)
  const [subscriptionError, setSubscriptionError] = useState('')
  const isOrgAdmin = (user?.role?.hierarchy_level || 0) >= 90
  useEffect(() => {
    if (!isOrgAdmin) return
    api.get('/subscriptions/current/').then(setSubscription).catch((exception) => setSubscriptionError(exception.message))
  }, [api, isOrgAdmin])
  async function saveProfile(event) {
    event.preventDefault(); setError(''); setMessage('')
    try { const result = await api.patch('/auth/me/', profile); onProfileUpdated(result); setMessage('Profile saved.') } catch (exception) { setError(exception.message) }
  }
  async function savePassword(event) {
    event.preventDefault(); setError(''); setMessage('')
    try { await api.post('/auth/change-password/', password); setPassword({ old_password: '', new_password: '' }); setMessage('Password updated.') } catch (exception) { setError(exception.message) }
  }
  const plan = subscription?.plan_details
  const money = (value) => value === null || value === undefined ? 'Negotiated' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: user?.organization?.currency || 'INR', maximumFractionDigits: 0 }).format(Number(value))
  return <section className="page"><h2>Settings</h2><p>Update your personal profile and password.</p>{error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {isOrgAdmin && <section className="subscription-card"><div><p className="eyebrow">Organization plan</p><h3>{subscription?.has_active_subscription ? plan?.name || 'Current plan' : 'No active subscription'}</h3><p>{subscription?.has_active_subscription ? `${subscription.status} · ${subscription.billing_cycle?.toLowerCase()} billing` : 'Choose a plan to activate organization limits and features.'}</p></div>
      {subscriptionError && <p role="alert">{subscriptionError}</p>}
      {subscription?.has_active_subscription && <><div className="subscription-facts"><div><span>Subscription reference</span><b>{subscription.Subscriptioncode}</b></div><div><span>Price</span><b>{money(subscription.billing_cycle === 'YEARLY' ? plan?.yearly_price : plan?.monthly_price)} / {subscription.billing_cycle === 'YEARLY' ? 'year' : 'month'}</b></div><div><span>Started</span><b>{subscription.start_date ? new Date(subscription.start_date).toLocaleDateString() : '—'}</b></div><div><span>Renewal date</span><b>{subscription.next_billing_date ? new Date(`${subscription.next_billing_date}T00:00:00`).toLocaleDateString() : 'Not scheduled'}</b></div><div><span>Days remaining</span><b>{subscription.days_remaining ?? '—'}</b></div><div><span>Staff</span><b>{subscription.usage?.staff_count ?? 0} / {subscription.usage?.max_staff_allowed ?? 'Negotiated'}</b></div><div><span>Leads</span><b>{subscription.usage?.leads_count ?? 0} / {subscription.usage?.max_leads_allowed ?? 'Negotiated'}</b></div></div></>}
      <button type="button" onClick={() => onNavigate('plans')}>{subscription?.has_active_subscription ? 'Renew or change plan' : 'View plans'}</button>
    </section>}
    <form className="settings-form" onSubmit={saveProfile}><h3>Profile</h3><label>First name<input value={profile.first_name} onChange={(event) => setProfile({ ...profile, first_name: event.target.value })} /></label><label>Last name<input value={profile.last_name} onChange={(event) => setProfile({ ...profile, last_name: event.target.value })} /></label><label>Email<input type="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} /></label><button type="submit">Save profile</button></form>
    <form className="settings-form" onSubmit={savePassword}><h3>Change password</h3><label>Current password<input type="password" autoComplete="current-password" required value={password.old_password} onChange={(event) => setPassword({ ...password, old_password: event.target.value })} /></label><label>New password<input type="password" autoComplete="new-password" minLength="6" required value={password.new_password} onChange={(event) => setPassword({ ...password, new_password: event.target.value })} /></label><button type="submit">Update password</button></form>
  </section>
}
