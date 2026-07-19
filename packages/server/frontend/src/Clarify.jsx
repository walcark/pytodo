import { useState } from 'react'

import { completeTodo, deleteTodo, updateTodo } from './api.js'

// The GTD clarify loop for the web, one inbox item at a time. It mirrors
// `todo clarify`: decide a disposition, and for the actionable ones its
// context and area. Completion and deletion take their dedicated endpoints;
// next/waiting/someday are a partial edit (PATCH).
const DISPOSITIONS = [
  { value: 'next', label: 'Next' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'someday', label: 'Someday' },
  { value: 'done', label: 'Done' },
  { value: 'delete', label: 'Delete' },
]

// The form for the current item. Keyed by todo id in the parent, so it
// remounts (fresh defaults) whenever we advance to the next item.
function ClarifyItem({ todo, vocab, projects, busy, onApply }) {
  const [disposition, setDisposition] = useState('next')
  const [title, setTitle] = useState(todo.title)
  const [context, setContext] = useState('')
  const [area, setArea] = useState('')
  const [project, setProject] = useState(todo.project || '')
  const [waitingOn, setWaitingOn] = useState('')

  function apply() {
    if (disposition === 'delete') return onApply({ kind: 'delete' })
    if (disposition === 'done') return onApply({ kind: 'done' })

    // next / waiting / someday: a partial edit. Fields irrelevant to the
    // chosen state are cleared (null), so a re-clarify starts from a clean slate.
    const fields = {
      title: title.trim() || todo.title,
      state: disposition,
      area: area || null,
      project: project || null,
      context: disposition === 'next' ? context || null : null,
      waiting_on: disposition === 'waiting' ? waitingOn.trim() || null : null,
    }
    return onApply({ kind: 'patch', fields })
  }

  return (
    <div className="clarify-card">
      <input
        className="clarify-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        aria-label="Title"
      />

      <div className="clarify-dispositions">
        {DISPOSITIONS.map((d) => (
          <button
            key={d.value}
            type="button"
            className={`seg${disposition === d.value ? ' active' : ''}`}
            onClick={() => setDisposition(d.value)}
          >
            {d.label}
          </button>
        ))}
      </div>

      {(disposition === 'next' ||
        disposition === 'waiting' ||
        disposition === 'someday') && (
        <div className="clarify-fields">
          {disposition === 'next' && (
            <label>
              Context
              <select value={context} onChange={(e) => setContext(e.target.value)}>
                <option value="">(none)</option>
                {vocab.contexts.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}

          {disposition === 'waiting' && (
            <label>
              Waiting on
              <input
                value={waitingOn}
                onChange={(e) => setWaitingOn(e.target.value)}
                placeholder="who or what"
              />
            </label>
          )}

          <label>
            Area
            <select value={area} onChange={(e) => setArea(e.target.value)}>
              <option value="">(none)</option>
              {vocab.areas.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>

          <label>
            Project
            <select value={project} onChange={(e) => setProject(e.target.value)}>
              <option value="">(none)</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <div className="clarify-actions">
        <button
          type="button"
          className="primary"
          onClick={apply}
          disabled={busy}
        >
          Apply &amp; next
        </button>
      </div>
    </div>
  )
}

export default function Clarify({ items, vocab, projects, onExit }) {
  // Snapshot the inbox: the list must not shift under us as we mutate items.
  const [queue] = useState(items)
  const [index, setIndex] = useState(0)
  const [busy, setBusy] = useState(false)

  const todo = queue[index]
  if (!todo) {
    onExit()
    return null
  }

  const step = () => {
    if (index + 1 >= queue.length) onExit()
    else setIndex((i) => i + 1)
  }

  async function apply(decision) {
    if (busy) return
    setBusy(true)
    try {
      if (decision.kind === 'done') await completeTodo(todo.id)
      else if (decision.kind === 'delete') await deleteTodo(todo.id)
      else await updateTodo(todo.id, decision.fields)
      step()
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="clarify">
      <header className="clarify-head">
        <span className="clarify-progress">
          {index + 1} / {queue.length}
        </span>
        <div className="clarify-head-actions">
          <button type="button" onClick={step} disabled={busy}>
            Skip
          </button>
          <button type="button" onClick={onExit} disabled={busy}>
            Stop
          </button>
        </div>
      </header>
      <ClarifyItem
        key={todo.id}
        todo={todo}
        vocab={vocab}
        projects={projects}
        busy={busy}
        onApply={apply}
      />
    </section>
  )
}
