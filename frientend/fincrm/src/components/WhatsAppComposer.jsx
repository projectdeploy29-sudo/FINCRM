import { useEffect, useRef, useState } from 'react'
import './WhatsAppComposer.css'

const dateTime = (value, timezone) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: timezone }).format(new Date(value)) : 'Not set'

export default function WhatsAppComposer({ api, followup, followupKind, timezone = 'UTC', onClose }) {
  const dialogRef = useRef(null)
  const [templates, setTemplates] = useState([])
  const [mode, setMode] = useState('template')
  const [templateId, setTemplateId] = useState('')
  const [customMessage, setCustomMessage] = useState('')
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => { if (dialog?.open) dialog.close() }
  }, [])

  useEffect(() => {
    let active = true
    const query = new URLSearchParams({ followup_kind: followupKind, followup_id: String(followup.id) })
    Promise.all([
      api.get('/whatsapp/templates/'),
      api.get(`/whatsapp/followup-history/?${query.toString()}`),
    ]).then(([templateResult, historyResult]) => {
      if (!active) return
      const choices = templateResult.messages || []
      setTemplates(choices)
      setTemplateId(choices.length ? String(choices[0].id) : '')
      setHistory(Array.isArray(historyResult) ? historyResult : historyResult.results || [])
    }).catch((exception) => {
      if (active) setError(exception.message || 'Could not load WhatsApp messages.')
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [api, followup.id, followupKind])

  async function submit(event) {
    event.preventDefault()
    setError('')
    setSending(true)
    try {
      const payload = {
        followup_kind: followupKind,
        followup_id: String(followup.id),
        ...(mode === 'template' ? { template_id: Number(templateId) } : { custom_message: customMessage.trim() }),
      }
      const result = await api.post('/whatsapp/prepare-followup/', payload)
      window.location.assign(result.whatsapp_url)
    } catch (exception) {
      setError(exception.message || 'Could not prepare the WhatsApp message.')
    } finally {
      setSending(false)
    }
  }

  const selectedTemplate = templates.find((item) => String(item.id) === templateId)
  const hasMessage = mode === 'template' ? Boolean(selectedTemplate) : Boolean(customMessage.trim())

  return <dialog ref={dialogRef} className="detail-dialog whatsapp-dialog" aria-labelledby="whatsapp-dialog-title" onCancel={(event) => { event.preventDefault(); onClose() }}>
    <div className="record-modal-header">
      <h3 id="whatsapp-dialog-title">Send WhatsApp follow-up</h3>
      <button type="button" className="modal-close" aria-label="Close WhatsApp dialog" onClick={onClose} disabled={sending}>×</button>
    </div>
    <p><strong>To:</strong> {followup.contact_name || 'Contact'} · {followup.contact_phone}</p>
    <dl className="whatsapp-followup-details">
      <div><dt>Type</dt><dd>{String(followup.followup_type || '').toLowerCase().replaceAll('_', ' ')}</dd></div>
      <div><dt>Scheduled time</dt><dd>{dateTime(followup.scheduled_at, timezone)}</dd></div>
      <div><dt>Reason</dt><dd>{followup.purpose || followup.description || 'Not specified'}</dd></div>
    </dl>
    <p className="whatsapp-policy-note">The follow-up type, time, and reason will be filled into the message. FINCRM will open the contact’s WhatsApp chat with the message ready; review it and press Send in WhatsApp. Only message contacts who have agreed to receive WhatsApp messages.</p>
    {loading && <p>Loading saved messages…</p>}
    {!loading && <form onSubmit={submit}>
      <fieldset className="whatsapp-message-mode">
        <legend>Choose a message</legend>
        <label><input type="radio" name="whatsapp-mode" value="template" checked={mode === 'template'} onChange={() => setMode('template')} disabled={!templates.length} /> Saved message</label>
        <label><input type="radio" name="whatsapp-mode" value="custom" checked={mode === 'custom'} onChange={() => setMode('custom')} /> Custom message</label>
      </fieldset>
      {mode === 'template' && <label>Default message
        <select value={templateId} onChange={(event) => setTemplateId(event.target.value)} disabled={!templates.length} required>
          {templates.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
        {selectedTemplate && <span className="whatsapp-message-preview">{selectedTemplate.body}</span>}
        {!templates.length && <span>No saved messages are available. Choose Custom message.</span>}
      </label>}
      {mode === 'custom' && <label>Custom message
        <textarea value={customMessage} onChange={(event) => setCustomMessage(event.target.value)} maxLength={1200} required placeholder="Write a short message to send after the follow-up details." />
      </label>}
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={sending || !hasMessage}>{sending ? 'Opening WhatsApp…' : 'Continue to WhatsApp'}</button>
      <button type="button" onClick={onClose} disabled={sending}>Close</button>
    </form>}
    {history.length > 0 && <section className="whatsapp-history">
      <h4>Recent WhatsApp messages</h4>
      {history.map((item) => <article key={item.id}>
        <strong>{item.status}</strong> · {dateTime(item.created_at, timezone)}{item.template_title ? ` · ${item.template_title}` : ''}
        {item.error_detail && <p role="alert">{item.error_detail}</p>}
        <details><summary>Message details</summary><pre>{item.message_body}</pre></details>
      </article>)}
    </section>}
  </dialog>
}
