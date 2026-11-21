import { useEffect, useRef, useState } from 'react'
import './AIAssistant.css'

const greeting = (roleName) => ({
  role: 'welcome',
  content: `Hi! I can answer questions about records available to you${roleName ? ` as ${roleName}` : ''}.`,
})

export default function AIAssistant({ api, roleName }) {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [messages, setMessages] = useState(() => [greeting(roleName)])
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, open])

  async function sendQuestion(event) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    const history = messages
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .slice(-8)
      .map(({ role, content }) => ({ role, content }))
    setMessages((current) => [...current, { role: 'user', content: text }])
    setQuestion('')
    setBusy(true)
    try {
      const result = await api.post('/ai-assistant/chat/', { question: text, history })
      setMessages((current) => [...current, { role: 'assistant', content: result.answer }])
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', content: error.message || 'The assistant could not answer right now.' }])
    } finally {
      setBusy(false)
    }
  }

  return <div className="ai-assistant">
    {open && <section className="ai-panel" aria-label="AI assistant chat">
      <header className="ai-panel-header">
        <div><span className="ai-status-dot" /><div><strong>CRM Assistant</strong><small>Answers use your authorized records</small></div></div>
        <button type="button" className="ai-close" aria-label="Close assistant" onClick={() => setOpen(false)}>×</button>
      </header>
      <div className="ai-messages" role="log" aria-live="polite" aria-relevant="additions">
        {messages.map((message, index) => <div key={`${message.role}-${index}`} className={`ai-message ai-message-${message.role}`}>
          <span>{message.content}</span>
        </div>)}
        {busy && <div className="ai-message ai-message-assistant"><span className="ai-typing">Thinking…</span></div>}
        <div ref={endRef} />
      </div>
      <form className="ai-form" onSubmit={sendQuestion}>
        <label className="ai-sr-only" htmlFor="ai-question">Ask a question</label>
        <textarea
          id="ai-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder="Ask about your CRM data…"
          maxLength={2000}
          rows={2}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !question.trim()} aria-label="Send question">Send</button>
      </form>
    </section>}
    <button
      type="button"
      className="ai-launcher"
      aria-expanded={open}
      aria-label={open ? 'Close AI assistant' : 'Open AI assistant'}
      onClick={() => setOpen((value) => !value)}
    >
      <span aria-hidden="true">{open ? '×' : '✦'}</span>{!open && <span>Ask AI</span>}
    </button>
  </div>
}
