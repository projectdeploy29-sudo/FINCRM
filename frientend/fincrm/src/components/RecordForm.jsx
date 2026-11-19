import { useEffect, useRef, useState } from 'react'
import { unwrapList } from '../api'

function optionLabel(item) {
  return item.name || item.full_name || item.user_details?.full_name || item.user_details?.username || item.assigned_to_name || item.assigned_employee_name || item.label || item.customer_code || item.application_code || item.employee_code || item.code || item.username || item.id
}

function initialValue(field, initial) {
  let value = initial[field.name]
  if (field.name === 'role_ids' && initial.roles) value = initial.roles.map((role) => role.id)
  else if (field.multiple && initial.permissions) value = initial.permissions.map((permission) => permission.permission__id)
  if (field.type === 'json' && value && typeof value === 'object') return JSON.stringify(value, null, 2)
  if (field.type === 'datetime-local' && value) {
    const date = new Date(value)
    if (!Number.isNaN(date.getTime())) return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  }
  return value ?? field.defaultValue ?? (field.type === 'checkbox' ? false : field.multiple ? [] : '')
}

export default function RecordForm({ fields, initial = {}, api, submitLabel = 'Save', onSubmit, onCancel, title = 'Record' }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [field.name, initialValue(field, initial)])))
  const [options, setOptions] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const dialogRef = useRef(null)
  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => { if (dialog?.open) dialog.close() }
  }, [])
  useEffect(() => {
    let live = true
    Promise.all(fields.filter((field) => field.optionsEndpoint).map(async (field) => {
      try { const result = api.getAll ? await api.getAll(field.optionsEndpoint) : unwrapList(await api.get(field.optionsEndpoint)); return [field.name, result] } catch { return [field.name, []] }
    })).then((entries) => { if (live && entries.length) setOptions(Object.fromEntries(entries)) })
    return () => { live = false }
  }, [fields, api])

  function change(field, value) { setValues((current) => ({ ...current, [field.name]: value })) }
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    const payload = {}
    for (const field of fields) {
      const value = values[field.name]
      if (field.type === 'file') { if (value) payload[field.name] = value; continue }
      if (value === '' || value === undefined) continue
      if (field.type === 'json') {
        try { payload[field.name] = value ? JSON.parse(value) : {} } catch { setError(`${field.label || field.name} must contain valid JSON.`); setBusy(false); return }
      } else payload[field.name] = field.type === 'checkbox' ? Boolean(value) : field.type === 'number' ? Number(value) : value
    }
    try { await onSubmit(payload); onCancel() } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }
  function renderField(field) {
    const value = values[field.name]
    if (field.when && values[field.when.field] !== field.when.value) return null
    if (field.type === 'textarea' || field.type === 'json') return <textarea id={field.name} value={value} required={field.required} onChange={(event) => change(field, event.target.value)} />
    if (field.type === 'select') {
      const items = options[field.name] || []
      const visibleItems=field.allowedCodes ? items.filter((item)=>field.allowedCodes.includes(item.code)) : items
      return <select id={field.name} value={value} required={field.required} multiple={field.multiple} onChange={(event) => change(field, field.multiple ? Array.from(event.target.selectedOptions, (option) => option.value) : event.target.value)}>
        <option value="">Choose…</option>
        {(field.options || visibleItems).map((item) => typeof item === 'string' ? <option key={item} value={item}>{item}</option> : <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}
      </select>
    }
    if (field.type === 'checkbox') return <input id={field.name} type="checkbox" checked={Boolean(value)} onChange={(event) => change(field, event.target.checked)} />
    return <input id={field.name} type={field.type || 'text'} value={field.type === 'file' ? undefined : value} required={field.required && !(field.type === 'file' && initial.id)} onChange={(event) => change(field, field.type === 'file' ? event.target.files[0] : event.target.value)} />
  }
  return <dialog ref={dialogRef} aria-labelledby="record-form-title" onCancel={(event) => { event.preventDefault(); onCancel() }}>
    <div className="record-modal-header"><h3 id="record-form-title">{title}</h3><button type="button" className="modal-close" aria-label="Close form" onClick={onCancel} disabled={busy}>×</button></div>
    <form onSubmit={submit}>
      {fields.filter((field) => !field.when || values[field.when.field] === field.when.value).map((field) => <p key={field.name}><label htmlFor={field.name}>{field.label || field.name.replaceAll('_', ' ')}{field.required ? ' *' : ''} {renderField(field)}</label></p>)}
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
      <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
    </form>
  </dialog>
}
