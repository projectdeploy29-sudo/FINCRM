import { useEffect, useState } from 'react'
import { API_ROOT, readApiResponse } from '../api'
import LoadingSkeleton from './LoadingSkeleton'
import './PlanCatalog.css'

const emptyInquiry = { full_name: '', email: '', phone: '', organization_name: '', website: '', linkedin_url: '', note: '' }

function money(value) {
  if (value === null || value === undefined) return 'Custom pricing'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function limit(value) {
  return value === null || value === undefined ? 'Negotiated' : Number(value).toLocaleString('en-IN')
}

async function loadRazorpay() {
  if (window.Razorpay) return window.Razorpay
  await new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-razorpay-checkout]')
    if (existing) {
      existing.addEventListener('load', resolve, { once: true })
      existing.addEventListener('error', reject, { once: true })
      if (window.Razorpay) resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.async = true
    script.dataset.razorpayCheckout = 'true'
    script.onload = resolve
    script.onerror = () => reject(new Error('Razorpay checkout could not be loaded.'))
    document.body.appendChild(script)
  })
  if (!window.Razorpay) throw new Error('Razorpay checkout did not initialize.')
  return window.Razorpay
}

export default function PlanCatalog({ api, user }) {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [cycle, setCycle] = useState('MONTHLY')
  const [selectedPlan, setSelectedPlan] = useState(null)
  const [email, setEmail] = useState(user?.email || '')
  const [enterpriseOpen, setEnterpriseOpen] = useState(false)
  const [inquiry, setInquiry] = useState(emptyInquiry)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [failedPayment, setFailedPayment] = useState(null)
  const [inquiryRequestKey, setInquiryRequestKey] = useState(() => crypto.randomUUID())

  useEffect(() => {
    let active = true
    const request = api
      ? api.get('/subscriptions/plans/')
      : fetch(`${API_ROOT}/subscriptions/plans/`).then(async (response) => {
        const data = await readApiResponse(response)
        if (!response.ok) throw new Error(data.detail || `Could not load plans (${response.status}).`)
        return data
      })
    request
      .then((data) => { if (active) setPlans(Array.isArray(data) ? data : data.results || []) })
      .catch((exception) => { if (active) setError(exception.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [api])

  async function post(path, body, headers = {}) {
    if (api) return api.post(path, body, headers)
    const response = await fetch(`${API_ROOT}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify(body),
    })
    const data = await readApiResponse(response)
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status}).`)
    return data
  }

  function choosePlan(plan) {
    setError('')
    setMessage('')
    if (plan.code === 'enterprise') {
      setInquiry((current) => ({ ...current, email: user?.email || current.email }))
      setInquiryRequestKey(crypto.randomUUID())
      setEnterpriseOpen(true)
      return
    }
    setEmail(user?.email || '')
    setSelectedPlan(plan)
  }

  async function continueToPayment(event) {
    event.preventDefault()
    if (!selectedPlan || !email.trim()) return
    setBusy(true)
    setError('')
    setFailedPayment(null)
    try {
      const order = await post('/subscriptions/checkout/create/', {
        plan_id: selectedPlan.id,
        billing_cycle: cycle,
        email: email.trim(),
      })
      const Razorpay = await loadRazorpay()
      const checkout = new Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'Auron FIN CRM',
        description: `${order.plan_name} · ${cycle === 'YEARLY' ? 'yearly' : 'monthly'} plan`,
        order_id: order.order_id,
        prefill: { email: order.email },
        theme: { color: '#1764e8' },
        handler: async (payment) => {
          await verifyPayment(payment)
        },
        modal: { ondismiss: () => setBusy(false) },
      })
      checkout.on('payment.failed', (payment) => {
        setError(payment.error?.description || 'Payment was not completed. You can select the plan and try again.')
        setBusy(false)
      })
      setSelectedPlan(null)
      setBusy(false)
      checkout.open()
    } catch (exception) {
      setError(exception.message)
      setBusy(false)
    }
  }

  async function verifyPayment(payment) {
    setBusy(true)
    setError('')
    try {
      const result = await post('/subscriptions/checkout/verify/', payment)
      setMessage(result.detail)
      setFailedPayment(null)
      setSelectedPlan(null)
    } catch (exception) {
      setFailedPayment(payment)
      setError(exception.message)
    } finally {
      setBusy(false)
    }
  }

  async function submitInquiry(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await post('/subscriptions/enterprise-inquiry/', inquiry, { 'Idempotency-Key': inquiryRequestKey })
      setMessage(result.detail)
      setEnterpriseOpen(false)
      setInquiry(emptyInquiry)
      setInquiryRequestKey(crypto.randomUUID())
    } catch (exception) {
      setError(exception.message)
    } finally {
      setBusy(false)
    }
  }

  const priceForCycle = (plan) => cycle === 'YEARLY' ? plan.yearly_price : plan.monthly_price
  return <section className="public-plans plan-catalog">
    <header className="plan-page-heading"><span>PLANS FOR YOUR ORGANIZATION</span><h1>Choose a plan built for your team</h1><p>Compare capacity, features, and billing. Your plan details are loaded from the live catalog.</p></header>
    <div className="plan-cycle-picker" role="group" aria-label="Billing cycle">
      <button type="button" className={cycle === 'MONTHLY' ? 'active' : ''} onClick={() => setCycle('MONTHLY')}>Monthly</button>
      <button type="button" className={cycle === 'YEARLY' ? 'active' : ''} onClick={() => setCycle('YEARLY')}>Yearly</button>
    </div>
    {loading && <LoadingSkeleton variant="cards" metricCount={4} panelCount={0} label="Loading subscription plans" />}
    {error && <p className="plans-error" role="alert">{error}</p>}
    {failedPayment && <button type="button" className="payment-retry" disabled={busy} onClick={() => verifyPayment(failedPayment)}>{busy ? 'Checking payment…' : 'Retry payment confirmation'}</button>}
    {message && <p className="plans-success" role="status">{message}</p>}
    {!loading && !error && plans.length === 0 && <p className="muted">No active plans are available right now.</p>}
    {!loading && !error && <div className="plan-grid">{plans.map((plan) => {
      const custom = plan.code === 'enterprise'
      const price = priceForCycle(plan)
      const features = Object.entries(plan.features || {}).filter(([, enabled]) => enabled).map(([name]) => name.replaceAll('_', ' '))
      return <article className={`plan-card ${plan.code === 'professional' ? 'popular' : ''}`} key={plan.id}>
        <div className="plan-title"><h2>{plan.name}</h2>{plan.code === 'professional' && <span>POPULAR</span>}</div>
        <p className="plan-description">{plan.description}</p>
        <div className="plan-price">{custom ? 'Custom pricing' : plan.checkout_enabled ? money(price) : 'Pricing pending confirmation'}{!custom && plan.checkout_enabled && price != null && <small> / {cycle === 'YEARLY' ? 'year' : 'month'}</small>}</div>
        <ul>
          <li>{limit(plan.max_employees)} Staff Accounts</li>
          <li>{limit(plan.max_leads)} Leads</li>
          {features.map((feature) => <li key={feature}>{feature}</li>)}
        </ul>
        <button type="button" className="plan-cta" disabled={!custom && (!plan.checkout_enabled || price == null)} onClick={() => choosePlan(plan)}>
          {custom ? 'Contact sales' : !plan.checkout_enabled || price == null ? 'Unavailable' : 'Select plan'} <span aria-hidden="true">⟶</span>
        </button>
      </article>
    })}</div>}

    {selectedPlan && <div className="plan-modal-backdrop">
      <section className="plan-modal" role="dialog" aria-modal="true" aria-labelledby="checkout-title">
        <button type="button" className="plan-modal-close" aria-label="Close" onClick={() => setSelectedPlan(null)}>×</button>
        <h2 id="checkout-title">Continue with {selectedPlan.name}?</h2>
        <p>You’ll pay <strong>{money(priceForCycle(selectedPlan))} per {cycle === 'YEARLY' ? 'year' : 'month'}</strong> using Razorpay. After payment, we’ll email a one-time organization registration link.</p>
        <form onSubmit={continueToPayment}>
          <label>Email for your registration link<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <div className="plan-modal-actions"><button type="button" onClick={() => setSelectedPlan(null)}>Cancel</button><button type="submit" disabled={busy}>{busy ? 'Preparing payment…' : 'Continue to payment'}</button></div>
        </form>
      </section>
    </div>}

    {enterpriseOpen && <div className="plan-modal-backdrop">
      <section className="plan-modal enterprise-modal" role="dialog" aria-modal="true" aria-labelledby="enterprise-title">
        <button type="button" className="plan-modal-close" aria-label="Close" onClick={() => setEnterpriseOpen(false)}>×</button>
        <h2 id="enterprise-title">Enterprise inquiry</h2>
        <p>Tell us how to reach you. We’ll send a confirmation and contact you about custom pricing.</p>
        <form onSubmit={submitInquiry}>
          <div className="enterprise-fields">
            <label>Your name<input required maxLength={200} value={inquiry.full_name} onChange={(event) => setInquiry({ ...inquiry, full_name: event.target.value })} /></label>
            <label>Email<input type="email" required value={inquiry.email} onChange={(event) => setInquiry({ ...inquiry, email: event.target.value })} /></label>
            <label>Phone<input type="tel" required maxLength={30} value={inquiry.phone} onChange={(event) => setInquiry({ ...inquiry, phone: event.target.value })} /></label>
            <label>Organization name<input required maxLength={200} value={inquiry.organization_name} onChange={(event) => setInquiry({ ...inquiry, organization_name: event.target.value })} /></label>
            <label>Organization website <span>(optional)</span><input type="url" value={inquiry.website} onChange={(event) => setInquiry({ ...inquiry, website: event.target.value })} /></label>
            <label>LinkedIn link <span>(optional)</span><input type="url" value={inquiry.linkedin_url} onChange={(event) => setInquiry({ ...inquiry, linkedin_url: event.target.value })} /></label>
            <label className="enterprise-note">Note <span>(optional)</span><textarea rows={3} maxLength={5000} value={inquiry.note} onChange={(event) => setInquiry({ ...inquiry, note: event.target.value })} /></label>
            <label aria-hidden="true" className="enterprise-honeypot">Fax<input tabIndex={-1} autoComplete="off" value={inquiry.fax || ''} onChange={(event) => setInquiry({ ...inquiry, fax: event.target.value })} /></label>
          </div>
          <div className="plan-modal-actions"><button type="button" onClick={() => setEnterpriseOpen(false)}>Cancel</button><button type="submit" disabled={busy}>{busy ? 'Sending…' : 'Submit inquiry'}</button></div>
        </form>
      </section>
    </div>}
  </section>
}
