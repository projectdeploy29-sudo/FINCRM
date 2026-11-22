import { useEffect, useRef, useState } from 'react'
import { unwrapList } from '../api'

function optionLabel(item, field) {
  if (field.optionLabelField && item[field.optionLabelField]) {
    const primary = item[field.optionLabelField]
    const secondary = field.optionLabelSecondaryField && item[field.optionLabelSecondaryField]
    return secondary ? `${primary} · ${secondary}` : primary
  }
  return item.label || item.name || item.full_name || item.user_details?.full_name || item.user_details?.username || item.assigned_to_name || item.assigned_employee_name || item.customer_code || item.application_code || item.employee_code || item.code || item.username || item.id
}

function datetimeLocalValue(value, timeZone) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  try {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(date).map(({ type, value: part }) => [type, part]))
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
  } catch {
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  }
}

function initialValue(field, initial, timeZone) {
  let value = initial[field.name]
  if (field.name === 'role_ids' && initial.roles) value = initial.roles.map((role) => role.id)
  else if (field.multiple && initial.permissions) value = initial.permissions.map((permission) => permission.permission__id)
  if (field.type === 'json' && value && typeof value === 'object') return JSON.stringify(value, null, 2)
  if (field.type === 'datetime-local' && value) return datetimeLocalValue(value, timeZone)
  return value ?? field.defaultValue ?? (field.type === 'checkbox' ? false : field.multiple ? [] : '')
}

export default function RecordForm({ fields, initial = {}, api, timezone = 'UTC', submitLabel = 'Save', onSubmit, onCancel, title = 'Record' }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [field.name, initialValue(field, initial, timezone)])))
  const [options, setOptions] = useState({})
  const [optionsErrors, setOptionsErrors] = useState({})
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
      try { const result = api.getAll ? await api.getAll(field.optionsEndpoint) : unwrapList(await api.get(field.optionsEndpoint)); return [field.name, result, ''] } catch (exception) { return [field.name, [], exception.message] }
    })).then((entries) => {
      if (!live || !entries.length) return
      setOptions(Object.fromEntries(entries.map(([name, result]) => [name, result])))
      setOptionsErrors(Object.fromEntries(entries.filter(([, , message]) => message).map(([name, , message]) => [name, message])))
    })
    return () => { live = false }
  }, [fields, api])

  function optionsFor(field, currentValues = values) {
    let items = options[field.name] || []
    if (field.allowedCodes) items = items.filter((item) => field.allowedCodes.includes(item.code))
    if (field.dependsOn) {
      const parentValue = currentValues[field.dependsOn.field]
      items = parentValue ? items.filter((item) => String(item[field.dependsOn.optionField]) === String(parentValue)) : []
    }
    return items
  }
  function change(field, value) {
    setValues((current) => {
      const updated = { ...current, [field.name]: value }
      if (field.populate && !field.multiple) {
        const selected = (options[field.name] || []).find((item) => String(item.id) === String(value))
        if (selected) {
          for (const [target, source] of Object.entries(field.populate)) {
            if (fields.some((candidate) => candidate.name === target)) {
              updated[target] = selected[source] == null ? '' : String(selected[source])
            }
          }
        }
      }
      for (const child of fields.filter((candidate) => candidate.dependsOn?.field === field.name)) {
        const validIds = new Set(optionsFor(child, updated).map((item) => String(item.id)))
        const selected = updated[child.name]
        if (child.multiple) updated[child.name] = (selected || []).filter((id) => validIds.has(String(id)))
        else if (selected && !validIds.has(String(selected))) updated[child.name] = ''
      }
      return updated
    })
  }
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    const payload = {}
    for (const field of fields) {
      const value = values[field.name]
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
      const visibleItems=optionsFor(field)
      return <>
        <select id={field.name} value={value} required={field.required} multiple={field.multiple} onChange={(event) => change(field, field.multiple ? Array.from(event.target.selectedOptions, (option) => option.value) : event.target.value)}>
          {!field.multiple && <option value="">Choose…</option>}
          {(field.options || visibleItems).map((item) => typeof item === 'string' ? <option key={item} value={item}>{item}</option> : <option key={item.id} value={item.id}>{optionLabel(item, field)}</option>)}
        </select>
        {optionsErrors[field.name] && <span role="alert">Could not load options: {optionsErrors[field.name]}</span>}
        {!field.optionsEndpoint && !field.options?.length && !optionsErrors[field.name] && <span role="alert">No options are configured for this field.</span>}
        {field.optionsEndpoint && !optionsErrors[field.name] && options[field.name]?.length === 0 && <span>No matching options are available.</span>}
      </>
    }
    if (field.type === 'checkbox') return <input id={field.name} type="checkbox" checked={Boolean(value)} onChange={(event) => change(field, event.target.checked)} />
    return <input id={field.name} type={field.type || 'text'} value={value} required={field.required} onChange={(event) => change(field, event.target.value)} />
  }
  return <dialog ref={dialogRef} aria-labelledby="record-form-title" onCancel={(event) => { event.preventDefault(); onCancel() }}>
    <div className="record-modal-header"><h3 id="record-form-title">{title}</h3><button type="button" className="modal-close" aria-label="Close form" onClick={onCancel} disabled={busy}>×</button></div>
    <form onSubmit={submit}>
      {fields.filter((field) => !field.when || values[field.when.field] === field.when.value).map((field) => <p key={field.name}><label htmlFor={field.name}>{field.label || field.name.replaceAll('_', ' ')}{field.type === 'datetime-local' ? ` (${timezone})` : ''}{field.required ? ' *' : ''} {renderField(field)}</label>{field.helpText && <small className="field-help">{field.helpText}</small>}</p>)}
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
      <button type="button" onClick={onCancel} disabled={busy}>Cancel</button>
    </form>
  </dialog>
}
