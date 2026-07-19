import { useCallback, useEffect, useState } from 'react'

import { createProject, getProjects, getProjectTodos } from './api.js'

// One project row: its counts, a stalled badge, and a lazy-loaded list of the
// todos that serve it (expanded on click).
function ProjectRow({ project }) {
  const [open, setOpen] = useState(false)
  const [todos, setTodos] = useState(null)

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && todos === null) {
      setTodos(await getProjectTodos(project.id))
    }
  }

  return (
    <li className="project">
      <button type="button" className="project-head" onClick={toggle}>
        <span className="project-caret">{open ? '▾' : '▸'}</span>
        <span className="project-title">{project.title}</span>
        {project.area && <span className="tag area">{project.area}</span>}
        {project.stalled ? (
          <span className="badge stalled">stalled</span>
        ) : (
          <span className="badge">{project.next_count} next</span>
        )}
        <span className="project-count">{project.action_count} action(s)</span>
      </button>
      {project.outcome && <p className="project-outcome">{project.outcome}</p>}
      {open && (
        <ul className="project-todos">
          {todos === null ? (
            <li className="muted">Loading…</li>
          ) : todos.length === 0 ? (
            <li className="muted">No actions yet. Add one and assign it here.</li>
          ) : (
            todos.map((t) => (
              <li key={t.id}>
                <span className={`pill state-${t.state}`}>{t.state}</span>
                <span className="todo-title">{t.title}</span>
                {t.context && <span className="tag context">{t.context}</span>}
              </li>
            ))
          )}
        </ul>
      )}
    </li>
  )
}

function CreateProject({ vocab, onCreated }) {
  const [title, setTitle] = useState('')
  const [outcome, setOutcome] = useState('')
  const [area, setArea] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const text = title.trim()
    if (!text || busy) return
    setBusy(true)
    try {
      await createProject({
        title: text,
        outcome: outcome.trim() || null,
        area: area || null,
      })
      setTitle('')
      setOutcome('')
      setArea('')
      onCreated()
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="project-create" onSubmit={submit}>
      <input
        type="text"
        placeholder="New project (the outcome you want)…"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        aria-label="Project title"
      />
      <input
        type="text"
        placeholder="Outcome (optional)"
        value={outcome}
        onChange={(e) => setOutcome(e.target.value)}
        aria-label="Project outcome"
      />
      <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="Area">
        <option value="">(no area)</option>
        {vocab.areas.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
      <button type="submit" disabled={busy || !title.trim()}>
        Create
      </button>
    </form>
  )
}

// The projects view: create outcomes and see, for each, whether it is moving
// (has a next action) and the todos that serve it.
export default function Projects({ vocab, onChanged }) {
  const [projects, setProjects] = useState([])
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setProjects(await getProjects())
  }, [])

  useEffect(() => {
    load().catch((e) => setError(String(e)))
  }, [load])

  const onCreated = () => {
    load().catch((e) => setError(String(e)))
    onChanged()
  }

  return (
    <div className="projects">
      <CreateProject vocab={vocab} onCreated={onCreated} />
      {error && <p className="error">{error}</p>}
      {projects.length === 0 ? (
        <p className="empty">No active projects yet.</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <ProjectRow key={p.id} project={p} />
          ))}
        </ul>
      )}
    </div>
  )
}
