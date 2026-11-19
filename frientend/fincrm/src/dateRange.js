function localDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function getPresetDateRange(preset, now = new Date()) {
  const end = localDateString(now)
  if (preset === 'today') return { preset, start_date: end, end_date: end }
  if (preset === 'month') return { preset, start_date: `${end.slice(0, 7)}-01`, end_date: end }
  if (preset === 'year') return { preset, start_date: `${end.slice(0, 4)}-01-01`, end_date: end }
  return { preset: 'custom', start_date: '', end_date: '' }
}

export function withDateRange(path, range) {
  if (!range?.start_date && !range?.end_date) return path
  const [base, query = ''] = path.split('?')
  const params = new URLSearchParams(query)
  if (range.start_date) params.set('start_date', range.start_date)
  if (range.end_date) params.set('end_date', range.end_date)
  return `${base}?${params.toString()}`
}
