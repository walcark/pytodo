// Thin wrapper over the read/capture API. The JSON contract is the generic
// surface (see packages/server/src/neverland/server/api.py); this SPA is just one
// consumer of it.
//
// When the server is token-protected, the token is kept in localStorage and
// sent as `Authorization: Bearer <token>`. A 401 prompts for it once and
// retries, so the same SPA works with or without a token.

const TOKEN_KEY = 'neverland_token'

// Shared across concurrent requests so a burst of 401s (sidebar + list load
// together) yields a single prompt, not one per request.
let pendingPrompt = null

function authHeaders(extra) {
  const token = localStorage.getItem(TOKEN_KEY)
  const headers = { ...extra }
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

// Ask for a token, unless a sibling request already refreshed it. `failed` is
// the token that just got rejected (or null when none was set).
function promptForToken(failed) {
  const current = localStorage.getItem(TOKEN_KEY)
  if (current && current !== failed) return Promise.resolve(current)
  if (!pendingPrompt) {
    pendingPrompt = Promise.resolve().then(() => {
      const token = window.prompt('Access token:')
      if (token) localStorage.setItem(TOKEN_KEY, token)
      pendingPrompt = null
      return token
    })
  }
  return pendingPrompt
}

async function request(path, options = {}) {
  const send = () => fetch(path, { ...options, headers: authHeaders(options.headers) })

  let resp = await send()
  if (resp.status === 401) {
    const token = await promptForToken(localStorage.getItem(TOKEN_KEY))
    if (!token) throw new Error('authentication required')
    resp = await send()
  }
  if (!resp.ok) throw new Error(`${path} -> ${resp.status}`)
  return resp.json()
}

export const getViews = () => request('/api/views')
export const getVocabulary = () => request('/api/vocabulary')

export function getTodos(view, { area, context } = {}) {
  const params = new URLSearchParams({ view })
  if (area) params.set('area', area)
  if (context) params.set('context', context)
  return request(`/api/todos?${params.toString()}`)
}

export function capture(title) {
  return request('/api/capture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}
