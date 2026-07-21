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
  if (!resp.ok) {
    // Carry the status so callers can tell a refusal (409) from a real failure.
    const error = new Error(`${path} -> ${resp.status}`)
    error.status = resp.status
    throw error
  }
  if (resp.status === 204) return null
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

// Partial edit: only the fields passed are changed (clarify sends state +
// context/area/waiting_on; an inline rename sends just the title).
export function updateTodo(id, fields) {
  return request(`/api/todos/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
}

export function completeTodo(id) {
  return request(`/api/todos/${id}/complete`, { method: 'POST' })
}

export function deleteTodo(id) {
  return request(`/api/todos/${id}`, { method: 'DELETE' })
}

// Today's plan (entries carry a per-day status: planned / doing / done).
export const getToday = () => request('/api/today')

export function addToToday(id) {
  return request(`/api/today/${id}`, { method: 'POST' })
}

export function removeFromToday(id) {
  return request(`/api/today/${id}`, { method: 'DELETE' })
}

export function setTodayStatus(id, status) {
  return request(`/api/today/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

// The archive of completed todos, most recently completed first.
export const getDone = () => request('/api/done')

// Undo a completion: the todo leaves the archive and comes back as "next".
export function reopenTodo(id) {
  return request(`/api/todos/${id}/reopen`, { method: 'POST' })
}

// The weekly-review report (inbox, stalled projects, contextless next, stale waiting).
export const getReview = () => request('/api/review')

// Recurring routines: templates that spawn todos on their schedule.
export const getRoutines = () => request('/api/routines')

export function createRoutine(fields) {
  return request('/api/routines', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
}

export function updateRoutine(id, fields) {
  return request(`/api/routines/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
}

export function deleteRoutine(id) {
  return request(`/api/routines/${id}`, { method: 'DELETE' })
}

// Projects (active ones, with action counts) and their serving todos.
export const getProjects = (includeDone = false) =>
  request(`/api/projects${includeDone ? '?include_done=true' : ''}`)

// Complete an outcome. Its actions stay active: only the project closes.
export const completeProject = (id) =>
  request(`/api/projects/${id}/complete`, { method: 'POST' })

export const reopenProject = (id) =>
  request(`/api/projects/${id}/reopen`, { method: 'POST' })

// Refused with 409 while active todos reference the project; detach clears
// their project field first so the actions survive.
export const deleteProject = (id, detach = false) =>
  request(`/api/projects/${id}${detach ? '?detach=true' : ''}`, { method: 'DELETE' })

export const getProjectTodos = (id) => request(`/api/projects/${id}/todos`)

// Capture into the inbox, pre-linked to a project (clarify decides the rest).
export function captureIntoProject(id, title) {
  return request(`/api/projects/${id}/todos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

export function createProject(fields) {
  return request('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
}
