import { useState } from 'react'

// Inline editor for any field of a todo: fix a typo in the title, move it to
// another state, correct its context or area. Completion is not offered here
// (that is the row's ✓ action), so the states are the four active ones.
const STATES = ['inbox', 'next', 'waiting', 'someday']

export default function TodoEditor({ todo, vocab, projects, busy, onSave, onCancel }) {
  const [title, setTitle] = useState(todo.title)
  const [state, setState] = useState(todo.state)
  const [context, setContext] = useState(todo.context || '')
  const [area, setArea] = useState(todo.area || '')
  const [project, setProject] = useState(todo.project || '')
  const [waitingOn, setWaitingOn] = useState(todo.waiting_on || '')

  function save() {
    onSave({
      title: title.trim() || todo.title,
      state,
      context: context || null,
      area: area || null,
      project: project || null,
      waiting_on: state === 'waiting' ? waitingOn.trim() || null : null,
    })
  }

  return (
    <div className="todo-editor">
      <input
        className="edit-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        aria-label="Title"
      />
      <div className="edit-fields">
        <label>
          State
          <select value={state} onChange={(e) => setState(e.target.value)}>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
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
        {state === 'waiting' && (
          <label>
            Waiting on
            <input
              value={waitingOn}
              onChange={(e) => setWaitingOn(e.target.value)}
              placeholder="who or what"
            />
          </label>
        )}
      </div>
      <div className="edit-actions">
        <button type="button" className="primary" onClick={save} disabled={busy}>
          Save
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  )
}
