import { useEffect, useRef, useState } from 'react'
import './AIAssistant.css'

const greeting = (roleName) => ({
  role: 'welcome',
  content: `Hi! I can answer questions about records available to you${roleName ? ` as ${roleName}` : ''}.`,
})

function inlineMarkdown(text, keyPrefix) {
  const tokens = String(text).split(/(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*]+\*)/g).filter(Boolean)
  return tokens.map((token, index) => {
    const key = `${keyPrefix}-${index}`
    if ((token.startsWith('**') && token.endsWith('**')) || (token.startsWith('__') && token.endsWith('__'))) return <strong key={key}>{token.slice(2, -2)}</strong>
    if (token.startsWith('`') && token.endsWith('`')) return <code key={key}>{token.slice(1, -1)}</code>
    if (token.startsWith('*') && token.endsWith('*')) return <em key={key}>{token.slice(1, -1)}</em>
    return token
  })
}

function tableCells(line) {
  const trimmed = line.trim().replace(/^\|+|\|+$/g, '').replace(/\|{2,}/g, '|')
  return trimmed.split('|').map((cell) => cell.trim())
}

function isTableSeparator(line) {
  const cells = tableCells(line)
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replaceAll(' ', '')))
}

function MarkdownContent({ content }) {
  const lines = String(content || '').replaceAll('\r', '').split('\n')
  const blocks = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) { index += 1; continue }
    const heading = line.match(/^\s*(#{1,4})\s+(.+)$/)
    const boldHeading = line.match(/^\s*\*\*(.+)\*\*:?\s*$/)
    if (heading || boldHeading) {
      blocks.push(<h4 key={`heading-${index}`}>{inlineMarkdown(heading ? heading[2] : boldHeading[1], `heading-${index}`)}</h4>)
      index += 1
      continue
    }
    if (line.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = tableCells(line)
      index += 2
      const rows = []
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(tableCells(lines[index]))
        index += 1
      }
      blocks.push(<div className="ai-table-wrap" key={`table-${index}`}><table><thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineMarkdown(cell, `th-${index}-${cellIndex}`)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{inlineMarkdown(row[cellIndex] || '', `td-${index}-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody></table></div>)
      continue
    }
    const listMatch = line.match(/^\s*(?:[-+*]\s+|\d+[.)]\s+)/)
    if (listMatch) {
      const ordered = /^\s*\d+[.)]\s+/.test(line)
      const List = ordered ? 'ol' : 'ul'
      const items = []
      while (index < lines.length && /^\s*(?:[-+*]\s+|\d+[.)]\s+)/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*(?:[-+*]|\d+[.)])\s+/, ''))
        index += 1
      }
      blocks.push(<List key={`list-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item, `li-${index}-${itemIndex}`)}</li>)}</List>)
      continue
    }
    const paragraph = [line.trim()]
    index += 1
    while (index < lines.length && lines[index].trim() && !/^\s*(#{1,4})\s+/.test(lines[index]) && !(lines[index].includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) && !/^\s*(?:[-+*]\s+|\d+[.)]\s+)/.test(lines[index])) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push(<p key={`paragraph-${index}`}>{paragraph.map((part, partIndex) => <span key={partIndex}>{partIndex > 0 && ' '}{inlineMarkdown(part, `p-${index}-${partIndex}`)}</span>)}</p>)
  }
  return <div className="ai-markdown">{blocks}</div>
}

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
          {message.role === 'assistant' ? <MarkdownContent content={message.content} /> : <span>{message.content}</span>}
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
