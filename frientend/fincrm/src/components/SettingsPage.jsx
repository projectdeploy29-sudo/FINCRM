import { useEffect, useState } from 'react'

export default function SettingsPage({ api, user, onProfileUpdated, onNavigate }) {
  const [profile, setProfile] = useState({ first_name: user?.first_name || '', last_name: user?.last_name || '', email: user?.email || '' })
  const [password, setPassword] = useState({ old_password: '', new_password: '' })
  const [resetOpen, setResetOpen] = useState(false)
  const [resetEmail, setResetEmail] = useState(user?.email || '')
  const [resetFeedback, setResetFeedback] = useState('')
  const [resetFeedbackRole, setResetFeedbackRole] = useState('status')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [subscription, setSubscription] = useState(null)
  const [subscriptionError, setSubscriptionError] = useState('')
  const [organization, setOrganization] = useState(null)
  const [organizationError, setOrganizationError] = useState('')
  const isOrgAdmin = (user?.role?.hierarchy_level || 0) >= 90
  const isLeadPortal = user?.role?.code === 'lead_portal'
  useEffect(() => {
    if (isOrgAdmin) {
      api.get('/subscriptions/current/').then(setSubscription).catch((exception) => setSubscriptionError(exception.message))
    }
    if (!isLeadPortal) {
      api.get('/organizations/current/')
        .then(setOrganization)
        .catch((exception) => setOrganizationError(exception.message))
    }
  }, [api, isOrgAdmin, isLeadPortal])
  async function saveProfile(event) {
    event.preventDefault(); setError(''); setMessage('')
    try { const result = await api.patch('/auth/me/', profile); onProfileUpdated(result); setMessage('Profile saved.') } catch (exception) { setError(exception.message) }
  }
  async function savePassword(event) {
    event.preventDefault(); setError(''); setMessage('')
    try { await api.post('/auth/change-password/', password); setPassword({ old_password: '', new_password: '' }); setMessage('Password updated.') } catch (exception) { setError(exception.message) }
  }
  async function sendResetLink(event) {
    event.preventDefault(); setResetFeedback(''); setResetFeedbackRole('status')
    try {
      const result = await api.post('/auth/forgot-password/', { email: resetEmail.trim() })
      setResetFeedback(result.detail || 'If this email is registered, a reset link will be sent.')
    } catch (exception) {
      const seconds = exception.data?.retry_after_seconds
      if (seconds) setResetFeedback(`A reset link was already requested. You can request another in ${Math.floor(seconds / 3600)}h ${Math.ceil((seconds % 3600) / 60)}m.`)
      else setResetFeedback(exception.message)
      setResetFeedbackRole('alert')
    }
  }
  const plan = subscription?.plan_details
  const money = (value) => value === null || value === undefined ? 'Negotiated' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: user?.organization?.currency || 'INR', maximumFractionDigits: 0 }).format(Number(value))
  return <section className="page"><h2>Settings</h2><p>Update your personal profile and password.</p>{error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {isOrgAdmin && <section className="subscription-card"><div><p className="eyebrow">Organization plan</p><h3>{subscription?.has_active_subscription ? plan?.name || 'Current plan' : 'No active subscription'}</h3><p>{subscription?.has_active_subscription ? `${subscription.status} · ${subscription.billing_cycle?.toLowerCase()} billing` : 'Choose a plan to activate organization limits and features.'}</p></div>
      {subscriptionError && <p role="alert">{subscriptionError}</p>}
      {subscription?.has_active_subscription && <><div className="subscription-facts"><div><span>Subscription reference</span><b>{subscription.Subscriptioncode}</b></div><div><span>Price</span><b>{plan?.checkout_enabled ? `${money(subscription.billing_cycle === 'YEARLY' ? plan?.yearly_price : plan?.monthly_price)} / ${subscription.billing_cycle === 'YEARLY' ? 'year' : 'month'}` : 'Pricing pending confirmation'}</b></div><div><span>Started</span><b>{subscription.start_date ? new Date(subscription.start_date).toLocaleDateString() : '—'}</b></div><div><span>Renewal date</span><b>{subscription.next_billing_date ? new Date(`${subscription.next_billing_date}T00:00:00`).toLocaleDateString() : 'Not scheduled'}</b></div><div><span>Days remaining</span><b>{subscription.days_remaining ?? '—'}</b></div><div><span>Staff</span><b>{subscription.usage?.staff_count ?? 0} / {subscription.usage?.max_staff_allowed ?? 'Negotiated'}</b></div><div><span>Leads</span><b>{subscription.usage?.leads_count ?? 0} / {subscription.usage?.max_leads_allowed ?? 'Negotiated'}</b></div></div></>}
      <button type="button" onClick={() => onNavigate('plans')}>{subscription?.has_active_subscription ? 'Renew or change plan' : 'View plans'}</button>
    </section>}
    <div className="settings-grid">
      <div className="settings-account-column">
        <form className="settings-form" onSubmit={saveProfile}><h3>Profile</h3><label>First name<input value={profile.first_name} onChange={(event) => setProfile({ ...profile, first_name: event.target.value })} /></label><label>Last name<input value={profile.last_name} onChange={(event) => setProfile({ ...profile, last_name: event.target.value })} /></label><label>Email<input type="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} /></label><button type="submit">Save profile</button></form>
        <form className="settings-form" onSubmit={savePassword}><h3>Change password</h3><label>Current password<input type="password" autoComplete="current-password" required value={password.old_password} onChange={(event) => setPassword({ ...password, old_password: event.target.value })} /></label><label>New password<input type="password" autoComplete="new-password" minLength="6" required value={password.new_password} onChange={(event) => setPassword({ ...password, new_password: event.target.value })} /></label><button type="submit">Update password</button><button type="button" onClick={() => { setResetEmail(user?.email || ''); setResetFeedback(''); setResetFeedbackRole('status'); setResetOpen(true) }}>Forgot your current password?</button></form>
      </div>
      {!isLeadPortal && <section className="organization-details-card">
        <div className="organization-details-header">
          <div className="organization-details-logo">{(organization?.name || user?.organization?.name || 'O').slice(0, 1).toUpperCase()}</div>
          <div><p>Organization information</p><h3>{organization?.name || user?.organization?.name || 'Organization'}</h3></div>
          <span className={`organization-status ${organization?.is_active === false ? 'inactive' : 'active'}`}>{organization?.is_active === false ? 'Inactive' : 'Active'}</span>
        </div>
        {organizationError && <p role="alert">{organizationError}</p>}
        {!organization && !organizationError && <p className="muted">Loading organization details…</p>}
        {organization && <>
          <dl className="organization-details-grid">
            <div><dt>Organization name</dt><dd>{organization.name || '—'}</dd></div>
            <div><dt>Legal name</dt><dd>{organization.legal_name || '—'}</dd></div>
            <div><dt>Organization email</dt><dd>{organization.email || '—'}</dd></div>
            <div><dt>Phone</dt><dd>{organization.phone || '—'}</dd></div>
            <div><dt>Website</dt><dd>{organization.website ? <a href={organization.website} target="_blank" rel="noreferrer">{organization.website}</a> : '—'}</dd></div>
            <div><dt>Timezone</dt><dd>{organization.timezone || '—'}</dd></div>
            <div><dt>Currency</dt><dd>{organization.currency || '—'}</dd></div>
            <div><dt>Country</dt><dd>{organization.country || '—'}</dd></div>
            <div className="organization-address"><dt>Address</dt><dd>{[organization.address_line1, organization.address_line2, organization.city, organization.state, organization.pin_code, organization.country].filter(Boolean).join(', ') || '—'}</dd></div>
            <div><dt>Organization ID</dt><dd className="organization-id">{organization.id || '—'}</dd></div>
            <div><dt>Created</dt><dd>{organization.created_at ? new Date(organization.created_at).toLocaleString() : '—'}</dd></div>
            <div><dt>Last updated</dt><dd>{organization.updated_at ? new Date(organization.updated_at).toLocaleString() : '—'}</dd></div>
          </dl>
          <p className="organization-readonly-note">Organization details are managed by the organization administrator.</p>
        </>}
      </section>}
    </div>
    {resetOpen && <div className="reset-confirm-backdrop"><section className="reset-confirm" role="dialog" aria-modal="true" aria-labelledby="settings-reset-title"><h3 id="settings-reset-title">Reset password by email?</h3><p>We’ll verify that this email belongs to an active account and matches your signed-in account before sending a reset link. The link is valid for 12 hours.</p><form onSubmit={sendResetLink}><label>Email for your signed-in account<input type="email" autoComplete="email" required value={resetEmail} onChange={(event) => setResetEmail(event.target.value)} /></label><div className="reset-confirm-actions"><button type="button" onClick={() => setResetOpen(false)}>Cancel</button><button type="submit">Send reset link</button></div></form>{resetFeedback && <p role={resetFeedbackRole}>{resetFeedback}</p>}</section></div>}
  </section>
}
