// Thin wrapper over the read/capture API. The JSON contract is the generic
// surface (see packages/server/src/pytodo/server/api.py); this SPA is just one
// consumer of it.

async function getJSON(path) {
  const resp = await fetch(path)
  if (!resp.ok) throw new Error(`${path} -> ${resp.status}`)
  return resp.json()
}

export const getViews = () => getJSON('/api/views')
export const getVocabulary = () => getJSON('/api/vocabulary')

export function getTodos(view, { area, context } = {}) {
  const params = new URLSearchParams({ view })
  if (area) params.set('area', area)
  if (context) params.set('context', context)
  return getJSON(`/api/todos?${params.toString()}`)
}

export async function capture(title) {
  const resp = await fetch('/api/capture', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!resp.ok) throw new Error(`capture -> ${resp.status}`)
  return resp.json()
}
