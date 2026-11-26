import { useEffect, useState } from 'react'
import { readApiResponse, resolveApiUrl } from '../api'
import BrandFooter from './BrandFooter'

async function getCheckoutConstructor() {
  if (window.Razorpay) return window.Razorpay
  await new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.async = true
    script.onload = resolve
    script.onerror = () => reject(new Error('Razorpay checkout could not be loaded.'))
    document.body.appendChild(script)
  })
  if (!window.Razorpay) throw new Error('Razorpay checkout did not initialize.')
  return window.Razorpay
}

export default function EnterpriseCheckoutPage() {
  const [link] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    const queryValue = params.get('enterprise_checkout') || ''
    const queryToken = params.get('token') || ''
    const queryId = queryToken ? queryValue : ''
    const accessToken = queryToken || queryValue
    if (accessToken) {
      if (queryId) window.sessionStorage.setItem('fincrm_enterprise_checkout', queryId)
      else window.sessionStorage.removeItem('fincrm_enterprise_checkout')
      window.sessionStorage.setItem('fincrm_enterprise_checkout_token', accessToken)
      window.history.replaceState({}, '', window.location.pathname)
    }
    return {
      checkoutId: queryId || window.sessionStorage.getItem('fincrm_enterprise_checkout') || '',
      token: accessToken || window.sessionStorage.getItem('fincrm_enterprise_checkout_token') || '',
    }
  })
  const { checkoutId, token } = link
  const invalidLink = !checkoutId || !token
  const [checkout, setCheckout] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [paymentSubmitted, setPaymentSubmitted] = useState(false)
  const checkoutDetailsUrl = checkoutId
    ? `/subscriptions/enterprise-checkout/${encodeURIComponent(checkoutId)}/?token=${encodeURIComponent(token)}`
    : `/subscriptions/enterprise-checkout/?token=${encodeURIComponent(token)}`

  useEffect(() => {
    let active = true
    if (invalidLink) return () => { active = false }
    fetch(resolveApiUrl(checkoutDetailsUrl))
      .then(async (response) => {
        const data = await readApiResponse(response)
        if (!response.ok) throw new Error(data.detail || 'This Enterprise checkout link is invalid or expired.')
        return data
      })
      .then((data) => { if (active) setCheckout(data) })
      .catch((exception) => { if (active) setError(exception.message) })
    return () => { active = false }
  }, [checkoutDetailsUrl, checkoutId, invalidLink, token])

  useEffect(() => {
    if (!checkout?.status || (!paymentSubmitted && !['paid', 'completed', 'activated'].includes(checkout.status))) return undefined
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(resolveApiUrl(checkoutDetailsUrl))
        const data = await readApiResponse(response)
        if (response.ok && ['paid', 'completed', 'activated'].includes(data.status)) {
          setCheckout(data)
          setMessage(data.status === 'completed' || data.status === 'activated' ? 'Your Enterprise checkout is complete.' : 'Payment confirmed. Check your email for the secure organization registration link. The link expires after 24 hours.')
        }
      } catch { /* Retry quietly while Razorpay delivers its webhook. */ }
    }, 4000)
    return () => window.clearInterval(timer)
  }, [checkout?.status, checkoutDetailsUrl, checkoutId, token, paymentSubmitted])

  async function startPayment() {
    if (!checkout) return
    setBusy(true)
    setError('')
    try {
      const Razorpay = await getCheckoutConstructor()
      const payment = new Razorpay({
        key: checkout.key_id,
        ...(checkout.payment_mode === 'recurring' ? { subscription_id: checkout.subscription_id } : { order_id: checkout.order_id, amount: checkout.amount, currency: checkout.currency }),
        name: 'Auron FIN CRM',
        description: `Enterprise · ${checkout.billing_cycle === 'YEARLY' ? 'yearly' : 'monthly'} plan`,
        prefill: { email: checkout.email },
        theme: { color: '#1764e8' },
        handler: async (result) => {
          try {
            if (checkout.payment_mode === 'recurring') {
              setMessage('Authorization was submitted. Auron FIN CRM is waiting for Razorpay confirmation before sending your registration link.')
              setCheckout({ ...checkout, status: 'awaiting_webhook' })
              setPaymentSubmitted(true)
              setBusy(false)
              return
            }
            const response = await fetch(resolveApiUrl('/subscriptions/checkout/verify/'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(result),
            })
            const data = await readApiResponse(response)
            if (!response.ok) throw new Error(data.detail || 'Payment verification failed.')
            setMessage(data.detail || 'Payment is awaiting secure confirmation.')
            setCheckout({ ...checkout, status: 'awaiting_webhook' })
            setPaymentSubmitted(true)
          } catch (exception) {
            setError(exception.message)
          } finally {
            setBusy(false)
          }
        },
        modal: { ondismiss: () => setBusy(false) },
      })
      payment.on('payment.failed', (failure) => {
        setError(failure.error?.description || 'Payment did not complete. You can retry from this link.')
        setBusy(false)
      })
      setBusy(false)
      payment.open()
    } catch (exception) {
      setError(exception.message)
      setBusy(false)
    }
  }

  return <main className="login-page checkout-page-layout"><section className="login-card" aria-labelledby="enterprise-checkout-title">
    <h1 id="enterprise-checkout-title">Auron FIN CRM Enterprise checkout</h1>
    {checkout && !paymentSubmitted && ['pending', 'pending_authorization'].includes(checkout.status) && <>
      <p>Complete the agreed custom price for the Enterprise plan.</p>
      <p><strong>{new Intl.NumberFormat('en-IN', { style: 'currency', currency: checkout.currency }).format(checkout.amount / 100)}</strong> per {checkout.billing_cycle === 'YEARLY' ? 'year' : 'month'}</p>
      {checkout.plan_snapshot?.included_services?.length > 0 && <p>Included: {checkout.plan_snapshot.included_services.join(', ')}</p>}
      {checkout.plan_snapshot?.features && <p>Features: {Object.entries(checkout.plan_snapshot.features).map(([name, value]) => `${name.replaceAll('_', ' ')}: ${String(value)}`).join(' · ')}</p>}
      {checkout.plan_snapshot?.storage_limit_mb && <p>Storage: {checkout.plan_snapshot.storage_limit_mb} MB</p>}
      {checkout.plan_snapshot?.additional_services && <p>{checkout.plan_snapshot.additional_services}</p>}
      {checkout.plan_snapshot?.terms_conditions && <p>Terms: {checkout.plan_snapshot.terms_conditions}</p>}
      {checkout.payment_mode === 'recurring' && <p>This plan renews automatically through Razorpay. The renewal period and price are shown in Razorpay Checkout.</p>}
      <button type="button" onClick={startPayment} disabled={busy}>{busy ? 'Preparing secure checkout…' : 'Continue to payment'}</button>
    </>}
    {(checkout?.status === 'awaiting_webhook' || (paymentSubmitted && checkout?.status === 'pending')) && <p role="status">Waiting for secure confirmation from Razorpay. You can keep this page open.</p>}
    {checkout?.status === 'paid' && <p role="status">Payment confirmed. Your secure registration link has been sent by email.</p>}
    {(error || invalidLink) && <p role="alert">{error || 'This Enterprise checkout link is invalid or incomplete.'}</p>}
    {message && <p role="status">{message}</p>}
    {!checkout && !error && !invalidLink && !message && <p>Loading secure checkout…</p>}
    {message && <p>Once payment is verified, Auron FIN CRM will email the next registration step or activate the associated organization.</p>}
  </section><BrandFooter className="checkout-brand-footer" /></main>
}
