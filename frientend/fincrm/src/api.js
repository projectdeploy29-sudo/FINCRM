const configuredApiRoot = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
export const API_ROOT = configuredApiRoot.endsWith('/api/v1') ? configuredApiRoot : `${configuredApiRoot}/api/v1`

export async function readApiResponse(response) {
  const contentType=response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return response.json()
  const body=await response.text()
  if (body.trimStart().startsWith('<!DOCTYPE') || body.trimStart().startsWith('<html')) {
    throw new Error(`The API returned an HTML page (HTTP ${response.status}). Check that Django is running at ${API_ROOT} and that the API route is correct.`)
  }
  throw new Error(`The API returned an unexpected response (HTTP ${response.status}).`)
}

export function createApi(token, onUnauthorized = () => {}, activeRole = '') {
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {})
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (activeRole) headers.set('X-Active-Role', activeRole)
    if (options.body !== undefined) headers.set('Content-Type', 'application/json')
    const url = (value) => /^https?:\/\//.test(value) ? value : `${API_ROOT}${value}`
    let response = await fetch(url(path), { ...options, headers })
    if (response.status === 401) {
      const refresh = localStorage.getItem('fincrm_refresh')
      if (refresh) {
        const refreshed = await fetch(`${API_ROOT}/auth/token/refresh/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh }) })
        const tokens = await refreshed.json().catch(() => ({}))
        if (refreshed.ok && tokens.access) {
          localStorage.setItem('fincrm_access', tokens.access)
          headers.set('Authorization', `Bearer ${tokens.access}`)
          response = await fetch(url(path), { ...options, headers })
        }
      }
      if (response.status === 401) onUnauthorized()
    }
    const result = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = result.detail || Object.entries(result).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`).join(' · ') || `Request failed (${response.status})`
      throw new Error(`Request failed (${response.status}) for ${options.method || 'GET'} ${url(path)}${detail ? `: ${detail}` : ''}`)
    }
    return result
  }
  return {
    request,
    get: (path) => request(path),
    getAll: async (path) => {
      let result = await request(path); const items = [...(Array.isArray(result) ? result : result.results || [])]
      let next = !Array.isArray(result) ? result.next : null; let pages = 1
      while (next && pages++ < 100) {
        result = await request(next); items.push(...(result.results || [])); next = result.next
      }
      return items
    },
    post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
    patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (path) => request(path, { method: 'DELETE' }),
  }
}

export function unwrapList(result) {
  if (Array.isArray(result)) return result
  return result.results || result.data || []
}
