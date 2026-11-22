import { useCallback, useEffect, useState } from 'react'
import './EnterpriseManagementPage.css'

const statusOptions = ['pending', 'new', 'in_review', 'contacted', 'under_discussion', 'approved', 'rejected', 'plan_created', 'payment_pending', 'completed', 'converted', 'closed']
const emptyPlan = { name: 'Enterprise Custom', customer_email: '', max_employees: 100, billing_cycle: 'MONTHLY', amount: '', currency: 'INR', duration_count: 12, storage_limit_mb: '', features: '{}', included_services: '', additional_services: '', description: '', terms_conditions: '', recurring: true }

export default function EnterpriseManagementPage({ api }) {
  const [data, setData] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [plan, setPlan] = useState(emptyPlan)
  const [statusValue, setStatusValue] = useState('new')
  const [notes, setNotes] = useState('')
  const [assignedAdmin, setAssignedAdmin] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [editingPlanId, setEditingPlanId] = useState('')
  const [editingPlan, setEditingPlan] = useState(null)
  const [editingInquiry, setEditingInquiry] = useState(null)
  const selected = data?.requests?.find((item) => item.id === selectedId)
  const visibleRequests = (data?.requests || []).filter((item) => {
    const query = search.trim().toLowerCase()
    const matchesText = !query || [item.full_name, item.email, item.organization_name].some((value) => value.toLowerCase().includes(query))
    return matchesText && (!statusFilter || item.status === statusFilter)
  })

  const reload = useCallback(async () => {
    const result = await api.get('/subscriptions/enterprise/manage/')
    setData(result)
  }, [api])

  useEffect(() => { reload().catch((exception) => setError(exception.message)) }, [reload])
  useEffect(() => {
    if (!selected) return
    setStatusValue(selected.status)
    setNotes(selected.internal_notes || '')
    setAssignedAdmin(selected.assigned_admin || '')
    setPlan((current) => ({ ...current, customer_email: selected.email }))
  }, [selectedId])

  async function run(action, success) {
    setBusy(true); setError(''); setMessage('')
    try { await action(); await reload(); setMessage(success) }
    catch (exception) { setError(exception.message) }
    finally { setBusy(false) }
  }

  function updatePlan(key, value) { setPlan((current) => ({ ...current, [key]: value })) }
  async function saveReview(event) {
    event.preventDefault()
    await run(() => api.patch(`/subscriptions/enterprise/manage/${selected.id}/`, { status: statusValue, internal_notes: notes, assigned_admin: assignedAdmin || null }), 'Inquiry review saved.')
  }
  async function saveCustomerDetails(event) {
    event.preventDefault()
    await run(async () => { await api.patch(`/subscriptions/enterprise/manage/${selected.id}/`, editingInquiry); setEditingInquiry(null) }, 'Customer details updated.')
  }
  async function createPlan(event) {
    event.preventDefault()
    let features
    try { features = JSON.parse(plan.features || '{}') } catch { setError('Features must be valid JSON.'); return }
    const body = { ...plan, amount: Number(plan.amount), max_employees: Number(plan.max_employees), duration_count: Number(plan.duration_count), storage_limit_mb: plan.storage_limit_mb ? Number(plan.storage_limit_mb) : null, features, included_services: plan.included_services.split('\n').map((item) => item.trim()).filter(Boolean) }
    await run(() => api.post(`/subscriptions/enterprise/manage/${selected.id}/plan/`, body), 'Custom plan created and linked to the inquiry.')
  }
  async function invite() {
    await run(() => api.post(`/subscriptions/enterprise/manage/${selected.id}/payment-invitation/`, {}), 'Payment invitation emailed to the customer.')
  }
  async function resendRegistration(checkoutId) {
    await run(() => api.post(`/subscriptions/enterprise/manage/invitations/${checkoutId}/resend-registration/`, {}), 'A fresh 24-hour registration link was emailed. The previous link is invalidated.')
  }
  function beginPlanEdit(item) {
    setEditingPlanId(item.id)
    setEditingPlan({ ...item, monthly_price: item.monthly_price ?? '', yearly_price: item.yearly_price ?? '', features: JSON.stringify(item.features || {}, null, 2), included_services: (item.included_services || []).join('\n'), storage_limit_mb: item.storage_limit_mb ?? '' })
  }
  async function savePlanEdit(event) {
    event.preventDefault()
    let features
    try { features = JSON.parse(editingPlan.features || '{}') } catch { setError('Features must be valid JSON.'); return }
    const body = { ...editingPlan, features, monthly_price: editingPlan.monthly_price === '' ? null : Number(editingPlan.monthly_price), yearly_price: editingPlan.yearly_price === '' ? null : Number(editingPlan.yearly_price), max_employees: Number(editingPlan.max_employees), storage_limit_mb: editingPlan.storage_limit_mb === '' ? null : Number(editingPlan.storage_limit_mb), included_services: editingPlan.included_services.split('\n').map((item) => item.trim()).filter(Boolean) }
    await run(async () => { await api.patch(`/subscriptions/enterprise/manage/plans/${editingPlanId}/`, body); setEditingPlanId(''); setEditingPlan(null) }, 'Custom plan updated.')
  }

  if (!data && !error) return <section className="page"><h2>Enterprise management</h2><p>Loading inquiries…</p></section>
  return <section className="page enterprise-management">
    <h2>Enterprise management</h2>
    <p>Review custom pricing requests, create an agreed plan, and send a payment invitation after approval.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <div className="enterprise-admin-grid">
      <section><h3>Inquiries ({data?.requests?.length || 0})</h3>
        <div className="enterprise-search"><input aria-label="Search inquiries" placeholder="Search name, email, organization" value={search} onChange={(event) => setSearch(event.target.value)} /><select aria-label="Filter inquiry status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option>{statusOptions.map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></div>
        <div className="table-scroll"><table><thead><tr><th>Request ID</th><th>Organization</th><th>Contact</th><th>Status</th><th>Assigned admin</th><th>Received</th></tr></thead><tbody>
          {visibleRequests.map((item) => <tr key={item.id} onClick={() => setSelectedId(item.id)} aria-selected={item.id === selectedId} tabIndex="0" onKeyDown={(event) => event.key === 'Enter' && setSelectedId(item.id)}>
            <td title={item.id}>{item.id.slice(0, 8)}</td><td>{item.organization_name}</td><td>{item.full_name}<br />{item.email}</td><td>{item.status}</td><td>{item.assigned_admin_name || 'Unassigned'}</td><td>{new Date(item.created_at).toLocaleDateString()}</td>
          </tr>)}
        </tbody></table></div>
      </section>
      <section>
        {!selected ? <p>Select an inquiry to review.</p> : <>
          <h3>{selected.organization_name}</h3><p>{selected.full_name} · {selected.email} · {selected.phone}</p>
          {selected.website && <p><a href={selected.website} target="_blank" rel="noreferrer">Website</a> · <a href={selected.linkedin_url} target="_blank" rel="noreferrer">LinkedIn</a></p>}
          <p>{selected.note || 'No additional requirements supplied.'}</p>
          <button type="button" onClick={() => setEditingInquiry({ full_name: selected.full_name, email: selected.email, phone: selected.phone, organization_name: selected.organization_name, website: selected.website || '', linkedin_url: selected.linkedin_url || '', note: selected.note || '' })}>Edit customer details</button>
          {editingInquiry && <form onSubmit={saveCustomerDetails} className="enterprise-admin-form"><h4>Edit customer details</h4><div className="enterprise-admin-fields">
            {Object.entries({ full_name: 'Full name', email: 'Email address', phone: 'Phone', organization_name: 'Organization', website: 'Website', linkedin_url: 'LinkedIn URL' }).map(([key, label]) => <label key={key}>{label}<input type={key === 'email' ? 'email' : key.includes('url') || key === 'website' ? 'url' : 'text'} value={editingInquiry[key]} required={['full_name', 'email', 'phone', 'organization_name'].includes(key)} onChange={(event) => setEditingInquiry({ ...editingInquiry, [key]: event.target.value })} /></label>)}
            <label className="enterprise-note">Requirements / notes<textarea value={editingInquiry.note} onChange={(event) => setEditingInquiry({ ...editingInquiry, note: event.target.value })} /></label>
          </div><button disabled={busy}>Save customer details</button><button type="button" onClick={() => setEditingInquiry(null)}>Cancel</button></form>}
          <form onSubmit={saveReview} className="enterprise-admin-form">
            <label>Status<select value={statusValue} onChange={(event) => setStatusValue(event.target.value)}>{statusOptions.map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
            <label>Assigned admin<select value={assignedAdmin} onChange={(event) => setAssignedAdmin(event.target.value)}><option value="">Unassigned</option>{(data?.administrators || []).map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
            <label>Internal notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows="3" /></label>
            <button disabled={busy}>Save review</button>
          </form>
          {selected.custom_plan ? <div><h4>Plan: {data?.plans?.find((item) => item.id === selected.custom_plan)?.name || selected.custom_plan}</h4><button type="button" disabled={busy || Boolean(selected.payment_link_email_sent_at) || !['plan_created', 'payment_pending'].includes(selected.status)} onClick={invite}>{selected.payment_link_email_sent_at ? 'Payment invitation sent' : 'Send payment invitation'}</button></div> : <form onSubmit={createPlan} className="enterprise-admin-form">
            <h4>Create agreed custom plan</h4>
            <p>Organization: <strong>{selected.organization_name}</strong></p>
            <div className="enterprise-admin-fields">
              <label>Plan name<input required value={plan.name} onChange={(e) => updatePlan('name', e.target.value)} /></label>
              <label>Customer email<input type="email" required value={plan.customer_email} onChange={(e) => updatePlan('customer_email', e.target.value)} /></label>
              <label>Maximum users<input type="number" min="1" required value={plan.max_employees} onChange={(e) => updatePlan('max_employees', e.target.value)} /></label>
              <label>Billing cycle<select value={plan.billing_cycle} onChange={(e) => updatePlan('billing_cycle', e.target.value)}><option value="MONTHLY">Monthly</option><option value="YEARLY">Yearly</option></select></label>
              <label>Currency<select value={plan.currency} onChange={(e) => updatePlan('currency', e.target.value)}><option value="INR">INR</option></select></label>
              <label>Amount (INR)<input type="number" min="1" step="0.01" required value={plan.amount} onChange={(e) => updatePlan('amount', e.target.value)} /></label>
              <label>Billing count<input type="number" min="1" max="120" required value={plan.duration_count} onChange={(e) => updatePlan('duration_count', e.target.value)} /></label>
              <label>Storage limit (MB)<input type="number" min="1" value={plan.storage_limit_mb} onChange={(e) => updatePlan('storage_limit_mb', e.target.value)} /></label>
              <label>Included services (one per line)<textarea value={plan.included_services} onChange={(e) => updatePlan('included_services', e.target.value)} /></label>
              <label>Feature details (JSON)<textarea value={plan.features} onChange={(e) => updatePlan('features', e.target.value)} /></label>
              <label>Additional services<textarea value={plan.additional_services} onChange={(e) => updatePlan('additional_services', e.target.value)} /></label>
              <label>Description<textarea value={plan.description} onChange={(e) => updatePlan('description', e.target.value)} /></label>
              <label>Terms and conditions<textarea value={plan.terms_conditions} onChange={(e) => updatePlan('terms_conditions', e.target.value)} /></label>
            </div>
            <details><summary>Review custom plan before creation</summary><p>{plan.name} for {selected.organization_name}; {plan.customer_email}; {plan.max_employees} users; {plan.currency} {plan.amount} per {plan.billing_cycle.toLowerCase()}; {plan.duration_count} billing periods.</p><p>{plan.included_services.split('\n').filter(Boolean).join(', ') || 'No included services listed.'}</p></details>
            <label><input type="checkbox" checked={plan.recurring} onChange={(e) => updatePlan('recurring', e.target.checked)} /> Recurring Razorpay subscription</label>
            <button disabled={busy || statusValue !== 'approved'}>Create custom plan</button>
            {statusValue !== 'approved' && <small>Set status to Approved and save before creating a plan.</small>}
          </form>}
        </>}
      </section>
    </div>
    <section><h3>Custom subscriptions, payments, and invitations</h3><div className="table-scroll"><table><thead><tr><th>Customer</th><th>Mode / status</th><th>Created</th><th>Registration link expiry</th><th>Invitation</th></tr></thead><tbody>
      {(data?.invitations || []).map((row) => <tr key={row.checkout_id}><td>{row.email}</td><td>{row.payment_mode || row.status}</td><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.expires_at ? new Date(row.expires_at).toLocaleString() : '—'}</td><td>{row.status === 'paid' && !row.registered ? <button type="button" disabled={busy} onClick={() => resendRegistration(row.checkout_id)}>Resend registration</button> : row.registered ? 'Completed' : row.status}</td></tr>)}
      {!data?.invitations?.length && <tr><td colSpan="5">No invitations yet.</td></tr>}
    </tbody></table></div></section>
    <section><h3>Custom plans</h3><div className="table-scroll"><table><thead><tr><th>Plan</th><th>Price</th><th>User limit</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {(data?.plans || []).map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.currency} {item.monthly_price ?? item.yearly_price ?? '—'}{item.monthly_price ? ' / month' : item.yearly_price ? ' / year' : ''}</td><td>{item.max_employees}</td><td>{item.is_active ? 'Active' : 'Inactive'}</td><td><button type="button" onClick={() => beginPlanEdit(item)}>Edit</button> <button type="button" disabled={!item.is_active || busy} onClick={() => run(() => api.patch(`/subscriptions/enterprise/manage/plans/${item.id}/`, { is_active: false }), 'Custom plan deactivated.')}>Deactivate</button></td></tr>)}
      {!data?.plans?.length && <tr><td colSpan="5">No custom plans created.</td></tr>}
    </tbody></table></div>
    {editingPlan && <form className="enterprise-admin-form" onSubmit={savePlanEdit}><h4>Edit {editingPlan.name}</h4><div className="enterprise-admin-fields">
      <label>Plan name<input value={editingPlan.name} onChange={(e) => setEditingPlan({ ...editingPlan, name: e.target.value })} required /></label>
      <label>Description<textarea value={editingPlan.description} onChange={(e) => setEditingPlan({ ...editingPlan, description: e.target.value })} /></label>
      <label>Monthly price<input type="number" min="1" step="0.01" value={editingPlan.monthly_price} disabled={Boolean(editingPlan.razorpay_plan_id)} onChange={(e) => setEditingPlan({ ...editingPlan, monthly_price: e.target.value })} /></label>
      <label>Yearly price<input type="number" min="1" step="0.01" value={editingPlan.yearly_price} disabled={Boolean(editingPlan.razorpay_plan_id)} onChange={(e) => setEditingPlan({ ...editingPlan, yearly_price: e.target.value })} /></label>
      <label>Maximum users<input type="number" min="1" value={editingPlan.max_employees} onChange={(e) => setEditingPlan({ ...editingPlan, max_employees: e.target.value })} /></label>
      <label>Storage limit (MB)<input type="number" min="1" value={editingPlan.storage_limit_mb} onChange={(e) => setEditingPlan({ ...editingPlan, storage_limit_mb: e.target.value })} /></label>
      <label>Features (JSON)<textarea value={editingPlan.features} onChange={(e) => setEditingPlan({ ...editingPlan, features: e.target.value })} /></label>
      <label>Included services (one per line)<textarea value={editingPlan.included_services} onChange={(e) => setEditingPlan({ ...editingPlan, included_services: e.target.value })} /></label>
      <label>Additional services<textarea value={editingPlan.additional_services} onChange={(e) => setEditingPlan({ ...editingPlan, additional_services: e.target.value })} /></label>
      <label>Terms and conditions<textarea value={editingPlan.terms_conditions} onChange={(e) => setEditingPlan({ ...editingPlan, terms_conditions: e.target.value })} /></label>
    </div><div className="enterprise-admin-actions"><button disabled={busy}>Save plan</button><button type="button" onClick={() => { setEditingPlan(null); setEditingPlanId('') }}>Close</button></div></form>}
    </section>
    <div className="enterprise-admin-grid">
      <section><h3>Subscriptions</h3><div className="table-scroll"><table><thead><tr><th>Organization</th><th>Plan</th><th>Status</th><th>End date</th></tr></thead><tbody>
        {(data?.subscriptions || []).map((row) => <tr key={row.id}><td>{row.organization_name}</td><td>{row.plan_details?.name}</td><td>{row.status}</td><td>{row.end_date ? new Date(row.end_date).toLocaleDateString() : '—'}</td></tr>)}
        {!data?.subscriptions?.length && <tr><td colSpan="4">No Enterprise subscriptions yet.</td></tr>}
      </tbody></table></div></section>
      <section><h3>Payments</h3><div className="table-scroll"><table><thead><tr><th>Amount</th><th>Provider payment</th><th>Status</th><th>Paid</th></tr></thead><tbody>
        {(data?.payments || []).map((row) => <tr key={row.id}><td>{row.currency} {row.amount}</td><td>{row.provider_payment_id || '—'}</td><td>{row.status}</td><td>{row.paid_at ? new Date(row.paid_at).toLocaleDateString() : '—'}</td></tr>)}
        {!data?.payments?.length && <tr><td colSpan="4">No Enterprise payments yet.</td></tr>}
      </tbody></table></div></section>
    </div>
    <section><h3>Enterprise customers</h3><div className="table-scroll"><table><thead><tr><th>Customer</th><th>Organization</th><th>Active plan</th><th>Subscription status</th><th>Registration</th></tr></thead><tbody>
      {(data?.customers || []).map((row) => <tr key={row.inquiry_id}><td>{row.full_name}<br />{row.email}<br />{row.phone}</td><td>{row.organization}</td><td>{row.plan || '—'}</td><td>{row.subscription_status}</td><td>{row.registered ? 'Complete' : 'Pending'}</td></tr>)}
      {!data?.customers?.length && <tr><td colSpan="5">No registered Enterprise customers yet.</td></tr>}
    </tbody></table></div></section>
  </section>
}
