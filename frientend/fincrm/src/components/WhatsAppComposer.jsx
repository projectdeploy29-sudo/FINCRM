import { useEffect, useRef, useState } from 'react'
import useSidePanelEntrance from './useSidePanelEntrance'
import './WhatsAppComposer.css'

const dateTime = (value, timezone) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: timezone }).format(new Date(value)) : 'Not set'

export default function WhatsAppComposer({ api, followup, followupKind, lead, timezone = 'UTC', onClose }) {
  const dialogRef = useRef(null)
  const entered = useSidePanelEntrance(dialogRef)
  const directLead = Boolean(lead)
  const targetId = lead?.id || followup?.id
  const recipientName = lead?.contact_name || followup?.contact_name || 'Contact'
  const recipientPhone = lead?.phone || followup?.contact_phone || ''
  const [templates, setTemplates] = useState([])
  const [mode, setMode] = useState('template')
  const [templateId, setTemplateId] = useState('')
  const [customMessage, setCustomMessage] = useState('')
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const query = directLead
      ? new URLSearchParams({ lead_id: String(targetId) })
      : new URLSearchParams({ followup_kind: followupKind, followup_id: String(targetId) })
    Promise.all([
      api.get('/whatsapp/templates/'),
      api.get(`${directLead ? '/whatsapp/lead-history/' : '/whatsapp/followup-history/'}?${query.toString()}`),
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
  }, [api, directLead, targetId, followupKind])

  async function submit(event) {
    event.preventDefault()
    setError('')
    setSending(true)
    try {
      const payload = {
        ...(directLead ? { lead_id: String(targetId) } : { followup_kind: followupKind, followup_id: String(targetId) }),
        ...(mode === 'template' ? { template_id: Number(templateId) } : { custom_message: customMessage.trim() }),
      }
      const result = await api.post(directLead ? '/whatsapp/prepare-lead/' : '/whatsapp/prepare-followup/', payload)
      window.location.assign(result.whatsapp_url)
    } catch (exception) {
      setError(exception.message || 'Could not prepare the WhatsApp message.')
    } finally {
      setSending(false)
    }
  }

  const selectedTemplate = templates.find((item) => String(item.id) === templateId)
  const hasMessage = mode === 'template' ? Boolean(selectedTemplate) : Boolean(customMessage.trim())

  return <dialog ref={dialogRef} className={`detail-dialog side-panel-dialog whatsapp-dialog${entered ? ' is-entered' : ''}`} aria-labelledby="whatsapp-dialog-title" onCancel={(event) => { event.preventDefault(); onClose() }}>
    <div className="record-modal-header">
      <h3 id="whatsapp-dialog-title">{directLead ? 'Send WhatsApp message' : 'Send WhatsApp follow-up'}</h3>
      <button type="button" className="modal-close" aria-label="Close WhatsApp dialog" onClick={onClose} disabled={sending}>×</button>
    </div>
    <p><strong>To:</strong> {recipientName} · {recipientPhone}</p>
    <dl className="whatsapp-followup-details">
      {directLead ? <>
        <div><dt>Lead code</dt><dd>{lead.lead_code || 'Not set'}</dd></div>
        <div><dt>Lead stage</dt><dd>{String(lead.status || 'new').replaceAll('_', ' ')}</dd></div>
      </> : <>
        <div><dt>Type</dt><dd>{String(followup.followup_type || '').toLowerCase().replaceAll('_', ' ')}</dd></div>
        <div><dt>Scheduled time</dt><dd>{dateTime(followup.scheduled_at, timezone)}</dd></div>
        <div><dt>Reason</dt><dd>{followup.purpose || followup.description || 'Not specified'}</dd></div>
      </>}
    </dl>
    <p className="whatsapp-policy-note">{directLead
      ? 'Choose a saved or custom message. Auron FIN CRM will open this lead’s WhatsApp chat with the message ready; review it and press Send in WhatsApp. Only message contacts who have agreed to receive WhatsApp messages.'
      : 'The follow-up type, time, and reason will be filled into the message. Auron FIN CRM will open the contact’s WhatsApp chat with the message ready; review it and press Send in WhatsApp. Only message contacts who have agreed to receive WhatsApp messages.'}</p>
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
        <textarea value={customMessage} onChange={(event) => setCustomMessage(event.target.value)} maxLength={1200} required placeholder={directLead ? 'Write a message for this lead.' : 'Write a short message to send after the follow-up details.'} />
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
