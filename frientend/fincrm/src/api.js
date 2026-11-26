const configuredApiRoot = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').trim().replace(/\/+$/, '')
export const API_ROOT = configuredApiRoot.endsWith('/api/v1') ? configuredApiRoot : `${configuredApiRoot}/api/v1`
let refreshPromise = null

export function resolveApiUrl(value) {
  const apiRoot = new URL(API_ROOT)
  const url = /^https?:\/\//i.test(value)
    ? new URL(value)
    : new URL(`${API_ROOT}${value.startsWith('/') ? value : `/${value}`}`)
  const apiPath = apiRoot.pathname.replace(/\/+$/, '')
  if (url.origin !== apiRoot.origin || !(url.pathname === apiPath || url.pathname.startsWith(`${apiPath}/`))) {
    throw new Error('The API returned a URL outside the configured API origin.')
  }
  return url.href
}

export async function readApiResponse(response) {
  const contentType=response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return response.json()
  const body=await response.text()
  if (body.trimStart().startsWith('<!DOCTYPE') || body.trimStart().startsWith('<html')) {
    throw new Error(`The API returned an HTML page (HTTP ${response.status}). Check that Django is running at ${API_ROOT} and that the API route is correct.`)
  }
  throw new Error(`The API returned an unexpected response (HTTP ${response.status}).`)
}

export function createApi(token, onUnauthorized = () => {}, activeRole = '', onTokenRefresh = () => {}) {
  async function refreshSession() {
    if (!refreshPromise) {
      const refresh = localStorage.getItem('fincrm_refresh')
      if (!refresh) return null
      refreshPromise = fetch(resolveApiUrl('/auth/token/refresh/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      }).then(async (response) => {
        const tokens = await response.json().catch(() => ({}))
        if (!response.ok || !tokens.access) return null
        localStorage.setItem('fincrm_access', tokens.access)
        if (tokens.refresh) localStorage.setItem('fincrm_refresh', tokens.refresh)
        onTokenRefresh(tokens.access)
        return tokens
      }).catch(() => null).finally(() => {
        refreshPromise = null
      })
    }
    return refreshPromise
  }

  async function request(path, options = {}) {
    const { responseType, ...fetchOptions } = options
    const headers = new Headers(options.headers || {})
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (activeRole) headers.set('X-Active-Role', activeRole)
    if (options.body !== undefined) headers.set('Content-Type', 'application/json')
    const requestUrl = resolveApiUrl(path)
    let response = await fetch(requestUrl, { ...fetchOptions, headers })
    if (response.status === 401) {
      const tokens = await refreshSession()
      if (tokens?.access) {
        headers.set('Authorization', `Bearer ${tokens.access}`)
        response = await fetch(requestUrl, { ...fetchOptions, headers })
      }
      if (response.status === 401) onUnauthorized()
    }
    if (response.ok && responseType === 'blob') return response.blob()
    const result = await response.json().catch(() => ({}))
    if (!response.ok) {
      const fieldErrors = Object.entries(result).filter(([key]) => key !== 'detail').map(([, value]) => Array.isArray(value) ? value.join(', ') : String(value)).filter(Boolean)
      const detail = result.detail || fieldErrors.join(' · ')
      const friendlyFallback = response.status === 403
        ? 'You do not have permission to do that.'
        : response.status === 404
          ? 'We could not find what you requested.'
          : 'Something went wrong. Please try again.'
      throw new Error(detail || friendlyFallback)
    }
    return result
  }
  return {
    request,
    get: (path) => request(path),
    download: (path) => request(path, { responseType: 'blob' }),
    getAll: async (path) => {
      let result = await request(path); const items = [...(Array.isArray(result) ? result : result.results || [])]
      let next = !Array.isArray(result) ? result.next : null; let pages = 1
      while (next && pages++ < 100) {
        result = await request(next); items.push(...(result.results || [])); next = result.next
      }
      return items
    },
    post: (path, body, headers = {}) => request(path, { method: 'POST', body: JSON.stringify(body), headers }),
    patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (path) => request(path, { method: 'DELETE' }),
    logout: async (refresh) => {
      const response = await fetch(resolveApiUrl('/auth/logout/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      })
      if (!response.ok) throw new Error(`Logout failed (${response.status}).`)
    },
  }
}

export function unwrapList(result) {
  if (Array.isArray(result)) return result
  return result.results || result.data || []
}
