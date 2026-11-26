import { useCallback, useEffect, useState } from 'react'
import LoadingSkeleton from './LoadingSkeleton'
import './SubscriptionPlanManagementPage.css'

const emptyPlan = {
  name: '', code: '', description: '', currency: 'INR', monthly_price: '', yearly_price: '',
  prices_confirmed: false, max_employees: '', max_leads: '', daily_ai_tokens: '',
  features: '{}', storage_limit_mb: '', included_services: '', additional_services: '',
  terms_conditions: '', is_active: true,
}

function planToForm(plan) {
  return {
    ...plan,
    monthly_price: plan.monthly_price ?? '', yearly_price: plan.yearly_price ?? '',
    max_employees: plan.max_employees ?? '', max_leads: plan.max_leads ?? '',
    daily_ai_tokens: plan.daily_ai_tokens ?? '', storage_limit_mb: plan.storage_limit_mb ?? '',
    features: JSON.stringify(plan.features || {}, null, 2),
    included_services: (plan.included_services || []).join('\n'),
  }
}

function optionalNumber(value) { return value === '' ? null : Number(value) }
async function fetchPlanAdminData(api) {
  const [planRows, checkoutState] = await Promise.all([
    api.get('/subscriptions/manage/plans/'),
    api.get('/subscriptions/manage/checkout-settings/'),
  ])
  return { plans: Array.isArray(planRows) ? planRows : planRows.results || [], checkout: checkoutState }
}

export default function SubscriptionPlanManagementPage({ api }) {
  const [plans, setPlans] = useState([])
  const [checkout, setCheckout] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(emptyPlan)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const result = await fetchPlanAdminData(api)
      setPlans(result.plans)
      setCheckout(result.checkout)
    } catch (exception) { setError(exception.message) }
    finally { setLoading(false) }
  }, [api])

  useEffect(() => {
    let active = true
    fetchPlanAdminData(api).then((result) => {
      if (active) { setPlans(result.plans); setCheckout(result.checkout) }
    }).catch((exception) => { if (active) setError(exception.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [api])

  function startCreate() { setEditing(null); setForm(emptyPlan); setError(''); setMessage('') }
  function startEdit(plan) { setEditing(plan); setForm(planToForm(plan)); setError(''); setMessage('') }
  function change(field, value) { setForm((current) => ({ ...current, [field]: value })) }

  async function save(event) {
    event.preventDefault()
    setSaving(true); setError(''); setMessage('')
    let features
    try { features = JSON.parse(form.features || '{}') }
    catch { setError('Features must be valid JSON.'); setSaving(false); return }
    const body = {
      ...form,
      monthly_price: optionalNumber(form.monthly_price), yearly_price: optionalNumber(form.yearly_price),
      max_employees: optionalNumber(form.max_employees), max_leads: optionalNumber(form.max_leads),
      daily_ai_tokens: optionalNumber(form.daily_ai_tokens), storage_limit_mb: optionalNumber(form.storage_limit_mb),
      features,
      included_services: form.included_services.split('\n').map((item) => item.trim()).filter(Boolean),
    }
    if (editing) delete body.code
    try {
      if (editing) await api.patch(`/subscriptions/manage/plans/${editing.id}/`, body)
      else await api.post('/subscriptions/manage/plans/', body)
      setMessage(editing ? 'Plan updated.' : 'Plan created and added to the catalog.')
      setEditing(null); setForm(emptyPlan)
      await reload()
    } catch (exception) { setError(exception.message) }
    finally { setSaving(false) }
  }

  async function setCheckoutEnabled(enabled) {
    setError(''); setMessage('')
    if (enabled && !window.confirm('This enables paid checkout for every active plan marked with confirmed prices. Continue?')) return
    try {
      await api.patch('/subscriptions/manage/checkout-settings/', { checkout_enabled: enabled })
      await reload()
      setMessage(enabled ? 'Paid checkout is enabled.' : 'Paid checkout is disabled.')
    } catch (exception) { setError(exception.message); await reload() }
  }

  async function setPlanActive(plan, isActive) {
    try { await api.patch(`/subscriptions/manage/plans/${plan.id}/`, { is_active: isActive }); await reload() }
    catch (exception) { setError(exception.message) }
  }

  return <section className="page plan-admin-page">
    <header className="plan-admin-heading"><div><h2>Edit plans</h2><p>Manage the public plan catalog and control when paid checkout is available.</p></div><button className="primary" type="button" onClick={startCreate}>Add a plan</button></header>
    {error && <div role="alert">{error}</div>}{message && <div role="status">{message}</div>}
    <section className={`checkout-control ${checkout?.checkout_enabled ? 'is-enabled' : ''}`}>
      <div><span className="eyebrow">Paid checkout</span><h3>{checkout?.checkout_enabled ? 'Enabled' : 'Disabled'}</h3><p>{checkout?.checkout_enabled ? 'Customers can purchase active plans with confirmed prices.' : 'Customers can view plans, but cannot start a paid checkout.'}</p></div>
      <button type="button" className={checkout?.checkout_enabled ? 'danger' : 'primary'} disabled={loading || (!checkout?.checkout_enabled && !checkout?.can_enable)} onClick={() => setCheckoutEnabled(!checkout?.checkout_enabled)}>{checkout?.checkout_enabled ? 'Disable checkout' : 'Enable checkout'}</button>
      {!checkout?.checkout_enabled && checkout?.unconfirmed_plans?.length > 0 && <div className="checkout-blockers"><strong>Confirm prices before enabling:</strong><ul>{checkout.unconfirmed_plans.map((plan) => <li key={plan.id}>{plan.name} ({plan.code})</li>)}</ul></div>}
    </section>

    <section className="plan-admin-section"><div className="plan-admin-section-title"><div><h3>Public plans</h3><p>Changes are reflected on the customer pricing page.</p></div></div>
      {loading ? <LoadingSkeleton variant="cards" metricCount={3} panelCount={0} label="Loading plans" /> : plans.length === 0 ? <p className="empty-state">No plans found.</p> : <div className="plan-admin-list">{plans.map((plan) => <article className="plan-admin-card" key={plan.id}>
        <div className="plan-admin-card-main"><div><h4>{plan.name} <span className={`plan-state ${plan.is_active ? 'active' : ''}`}>{plan.is_active ? 'Active' : 'Inactive'}</span></h4><p>{plan.description || plan.code}</p></div><div className="plan-price-pair"><span>Monthly<strong>{plan.monthly_price ? `₹${Number(plan.monthly_price).toLocaleString('en-IN')}` : '—'}</strong></span><span>Yearly<strong>{plan.yearly_price ? `₹${Number(plan.yearly_price).toLocaleString('en-IN')}` : '—'}</strong></span></div></div>
        <div className="plan-admin-meta"><span>Code: <b>{plan.code}</b></span><span>Price confirmation: <b>{plan.prices_confirmed ? 'Confirmed' : 'Not confirmed'}</b></span><span>Employees: <b>{plan.max_employees ?? 'Custom'}</b></span><span>Leads: <b>{plan.max_leads ?? 'Custom'}</b></span></div>
        <div className="plan-admin-actions"><button type="button" onClick={() => startEdit(plan)}>Edit plan</button><button type="button" onClick={() => setPlanActive(plan, !plan.is_active)}>{plan.is_active ? 'Deactivate' : 'Activate'}</button></div>
      </article>)}</div>}
    </section>

    {(editing || form !== emptyPlan) && <section className="plan-editor"><div className="plan-editor-title"><div><h3>{editing ? `Edit ${editing.name}` : 'Create a plan'}</h3><p>Prices remain unavailable to customers until checkout is enabled and the prices are confirmed.</p></div><button type="button" onClick={() => { setEditing(null); setForm(emptyPlan) }}>Close</button></div>
      <form onSubmit={save}>
        <div className="plan-form-grid">
          <label>Plan name<input required maxLength="100" value={form.name} onChange={(event) => change('name', event.target.value)} /></label>
          <label>Plan code<input required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" title="Lowercase letters, numbers, and hyphens" disabled={Boolean(editing)} value={form.code} onChange={(event) => change('code', event.target.value)} /></label>
          <label>Monthly price (INR)<input type="number" min="0" step="0.01" value={form.monthly_price} onChange={(event) => change('monthly_price', event.target.value)} /></label>
          <label>Yearly price (INR)<input type="number" min="0" step="0.01" value={form.yearly_price} onChange={(event) => change('yearly_price', event.target.value)} /></label>
          <label>Maximum employees<input type="number" min="0" value={form.max_employees} onChange={(event) => change('max_employees', event.target.value)} /></label>
          <label>Maximum leads<input type="number" min="0" value={form.max_leads} onChange={(event) => change('max_leads', event.target.value)} /></label>
          <label>Daily AI tokens<input type="number" min="0" value={form.daily_ai_tokens} onChange={(event) => change('daily_ai_tokens', event.target.value)} /></label>
          <label>Storage limit (MB)<input type="number" min="0" value={form.storage_limit_mb} onChange={(event) => change('storage_limit_mb', event.target.value)} /></label>
          <label className="wide">Description<textarea value={form.description} onChange={(event) => change('description', event.target.value)} /></label>
          <label className="wide">Features (JSON)<textarea className="code-input" value={form.features} onChange={(event) => change('features', event.target.value)} /></label>
          <label className="wide">Included services (one per line)<textarea value={form.included_services} onChange={(event) => change('included_services', event.target.value)} /></label>
          <label className="wide">Additional services<textarea value={form.additional_services} onChange={(event) => change('additional_services', event.target.value)} /></label>
          <label className="wide">Terms and conditions<textarea value={form.terms_conditions} onChange={(event) => change('terms_conditions', event.target.value)} /></label>
        </div>
        <div className="plan-form-checks"><label><input type="checkbox" checked={form.prices_confirmed} onChange={(event) => change('prices_confirmed', event.target.checked)} /> Prices confirmed</label><label><input type="checkbox" checked={form.is_active} onChange={(event) => change('is_active', event.target.checked)} /> Visible on pricing page</label></div>
        <button type="submit" className="primary" disabled={saving}>{saving ? 'Saving…' : editing ? 'Save plan' : 'Create plan'}</button>
      </form>
    </section>}
  </section>
}
